"""Governed full-Series evidence blocks and common Group Fantasy scenarios."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from ti_predictor.fantasy.scoring import score_stat
from ti_predictor.hashing import sha256_bytes, sha256_json
from ti_predictor.schemas import StrictModel, TournamentManifest, as_utc
from ti_predictor.tournament.group import CATEGORY_CAPACITIES, CATEGORY_IDS

ROLE_IDS = ("core", "mid", "support")


class BootstrapScenarioPolicy(StrictModel):
    replicates: int = Field(gt=0)
    scenarios_per_replicate: int = Field(gt=0)
    confidence_level: float = Field(gt=0.0, lt=1.0)
    unit: Literal["full_series_block"]


class ScenarioRiskPolicy(StrictModel):
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    verified_mean_retention_epsilons: list[float]
    reserved_mean_retention_epsilons: list[float]

    @model_validator(mode="after")
    def validate_epsilons(self) -> ScenarioRiskPolicy:
        values = [*self.verified_mean_retention_epsilons, *self.reserved_mean_retention_epsilons]
        if any(value < 0.0 or value >= 1.0 for value in values):
            raise ValueError("mean-retention epsilons must be in [0, 1)")
        if len(values) != len(set(values)):
            raise ValueError("mean-retention epsilons must be unique")
        return self


class GroupScenarioPolicy(StrictModel):
    schema_version: Literal[1]
    policy_id: str = Field(min_length=1)
    period: Literal["group"]
    scenario_count: int = Field(gt=0)
    group_outcome_model: Literal["balanced_pairing"]
    group_category_series_counts: dict[str, int]
    historical_series_types: list[Literal[1, 3]]
    historical_series_formats: list[Literal["bo3", "bo2"]]
    minimum_games_per_series: Literal[2]
    maximum_games_per_series: Literal[3]
    minimum_series_blocks: int = Field(gt=0)
    require_all_rule_stats: Literal[True]
    allowed_provenance: list[Literal["exact", "derived"]]
    provenance_policy: Literal["must_match_current_stat_rule"]
    series_sampling: Literal["weighted_with_replacement"]
    series_weight: Literal["mean_game_evidence_weight"]
    role_sampling: Literal["independent_by_team_given_group_outcome"]
    coach_policy: Literal["validated_scenario_aligned_candidates_only"]
    production_coach_status: Literal["unavailable_excluded"]
    bootstrap: BootstrapScenarioPolicy
    risk: ScenarioRiskPolicy

    @model_validator(mode="after")
    def validate_contract(self) -> GroupScenarioPolicy:
        if tuple(self.group_category_series_counts) != CATEGORY_IDS:
            raise ValueError("Group category Series-count keys must follow the canonical category order")
        if set(self.allowed_provenance) != {"exact", "derived"}:
            raise ValueError("P3 permits only exact and derived rule provenance")
        if self.historical_series_types != [1, 3] or self.historical_series_formats != ["bo3", "bo2"]:
            raise ValueError("P3 historical Series support must be the frozen BO3-plus-BO2 set")
        if max(self.group_category_series_counts.values()) > 6:
            raise ValueError("P3 storage reserves at most six Group Series")
        return self


def load_group_scenario_policy(path: Path) -> GroupScenarioPolicy:
    return GroupScenarioPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _readonly_array(values: Any, *, dtype: str | np.dtype) -> np.ndarray:
    result = np.ascontiguousarray(values, dtype=dtype)
    result.setflags(write=False)
    return result


def _array_sha256(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values)
    header = json.dumps(
        {"dtype": canonical.dtype.str, "shape": canonical.shape},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return sha256_bytes(header + b"\0" + canonical.tobytes(order="C"))


@dataclass(frozen=True)
class SeriesBlock:
    target_team_id: int
    role: str
    player_ids: tuple[int, ...]
    historical_team_id: int
    series_id: int
    match_ids: tuple[int, ...]
    start_times: tuple[str, ...]
    evidence_weight: float
    stat_ids: tuple[str, ...]
    game_stat_scores: np.ndarray = field(repr=False, compare=False)
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        player_ids = tuple(int(value) for value in self.player_ids)
        match_ids = tuple(int(value) for value in self.match_ids)
        stat_ids = tuple(str(value) for value in self.stat_ids)
        scores = _readonly_array(self.game_stat_scores, dtype="<f8")
        object.__setattr__(self, "player_ids", player_ids)
        object.__setattr__(self, "match_ids", match_ids)
        object.__setattr__(self, "stat_ids", stat_ids)
        object.__setattr__(self, "game_stat_scores", scores)
        if self.role not in ROLE_IDS:
            raise ValueError(f"unknown Fantasy role: {self.role}")
        expected_players = 1 if self.role == "mid" else 2
        if len(player_ids) != expected_players or len(set(player_ids)) != len(player_ids):
            raise ValueError(f"{self.role} Series block requires {expected_players} stable player IDs")
        if len(match_ids) not in {2, 3} or len(set(match_ids)) != len(match_ids):
            raise ValueError("a Group Series block must contain two or three unique Games")
        if len(self.start_times) != len(match_ids):
            raise ValueError("Series block timestamps must align with Games")
        if scores.shape != (len(match_ids), len(stat_ids)):
            raise ValueError("Series block score matrix does not align with Games and Stats")
        if not np.isfinite(scores).all():
            raise ValueError("Series block score matrix must be complete and finite")
        if self.evidence_weight <= 0.0 or not np.isfinite(self.evidence_weight):
            raise ValueError("Series block evidence weight must be positive and finite")
        payload = {
            "target_team_id": int(self.target_team_id),
            "role": self.role,
            "player_ids": player_ids,
            "historical_team_id": int(self.historical_team_id),
            "series_id": int(self.series_id),
            "match_ids": match_ids,
            "start_times": tuple(self.start_times),
            "evidence_weight": float(self.evidence_weight),
            "stat_ids": stat_ids,
            "scores_sha256": _array_sha256(scores),
        }
        object.__setattr__(self, "semantic_hash", sha256_json(payload))


@dataclass(frozen=True)
class SeriesBlockPool:
    target_team_id: int
    role: str
    player_ids: tuple[int, ...]
    stat_ids: tuple[str, ...]
    blocks: tuple[SeriesBlock, ...]
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        blocks = tuple(self.blocks)
        object.__setattr__(self, "blocks", blocks)
        if not blocks:
            raise ValueError("a Series block pool cannot be empty")
        if any(
            block.target_team_id != self.target_team_id
            or block.role != self.role
            or block.player_ids != tuple(self.player_ids)
            or block.stat_ids != tuple(self.stat_ids)
            for block in blocks
        ):
            raise ValueError("Series block pool contains a block with mismatched identity or schema")
        if tuple(block.series_id for block in blocks) != tuple(sorted(block.series_id for block in blocks)):
            raise ValueError("Series block pools must be ordered by stable Series ID")
        if len({block.series_id for block in blocks}) != len(blocks):
            raise ValueError("Series block pools cannot repeat a stable Series ID")
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "target_team_id": int(self.target_team_id),
                    "role": self.role,
                    "player_ids": tuple(self.player_ids),
                    "stat_ids": tuple(self.stat_ids),
                    "blocks": [block.semantic_hash for block in blocks],
                }
            ),
        )

    @property
    def weights(self) -> np.ndarray:
        values = np.asarray([block.evidence_weight for block in self.blocks], dtype=float)
        return values / values.sum()


@dataclass(frozen=True)
class PoolBuildResult:
    pools: tuple[SeriesBlockPool, ...]
    audit: dict[str, Any]
    semantic_hash: str

    def by_key(self) -> dict[tuple[int, str], SeriesBlockPool]:
        return {(pool.target_team_id, pool.role): pool for pool in self.pools}


def _stat_coverage(
    observations: pd.DataFrame,
    stat_ids: tuple[str, ...],
    rules: dict[str, Any],
) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for stat_id in stat_ids:
        provenance_column = f"{stat_id}_provenance"
        expected = str(rules["fantasy"]["stats"][stat_id]["provenance"])
        if stat_id not in observations or provenance_column not in observations:
            matching = pd.Series(False, index=observations.index)
        else:
            matching = (
                observations[provenance_column].eq(expected)
                & pd.to_numeric(observations[stat_id], errors="coerce").notna()
            )
        result[stat_id] = {
            "expected_provenance": expected,
            "complete_rows": int(matching.sum()),
            "eligible_rows": int(len(observations)),
            "coverage": float(matching.mean()) if len(matching) else 0.0,
        }
    return result


def build_series_block_pools(
    observations: pd.DataFrame,
    matches: pd.DataFrame,
    evidence_games: pd.DataFrame,
    manifest: TournamentManifest,
    rules: dict[str, Any],
    policy: GroupScenarioPolicy,
    *,
    as_of,
) -> PoolBuildResult:
    """Build one indivisible BO3 Series pool for each current Team and Fantasy role."""

    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    if manifest.roster_valid_from > cutoff:
        raise ValueError("the reviewed tournament roster is not effective at as_of")
    required_match_columns = {"match_id", "series_id", "series_type", "start_time"}
    required_observation_columns = {"match_id", "account_id", "team_id", "start_time"}
    required_evidence_columns = {"match_id", "evidence_weight"}
    for label, frame, required in (
        ("match", matches, required_match_columns),
        ("Fantasy observation", observations, required_observation_columns),
        ("evidence", evidence_games, required_evidence_columns),
    ):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{label} data is missing required columns: {sorted(missing)}")

    stat_ids = tuple(rules["fantasy"]["stats"])
    for stat_id in stat_ids:
        expected = str(rules["fantasy"]["stats"][stat_id]["provenance"])
        if expected not in policy.allowed_provenance:
            raise ValueError(f"Stat {stat_id} has disallowed formal provenance {expected!r}")

    availability_columns = [column for column in ("as_of", "fetched_at") if column in matches.columns]
    match_frame = matches[[*required_match_columns, *availability_columns]].copy()
    match_frame["start_time"] = pd.to_datetime(match_frame["start_time"], utc=True, errors="coerce")
    match_frame["_available_by_cutoff"] = True
    for column in availability_columns:
        timestamp = pd.to_datetime(match_frame[column], utc=True, errors="coerce")
        match_frame["_available_by_cutoff"] &= timestamp.notna() & (timestamp <= pd.Timestamp(cutoff))
    if match_frame["match_id"].duplicated().any():
        raise ValueError("match data contains duplicate stable match IDs")
    weights = evidence_games[["match_id", "evidence_weight"]].copy()
    if weights["match_id"].duplicated().any():
        raise ValueError("evidence data contains duplicate stable match IDs")
    weights["evidence_weight"] = pd.to_numeric(weights["evidence_weight"], errors="coerce").fillna(0.0)
    match_frame = match_frame.merge(weights, on="match_id", how="left")
    match_frame["evidence_weight"] = match_frame["evidence_weight"].fillna(0.0)
    available_by_cutoff = match_frame["_available_by_cutoff"].astype(bool)

    valid_time = (
        match_frame["start_time"].notna()
        & (match_frame["start_time"] < pd.Timestamp(cutoff))
        & available_by_cutoff
    )
    positive = match_frame["evidence_weight"].gt(0.0)
    accepted_format = match_frame["series_type"].isin(policy.historical_series_types)
    has_series = match_frame["series_id"].notna()
    eligible_matches = match_frame.loc[valid_time & positive & accepted_format & has_series].copy()
    eligible_matches["match_id"] = eligible_matches["match_id"].astype(int)
    eligible_matches["series_id"] = eligible_matches["series_id"].astype(int)
    eligible_matches = eligible_matches.sort_values(["series_id", "start_time", "match_id"], kind="stable")

    series_games: dict[int, pd.DataFrame] = {}
    structurally_complete = 0
    structurally_incomplete = 0
    for series_id, games in eligible_matches.groupby("series_id", sort=True):
        one_format = games["series_type"].nunique(dropna=False) == 1
        if one_format and policy.minimum_games_per_series <= len(games) <= policy.maximum_games_per_series:
            series_games[int(series_id)] = games.copy()
            structurally_complete += 1
        else:
            structurally_incomplete += 1

    observation_frame = observations.copy()
    observation_frame["start_time"] = pd.to_datetime(
        observation_frame["start_time"], utc=True, errors="coerce"
    )
    observation_available = pd.Series(True, index=observation_frame.index, dtype=bool)
    if "as_of" in observation_frame:
        observation_as_of = pd.to_datetime(observation_frame["as_of"], utc=True, errors="coerce")
        observation_available &= observation_as_of.notna() & (observation_as_of <= pd.Timestamp(cutoff))
    observation_frame = observation_frame.loc[
        observation_frame["start_time"].notna()
        & (observation_frame["start_time"] < pd.Timestamp(cutoff))
        & observation_available
        & observation_frame["match_id"].isin(eligible_matches["match_id"])
    ].copy()
    if observation_frame.duplicated(["match_id", "account_id"]).any():
        raise ValueError("Fantasy observations contain duplicate (match_id, account_id) identities")
    observation_frame["match_id"] = observation_frame["match_id"].astype(int)
    observation_frame["account_id"] = observation_frame["account_id"].astype(int)

    target_player_ids = {
        int(player.account_id)
        for team in manifest.teams
        for players in team.players.values()
        for player in players
    }
    target_rows = observation_frame.loc[observation_frame["account_id"].isin(target_player_ids)]
    coverage = _stat_coverage(target_rows, stat_ids, rules)
    observation_by_match = {
        int(match_id): rows.set_index("account_id", drop=False)
        for match_id, rows in observation_frame.groupby("match_id", sort=False)
    }

    pools: list[SeriesBlockPool] = []
    pool_audit: list[dict[str, Any]] = []
    rejection_totals = {
        "missing_required_player_game": 0,
        "cross_team_pair_or_series": 0,
        "missing_or_wrong_provenance": 0,
    }
    for team in manifest.teams:
        for role in ROLE_IDS:
            player_ids = tuple(int(player.account_id) for player in team.players[role])
            blocks: list[SeriesBlock] = []
            rejected = {name: 0 for name in rejection_totals}
            for series_id, games in series_games.items():
                rows_by_game: list[pd.DataFrame] = []
                historical_team_ids: list[int] = []
                missing_players = False
                cross_team = False
                for match_id in games["match_id"]:
                    indexed = observation_by_match.get(int(match_id))
                    if indexed is None or any(player_id not in indexed.index for player_id in player_ids):
                        missing_players = True
                        break
                    selected = indexed.loc[list(player_ids)]
                    if isinstance(selected, pd.Series):
                        selected = selected.to_frame().T
                    team_values = pd.to_numeric(selected["team_id"], errors="coerce")
                    if team_values.isna().any() or team_values.nunique() != 1:
                        cross_team = True
                        break
                    historical_team_ids.append(int(team_values.iloc[0]))
                    rows_by_game.append(selected)
                if missing_players:
                    rejected["missing_required_player_game"] += 1
                    continue
                if cross_team or len(set(historical_team_ids)) != 1:
                    rejected["cross_team_pair_or_series"] += 1
                    continue

                game_scores: list[list[float]] = []
                invalid_stat = False
                for selected in rows_by_game:
                    per_stat: list[float] = []
                    for stat_id in stat_ids:
                        rule = rules["fantasy"]["stats"][stat_id]
                        provenance_column = f"{stat_id}_provenance"
                        if stat_id not in selected or provenance_column not in selected:
                            invalid_stat = True
                            break
                        numeric = pd.to_numeric(selected[stat_id], errors="coerce")
                        if (
                            numeric.isna().any()
                            or not selected[provenance_column].eq(rule["provenance"]).all()
                        ):
                            invalid_stat = True
                            break
                        player_scores = [score_stat(float(value), rule) for value in numeric]
                        if any(value is None for value in player_scores):
                            invalid_stat = True
                            break
                        per_stat.append(float(np.mean(player_scores)))
                    if invalid_stat:
                        break
                    game_scores.append(per_stat)
                if invalid_stat:
                    rejected["missing_or_wrong_provenance"] += 1
                    continue

                blocks.append(
                    SeriesBlock(
                        target_team_id=int(team.team_id),
                        role=role,
                        player_ids=player_ids,
                        historical_team_id=historical_team_ids[0],
                        series_id=series_id,
                        match_ids=tuple(int(value) for value in games["match_id"]),
                        start_times=tuple(
                            value.isoformat().replace("+00:00", "Z") for value in games["start_time"]
                        ),
                        evidence_weight=float(games["evidence_weight"].mean()),
                        stat_ids=stat_ids,
                        game_stat_scores=np.asarray(game_scores, dtype=float),
                    )
                )
            blocks.sort(key=lambda block: block.series_id)
            if len(blocks) < policy.minimum_series_blocks:
                raise ValueError(
                    f"Team {team.team_id} {role} has {len(blocks)} complete Series blocks; "
                    f"policy requires {policy.minimum_series_blocks}"
                )
            pool = SeriesBlockPool(
                target_team_id=int(team.team_id),
                role=role,
                player_ids=player_ids,
                stat_ids=stat_ids,
                blocks=tuple(blocks),
            )
            pools.append(pool)
            for name, count in rejected.items():
                rejection_totals[name] += count
            pool_audit.append(
                {
                    "target_team_id": int(team.team_id),
                    "role": role,
                    "player_ids": list(player_ids),
                    "complete_series_blocks": len(blocks),
                    "effective_series_weight": float(sum(block.evidence_weight for block in blocks)),
                    "rejected_series": rejected,
                    "pool_sha256": pool.semantic_hash,
                }
            )

    pools.sort(key=lambda pool: (pool.target_team_id, ROLE_IDS.index(pool.role)))
    pool_hash = sha256_json([pool.semantic_hash for pool in pools])
    audit = {
        "policy_id": policy.policy_id,
        "as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "formal_stat_ids": list(stat_ids),
        "positive_weight_games": int((valid_time & positive).sum()),
        "games_unavailable_at_as_of": int((~available_by_cutoff).sum()),
        "positive_weight_excluded_series_format_games": int((valid_time & positive & ~accepted_format).sum()),
        "eligible_bo2_or_bo3_games": int(len(eligible_matches)),
        "structurally_complete_bo2_or_bo3_series": structurally_complete,
        "structurally_incomplete_or_mixed_series": structurally_incomplete,
        "target_player_rows": int(len(target_rows)),
        "observations_unavailable_at_as_of": int((~observation_available).sum()),
        "stat_provenance_coverage": coverage,
        "rejection_totals_across_team_roles": rejection_totals,
        "pool_count": len(pools),
        "minimum_complete_series_blocks": min(len(pool.blocks) for pool in pools),
        "maximum_complete_series_blocks": max(len(pool.blocks) for pool in pools),
        "pools": pool_audit,
        "pool_set_sha256": pool_hash,
    }
    return PoolBuildResult(pools=tuple(pools), audit=audit, semantic_hash=pool_hash)


@dataclass(frozen=True)
class ScenarioDraws:
    target_team_id: int
    role: str
    pool_sha256: str
    block_indexes: np.ndarray = field(repr=False, compare=False)
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        indexes = _readonly_array(self.block_indexes, dtype="<i4")
        object.__setattr__(self, "block_indexes", indexes)
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "target_team_id": int(self.target_team_id),
                    "role": self.role,
                    "pool_sha256": self.pool_sha256,
                    "indexes_sha256": _array_sha256(indexes),
                }
            ),
        )


@dataclass(frozen=True)
class CommonScenarioSet:
    policy_id: str
    data_snapshot_sha256: str
    as_of: str
    seed: int
    team_ids: tuple[int, ...]
    scenario_ids: np.ndarray = field(repr=False, compare=False)
    group_categories: np.ndarray = field(repr=False, compare=False)
    series_counts: np.ndarray = field(repr=False, compare=False)
    draws: tuple[ScenarioDraws, ...] = field(repr=False, compare=False)
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        scenario_ids = _readonly_array(self.scenario_ids, dtype="<i8")
        categories = _readonly_array(self.group_categories, dtype="<i1")
        series_counts = _readonly_array(self.series_counts, dtype="<i1")
        draws = tuple(self.draws)
        object.__setattr__(self, "scenario_ids", scenario_ids)
        object.__setattr__(self, "group_categories", categories)
        object.__setattr__(self, "series_counts", series_counts)
        object.__setattr__(self, "draws", draws)
        expected_shape = (len(scenario_ids), len(self.team_ids))
        if categories.shape != expected_shape or series_counts.shape != expected_shape:
            raise ValueError("Group categories and Series counts must align with scenario and Team IDs")
        for category, expected in enumerate(CATEGORY_CAPACITIES):
            if not np.all((categories == category).sum(axis=1) == expected):
                raise ValueError(f"Group category {CATEGORY_IDS[category]} violates capacity {int(expected)}")
        if not np.array_equal(scenario_ids, np.arange(len(scenario_ids), dtype=np.int64)):
            raise ValueError("common Scenario IDs must be a contiguous stable zero-based sequence")
        keys = [(item.target_team_id, item.role) for item in draws]
        expected_keys = [(team_id, role) for team_id in self.team_ids for role in ROLE_IDS]
        if keys != expected_keys:
            raise ValueError("Scenario draws must contain every Team/role in canonical order")
        max_series = int(series_counts.max())
        if any(item.block_indexes.shape != (len(scenario_ids), max_series) for item in draws):
            raise ValueError("Scenario block references must align with all Scenario IDs and Series slots")
        payload = {
            "policy_id": self.policy_id,
            "data_snapshot_sha256": self.data_snapshot_sha256,
            "as_of": self.as_of,
            "seed": int(self.seed),
            "team_ids": self.team_ids,
            "scenario_ids_sha256": _array_sha256(scenario_ids),
            "group_categories_sha256": _array_sha256(categories),
            "series_counts_sha256": _array_sha256(series_counts),
            "draws": [item.semantic_hash for item in draws],
        }
        object.__setattr__(self, "semantic_hash", sha256_json(payload))

    def draw_record_for(self, team_id: int, role: str) -> ScenarioDraws:
        for item in self.draws:
            if item.target_team_id == team_id and item.role == role:
                return item
        raise KeyError(f"no common Scenario draws for Team {team_id}, role {role}")

    def draws_for(self, team_id: int, role: str) -> np.ndarray:
        return self.draw_record_for(team_id, role).block_indexes


def _stream_seed(seed: int, team_id: int, role: str, purpose: str) -> int:
    digest = hashlib.sha256(f"{seed}:{team_id}:{role}:{purpose}".encode()).digest()
    return int.from_bytes(digest[:8], "little", signed=False)


def build_common_scenario_set(
    pool_result: PoolBuildResult,
    *,
    group_team_ids: np.ndarray,
    group_outcomes: np.ndarray,
    policy: GroupScenarioPolicy,
    data_snapshot_sha256: str,
    as_of,
    seed: int,
) -> CommonScenarioSet:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    team_ids = tuple(int(value) for value in np.asarray(group_team_ids).tolist())
    if len(team_ids) != 16 or len(set(team_ids)) != 16:
        raise ValueError("Group Fantasy scenarios require sixteen unique stable Team IDs")
    if len(data_snapshot_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in data_snapshot_sha256
    ):
        raise ValueError("common Scenario set requires a lowercase data snapshot SHA-256")
    outcomes = np.asarray(group_outcomes, dtype=np.int8)
    if outcomes.shape != (policy.scenario_count, len(team_ids)):
        raise ValueError("Group outcome matrix does not match the configured common Scenario count")
    if outcomes.min() < 0 or outcomes.max() >= len(CATEGORY_IDS):
        raise ValueError("Group outcome matrix contains an unknown category")
    series_by_category = np.asarray(
        [policy.group_category_series_counts[category] for category in CATEGORY_IDS], dtype=np.int8
    )
    series_counts = series_by_category[outcomes]
    max_series = int(series_counts.max())
    pool_by_key = pool_result.by_key()
    draws: list[ScenarioDraws] = []
    for team_index, team_id in enumerate(team_ids):
        for role in ROLE_IDS:
            try:
                pool = pool_by_key[(team_id, role)]
            except KeyError as error:
                raise ValueError(f"missing Series block pool for Team {team_id}, role {role}") from error
            rng = np.random.default_rng(_stream_seed(seed, team_id, role, "predictive-series"))
            indexes = rng.choice(
                len(pool.blocks),
                size=(policy.scenario_count, max_series),
                replace=True,
                p=pool.weights,
            ).astype(np.int32)
            unused = np.arange(max_series)[None, :] >= series_counts[:, team_index, None]
            indexes[unused] = -1
            draws.append(
                ScenarioDraws(
                    target_team_id=team_id,
                    role=role,
                    pool_sha256=pool.semantic_hash,
                    block_indexes=indexes,
                )
            )
    return CommonScenarioSet(
        policy_id=policy.policy_id,
        data_snapshot_sha256=data_snapshot_sha256,
        as_of=cutoff.isoformat().replace("+00:00", "Z"),
        seed=seed,
        team_ids=team_ids,
        scenario_ids=np.arange(policy.scenario_count, dtype=np.int64),
        group_categories=outcomes,
        series_counts=series_counts,
        draws=tuple(draws),
    )
