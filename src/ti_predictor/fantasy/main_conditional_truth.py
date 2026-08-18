"""Research-only exact-bracket, conditional Main Fantasy reference simulation.

This module is deliberately isolated from the consumer Web and frozen solver releases.
It enumerates every coherent eight-Team Main bracket path, converts the frozen
single-Game Team-strength probability to BO3/BO5 Series probabilities, and samples
future Game-level Fantasy evidence conditional on Team, opponent-strength band,
Series result and format.  Generated draws are reusable offline evidence; a user's
five-slot Banners are scored only after the evidence has been frozen.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from math import comb
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from ti_predictor.config import (
    load_rules,
    load_team_strength_policy,
    load_tournament_manifest,
)
from ti_predictor.fantasy.roll import BannerState, EmblemState
from ti_predictor.fantasy.scenarios import ROLE_IDS
from ti_predictor.fantasy.scoring import score_stat
from ti_predictor.fantasy.valuation import _banner_score_inputs
from ti_predictor.forecasting import _available_by_as_of, load_strength_model_as_of
from ti_predictor.hashing import sha256_bytes, sha256_file, sha256_json
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import source_tree_hash, source_version
from ti_predictor.schemas import StrictModel, as_utc
from ti_predictor.storage import read_parquet_if_exists
from ti_predictor.tournament.bracket import BracketEngine

SERIES_NODE_COUNT = 14
SERIES_SIDE_COUNT = 2
MAX_SERIES_GAMES = 5
GAME_TEMPLATE_SENTINEL = np.iinfo(np.uint16).max
ROLE_PLAYER_OFFSETS: Mapping[str, tuple[int, ...]] = {
    "core": (0, 1),
    "mid": (2,),
    "support": (3, 4),
}
FORMAT_CODE = {"bo2": 2, "bo3": 3, "bo5": 5}
FORMAT_NAME = {value: key for key, value in FORMAT_CODE.items()}
RESULT_CODE = {"loss": 0, "win": 1, "draw": 2}
RESULT_NAME = {value: key for key, value in RESULT_CODE.items()}
BAND_CODE = {"underdog": 0, "peer": 1, "favored": 2}
BAND_NAME = {value: key for key, value in BAND_CODE.items()}


class MainConditionalTruthError(ValueError):
    """The research contract, evidence or generated draws are invalid."""


class MainConditionalTruthConfig(StrictModel):
    schema_version: Literal[1]
    experiment_id: Literal["ti2026-main-conditional-truth-v1"]
    period: Literal["main"]
    as_of: str
    outer_path_count: Literal[16384]
    outer_weighting: Literal["exact-series-probability"]
    inner_samples_per_path: int = Field(ge=1, le=64)
    seeds: list[int] = Field(min_length=1, max_length=8)
    opponent_probability_boundaries: tuple[float, float]
    minimum_conditioned_series: int = Field(ge=1, le=20)
    historical_series_formats: list[Literal["bo2", "bo3", "bo5"]]
    future_series_formats: list[Literal["bo3", "bo5"]]
    series_probability_model: Literal["iid-binomial-from-frozen-team-strength"]
    game_sampling: Literal["weighted-result-conditioned-joint-five-player-template"]
    team_side_correlation: Literal["shared-series-sequence-independent-team-templates-given-game-result"]
    coach_title_policy: Literal["excluded-from-reference-v1"]
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    mean_retention_epsilon: float = Field(ge=0.0, lt=1.0)

    @model_validator(mode="after")
    def validate_contract(self) -> MainConditionalTruthConfig:
        lower, upper = self.opponent_probability_boundaries
        if not 0.0 < lower < upper < 1.0:
            raise ValueError("opponent probability boundaries must be ordered inside (0, 1)")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("conditional truth seeds must be unique")
        if self.historical_series_formats != ["bo2", "bo3", "bo5"]:
            raise ValueError("conditional truth requires the frozen BO2/BO3/BO5 fallback order")
        if self.future_series_formats != ["bo3", "bo5"]:
            raise ValueError("Main future Series formats must be BO3 then BO5")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


def load_main_conditional_truth_config(path: Path) -> MainConditionalTruthConfig:
    return MainConditionalTruthConfig.model_validate_json(path.read_text(encoding="utf-8"))


def series_win_probability(game_probability: float, best_of: int) -> float:
    """Convert an IID single-Game probability to a BO3/BO5 Series probability."""

    p = float(game_probability)
    if not 0.0 <= p <= 1.0:
        raise MainConditionalTruthError("single-Game probability must be in [0, 1]")
    if best_of not in {3, 5}:
        raise MainConditionalTruthError("Main Series probability supports only BO3 or BO5")
    needed = best_of // 2 + 1
    probability = 0.0
    for wins in range(needed, best_of + 1):
        probability += float(comb(best_of, wins)) * p**wins * (1.0 - p) ** (best_of - wins)
    return probability


def legal_series_sequences(
    game_probability: float,
    *,
    best_of: int,
    target_wins: bool,
) -> tuple[tuple[tuple[int, ...], ...], np.ndarray]:
    """Enumerate legal terminal Game-result sequences conditional on Series result."""

    p = float(game_probability)
    if not 0.0 < p < 1.0:
        raise MainConditionalTruthError("conditional Game sequences require probability in (0, 1)")
    if best_of not in {3, 5}:
        raise MainConditionalTruthError("Main conditional sequences support only BO3 or BO5")
    needed = best_of // 2 + 1
    sequences: list[tuple[int, ...]] = []
    weights: list[float] = []
    for length in range(needed, best_of + 1):
        for prefix in product((0, 1), repeat=length - 1):
            final = 1 if target_wins else 0
            sequence = (*prefix, final)
            target_count = sum(sequence)
            opponent_count = length - target_count
            if target_wins:
                legal = target_count == needed and opponent_count < needed
            else:
                legal = opponent_count == needed and target_count < needed
            if not legal:
                continue
            # The deciding Game must be the first time either side reaches ``needed``.
            if sum(sequence[:-1]) >= needed or (length - 1 - sum(sequence[:-1])) >= needed:
                continue
            sequences.append(tuple(int(value) for value in sequence))
            weights.append(p**target_count * (1.0 - p) ** opponent_count)
    probabilities = np.asarray(weights, dtype=float)
    if not len(probabilities) or probabilities.sum() <= 0.0:
        raise MainConditionalTruthError("conditional Series sequence support is empty")
    probabilities /= probabilities.sum()
    return tuple(sequences), probabilities


def opponent_strength_band(
    target_game_probability: float,
    boundaries: tuple[float, float],
) -> int:
    lower, upper = boundaries
    probability = float(target_game_probability)
    if probability < lower:
        return BAND_CODE["underdog"]
    if probability > upper:
        return BAND_CODE["favored"]
    return BAND_CODE["peer"]


@dataclass(frozen=True)
class ExactMainOuterPaths:
    team_ids: tuple[int, ...]
    participants: np.ndarray
    winners: np.ndarray
    probabilities: np.ndarray
    semantic_hash: str

    def __post_init__(self) -> None:
        participants = np.ascontiguousarray(self.participants, dtype="<i2")
        winners = np.ascontiguousarray(self.winners, dtype="<i2")
        probabilities = np.ascontiguousarray(self.probabilities, dtype="<f8")
        object.__setattr__(self, "participants", participants)
        object.__setattr__(self, "winners", winners)
        object.__setattr__(self, "probabilities", probabilities)
        expected_paths = 2**SERIES_NODE_COUNT
        if participants.shape != (expected_paths, SERIES_NODE_COUNT, SERIES_SIDE_COUNT):
            raise MainConditionalTruthError("exact outer participants have an invalid shape")
        if winners.shape != (expected_paths, SERIES_NODE_COUNT):
            raise MainConditionalTruthError("exact outer winners have an invalid shape")
        if probabilities.shape != (expected_paths,) or np.any(probabilities <= 0.0):
            raise MainConditionalTruthError("exact outer probabilities are incomplete")
        if not np.isclose(probabilities.sum(), 1.0, atol=1e-12):
            raise MainConditionalTruthError("exact outer probabilities do not sum to one")
        if np.any(participants < 0) or np.any(participants >= len(self.team_ids)):
            raise MainConditionalTruthError("outer participant indexes exceed the eight-Team roster")
        if np.any(winners < 0) or np.any(winners >= len(self.team_ids)):
            raise MainConditionalTruthError("outer winner indexes exceed the eight-Team roster")


def build_exact_main_outer_paths(
    team_ids: Sequence[int],
    model: TeamStrengthModel,
) -> ExactMainOuterPaths:
    """Enumerate all 16,384 paths with BO3/BO5 Series probabilities."""

    stable_ids = tuple(int(value) for value in team_ids)
    if len(stable_ids) != 8 or len(set(stable_ids)) != 8:
        raise MainConditionalTruthError("exact Main outer paths require eight unique seeded Teams")
    engine = BracketEngine(stable_ids, model)
    index = {team_id: offset for offset, team_id in enumerate(stable_ids)}
    paths = engine.enumerate()
    participants = np.empty((len(paths), SERIES_NODE_COUNT, SERIES_SIDE_COUNT), dtype=np.int16)
    winners = np.empty((len(paths), SERIES_NODE_COUNT), dtype=np.int16)
    probabilities = np.empty(len(paths), dtype=float)
    for path_index, path in enumerate(paths):
        probability = 1.0
        for node, ((left, right), winner) in enumerate(zip(path.participants, path.winners, strict=True)):
            participants[path_index, node] = (index[left], index[right])
            winners[path_index, node] = index[winner]
            best_of = 5 if node == SERIES_NODE_COUNT - 1 else 3
            p_left = series_win_probability(model.predict(left, right), best_of)
            probability *= p_left if winner == left else 1.0 - p_left
        probabilities[path_index] = probability
    probabilities /= probabilities.sum()
    semantic_hash = sha256_json(
        {
            "team_ids": stable_ids,
            "probabilities_sha256": _array_sha256(probabilities),
            "participants_sha256": _array_sha256(participants),
            "winners_sha256": _array_sha256(winners),
            "series_probability_model": "iid-binomial-from-frozen-team-strength",
            "node_formats": ["bo3"] * 13 + ["bo5"],
        }
    )
    return ExactMainOuterPaths(stable_ids, participants, winners, probabilities, semantic_hash)


def _array_sha256(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values)
    header = canonical.dtype.str.encode("ascii") + b":" + str(canonical.shape).encode("ascii")
    return sha256_bytes(header + b"\0" + canonical.tobytes(order="C"))


@dataclass(frozen=True)
class JointGameTemplateSet:
    team_ids: tuple[int, ...]
    stat_ids: tuple[str, ...]
    player_ids: np.ndarray
    scores: np.ndarray
    game_team_indexes: np.ndarray
    game_series_indexes: np.ndarray
    game_wins: np.ndarray
    game_bands: np.ndarray
    series_ids: np.ndarray
    series_team_indexes: np.ndarray
    series_formats: np.ndarray
    series_results: np.ndarray
    series_bands: np.ndarray
    series_weights: np.ndarray
    series_game_offsets: np.ndarray
    series_game_ids: np.ndarray
    audit: Mapping[str, Any]
    semantic_hash: str

    def __post_init__(self) -> None:
        player_ids = np.ascontiguousarray(self.player_ids, dtype="<i8")
        scores = np.ascontiguousarray(self.scores, dtype="<f4")
        game_team_indexes = np.ascontiguousarray(self.game_team_indexes, dtype="<i2")
        game_series_indexes = np.ascontiguousarray(self.game_series_indexes, dtype="<i4")
        game_wins = np.ascontiguousarray(self.game_wins, dtype="<i1")
        game_bands = np.ascontiguousarray(self.game_bands, dtype="<i1")
        series_ids = np.ascontiguousarray(self.series_ids, dtype="<i8")
        series_team_indexes = np.ascontiguousarray(self.series_team_indexes, dtype="<i2")
        series_formats = np.ascontiguousarray(self.series_formats, dtype="<i1")
        series_results = np.ascontiguousarray(self.series_results, dtype="<i1")
        series_bands = np.ascontiguousarray(self.series_bands, dtype="<i1")
        series_weights = np.ascontiguousarray(self.series_weights, dtype="<f8")
        series_game_offsets = np.ascontiguousarray(self.series_game_offsets, dtype="<i4")
        series_game_ids = np.ascontiguousarray(self.series_game_ids, dtype="<i4")
        for name, value in (
            ("player_ids", player_ids),
            ("scores", scores),
            ("game_team_indexes", game_team_indexes),
            ("game_series_indexes", game_series_indexes),
            ("game_wins", game_wins),
            ("game_bands", game_bands),
            ("series_ids", series_ids),
            ("series_team_indexes", series_team_indexes),
            ("series_formats", series_formats),
            ("series_results", series_results),
            ("series_bands", series_bands),
            ("series_weights", series_weights),
            ("series_game_offsets", series_game_offsets),
            ("series_game_ids", series_game_ids),
        ):
            object.__setattr__(self, name, value)
        game_count = len(scores)
        series_count = len(series_ids)
        if scores.ndim != 3 or scores.shape[1:] != (5, len(self.stat_ids)):
            raise MainConditionalTruthError("joint Game score templates must be Game×5 players×Stats")
        if player_ids.shape != (len(self.team_ids), 5):
            raise MainConditionalTruthError("joint template player identities must align with eight Teams")
        if game_count >= int(GAME_TEMPLATE_SENTINEL):
            raise MainConditionalTruthError("joint Game template count exceeds uint16 draw storage")
        if series_count >= np.iinfo(np.int16).max:
            raise MainConditionalTruthError("joint Series count exceeds int16 draw storage")
        if any(
            len(value) != game_count
            for value in (game_team_indexes, game_series_indexes, game_wins, game_bands)
        ):
            raise MainConditionalTruthError("joint Game template metadata does not align")
        if any(
            len(value) != series_count
            for value in (
                series_team_indexes,
                series_formats,
                series_results,
                series_bands,
                series_weights,
            )
        ):
            raise MainConditionalTruthError("joint Series template metadata does not align")
        if series_game_offsets.shape != (series_count + 1,):
            raise MainConditionalTruthError("joint Series Game offsets do not align")
        if series_game_offsets[0] != 0 or series_game_offsets[-1] != len(series_game_ids):
            raise MainConditionalTruthError("joint Series Game offsets are incomplete")
        if np.any(series_weights <= 0.0) or not np.isfinite(series_weights).all():
            raise MainConditionalTruthError("joint Series weights must be positive and finite")

    def games_for_series(self, series_index: int) -> np.ndarray:
        start = int(self.series_game_offsets[series_index])
        end = int(self.series_game_offsets[series_index + 1])
        return self.series_game_ids[start:end]


def _format_from_catalog(series_type: int, game_count: int) -> int | None:
    if series_type == 1 and game_count in {2, 3}:
        return FORMAT_CODE["bo3"]
    if series_type == 2 and game_count in {3, 4, 5}:
        return FORMAT_CODE["bo5"]
    if series_type == 3 and game_count == 2:
        return FORMAT_CODE["bo2"]
    return None


def _team_game_result(match: Mapping[str, Any], historical_team_id: int) -> tuple[int, bool] | None:
    radiant = match.get("radiant_team_id")
    dire = match.get("dire_team_id")
    radiant_win = match.get("radiant_win")
    if pd.isna(radiant) or pd.isna(dire) or not isinstance(radiant_win, (bool, np.bool_)):
        return None
    radiant_id = int(radiant)
    dire_id = int(dire)
    if historical_team_id == radiant_id:
        return dire_id, bool(radiant_win)
    if historical_team_id == dire_id:
        return radiant_id, not bool(radiant_win)
    return None


def _player_order(manifest: Any, team_id: int) -> tuple[int, ...]:
    team = next(item for item in manifest.teams if int(item.team_id) == int(team_id))
    return tuple(int(player.account_id) for role in ROLE_IDS for player in team.players[role])


def build_joint_game_templates(
    *,
    as_of: Any,
    config: MainConditionalTruthConfig,
    model: TeamStrengthModel,
    paths: ProjectPaths = PATHS,
) -> JointGameTemplateSet:
    """Build complete five-player historical Game templates from the frozen Main snapshot."""

    cutoff = as_utc(as_of)
    if cutoff is None:
        raise MainConditionalTruthError("conditional truth evidence requires an explicit as_of")
    evidence_paths = main_evidence_paths(paths, require=True)
    manifest = load_tournament_manifest(evidence_paths.tournament)
    rules = load_rules(evidence_paths.rules)
    team_ids = tuple(int(value) for value in manifest.main_event_seeds)
    if len(team_ids) != 8:
        raise MainConditionalTruthError("conditional truth requires the actual eight Main Teams")
    matches_path = evidence_paths.processed / "matches.parquet"
    observations_path = evidence_paths.processed / "fantasy_performance_samples.parquet"
    patches_path = evidence_paths.processed / "patches.parquet"
    matches = _available_by_as_of(read_parquet_if_exists(matches_path), cutoff)
    observations = _available_by_as_of(read_parquet_if_exists(observations_path), cutoff)
    patches = _available_by_as_of(read_parquet_if_exists(patches_path), cutoff)
    strength_policy = load_team_strength_policy(manifest, config_root=evidence_paths.config, period="main")
    fantasy_policy = strength_policy.model_copy(
        update={
            "policy_id": f"{strength_policy.policy_id}-conditional-truth-history",
            "evidence_scope": EvidenceScopePolicy(mode="global"),
        }
    )
    evidence = build_evidence_set(
        matches,
        patches,
        as_of=cutoff,
        policy=fantasy_policy,
        target_patch_family=model.target_patch_family,
        evidence_channel="fantasy",
    )
    blocking = [issue.message for issue in evidence.issues if issue.severity == "blocking"]
    if blocking:
        raise MainConditionalTruthError("conditional truth evidence is blocked: " + "; ".join(blocking))
    weights = evidence.matches[["match_id", "evidence_weight"]].copy()
    weights["match_id"] = pd.to_numeric(weights["match_id"], errors="coerce")
    weights = weights.dropna(subset=["match_id"]).astype({"match_id": int})
    weight_by_match = {
        int(row.match_id): float(row.evidence_weight) for row in weights.itertuples(index=False)
    }

    match_frame = matches.loc[
        matches["match_id"].isin(weight_by_match)
        & matches["series_id"].notna()
        & matches["series_type"].notna()
    ].copy()
    match_frame["match_id"] = match_frame["match_id"].astype(int)
    match_frame["series_id"] = match_frame["series_id"].astype(int)
    match_frame["series_type"] = match_frame["series_type"].astype(int)
    match_by_id = {int(row["match_id"]): row for row in match_frame.to_dict(orient="records")}
    observation_frame = observations.copy()
    observation_frame["match_id"] = pd.to_numeric(observation_frame["match_id"], errors="coerce")
    observation_frame["account_id"] = pd.to_numeric(observation_frame["account_id"], errors="coerce")
    observation_frame = observation_frame.dropna(subset=["match_id", "account_id"])
    observation_frame = observation_frame.astype({"match_id": int, "account_id": int})
    observation_by_match = {
        int(match_id): rows.set_index("account_id", drop=False)
        for match_id, rows in observation_frame.groupby("match_id", sort=False)
    }
    stat_ids = tuple(str(value) for value in rules["fantasy"]["stats"])
    player_ids = np.asarray([_player_order(manifest, team_id) for team_id in team_ids], dtype=np.int64)

    game_scores: list[np.ndarray] = []
    game_team_indexes: list[int] = []
    game_series_indexes: list[int] = []
    game_wins: list[int] = []
    game_bands: list[int] = []
    series_ids: list[int] = []
    series_team_indexes: list[int] = []
    series_formats: list[int] = []
    series_results: list[int] = []
    series_bands: list[int] = []
    series_weights: list[float] = []
    series_game_offsets = [0]
    series_game_ids: list[int] = []
    rejection = Counter()
    accepted_by_team_format: dict[str, Counter[str]] = {str(team_id): Counter() for team_id in team_ids}

    grouped_series = {
        int(series_id): games.sort_values(["start_time", "match_id"], kind="stable")
        for series_id, games in match_frame.groupby("series_id", sort=True)
    }
    for team_index, team_id in enumerate(team_ids):
        required_players = tuple(int(value) for value in player_ids[team_index])
        for series_id, games in grouped_series.items():
            if games["series_type"].nunique(dropna=False) != 1:
                rejection["mixed_series_type"] += 1
                continue
            series_format = _format_from_catalog(int(games["series_type"].iloc[0]), len(games))
            if series_format is None:
                rejection["unsupported_or_incomplete_format"] += 1
                continue
            historical_team_ids: list[int] = []
            per_game_scores: list[np.ndarray] = []
            per_game_results: list[bool] = []
            opponents: list[int] = []
            valid = True
            for match_id in games["match_id"].astype(int):
                indexed = observation_by_match.get(int(match_id))
                if indexed is None or any(account_id not in indexed.index for account_id in required_players):
                    rejection["missing_required_player_game"] += 1
                    valid = False
                    break
                selected = indexed.loc[list(required_players)]
                if isinstance(selected, pd.Series):
                    selected = selected.to_frame().T
                historical = pd.to_numeric(selected["team_id"], errors="coerce")
                if historical.isna().any() or historical.nunique() != 1:
                    rejection["cross_team_players"] += 1
                    valid = False
                    break
                historical_team_id = int(historical.iloc[0])
                result = _team_game_result(match_by_id[int(match_id)], historical_team_id)
                if result is None:
                    rejection["team_side_unresolved"] += 1
                    valid = False
                    break
                opponent_id, won = result
                matrix = np.empty((5, len(stat_ids)), dtype=np.float32)
                for player_offset, (_, row) in enumerate(selected.iterrows()):
                    for stat_offset, stat_id in enumerate(stat_ids):
                        rule = rules["fantasy"]["stats"][stat_id]
                        if (
                            pd.isna(row.get(stat_id))
                            or row.get(f"{stat_id}_provenance") != rule["provenance"]
                        ):
                            valid = False
                            break
                        value = score_stat(float(row[stat_id]), rule)
                        if value is None:
                            valid = False
                            break
                        matrix[player_offset, stat_offset] = float(value)
                    if not valid:
                        break
                if not valid:
                    rejection["missing_or_wrong_provenance"] += 1
                    break
                historical_team_ids.append(historical_team_id)
                per_game_scores.append(matrix)
                per_game_results.append(bool(won))
                opponents.append(opponent_id)
            if not valid:
                continue
            if len(set(historical_team_ids)) != 1 or len(set(opponents)) != 1:
                rejection["cross_team_or_opponent_series"] += 1
                continue
            wins = sum(per_game_results)
            losses = len(per_game_results) - wins
            result_name = "win" if wins > losses else "loss" if losses > wins else "draw"
            probability = model.predict(team_id, opponents[0])
            band = opponent_strength_band(probability, config.opponent_probability_boundaries)
            evidence_weight = float(np.mean([weight_by_match[int(value)] for value in games["match_id"]]))
            if evidence_weight <= 0.0 or not np.isfinite(evidence_weight):
                rejection["nonpositive_weight"] += 1
                continue
            series_index = len(series_ids)
            series_ids.append(series_id)
            series_team_indexes.append(team_index)
            series_formats.append(series_format)
            series_results.append(RESULT_CODE[result_name])
            series_bands.append(band)
            series_weights.append(evidence_weight)
            for matrix, won in zip(per_game_scores, per_game_results, strict=True):
                game_id = len(game_scores)
                game_scores.append(matrix)
                game_team_indexes.append(team_index)
                game_series_indexes.append(series_index)
                game_wins.append(int(won))
                game_bands.append(band)
                series_game_ids.append(game_id)
            series_game_offsets.append(len(series_game_ids))
            accepted_by_team_format[str(team_id)][FORMAT_NAME[series_format]] += 1

    if any(sum(accepted_by_team_format[str(team_id)].values()) == 0 for team_id in team_ids):
        raise MainConditionalTruthError("at least one Main Team has no complete joint Series template")
    scores = np.asarray(game_scores, dtype=np.float32)
    if not len(scores):
        raise MainConditionalTruthError("conditional truth produced no complete joint Game templates")
    audit = {
        "as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "team_ids": list(team_ids),
        "stat_ids": list(stat_ids),
        "game_template_count": len(game_scores),
        "series_template_count": len(series_ids),
        "accepted_series_by_team_format": {
            key: dict(sorted(value.items())) for key, value in accepted_by_team_format.items()
        },
        "rejection_counts": dict(sorted(rejection.items())),
        "evidence_audit": evidence.audit,
        "warnings": sorted(issue.message for issue in evidence.issues if issue.severity == "warning"),
    }
    arrays = {
        "player_ids": player_ids,
        "scores": scores,
        "game_team_indexes": np.asarray(game_team_indexes, dtype=np.int16),
        "game_series_indexes": np.asarray(game_series_indexes, dtype=np.int32),
        "game_wins": np.asarray(game_wins, dtype=np.int8),
        "game_bands": np.asarray(game_bands, dtype=np.int8),
        "series_ids": np.asarray(series_ids, dtype=np.int64),
        "series_team_indexes": np.asarray(series_team_indexes, dtype=np.int16),
        "series_formats": np.asarray(series_formats, dtype=np.int8),
        "series_results": np.asarray(series_results, dtype=np.int8),
        "series_bands": np.asarray(series_bands, dtype=np.int8),
        "series_weights": np.asarray(series_weights, dtype=float),
        "series_game_offsets": np.asarray(series_game_offsets, dtype=np.int32),
        "series_game_ids": np.asarray(series_game_ids, dtype=np.int32),
    }
    semantic_hash = sha256_json(
        {
            "team_ids": team_ids,
            "stat_ids": stat_ids,
            "arrays": {name: _array_sha256(value) for name, value in arrays.items()},
            "audit_sha256": sha256_json(audit),
        }
    )
    return JointGameTemplateSet(
        team_ids=team_ids,
        stat_ids=stat_ids,
        audit=audit,
        semantic_hash=semantic_hash,
        **arrays,
    )


def _normalized_choice(
    rng: np.random.Generator,
    candidates: np.ndarray,
    weights: np.ndarray,
    size: int,
) -> np.ndarray:
    selected_weights = np.asarray(weights[candidates], dtype=float)
    selected_weights /= selected_weights.sum()
    return rng.choice(candidates, size=size, replace=True, p=selected_weights)


class _ConditionalSampler:
    def __init__(self, templates: JointGameTemplateSet, config: MainConditionalTruthConfig) -> None:
        self.templates = templates
        self.config = config
        self._series_cache: dict[tuple[int, int, int, int], tuple[np.ndarray, int]] = {}
        self._game_cache: dict[tuple[int, int, int], tuple[np.ndarray, int]] = {}

    def series_candidates(
        self,
        team_index: int,
        requested_format: int,
        requested_result: int,
        band: int,
    ) -> tuple[np.ndarray, int]:
        key = (team_index, requested_format, requested_result, band)
        if key in self._series_cache:
            return self._series_cache[key]
        t = self.templates
        team = t.series_team_indexes == team_index
        format_match = t.series_formats == requested_format
        result_match = t.series_results == requested_result
        band_match = t.series_bands == band
        levels = (
            team & format_match & result_match & band_match,
            team & format_match & result_match,
            team & result_match & band_match,
            team & result_match,
            team & format_match & band_match,
            team & format_match,
            team & band_match,
            team,
        )
        for level, mask in enumerate(levels):
            candidates = np.flatnonzero(mask)
            minimum = self.config.minimum_conditioned_series if level < len(levels) - 1 else 1
            if len(candidates) >= minimum:
                self._series_cache[key] = (candidates, level)
                return candidates, level
        raise MainConditionalTruthError(f"Team index {team_index} has no conditional Series candidates")

    def game_candidates(self, series_index: int, desired_win: int, band: int) -> tuple[np.ndarray, int]:
        key = (series_index, desired_win, band)
        if key in self._game_cache:
            return self._game_cache[key]
        t = self.templates
        source = t.games_for_series(series_index)
        same_result = source[t.game_wins[source] == desired_win]
        if len(same_result):
            result = (same_result, 0)
        else:
            team_index = int(t.series_team_indexes[series_index])
            team = t.game_team_indexes == team_index
            win = t.game_wins == desired_win
            same_band = t.game_bands == band
            candidates = np.flatnonzero(team & win & same_band)
            if len(candidates):
                result = (candidates, 1)
            else:
                candidates = np.flatnonzero(team & win)
                if len(candidates):
                    result = (candidates, 2)
                else:
                    raise MainConditionalTruthError(
                        f"Team index {team_index} has no Game templates for result {desired_win}"
                    )
        self._game_cache[key] = result
        return result


@dataclass(frozen=True)
class ConditionalDrawResult:
    game_template_ids: np.ndarray
    source_series_indexes: np.ndarray
    series_fallback_levels: np.ndarray
    shared_left_game_results: np.ndarray
    audit: Mapping[str, Any]


def generate_conditional_draws(
    templates: JointGameTemplateSet,
    outer: ExactMainOuterPaths,
    model: TeamStrengthModel,
    config: MainConditionalTruthConfig,
    *,
    seed: int,
) -> ConditionalDrawResult:
    """Generate one deterministic inner panel over every exact outer path."""

    if outer.team_ids != templates.team_ids:
        raise MainConditionalTruthError("outer bracket and joint templates use different Team order")
    rng = np.random.default_rng(int(seed))
    sampler = _ConditionalSampler(templates, config)
    inner = config.inner_samples_per_path
    path_count = len(outer.probabilities)
    shape = (inner, path_count, SERIES_NODE_COUNT, SERIES_SIDE_COUNT)
    source_series = np.full(shape, -1, dtype=np.int16)
    fallback_levels = np.full(shape, 255, dtype=np.uint8)
    game_ids = np.full((*shape, MAX_SERIES_GAMES), GAME_TEMPLATE_SENTINEL, dtype=np.uint16)
    shared_left_results = np.full(
        (inner, path_count, SERIES_NODE_COUNT, MAX_SERIES_GAMES),
        -1,
        dtype=np.int8,
    )
    series_fallback_counts: Counter[int] = Counter()
    game_fallback_counts: Counter[int] = Counter()
    requested_context_counts: Counter[str] = Counter()

    base_team = outer.participants
    base_opponent = outer.participants[:, :, ::-1]
    base_result = (outer.participants == outer.winners[:, :, None]).astype(np.int8)
    format_by_node = np.asarray([FORMAT_CODE["bo3"]] * 13 + [FORMAT_CODE["bo5"]], dtype=np.int8)

    # Freeze one coherent score sequence per future Series.  Both Team sides
    # subsequently see the same Series length and opposite per-Game results.
    for left_index in range(len(outer.team_ids)):
        for right_index in range(len(outer.team_ids)):
            if left_index == right_index:
                continue
            p_left = model.predict(outer.team_ids[left_index], outer.team_ids[right_index])
            for left_result in (RESULT_CODE["loss"], RESULT_CODE["win"]):
                for requested_format in (FORMAT_CODE["bo3"], FORMAT_CODE["bo5"]):
                    series_mask = (
                        (base_team[:, :, 0] == left_index)
                        & (base_team[:, :, 1] == right_index)
                        & (base_result[:, :, 0] == left_result)
                        & (format_by_node[None, :] == requested_format)
                    )
                    positions = np.argwhere(series_mask)
                    if not len(positions):
                        continue
                    sequences, probabilities = legal_series_sequences(
                        p_left,
                        best_of=requested_format,
                        target_wins=left_result == RESULT_CODE["win"],
                    )
                    count = inner * len(positions)
                    chosen_sequences = rng.choice(
                        len(sequences),
                        size=count,
                        replace=True,
                        p=probabilities,
                    )
                    inner_indexes = np.repeat(np.arange(inner, dtype=np.int32), len(positions))
                    tiled_positions = np.tile(positions, (inner, 1))
                    paths = tiled_positions[:, 0]
                    nodes = tiled_positions[:, 1]
                    for sequence_index, sequence in enumerate(sequences):
                        rows = np.flatnonzero(chosen_sequences == sequence_index)
                        if len(rows):
                            shared_left_results[
                                inner_indexes[rows],
                                paths[rows],
                                nodes[rows],
                                : len(sequence),
                            ] = sequence

    if np.any(shared_left_results[..., 0] < 0):
        raise MainConditionalTruthError("shared future Series sequences are incomplete")

    for team_index in range(len(outer.team_ids)):
        for opponent_index in range(len(outer.team_ids)):
            if opponent_index == team_index:
                continue
            p_game = model.predict(outer.team_ids[team_index], outer.team_ids[opponent_index])
            band = opponent_strength_band(p_game, config.opponent_probability_boundaries)
            for requested_result in (RESULT_CODE["loss"], RESULT_CODE["win"]):
                for requested_format in (FORMAT_CODE["bo3"], FORMAT_CODE["bo5"]):
                    base_mask = (
                        (base_team == team_index)
                        & (base_opponent == opponent_index)
                        & (base_result == requested_result)
                        & (format_by_node[None, :, None] == requested_format)
                    )
                    base_positions = np.argwhere(base_mask)
                    if not len(base_positions):
                        continue
                    count = inner * len(base_positions)
                    candidates, fallback = sampler.series_candidates(
                        team_index,
                        requested_format,
                        requested_result,
                        band,
                    )
                    chosen = _normalized_choice(
                        rng,
                        candidates,
                        templates.series_weights,
                        count,
                    ).astype(np.int32)
                    inner_indexes = np.repeat(np.arange(inner, dtype=np.int32), len(base_positions))
                    tiled_positions = np.tile(base_positions, (inner, 1))
                    paths = tiled_positions[:, 0]
                    nodes = tiled_positions[:, 1]
                    sides = tiled_positions[:, 2]
                    source_series[inner_indexes, paths, nodes, sides] = chosen.astype(np.int16)
                    fallback_levels[inner_indexes, paths, nodes, sides] = fallback
                    series_fallback_counts[fallback] += count
                    requested_context_counts[
                        f"{FORMAT_NAME[requested_format]}/{RESULT_NAME[requested_result]}/{BAND_NAME[band]}"
                    ] += count
                    for game_offset in range(MAX_SERIES_GAMES):
                        left_results = shared_left_results[
                            inner_indexes,
                            paths,
                            nodes,
                            game_offset,
                        ]
                        valid_rows = np.flatnonzero(left_results >= 0)
                        if not len(valid_rows):
                            continue
                        desired_results = np.where(
                            sides == 0,
                            left_results,
                            1 - left_results,
                        )
                        for desired_win in (0, 1):
                            selected_rows = valid_rows[desired_results[valid_rows] == desired_win]
                            if not len(selected_rows):
                                continue
                            selected_series = chosen[selected_rows]
                            for series_index in np.unique(selected_series):
                                rows = selected_rows[selected_series == series_index]
                                game_candidates, game_fallback = sampler.game_candidates(
                                    int(series_index), int(desired_win), band
                                )
                                selected_games = rng.choice(
                                    game_candidates,
                                    size=len(rows),
                                    replace=True,
                                ).astype(np.uint16)
                                game_ids[
                                    inner_indexes[rows],
                                    paths[rows],
                                    nodes[rows],
                                    sides[rows],
                                    game_offset,
                                ] = selected_games
                                game_fallback_counts[game_fallback] += len(rows)

    if np.any(source_series < 0) or np.any(fallback_levels == 255):
        raise MainConditionalTruthError("conditional draw panel has unfilled Series sides")
    valid_game_counts = (game_ids != GAME_TEMPLATE_SENTINEL).sum(axis=-1)
    expected_best_of = np.broadcast_to(format_by_node[None, None, :, None], shape)
    required_wins = expected_best_of // 2 + 1
    if np.any(valid_game_counts < required_wins) or np.any(valid_game_counts > expected_best_of):
        raise MainConditionalTruthError("conditional draw panel contains an illegal Series length")
    if not np.array_equal(valid_game_counts[..., 0], valid_game_counts[..., 1]):
        raise MainConditionalTruthError("future Series sides have inconsistent Game counts")
    referenced = game_ids[game_ids != GAME_TEMPLATE_SENTINEL].astype(np.int64)
    if np.any(referenced >= len(templates.scores)):
        raise MainConditionalTruthError("conditional draw panel references an unknown Game template")
    for side in range(SERIES_SIDE_COUNT):
        side_ids = game_ids[..., side, :]
        side_valid = side_ids != GAME_TEMPLATE_SENTINEL
        safe_side_ids = np.where(side_valid, side_ids, 0).astype(np.int64)
        expected_results = (
            shared_left_results
            if side == 0
            else np.where(shared_left_results < 0, -1, 1 - shared_left_results)
        )
        actual_results = templates.game_wins[safe_side_ids]
        if np.any(side_valid & (actual_results != expected_results)):
            raise MainConditionalTruthError("future Game templates do not match the shared Series results")
    audit = {
        "seed": int(seed),
        "inner_samples_per_path": inner,
        "outer_path_count": path_count,
        "series_side_draw_count": int(np.prod(shape)),
        "game_template_draw_count": int(len(referenced)),
        "shared_series_sequence_count": inner * path_count * SERIES_NODE_COUNT,
        "shared_series_lengths_validated": True,
        "opposite_team_game_results_validated": True,
        "series_fallback_counts": {str(key): value for key, value in sorted(series_fallback_counts.items())},
        "game_fallback_counts": {str(key): value for key, value in sorted(game_fallback_counts.items())},
        "requested_context_counts": dict(sorted(requested_context_counts.items())),
        "game_template_ids_sha256": _array_sha256(game_ids),
        "source_series_indexes_sha256": _array_sha256(source_series),
        "series_fallback_levels_sha256": _array_sha256(fallback_levels),
        "shared_left_game_results_sha256": _array_sha256(shared_left_results),
    }
    return ConditionalDrawResult(
        game_ids,
        source_series,
        fallback_levels,
        shared_left_results,
        audit,
    )


def _atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.npz")
    np.savez_compressed(temporary, **arrays)
    if path.is_file():
        with np.load(path, allow_pickle=False) as current:
            same_keys = set(current.files) == set(arrays)
            same_values = same_keys and all(
                np.array_equal(current[name], np.asarray(value)) for name, value in arrays.items()
            )
        temporary.unlink(missing_ok=True)
        if not same_values:
            raise MainConditionalTruthError(f"immutable truth array differs: {path}")
        return
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    if path.is_file():
        if path.read_text(encoding="utf-8") != content:
            raise MainConditionalTruthError(f"immutable truth JSON differs: {path}")
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _artifact_root(
    config: MainConditionalTruthConfig,
    *,
    snapshot_sha256: str,
    model_sha256: str,
    paths: ProjectPaths,
) -> Path:
    identity = sha256_json(
        {
            "config_sha256": config.semantic_hash,
            "snapshot_sha256": snapshot_sha256,
            "model_sha256": model_sha256,
            "source_tree_sha256": source_tree_hash(paths),
        }
    )
    return paths.artifacts / "research" / "main-conditional-truth" / f"{config.as_of[:10]}-{identity[:12]}"


def build_main_conditional_truth_evidence(
    config: MainConditionalTruthConfig,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    """Generate resumable, immutable research evidence without touching production pointers."""

    cutoff = as_utc(config.as_of)
    if cutoff is None:
        raise MainConditionalTruthError("conditional truth config has no explicit UTC as_of")
    evidence_paths = main_evidence_paths(paths, require=True)
    snapshot_manifest_path = evidence_paths.processed / "manifest.json"
    snapshot_manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
    if snapshot_manifest.get("as_of") != cutoff.isoformat().replace("+00:00", "Z"):
        raise MainConditionalTruthError("conditional truth as_of differs from the frozen Main snapshot")
    model, model_report = load_strength_model_as_of(
        as_of=cutoff,
        paths=evidence_paths,
        period="main",
    )
    blocking = [issue.message for issue in model_report.issues if issue.severity == "blocking"]
    if blocking:
        raise MainConditionalTruthError(
            "conditional truth Team-strength model is blocked: " + "; ".join(blocking)
        )
    model_sha256 = sha256_json(model.as_dict())
    snapshot_sha256 = str(snapshot_manifest["semantic_hash"])
    root = _artifact_root(
        config,
        snapshot_sha256=snapshot_sha256,
        model_sha256=model_sha256,
        paths=paths,
    )
    root.mkdir(parents=True, exist_ok=True)
    templates = build_joint_game_templates(
        as_of=cutoff,
        config=config,
        model=model,
        paths=evidence_paths,
    )
    outer = build_exact_main_outer_paths(templates.team_ids, model)
    _atomic_npz(
        root / "templates.npz",
        player_ids=templates.player_ids,
        scores=templates.scores,
        game_team_indexes=templates.game_team_indexes,
        game_series_indexes=templates.game_series_indexes,
        game_wins=templates.game_wins,
        game_bands=templates.game_bands,
        series_ids=templates.series_ids,
        series_team_indexes=templates.series_team_indexes,
        series_formats=templates.series_formats,
        series_results=templates.series_results,
        series_bands=templates.series_bands,
        series_weights=templates.series_weights,
        series_game_offsets=templates.series_game_offsets,
        series_game_ids=templates.series_game_ids,
    )
    _atomic_npz(
        root / "outer-paths.npz",
        participants=outer.participants,
        winners=outer.winners,
        probabilities=outer.probabilities,
    )
    _atomic_json(root / "pool-audit.json", dict(templates.audit))
    draw_audits = []
    for seed in config.seeds:
        draw_path = root / f"draws-{seed}.npz"
        audit_path = root / f"draws-{seed}-audit.json"
        if draw_path.is_file() and audit_path.is_file():
            draw_audits.append(json.loads(audit_path.read_text(encoding="utf-8")))
            continue
        result = generate_conditional_draws(templates, outer, model, config, seed=seed)
        _atomic_npz(
            draw_path,
            game_template_ids=result.game_template_ids,
            source_series_indexes=result.source_series_indexes,
            series_fallback_levels=result.series_fallback_levels,
            shared_left_game_results=result.shared_left_game_results,
        )
        _atomic_json(audit_path, dict(result.audit))
        draw_audits.append(dict(result.audit))
    provenance = {
        "source_version": source_version(paths),
        "source_tree_sha256": source_tree_hash(paths),
        "config_sha256": config.semantic_hash,
        "snapshot_manifest_sha256": sha256_file(snapshot_manifest_path),
        "snapshot_semantic_hash": snapshot_sha256,
        "model_sha256": model_sha256,
        "model_report_sha256": sha256_json(model_report.as_dict()),
        "rules_sha256": sha256_file(evidence_paths.rules),
        "tournament_manifest_sha256": sha256_file(evidence_paths.tournament),
        "template_semantic_hash": templates.semantic_hash,
        "outer_semantic_hash": outer.semantic_hash,
    }
    manifest = {
        "schema_version": 1,
        "artifact_type": "ti2026-main-conditional-truth-evidence",
        "status": "ready",
        "research_only": True,
        "web_integration": False,
        "runtime_pointer_writes": False,
        "as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "config": config.model_dump(mode="json"),
        "provenance": provenance,
        "team_ids": list(templates.team_ids),
        "stat_ids": list(templates.stat_ids),
        "outer_path_count": len(outer.probabilities),
        "inner_samples_per_path": config.inner_samples_per_path,
        "seed_count": len(config.seeds),
        "weighted_scenario_count": (
            len(outer.probabilities) * config.inner_samples_per_path * len(config.seeds)
        ),
        "draw_audits": draw_audits,
        "limitations": [
            "This is model-conditional offline reference evidence, not future observed truth.",
            (
                "Both Team sides share one Series length and opposite per-Game results; "
                "their five-player templates are resampled independently conditional on "
                "those results."
            ),
            (
                "Sparse Team/format/result/opponent-band cells use the frozen hierarchical "
                "fallback recorded per draw."
            ),
            "Coach Title effects are excluded from reference v1 and remain a separate recommendation.",
            "No file from this research artifact is selected by the Web or a runtime pointer.",
        ],
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    _atomic_json(root / "manifest.json", manifest)
    checksums = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "checksums.json"
    }
    _atomic_json(root / "checksums.json", checksums)
    return {**manifest, "artifact_path": str(root.resolve())}


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {name: np.asarray(payload[name]) for name in payload.files}


def _validate_artifact(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    checksums_path = root / "checksums.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed = manifest.pop("manifest_sha256", None)
    if claimed != sha256_json(manifest):
        raise MainConditionalTruthError("conditional truth manifest hash is invalid")
    manifest["manifest_sha256"] = claimed
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    for name, expected in checksums.items():
        candidate = root / name
        if not candidate.is_file() or sha256_file(candidate) != expected:
            raise MainConditionalTruthError(f"conditional truth artifact checksum failed: {name}")
    return manifest


def weighted_lower_tail_cvar(values: np.ndarray, weights: np.ndarray, alpha: float) -> float:
    numeric = np.asarray(values, dtype=float).reshape(-1)
    mass = np.asarray(weights, dtype=float).reshape(-1)
    if numeric.shape != mass.shape or not len(numeric):
        raise MainConditionalTruthError("weighted CVaR values and weights must align")
    if not np.isfinite(numeric).all() or not np.isfinite(mass).all() or np.any(mass < 0.0):
        raise MainConditionalTruthError("weighted CVaR input must be finite with nonnegative weights")
    if not 0.0 < alpha <= 1.0 or mass.sum() <= 0.0:
        raise MainConditionalTruthError("weighted CVaR alpha or total mass is invalid")
    mass = mass / mass.sum()
    order = np.argsort(numeric, kind="stable")
    sorted_values = numeric[order]
    sorted_mass = mass[order]
    remaining = float(alpha)
    total = 0.0
    for value, weight in zip(sorted_values, sorted_mass, strict=True):
        used = min(remaining, float(weight))
        total += used * float(value)
        remaining -= used
        if remaining <= 1e-15:
            break
    return total / alpha


def _state_banners(payload: Mapping[str, Any]) -> tuple[BannerState, ...]:
    if payload.get("period") != "main" or payload.get("slot_count") != 5:
        raise MainConditionalTruthError("conditional truth solve requires a five-slot Main state")
    banners = tuple(
        BannerState(
            role=str(row["role"]),
            emblems=tuple(
                EmblemState(
                    stat_id=str(item["stat_id"]),
                    quality_tier=int(item["quality_tier"]),
                    trait_id=str(item["trait_id"]),
                )
                for item in row["emblems"]
            ),
        )
        for row in payload["banners"]
    )
    if tuple(item.role for item in banners) != ROLE_IDS:
        raise MainConditionalTruthError("Main state Banners must follow core, mid, support order")
    return banners


def _template_role_values(
    scores: np.ndarray,
    stat_ids: tuple[str, ...],
    banner: BannerState,
    rules: dict[str, Any],
) -> np.ndarray:
    selected_stats, multipliers = _banner_score_inputs(
        banner,
        rules,
        slot_count=5,
        period_label="Main",
    )
    index = {stat_id: offset for offset, stat_id in enumerate(stat_ids)}
    selected = np.asarray([index[stat_id] for stat_id in selected_stats], dtype=np.int32)
    player_values = scores[:, :, selected] @ np.asarray(multipliers, dtype=np.float32)
    offsets = ROLE_PLAYER_OFFSETS[banner.role]
    return player_values[:, offsets].mean(axis=1, dtype=np.float32)


def _period_outcomes(
    game_template_ids: np.ndarray,
    participants: np.ndarray,
    template_values: np.ndarray,
    team_count: int,
) -> np.ndarray:
    valid = game_template_ids != GAME_TEMPLATE_SENTINEL
    safe_ids = np.where(valid, game_template_ids, 0).astype(np.int64)
    game_values = template_values[safe_ids]
    game_values = np.where(valid, game_values, 0.0)
    top_two = np.partition(game_values, -2, axis=-1)[..., -2:].sum(axis=-1)
    inner, path_count = top_two.shape[:2]
    period = np.zeros((team_count, inner, path_count), dtype=np.float32)
    for node in range(SERIES_NODE_COUNT):
        for side in range(SERIES_SIDE_COUNT):
            team_by_path = participants[:, node, side]
            values = top_two[:, :, node, side]
            for team_index in range(team_count):
                path_mask = team_by_path == team_index
                if np.any(path_mask):
                    team_period = period[team_index]
                    team_period[:, path_mask] = np.maximum(
                        team_period[:, path_mask],
                        values[:, path_mask],
                    )
    return period.reshape(team_count, inner * path_count)


def solve_main_conditional_truth(
    artifact_root: Path,
    state_path: Path,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    """Score one confirmed five-slot state against frozen conditional truth evidence."""

    root = artifact_root.resolve()
    manifest = _validate_artifact(root)
    config = MainConditionalTruthConfig.model_validate(manifest["config"])
    templates_payload = _load_npz(root / "templates.npz")
    outer_payload = _load_npz(root / "outer-paths.npz")
    scores = np.asarray(templates_payload["scores"], dtype=np.float32)
    participants = np.asarray(outer_payload["participants"], dtype=np.int16)
    path_probabilities = np.asarray(outer_payload["probabilities"], dtype=float)
    team_ids = tuple(int(value) for value in manifest["team_ids"])
    stat_ids = tuple(str(value) for value in manifest["stat_ids"])
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    banners = _state_banners(state_payload)
    rules = load_rules(paths.rules)
    role_template_values = {
        banner.role: _template_role_values(scores, stat_ids, banner, rules) for banner in banners
    }
    role_seed_outcomes: dict[str, list[np.ndarray]] = {role: [] for role in ROLE_IDS}
    seed_weights: list[np.ndarray] = []
    seed_reports: list[dict[str, Any]] = []
    for seed in config.seeds:
        draws = _load_npz(root / f"draws-{seed}.npz")
        game_ids = np.asarray(draws["game_template_ids"], dtype=np.uint16)
        inner = game_ids.shape[0]
        weights = np.tile(path_probabilities / inner, inner)
        seed_weights.append(weights)
        seed_role_means: dict[str, dict[str, float]] = {}
        seed_selected: dict[str, int] = {}
        for role in ROLE_IDS:
            outcomes = _period_outcomes(
                game_ids,
                participants,
                role_template_values[role],
                len(team_ids),
            )
            role_seed_outcomes[role].append(outcomes)
            means = outcomes @ weights
            seed_selected[role] = team_ids[int(np.argmax(means))]
            seed_role_means[role] = {
                str(team_id): float(means[index]) for index, team_id in enumerate(team_ids)
            }
        seed_reports.append(
            {
                "seed": seed,
                "selected_team_ids": [seed_selected[role] for role in ROLE_IDS],
                "role_team_means": seed_role_means,
            }
        )
    all_weights = np.concatenate(seed_weights) / len(config.seeds)
    role_outcomes = {role: np.concatenate(role_seed_outcomes[role], axis=1) for role in ROLE_IDS}
    role_rows: dict[str, list[dict[str, Any]]] = {}
    selected_indexes: dict[str, int] = {}
    maximum_mean = 0.0
    for role in ROLE_IDS:
        outcomes = role_outcomes[role]
        means = outcomes @ all_weights
        maximum_mean += float(means.max())
        rows = []
        for index, team_id in enumerate(team_ids):
            rows.append(
                {
                    "team_id": team_id,
                    "mean": float(means[index]),
                    "cvar10": weighted_lower_tail_cvar(outcomes[index], all_weights, config.cvar_alpha),
                }
            )
        rows.sort(key=lambda row: (-float(row["mean"]), -float(row["cvar10"]), int(row["team_id"])))
        role_rows[role] = rows
        selected_indexes[role] = team_ids.index(int(rows[0]["team_id"]))
    selected_team_ids = tuple(team_ids[selected_indexes[role]] for role in ROLE_IDS)
    total_outcomes = sum(
        (role_outcomes[role][selected_indexes[role]] for role in ROLE_IDS),
        start=np.zeros_like(all_weights),
    )
    result = {
        "schema_version": 1,
        "artifact_type": "ti2026-main-conditional-truth-state-solution",
        "status": "research-only",
        "as_of": manifest["as_of"],
        "evidence_manifest_sha256": manifest["manifest_sha256"],
        "state_path": str(state_path.resolve()),
        "state_sha256": sha256_file(state_path),
        "scenario_count": len(all_weights),
        "outer_path_count": len(path_probabilities),
        "inner_samples_per_path": config.inner_samples_per_path,
        "seeds": list(config.seeds),
        "selected_team_ids": list(selected_team_ids),
        "maximum_mean": maximum_mean,
        "summary": {
            "mean": float(np.dot(total_outcomes, all_weights)),
            "cvar10": weighted_lower_tail_cvar(total_outcomes, all_weights, config.cvar_alpha),
        },
        "role_rankings": role_rows,
        "seed_convergence": seed_reports,
        "coach_title": {
            "status": "excluded-from-reference-v1",
            "reason": "Title remains separate until player-level trigger simulation is independently frozen.",
        },
        "limitations": manifest["limitations"],
    }
    result["solution_sha256"] = sha256_json(result)
    solution_dir = root / "solutions"
    solution_path = solution_dir / f"{result['state_sha256'][:12]}.json"
    _atomic_json(solution_path, result)
    return {**result, "solution_path": str(solution_path.resolve())}


__all__ = [
    "ExactMainOuterPaths",
    "JointGameTemplateSet",
    "MainConditionalTruthConfig",
    "MainConditionalTruthError",
    "build_exact_main_outer_paths",
    "build_joint_game_templates",
    "build_main_conditional_truth_evidence",
    "generate_conditional_draws",
    "legal_series_sequences",
    "load_main_conditional_truth_config",
    "opponent_strength_band",
    "series_win_probability",
    "solve_main_conditional_truth",
    "weighted_lower_tail_cvar",
]
