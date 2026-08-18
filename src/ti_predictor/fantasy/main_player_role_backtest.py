"""Research-only rolling evaluation for the Main Player-role generator.

This module never participates in Web or release loading.  It reconstructs an
event-time split from the frozen local snapshot, compares the Player-role
generator with the existing absolute historical Game-template sampler, and
reports proper scores on later complete Series.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.fantasy.main_player_role_generator import (
    ROLE_IDS,
    PlayerRoleEvidence,
    PlayerRoleGeneratorModel,
    _canonical_team_side,
    _series_contexts,
)
from ti_predictor.fantasy.scoring import Emblem, emblem_multipliers
from ti_predictor.forecasting import _available_by_as_of
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.identity import canonicalize_match_team_ids
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import as_utc
from ti_predictor.storage import read_parquet_if_exists

ROLE_PLAYER_OFFSETS: Mapping[str, tuple[int, ...]] = {
    "core": (0, 1),
    "mid": (2,),
    "support": (3, 4),
}


class MainPlayerRoleBacktestError(ValueError):
    """A frozen fold, prediction panel, or proper-score input is invalid."""


@dataclass(frozen=True)
class EvaluationSeries:
    league_id: int
    series_id: int
    current_team_id: int
    historical_team_id: int
    opponent_team_id: int
    best_of: int
    series_won: bool
    opponent_probability: float
    match_ids: tuple[int, ...]
    won_games: tuple[bool, ...]
    durations: np.ndarray
    raw_stats: np.ndarray

    def __post_init__(self) -> None:
        duration = np.ascontiguousarray(self.durations, dtype=float).reshape(-1)
        raw = np.ascontiguousarray(self.raw_stats, dtype=np.float32)
        game_count = len(self.match_ids)
        if (
            game_count < 2
            or len(self.won_games) != game_count
            or duration.shape != (game_count,)
            or raw.ndim != 3
            or raw.shape[:2] != (game_count, 5)
        ):
            raise MainPlayerRoleBacktestError("evaluation Series arrays do not align")
        if self.best_of not in {2, 3, 5} or game_count > self.best_of:
            raise MainPlayerRoleBacktestError("evaluation Series format is invalid")
        if np.any(duration <= 0.0) or np.any(raw < 0.0) or not np.isfinite(raw).all():
            raise MainPlayerRoleBacktestError("evaluation Series contains an illegal outcome")
        object.__setattr__(self, "durations", duration)
        object.__setattr__(self, "raw_stats", raw)


@dataclass(frozen=True)
class PlayerRoleHoldout:
    fold_id: str
    league_id: int
    train_cutoff: datetime
    test_end: datetime
    available_as_of: datetime
    team_ids: tuple[int, ...]
    stat_ids: tuple[str, ...]
    series: tuple[EvaluationSeries, ...]
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        train = as_utc(self.train_cutoff)
        end = as_utc(self.test_end)
        available = as_utc(self.available_as_of)
        if train is None or end is None or available is None or not train < end <= available:
            raise MainPlayerRoleBacktestError("holdout timestamps are not ordered explicit UTC")
        if not self.series:
            raise MainPlayerRoleBacktestError("holdout contains no complete current-roster Series")
        if any(item.league_id != self.league_id for item in self.series):
            raise MainPlayerRoleBacktestError("holdout contains a Series from another League")
        object.__setattr__(self, "train_cutoff", train)
        object.__setattr__(self, "test_end", end)
        object.__setattr__(self, "available_as_of", available)


@dataclass(frozen=True)
class BannerProjection:
    projection_id: str
    role: str
    stat_ids: tuple[str, ...]
    multipliers: np.ndarray

    def __post_init__(self) -> None:
        multipliers = np.ascontiguousarray(self.multipliers, dtype=float).reshape(-1)
        if self.role not in ROLE_IDS or len(self.stat_ids) != 5 or multipliers.shape != (5,):
            raise MainPlayerRoleBacktestError("Banner projection is not a legal five-slot role")
        if np.any(multipliers < 0.0) or not np.isfinite(multipliers).all():
            raise MainPlayerRoleBacktestError("Banner projection multipliers are invalid")
        object.__setattr__(self, "multipliers", multipliers)


@dataclass(frozen=True)
class HistoricalSeriesTemplate:
    team_id: int
    series_id: int
    best_of: int
    series_won: bool
    opponent_band: int
    evidence_weight: float
    won_games: tuple[bool, ...]
    raw_stats: np.ndarray

    def __post_init__(self) -> None:
        raw = np.ascontiguousarray(self.raw_stats, dtype=np.float32)
        if raw.ndim != 3 or raw.shape[1] != 5 or len(self.won_games) != raw.shape[0]:
            raise MainPlayerRoleBacktestError("historical Series template arrays do not align")
        if self.evidence_weight <= 0.0 or np.any(raw < 0.0) or not np.isfinite(raw).all():
            raise MainPlayerRoleBacktestError("historical Series template is invalid")
        object.__setattr__(self, "raw_stats", raw)


@dataclass(frozen=True)
class BacktestResult:
    fold_id: str
    metrics: Mapping[str, Any]
    series_records: tuple[Mapping[str, Any], ...]
    joint_records: tuple[Mapping[str, Any], ...]
    semantic_hash: str


def empirical_crps(samples: Sequence[float] | np.ndarray, observed: float) -> float:
    """Exact CRPS for an equally weighted finite predictive sample."""

    values = np.asarray(samples, dtype=float).reshape(-1)
    if not len(values) or not np.isfinite(values).all() or not np.isfinite(observed):
        raise MainPlayerRoleBacktestError("CRPS requires finite predictive samples and outcome")
    first = float(np.mean(np.abs(values - float(observed))))
    ordered = np.sort(values, kind="stable")
    indexes = np.arange(1, len(ordered) + 1, dtype=float)
    pair_mean = float(
        2.0
        * np.sum((2.0 * indexes - len(ordered) - 1.0) * ordered)
        / (len(ordered) ** 2)
    )
    return first - 0.5 * pair_mean


def energy_score(samples: np.ndarray, observed: np.ndarray) -> float:
    predictive = np.asarray(samples, dtype=float)
    truth = np.asarray(observed, dtype=float).reshape(-1)
    if predictive.ndim != 2 or predictive.shape[1] != len(truth) or not len(predictive):
        raise MainPlayerRoleBacktestError("Energy score vectors do not align")
    if not np.isfinite(predictive).all() or not np.isfinite(truth).all():
        raise MainPlayerRoleBacktestError("Energy score requires finite input")
    first = float(np.linalg.norm(predictive - truth[None, :], axis=1).mean())
    pairwise = predictive[:, None, :] - predictive[None, :, :]
    second = float(np.linalg.norm(pairwise, axis=2).mean())
    return first - 0.5 * second


def _opponent_band(probability: float) -> int:
    if probability < 0.4:
        return 0
    if probability > 0.6:
        return 2
    return 1


def build_hash_fixed_banner_panel(
    rules: Mapping[str, Any],
    *,
    projections_per_role: int = 4,
    salt: str = "ti2026-player-role-backtest-panel-v1",
) -> tuple[BannerProjection, ...]:
    """Generate a deterministic legal panel before looking at model results."""

    if projections_per_role < 1:
        raise MainPlayerRoleBacktestError("Banner panel must contain a projection per role")
    fantasy = rules["fantasy"]
    stats_by_color: dict[str, list[str]] = {}
    for stat_id, rule in fantasy["stats"].items():
        stats_by_color.setdefault(str(rule["color"]), []).append(str(stat_id))
    for values in stats_by_color.values():
        values.sort()
    trait_ids = tuple(str(item["id"]) for item in fantasy["traits"])
    quality_tiers = tuple(int(item["tier"]) for item in fantasy["qualities"])
    panel: list[BannerProjection] = []
    for role in ROLE_IDS:
        colors = tuple(str(value) for value in fantasy["role_banners"][role])
        for projection_index in range(projections_per_role):
            emblems: list[Emblem] = []
            selected_stats: list[str] = []
            for slot_index, color in enumerate(colors):
                digest = hashlib.sha256(
                    f"{salt}:{role}:{projection_index}:{slot_index}".encode()
                ).digest()
                candidates = stats_by_color[color]
                stat_id = candidates[int.from_bytes(digest[:4], "big") % len(candidates)]
                quality = quality_tiers[digest[4] % len(quality_tiers)]
                trait = trait_ids[digest[5] % len(trait_ids)]
                selected_stats.append(stat_id)
                emblems.append(Emblem(stat_id, color, quality, trait))
            multipliers = np.asarray(emblem_multipliers(emblems, dict(rules)), dtype=float)
            panel.append(
                BannerProjection(
                    projection_id=f"{role}-{projection_index:02d}",
                    role=role,
                    stat_ids=tuple(selected_stats),
                    multipliers=multipliers,
                )
            )
    return tuple(panel)


def _stat_value(raw: np.ndarray, rule: Mapping[str, Any]) -> np.ndarray:
    numeric = np.asarray(raw, dtype=float)
    if rule["mode"] == "linear":
        result = numeric * float(rule["factor"])
    elif rule["mode"] == "inverse":
        result = float(rule["base"]) - numeric * float(rule["factor"])
        result = np.maximum(float(rule.get("floor", -np.inf)), result)
    else:
        raise MainPlayerRoleBacktestError(f"unknown Fantasy score mode {rule['mode']!r}")
    if "cap" in rule:
        result = np.minimum(float(rule["cap"]), result)
    return result


def score_raw_games(
    raw_stats: np.ndarray,
    *,
    stat_ids: tuple[str, ...],
    projection: BannerProjection,
    rules: Mapping[str, Any],
) -> np.ndarray:
    """Score raw 5-player Games; leading dimensions are preserved."""

    raw = np.asarray(raw_stats, dtype=float)
    if raw.ndim < 3 or raw.shape[-2:] != (5, len(stat_ids)):
        raise MainPlayerRoleBacktestError("raw Game matrix does not match five players and Stats")
    index = {stat_id: offset for offset, stat_id in enumerate(stat_ids)}
    player_values = np.zeros(raw.shape[:-1], dtype=float)
    for stat_id, multiplier in zip(
        projection.stat_ids, projection.multipliers, strict=True
    ):
        player_values += _stat_value(
            raw[..., index[stat_id]], rules["fantasy"]["stats"][stat_id]
        ) * float(multiplier)
    offsets = ROLE_PLAYER_OFFSETS[projection.role]
    return player_values[..., list(offsets)].mean(axis=-1)


def _top_two(values: np.ndarray) -> np.ndarray:
    numeric = np.asarray(values, dtype=float)
    if numeric.shape[-1] < 2:
        raise MainPlayerRoleBacktestError("Series Top-2 scoring requires at least two Games")
    return np.partition(numeric, -2, axis=-1)[..., -2:].sum(axis=-1)


def build_player_role_holdout(
    *,
    fold_id: str,
    league_id: int,
    train_cutoff: datetime,
    test_end: datetime,
    available_as_of: datetime,
    strength_model: Any,
    paths: ProjectPaths = PATHS,
) -> PlayerRoleHoldout:
    """Materialize complete current-roster Series strictly after a training cutoff."""

    train = as_utc(train_cutoff)
    end = as_utc(test_end)
    available = as_utc(available_as_of)
    if train is None or end is None or available is None or not train < end <= available:
        raise MainPlayerRoleBacktestError("holdout cutoffs must be ordered explicit UTC")
    evidence_paths = main_evidence_paths(paths, require=True)
    manifest = load_tournament_manifest(evidence_paths.tournament)
    rules = load_rules(evidence_paths.rules)
    team_ids = tuple(int(value) for value in manifest.main_event_seeds)
    matches_path = evidence_paths.processed / "matches.parquet"
    observations_path = evidence_paths.processed / "fantasy_performance_samples.parquet"
    matches = _available_by_as_of(read_parquet_if_exists(matches_path), available)
    observations = _available_by_as_of(
        read_parquet_if_exists(observations_path), available
    )
    matches, identity_audit = canonicalize_match_team_ids(
        matches,
        manifest.team_identity_bridges,
        as_of=available,
        registration_identities={
            team.team_id: team.registration_identity
            for team in manifest.teams
            if team.registration_identity is not None
        },
    )
    matches["start_time"] = pd.to_datetime(matches["start_time"], utc=True, errors="coerce")
    selected_matches = matches.loc[
        pd.to_numeric(matches["league_id"], errors="coerce").eq(int(league_id))
        & matches["start_time"].ge(pd.Timestamp(train))
        & matches["start_time"].le(pd.Timestamp(end))
    ].copy()
    selected_matches["match_id"] = pd.to_numeric(
        selected_matches["match_id"], errors="coerce"
    )
    selected_matches = selected_matches.dropna(subset=["match_id"]).astype({"match_id": int})
    context_by_game, series_rejection = _series_contexts(selected_matches)
    match_by_id = {
        int(row["match_id"]): row for row in selected_matches.to_dict(orient="records")
    }
    observations["match_id"] = pd.to_numeric(observations["match_id"], errors="coerce")
    observations["account_id"] = pd.to_numeric(observations["account_id"], errors="coerce")
    observations = observations.dropna(subset=["match_id", "account_id"]).astype(
        {"match_id": int, "account_id": int}
    )
    observations = observations.loc[observations["match_id"].isin(match_by_id)]
    observation_by_match = {
        int(match_id): group.set_index("account_id", drop=False)
        for match_id, group in observations.groupby("match_id", sort=False)
    }
    stat_ids = tuple(str(value) for value in rules["fantasy"]["stats"])
    provenance = {
        stat_id: str(rules["fantasy"]["stats"][stat_id]["provenance"])
        for stat_id in stat_ids
    }
    team_by_id = {int(team.team_id): team for team in manifest.teams}
    game_blocks: dict[tuple[int, int], dict[str, Any]] = {}
    rejection: Counter[str] = Counter(series_rejection)
    for current_team_id in team_ids:
        team = team_by_id[current_team_id]
        players = tuple(
            int(player.account_id)
            for role in ROLE_IDS
            for player in team.players[role]
        )
        for match_id, match in match_by_id.items():
            indexed = observation_by_match.get(match_id)
            if indexed is None or any(account_id not in indexed.index for account_id in players):
                continue
            selected = indexed.loc[list(players)]
            if isinstance(selected, pd.Series):
                selected = selected.to_frame().T
            historical_ids: list[int] = []
            opponent_ids: list[int] = []
            valid = True
            for row in selected.to_dict(orient="records"):
                source_team = row.get("team_id")
                if source_team is None or pd.isna(source_team):
                    valid = False
                    break
                side = _canonical_team_side(int(source_team), match)
                if side is None:
                    valid = False
                    break
                historical_ids.append(side[0])
                opponent_ids.append(side[1])
            if not valid or len(set(historical_ids)) != 1 or len(set(opponent_ids)) != 1:
                rejection["cross_team_current_roster_game"] += 1
                continue
            historical_team_id = historical_ids[0]
            context = context_by_game.get((match_id, historical_team_id))
            if context is None:
                rejection["missing_series_context"] += 1
                continue
            raw = np.empty((5, len(stat_ids)), dtype=np.float32)
            for player_index, (_, row) in enumerate(selected.iterrows()):
                for stat_index, stat_id in enumerate(stat_ids):
                    value = row.get(stat_id)
                    if (
                        value is None
                        or pd.isna(value)
                        or row.get(f"{stat_id}_provenance") != provenance[stat_id]
                        or float(value) < 0.0
                    ):
                        valid = False
                        break
                    raw[player_index, stat_index] = float(value)
                if not valid:
                    break
            if not valid:
                rejection["missing_or_illegal_stat"] += 1
                continue
            duration = match.get("duration")
            if duration is None or pd.isna(duration) or float(duration) <= 0.0:
                rejection["missing_duration"] += 1
                continue
            game_blocks[(current_team_id, match_id)] = {
                "series_id": int(match["series_id"]),
                "historical_team_id": historical_team_id,
                "opponent_team_id": opponent_ids[0],
                "context": context,
                "duration": float(duration),
                "raw": raw,
            }

    series_items: list[EvaluationSeries] = []
    blocks = list(game_blocks.items())
    for (current_team_id, series_id), grouped in pd.DataFrame(
        [
            {
                "current_team_id": key[0],
                "match_id": key[1],
                "series_id": value["series_id"],
            }
            for key, value in blocks
        ]
    ).groupby(["current_team_id", "series_id"], sort=True):
        match_ids = tuple(
            sorted(
                grouped["match_id"].astype(int),
                key=lambda value: int(game_blocks[(int(current_team_id), value)]["context"]["game_index"]),
            )
        )
        selected_blocks = [game_blocks[(int(current_team_id), match_id)] for match_id in match_ids]
        contexts = [item["context"] for item in selected_blocks]
        expected_length = int(contexts[0]["series_length"])
        if len(match_ids) != expected_length or [item["game_index"] for item in contexts] != list(
            range(expected_length)
        ):
            rejection["incomplete_current_roster_series"] += 1
            continue
        historical_ids = {int(item["historical_team_id"]) for item in selected_blocks}
        opponent_ids = {int(item["opponent_team_id"]) for item in selected_blocks}
        if len(historical_ids) != 1 or len(opponent_ids) != 1:
            rejection["team_or_opponent_change"] += 1
            continue
        historical_team_id = next(iter(historical_ids))
        opponent_team_id = next(iter(opponent_ids))
        series_items.append(
            EvaluationSeries(
                league_id=int(league_id),
                series_id=int(series_id),
                current_team_id=int(current_team_id),
                historical_team_id=historical_team_id,
                opponent_team_id=opponent_team_id,
                best_of=int(contexts[0]["best_of"]),
                series_won=bool(contexts[0]["series_won"]),
                opponent_probability=float(
                    strength_model.predict(historical_team_id, opponent_team_id)
                ),
                match_ids=match_ids,
                won_games=tuple(bool(item["won_game"]) for item in contexts),
                durations=np.asarray([item["duration"] for item in selected_blocks]),
                raw_stats=np.asarray([item["raw"] for item in selected_blocks]),
            )
        )
    series_items.sort(key=lambda item: (item.series_id, item.current_team_id))
    if not series_items:
        raise MainPlayerRoleBacktestError(
            f"fold {fold_id} has no complete current-roster Series"
        )
    audit = {
        "schema_version": 1,
        "fold_id": fold_id,
        "league_id": int(league_id),
        "train_cutoff": train.isoformat().replace("+00:00", "Z"),
        "test_end": end.isoformat().replace("+00:00", "Z"),
        "available_as_of": available.isoformat().replace("+00:00", "Z"),
        "reconstructed_time_split": available > train,
        "catalog_games": len(selected_matches),
        "complete_team_games": len(game_blocks),
        "complete_series": len(series_items),
        "teams_with_complete_series": sorted(
            {item.current_team_id for item in series_items}
        ),
        "rejection_counts": dict(sorted(rejection.items())),
        "identity_audit": identity_audit,
        "source_sha256": {
            "matches": sha256_file(matches_path),
            "observations": sha256_file(observations_path),
        },
    }
    audit["semantic_hash"] = sha256_json(
        {
            "fold_id": fold_id,
            "league_id": league_id,
            "train_cutoff": audit["train_cutoff"],
            "test_end": audit["test_end"],
            "series": [
                {
                    "series_id": item.series_id,
                    "team_id": item.current_team_id,
                    "match_ids": item.match_ids,
                }
                for item in series_items
            ],
            "source_sha256": audit["source_sha256"],
        }
    )
    return PlayerRoleHoldout(
        fold_id=fold_id,
        league_id=int(league_id),
        train_cutoff=train,
        test_end=end,
        available_as_of=available,
        team_ids=team_ids,
        stat_ids=stat_ids,
        series=tuple(series_items),
        audit=audit,
    )


def build_historical_series_templates(
    evidence: PlayerRoleEvidence,
) -> tuple[HistoricalSeriesTemplate, ...]:
    """Recover the old v1 absolute-Game template pool from the same training evidence."""

    frame = evidence.frame
    templates: list[HistoricalSeriesTemplate] = []
    team_index = {team_id: index for index, team_id in enumerate(evidence.team_ids)}
    complete_games: dict[tuple[int, int], dict[str, Any]] = {}
    for (team_id, match_id), group in frame.groupby(
        ["current_team_id", "match_id"], sort=True
    ):
        team_id = int(team_id)
        expected = evidence.player_ids_by_team[team_index[team_id]]
        indexed = group.set_index("account_id", drop=False)
        if any(int(account_id) not in indexed.index for account_id in expected):
            continue
        ordered = indexed.loc[list(expected)]
        if isinstance(ordered, pd.Series):
            ordered = ordered.to_frame().T
        if ordered["historical_team_id"].nunique() != 1:
            continue
        raw = np.empty((5, len(evidence.stat_ids)), dtype=np.float32)
        valid = True
        for stat_index, stat_id in enumerate(evidence.stat_ids):
            values = pd.to_numeric(ordered[stat_id], errors="coerce")
            if values.isna().any() or (values < 0.0).any():
                valid = False
                break
            raw[:, stat_index] = values.to_numpy(dtype=float)
        if not valid:
            continue
        complete_games[(team_id, int(match_id))] = {
            "series_id": int(ordered["series_id"].iloc[0]),
            "best_of": int(ordered["best_of"].iloc[0]),
            "series_won": bool(ordered["series_won"].iloc[0]),
            "series_length": int(ordered["series_length"].iloc[0]),
            "game_index": int(ordered["game_index"].iloc[0]),
            "won_game": bool(ordered["won_game"].iloc[0]),
            "opponent_probability": float(ordered["opponent_probability"].iloc[0]),
            "evidence_weight": float(ordered["evidence_weight"].mean()),
            "raw": raw,
        }
    if not complete_games:
        raise MainPlayerRoleBacktestError("v1 comparison pool has no complete Games")
    index_frame = pd.DataFrame(
        [
            {"team_id": key[0], "match_id": key[1], "series_id": value["series_id"]}
            for key, value in complete_games.items()
        ]
    )
    for (team_id, series_id), group in index_frame.groupby(
        ["team_id", "series_id"], sort=True
    ):
        games = [
            complete_games[(int(team_id), int(match_id))]
            for match_id in group["match_id"].astype(int)
        ]
        games.sort(key=lambda item: int(item["game_index"]))
        expected_length = int(games[0]["series_length"])
        if len(games) != expected_length or [int(item["game_index"]) for item in games] != list(
            range(expected_length)
        ):
            continue
        templates.append(
            HistoricalSeriesTemplate(
                team_id=int(team_id),
                series_id=int(series_id),
                best_of=int(games[0]["best_of"]),
                series_won=bool(games[0]["series_won"]),
                opponent_band=_opponent_band(float(games[0]["opponent_probability"])),
                evidence_weight=float(np.mean([item["evidence_weight"] for item in games])),
                won_games=tuple(bool(item["won_game"]) for item in games),
                raw_stats=np.asarray([item["raw"] for item in games]),
            )
        )
    if not templates:
        raise MainPlayerRoleBacktestError("v1 comparison pool has no complete Series")
    return tuple(templates)


def _series_candidates(
    templates: tuple[HistoricalSeriesTemplate, ...],
    target: EvaluationSeries,
    *,
    minimum_conditioned_series: int,
) -> tuple[list[HistoricalSeriesTemplate], int]:
    team = [item for item in templates if item.team_id == target.current_team_id]
    band = _opponent_band(target.opponent_probability)
    levels = (
        [
            item
            for item in team
            if item.best_of == target.best_of
            and item.series_won == target.series_won
            and item.opponent_band == band
        ],
        [
            item
            for item in team
            if item.best_of == target.best_of and item.series_won == target.series_won
        ],
        [
            item
            for item in team
            if item.series_won == target.series_won and item.opponent_band == band
        ],
        [item for item in team if item.series_won == target.series_won],
        [
            item
            for item in team
            if item.best_of == target.best_of and item.opponent_band == band
        ],
        [item for item in team if item.best_of == target.best_of],
        [item for item in team if item.opponent_band == band],
        team,
    )
    for level, candidates in enumerate(levels):
        minimum = minimum_conditioned_series if level < len(levels) - 1 else 1
        if len(candidates) >= minimum:
            return candidates, level
    raise MainPlayerRoleBacktestError(
        f"v1 comparison pool has no Series candidates for Team {target.current_team_id}"
    )


def sample_v1_series(
    templates: tuple[HistoricalSeriesTemplate, ...],
    target: EvaluationSeries,
    *,
    sample_count: int,
    seed: int,
    minimum_conditioned_series: int = 3,
) -> tuple[np.ndarray, int]:
    """Replicate v1's weighted Series then result-matched absolute Game draw."""

    rng = np.random.default_rng(int(seed))
    candidates, fallback = _series_candidates(
        templates,
        target,
        minimum_conditioned_series=minimum_conditioned_series,
    )
    weights = np.asarray([item.evidence_weight for item in candidates], dtype=float)
    weights /= weights.sum()
    source_indexes = rng.choice(len(candidates), size=sample_count, replace=True, p=weights)
    result = np.empty(
        (sample_count, len(target.match_ids), 5, target.raw_stats.shape[-1]),
        dtype=np.float32,
    )
    team_templates = [item for item in templates if item.team_id == target.current_team_id]
    target_band = _opponent_band(target.opponent_probability)
    for sample_index, source_index in enumerate(source_indexes):
        source = candidates[int(source_index)]
        for game_index, desired_win in enumerate(target.won_games):
            local = [
                offset for offset, won in enumerate(source.won_games) if won == desired_win
            ]
            if local:
                source_game = int(rng.choice(local))
                result[sample_index, game_index] = source.raw_stats[source_game]
                continue
            fallback_games = [
                (item, offset)
                for item in team_templates
                for offset, won in enumerate(item.won_games)
                if won == desired_win and item.opponent_band == target_band
            ]
            if not fallback_games:
                fallback_games = [
                    (item, offset)
                    for item in team_templates
                    for offset, won in enumerate(item.won_games)
                    if won == desired_win
                ]
            if not fallback_games:
                raise MainPlayerRoleBacktestError(
                    f"v1 Team {target.current_team_id} lacks result-matched Games"
                )
            item, offset = fallback_games[int(rng.integers(len(fallback_games)))]
            result[sample_index, game_index] = item.raw_stats[offset]
    return result, fallback


def sample_player_role_series(
    model: PlayerRoleGeneratorModel,
    target: EvaluationSeries,
    *,
    sample_count: int,
    seed: int,
) -> np.ndarray:
    """Generate a conditional future Series without using its realized duration or Stats."""

    rng = np.random.default_rng(int(seed))
    result = np.empty(
        (sample_count, len(target.match_ids), 5, len(model.stat_ids)), dtype=np.float32
    )
    for game_index, won_game in enumerate(target.won_games):
        durations = model.sample_durations(
            opponent_probability=target.opponent_probability,
            won_game=won_game,
            best_of=target.best_of,
            series_won=target.series_won,
            series_length=len(target.match_ids),
            game_index=game_index,
            size=sample_count,
            rng=rng,
        )
        result[:, game_index] = model.sample_team_games(
            team_id=target.current_team_id,
            opponent_probability=target.opponent_probability,
            won_game=won_game,
            best_of=target.best_of,
            series_won=target.series_won,
            series_length=len(target.match_ids),
            game_index=game_index,
            durations=durations,
            rng=rng,
        )
    return result


def _prediction_seed(base_seed: int, *parts: Any) -> int:
    material = ":".join([str(int(base_seed)), *(str(value) for value in parts)])
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")


def evaluate_fold(
    *,
    model: PlayerRoleGeneratorModel,
    training_evidence: PlayerRoleEvidence,
    holdout: PlayerRoleHoldout,
    rules: Mapping[str, Any],
    panel: tuple[BannerProjection, ...],
    sample_count: int,
    seeds: Sequence[int],
    minimum_conditioned_series: int = 3,
    candidate_sampler: Callable[..., np.ndarray] | None = None,
) -> BacktestResult:
    """Compare B and v1 on identical later Series and deterministic random streams."""

    if model.stat_ids != holdout.stat_ids or training_evidence.stat_ids != holdout.stat_ids:
        raise MainPlayerRoleBacktestError("training, model, and holdout Stat order differs")
    if sample_count < 2 or not seeds:
        raise MainPlayerRoleBacktestError("backtest requires multiple draws and at least one seed")
    templates = build_historical_series_templates(training_evidence)
    v1_team_ids = {item.team_id for item in templates}
    if not any(item.current_team_id in v1_team_ids for item in holdout.series):
        raise MainPlayerRoleBacktestError(
            "fold has no later Series on the v1 and Player-role common Team support"
        )
    # Stats have different physical units; Energy score uses a per-Stat robust scale.
    stat_scales = np.asarray(
        [
            max(
                float(
                    np.nanstd(
                        np.log1p(
                            pd.to_numeric(
                                training_evidence.frame[stat_id], errors="coerce"
                            ).to_numpy(dtype=float)
                        )
                    )
                ),
                1e-3,
            )
            for stat_id in training_evidence.stat_ids
        ]
    )
    records: list[dict[str, Any]] = []
    joint_records: list[dict[str, float | int | None]] = []
    period_payload: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    fallback_counts: Counter[int] = Counter()
    combined_sample_count = sample_count * len(seeds)
    sampler = sample_player_role_series if candidate_sampler is None else candidate_sampler
    for series in holdout.series:
        has_v1 = series.current_team_id in v1_team_ids
        b_blocks: list[np.ndarray] = []
        v1_blocks: list[np.ndarray] = []
        for seed in seeds:
            keyed = _prediction_seed(seed, holdout.fold_id, series.series_id, series.current_team_id)
            b_blocks.append(
                sampler(
                    model,
                    series,
                    sample_count=sample_count,
                    seed=keyed,
                )
            )
            if has_v1:
                v1, fallback = sample_v1_series(
                    templates,
                    series,
                    sample_count=sample_count,
                    seed=keyed,
                    minimum_conditioned_series=minimum_conditioned_series,
                )
                v1_blocks.append(v1)
                fallback_counts[fallback] += sample_count
        b_raw = np.concatenate(b_blocks, axis=0)
        v1_raw = np.concatenate(v1_blocks, axis=0) if has_v1 else None
        for game_index, match_id in enumerate(series.match_ids):
            actual_joint = np.log1p(series.raw_stats[game_index]) / stat_scales[None, :]
            b_joint = np.log1p(b_raw[:, game_index]) / stat_scales[None, None, :]
            v1_energy = None
            if v1_raw is not None:
                v1_joint = np.log1p(v1_raw[:, game_index]) / stat_scales[None, None, :]
                v1_energy = energy_score(
                    v1_joint.reshape(combined_sample_count, -1), actual_joint.reshape(-1)
                )
            joint_records.append(
                {
                    "match_id": int(match_id),
                    "series_id": series.series_id,
                    "team_id": series.current_team_id,
                    "b_energy": energy_score(
                        b_joint.reshape(combined_sample_count, -1), actual_joint.reshape(-1)
                    ),
                    "v1_energy": v1_energy,
                }
            )
        for projection in panel:
            actual_games = score_raw_games(
                series.raw_stats,
                stat_ids=holdout.stat_ids,
                projection=projection,
                rules=rules,
            )
            b_games = score_raw_games(
                b_raw,
                stat_ids=holdout.stat_ids,
                projection=projection,
                rules=rules,
            )
            actual = float(_top_two(actual_games))
            b_samples = _top_two(b_games)
            v1_samples = None
            if v1_raw is not None:
                v1_games = score_raw_games(
                    v1_raw,
                    stat_ids=holdout.stat_ids,
                    projection=projection,
                    rules=rules,
                )
                v1_samples = _top_two(v1_games)
            record = {
                "fold_id": holdout.fold_id,
                "league_id": holdout.league_id,
                "series_id": series.series_id,
                "team_id": series.current_team_id,
                "role": projection.role,
                "projection_id": projection.projection_id,
                "actual": actual,
                "b_mean": float(np.mean(b_samples)),
                "v1_mean": None if v1_samples is None else float(np.mean(v1_samples)),
                "b_crps": empirical_crps(b_samples, actual),
                "v1_crps": (
                    None if v1_samples is None else empirical_crps(v1_samples, actual)
                ),
                "b_q05": float(np.quantile(b_samples, 0.05)),
                "b_q10": float(np.quantile(b_samples, 0.10)),
                "b_q90": float(np.quantile(b_samples, 0.90)),
                "b_q95": float(np.quantile(b_samples, 0.95)),
            }
            records.append(record)
            period_key = (
                projection.projection_id,
                projection.role,
                series.current_team_id,
                series.series_id,
            )
            period_payload[period_key] = {
                "actual": actual,
                "b": b_samples,
                "v1": v1_samples,
            }
    if not records or not joint_records:
        raise MainPlayerRoleBacktestError("fold evaluation produced no proper-score records")
    frame = pd.DataFrame(records)
    joint = pd.DataFrame(joint_records)
    common_frame = frame.loc[frame["v1_crps"].notna()].copy()
    common_joint = joint.loc[joint["v1_energy"].notna()].copy()
    b_crps = float(frame["b_crps"].mean())
    common_b_crps = float(common_frame["b_crps"].mean())
    v1_crps = float(common_frame["v1_crps"].mean())
    coverage80 = float(
        ((frame["actual"] >= frame["b_q10"]) & (frame["actual"] <= frame["b_q90"])).mean()
    )
    coverage90 = float(
        ((frame["actual"] >= frame["b_q05"]) & (frame["actual"] <= frame["b_q95"])).mean()
    )
    role_metrics: dict[str, dict[str, float]] = {}
    for role, group in frame.groupby("role", sort=True):
        common_role = group.loc[group["v1_crps"].notna()]
        role_metrics[role] = {
            "b_crps": float(group["b_crps"].mean()),
            "common_b_crps": float(common_role["b_crps"].mean()),
            "v1_crps": float(common_role["v1_crps"].mean()),
            "relative_improvement": float(
                (common_role["v1_crps"].mean() - common_role["b_crps"].mean())
                / max(common_role["v1_crps"].mean(), 1e-12)
            ),
        }
    regrets: dict[str, list[float]] = {"b": [], "v1": []}
    for projection in panel:
        team_payload: dict[int, list[dict[str, Any]]] = {}
        for key, value in period_payload.items():
            projection_id, role, team_id, _ = key
            if projection_id == projection.projection_id and role == projection.role:
                team_payload.setdefault(int(team_id), []).append(value)
        if len(team_payload) < 2:
            continue
        actual_by_team = {
            team_id: max(float(item["actual"]) for item in values)
            for team_id, values in team_payload.items()
        }
        for label in ("b", "v1"):
            eligible_payload = {
                team_id: values
                for team_id, values in team_payload.items()
                if label == "b" or all(item[label] is not None for item in values)
            }
            if len(eligible_payload) < 2:
                continue
            predicted_mean = {
                team_id: float(
                    np.max(np.stack([item[label] for item in values]), axis=0).mean()
                )
                for team_id, values in eligible_payload.items()
            }
            selected = min(
                predicted_mean,
                key=lambda team_id: (-predicted_mean[team_id], team_id),
            )
            eligible_actual = {
                team_id: actual_by_team[team_id] for team_id in eligible_payload
            }
            regrets[label].append(max(eligible_actual.values()) - eligible_actual[selected])
    metrics = {
        "fold_id": holdout.fold_id,
        "holdout_series": len(holdout.series),
        "series": len(holdout.series),
        "common_v1_series": int(common_frame[["series_id", "team_id"]].drop_duplicates().shape[0]),
        "excluded_without_v1_training_pool": int(
            len(holdout.series)
            - common_frame[["series_id", "team_id"]].drop_duplicates().shape[0]
        ),
        "v1_training_team_ids": sorted(v1_team_ids),
        "series_projection_records": len(frame),
        "joint_games": len(joint),
        "predictive_samples_per_series": combined_sample_count,
        "b_series_crps": b_crps,
        "common_b_series_crps": common_b_crps,
        "v1_series_crps": v1_crps,
        "series_crps_relative_improvement": (
            v1_crps - common_b_crps
        ) / max(v1_crps, 1e-12),
        "b_coverage80": coverage80,
        "b_coverage90": coverage90,
        "b_joint_energy": float(joint["b_energy"].mean()),
        "common_b_joint_energy": float(common_joint["b_energy"].mean()),
        "v1_joint_energy": float(common_joint["v1_energy"].mean()),
        "joint_energy_relative_improvement": float(
            (common_joint["v1_energy"].mean() - common_joint["b_energy"].mean())
            / max(common_joint["v1_energy"].mean(), 1e-12)
        ),
        "b_mean_regret": float(np.mean(regrets["b"])) if regrets["b"] else None,
        "v1_mean_regret": float(np.mean(regrets["v1"])) if regrets["v1"] else None,
        "role_metrics": role_metrics,
        "v1_series_fallback_counts": {
            str(level): count for level, count in sorted(fallback_counts.items())
        },
        "panel_sha256": sha256_json(
            [
                {
                    "projection_id": item.projection_id,
                    "role": item.role,
                    "stat_ids": item.stat_ids,
                    "multipliers": item.multipliers.tolist(),
                }
                for item in panel
            ]
        ),
        "model_sha256": model.semantic_hash,
        "training_evidence_sha256": training_evidence.audit.get("semantic_hash"),
        "holdout_sha256": holdout.audit.get("semantic_hash"),
    }
    compact_records = tuple(
        {
            key: (
                int(value)
                if isinstance(value, np.integer)
                else float(value)
                if isinstance(value, np.floating)
                else value
            )
            for key, value in row.items()
        }
        for row in records
    )
    compact_joint = tuple(
        {
            key: (
                int(value)
                if isinstance(value, np.integer)
                else float(value)
                if isinstance(value, np.floating)
                else value
            )
            for key, value in row.items()
        }
        for row in joint_records
    )
    semantic_hash = sha256_json(
        {"metrics": metrics, "records": compact_records, "joint_records": compact_joint}
    )
    return BacktestResult(
        holdout.fold_id,
        metrics,
        compact_records,
        compact_joint,
        semantic_hash,
    )


def paired_series_bootstrap_lower_bound(
    records: Sequence[Mapping[str, Any]],
    *,
    confidence: float,
    seed: int,
    replicates: int = 10_000,
) -> dict[str, float]:
    """Series-block bootstrap of v1 minus B CRPS, preserving all role projections."""

    if not 0.5 < confidence < 1.0 or replicates < 100:
        raise MainPlayerRoleBacktestError("bootstrap confidence or replicate count is invalid")
    frame = pd.DataFrame(records)
    required = {"series_id", "team_id", "v1_crps", "b_crps"}
    if not required <= set(frame):
        raise MainPlayerRoleBacktestError("bootstrap records lack paired CRPS fields")
    grouped = (
        frame.assign(delta=frame["v1_crps"] - frame["b_crps"])
        .groupby(["series_id", "team_id"], sort=True)["delta"]
        .mean()
        .to_numpy(dtype=float)
    )
    rng = np.random.default_rng(int(seed))
    indexes = rng.integers(0, len(grouped), size=(replicates, len(grouped)))
    distribution = grouped[indexes].mean(axis=1)
    lower = float(np.quantile(distribution, 1.0 - confidence))
    mean = float(grouped.mean())
    return {
        "paired_series_blocks": len(grouped),
        "mean_absolute_improvement": mean,
        "one_sided_lower_bound": lower,
        "confidence": float(confidence),
        "replicates": int(replicates),
    }


__all__ = [
    "BacktestResult",
    "BannerProjection",
    "EvaluationSeries",
    "HistoricalSeriesTemplate",
    "MainPlayerRoleBacktestError",
    "PlayerRoleHoldout",
    "build_hash_fixed_banner_panel",
    "build_historical_series_templates",
    "build_player_role_holdout",
    "empirical_crps",
    "energy_score",
    "evaluate_fold",
    "paired_series_bootstrap_lower_bound",
    "sample_player_role_series",
    "sample_v1_series",
    "score_raw_games",
]
