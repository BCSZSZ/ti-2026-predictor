"""Exact Group Fantasy terminal arithmetic over common full-Series scenarios."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from itertools import product
from typing import Any

import numpy as np

from ti_predictor.fantasy.roll import BannerState
from ti_predictor.fantasy.scenarios import (
    ROLE_IDS,
    CommonScenarioSet,
    GroupScenarioPolicy,
    PoolBuildResult,
    SeriesBlock,
    SeriesBlockPool,
)
from ti_predictor.fantasy.scoring import Emblem, emblem_multipliers
from ti_predictor.hashing import sha256_bytes, sha256_json


def _readonly_array(values: Any, *, dtype: str | np.dtype = "<f8") -> np.ndarray:
    result = np.ascontiguousarray(values, dtype=dtype)
    result.setflags(write=False)
    return result


def _array_sha256(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values)
    header = f"{canonical.dtype.str}:{','.join(str(value) for value in canonical.shape)}".encode()
    return sha256_bytes(header + b"\0" + canonical.tobytes(order="C"))


def lower_tail_cvar(values: np.ndarray, alpha: float = 0.1) -> float:
    """Average the worst ``alpha`` mass, including a deterministic fractional boundary."""

    numeric = np.asarray(values, dtype=float).reshape(-1)
    if not len(numeric) or not np.isfinite(numeric).all():
        raise ValueError("CVaR values must be a non-empty finite vector")
    if alpha <= 0.0 or alpha > 1.0:
        raise ValueError("CVaR alpha must be in (0, 1]")
    mass = alpha * len(numeric)
    whole = int(np.floor(mass))
    fraction = mass - whole
    if whole == len(numeric):
        return float(numeric.mean())
    boundary_index = whole if fraction > 0.0 else whole - 1
    partitioned = np.partition(numeric, boundary_index)
    total = float(partitioned[:whole].sum())
    if fraction > 0.0:
        total += fraction * float(partitioned[whole])
    return total / mass


def distribution_summary(values: np.ndarray, *, cvar_alpha: float) -> dict[str, float]:
    numeric = np.asarray(values, dtype=float)
    return {
        "mean": float(numeric.mean()),
        "cvar": lower_tail_cvar(numeric, cvar_alpha),
        "p10": float(np.quantile(numeric, 0.1)),
        "p50": float(np.quantile(numeric, 0.5)),
        "p90": float(np.quantile(numeric, 0.9)),
        "minimum": float(numeric.min()),
        "maximum": float(numeric.max()),
    }


@dataclass(frozen=True)
class RiskConfiguration:
    mean_retention_epsilon: float = 0.0
    cvar_alpha: float = 0.1

    def __post_init__(self) -> None:
        if self.mean_retention_epsilon < 0.0 or self.mean_retention_epsilon >= 1.0:
            raise ValueError("mean-retention epsilon must be in [0, 1)")
        if self.cvar_alpha <= 0.0 or self.cvar_alpha > 1.0:
            raise ValueError("CVaR alpha must be in (0, 1]")

    @property
    def semantic_hash(self) -> str:
        return sha256_json(
            {
                "mean_retention_epsilon": self.mean_retention_epsilon,
                "cvar_alpha": self.cvar_alpha,
            }
        )


@dataclass(frozen=True)
class CoachTeamRoleMultipliers:
    target_team_id: int
    role: str
    values: np.ndarray = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        values = _readonly_array(self.values)
        object.__setattr__(self, "values", values)
        if values.ndim != 3 or values.shape[2] != 3:
            raise ValueError("Coach multipliers must have shape (Scenario, Series slot, three Games)")
        if not np.isfinite(values).all() or np.any(values <= 0.0):
            raise ValueError("Coach multipliers must be positive and finite")


@dataclass(frozen=True)
class ValidatedCoachScenario:
    candidate_id: str
    scenario_sha256: str
    entries: tuple[CoachTeamRoleMultipliers, ...]
    evidence_sha256: str

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        object.__setattr__(self, "entries", entries)
        keys = [(entry.target_team_id, entry.role) for entry in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("validated Coach Scenario contains duplicate Team/role entries")
        if len(self.evidence_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.evidence_sha256
        ):
            raise ValueError("validated Coach Scenario requires an evidence SHA-256")

    def values_for(self, team_id: int, role: str) -> np.ndarray:
        for entry in self.entries:
            if entry.target_team_id == team_id and entry.role == role:
                return entry.values
        raise KeyError(f"validated Coach Scenario lacks Team {team_id}, role {role}")

    @property
    def semantic_hash(self) -> str:
        return sha256_json(
            {
                "candidate_id": self.candidate_id,
                "scenario_sha256": self.scenario_sha256,
                "evidence_sha256": self.evidence_sha256,
                "entries": [
                    {
                        "team_id": entry.target_team_id,
                        "role": entry.role,
                        "values_sha256": _array_sha256(entry.values),
                    }
                    for entry in self.entries
                ],
            }
        )


def score_series_block(
    block: SeriesBlock,
    *,
    stat_indexes: tuple[int, ...],
    emblem_score_multipliers: tuple[float, ...],
    coach_game_multipliers: np.ndarray | None = None,
) -> float:
    if len(stat_indexes) != len(emblem_score_multipliers):
        raise ValueError("Stat indexes and Emblem multipliers must align")
    game_scores = block.game_stat_scores[:, stat_indexes] @ np.asarray(emblem_score_multipliers, dtype=float)
    if coach_game_multipliers is not None:
        coach = np.asarray(coach_game_multipliers, dtype=float)
        if coach.shape != (len(block.match_ids),):
            raise ValueError("Coach multipliers must align with the played Games in the Series block")
        if not np.isfinite(coach).all() or np.any(coach <= 0.0):
            raise ValueError("Coach multipliers must be positive and finite")
        game_scores = game_scores * coach
    return float(np.sort(game_scores, kind="stable")[-2:].sum())


def _pool_stat_indexes(pool: SeriesBlockPool, stat_ids: tuple[str, ...]) -> tuple[int, ...]:
    index = {stat_id: offset for offset, stat_id in enumerate(pool.stat_ids)}
    try:
        return tuple(index[stat_id] for stat_id in stat_ids)
    except KeyError as error:
        raise ValueError(f"Series block pool does not contain Stat {error.args[0]}") from error


def _period_outcomes_for_pool(
    pool: SeriesBlockPool,
    scenario_set: CommonScenarioSet,
    *,
    stat_indexes: tuple[int, ...],
    score_multipliers: tuple[float, ...],
    coach_values: np.ndarray | None,
) -> np.ndarray:
    draw_record = scenario_set.draw_record_for(pool.target_team_id, pool.role)
    if draw_record.pool_sha256 != pool.semantic_hash:
        raise ValueError("common Scenario block references do not match the supplied Series pool")
    draws = draw_record.block_indexes
    if coach_values is None:
        block_values = np.asarray(
            [
                score_series_block(
                    block,
                    stat_indexes=stat_indexes,
                    emblem_score_multipliers=score_multipliers,
                )
                for block in pool.blocks
            ],
            dtype=float,
        )
        sampled = np.full(draws.shape, -np.inf, dtype=float)
        used = draws >= 0
        sampled[used] = block_values[draws[used]]
        return sampled.max(axis=1)

    expected_shape = (*draws.shape, 3)
    if coach_values.shape != expected_shape:
        raise ValueError(
            f"Coach Scenario for Team {pool.target_team_id}, role {pool.role} has "
            f"shape {coach_values.shape}, expected {expected_shape}"
        )
    outcomes = np.full(len(draws), -np.inf, dtype=float)
    for scenario_index in range(len(draws)):
        best = -np.inf
        for series_slot, block_index in enumerate(draws[scenario_index]):
            if block_index < 0:
                continue
            block = pool.blocks[int(block_index)]
            value = score_series_block(
                block,
                stat_indexes=stat_indexes,
                emblem_score_multipliers=score_multipliers,
                coach_game_multipliers=coach_values[scenario_index, series_slot, : len(block.match_ids)],
            )
            best = max(best, value)
        outcomes[scenario_index] = best
    return outcomes


@dataclass(frozen=True)
class TeamOutcomeMatrix:
    kind: str
    item_id: str
    role: str
    scenario_sha256: str
    team_ids: tuple[int, ...]
    outcomes: np.ndarray = field(repr=False, compare=False)
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        outcomes = _readonly_array(self.outcomes)
        object.__setattr__(self, "outcomes", outcomes)
        if outcomes.shape[0] != len(self.team_ids) or outcomes.ndim != 2:
            raise ValueError("Team outcome matrix must align with Team IDs")
        if not np.isfinite(outcomes).all():
            raise ValueError("Team outcome matrix must be complete and finite")
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "kind": self.kind,
                    "item_id": self.item_id,
                    "role": self.role,
                    "scenario_sha256": self.scenario_sha256,
                    "team_ids": self.team_ids,
                    "outcomes_sha256": _array_sha256(outcomes),
                }
            ),
        )


def _pool_map(pool_result: PoolBuildResult) -> dict[tuple[int, str], SeriesBlockPool]:
    result = pool_result.by_key()
    if len(result) != len(pool_result.pools):
        raise ValueError("Series block pools contain duplicate Team/role keys")
    return result


def evaluate_stat_teams(
    pool_result: PoolBuildResult,
    scenario_set: CommonScenarioSet,
    *,
    role: str,
    stat_id: str,
) -> TeamOutcomeMatrix:
    pools = _pool_map(pool_result)
    rows: list[np.ndarray] = []
    team_ids = tuple(team_id for team_id in scenario_set.team_ids if (team_id, role) in pools)
    if not team_ids:
        raise ValueError(f"no Fantasy Team is available for role {role}")
    for team_id in team_ids:
        pool = pools[(team_id, role)]
        stat_indexes = _pool_stat_indexes(pool, (stat_id,))
        rows.append(
            _period_outcomes_for_pool(
                pool,
                scenario_set,
                stat_indexes=stat_indexes,
                score_multipliers=(1.0,),
                coach_values=None,
            )
        )
    return TeamOutcomeMatrix(
        kind="stat",
        item_id=stat_id,
        role=role,
        scenario_sha256=scenario_set.semantic_hash,
        team_ids=team_ids,
        outcomes=np.stack(rows),
    )


def _banner_identity(banner: BannerState) -> str:
    emblems = ";".join(
        f"{emblem.stat_id}:T{emblem.quality_tier}:{emblem.trait_id}" for emblem in banner.emblems
    )
    return f"{banner.role}|{emblems}"


def _banner_score_inputs(
    banner: BannerState,
    rules: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    if banner.role not in ROLE_IDS:
        raise ValueError(f"unknown Fantasy role: {banner.role}")
    colors = tuple(rules["fantasy"]["role_banners"][banner.role][:3])
    if len(banner.emblems) != 3:
        raise ValueError("P3 Group valuation requires exactly three Emblems")
    legal_traits = {str(item["id"]) for item in rules["fantasy"]["traits"]}
    emblems: list[Emblem] = []
    for state, expected_color in zip(banner.emblems, colors, strict=True):
        try:
            actual_color = str(rules["fantasy"]["stats"][state.stat_id]["color"])
        except KeyError as error:
            raise ValueError(f"unknown Fantasy Stat: {state.stat_id}") from error
        if actual_color != expected_color:
            raise ValueError(
                f"{banner.role} slot expects {expected_color}, but {state.stat_id} is {actual_color}"
            )
        if state.trait_id not in legal_traits:
            raise ValueError(f"unknown Fantasy Trait: {state.trait_id}")
        emblems.append(
            Emblem(
                stat_id=state.stat_id,
                color=actual_color,
                quality_tier=state.quality_tier,
                trait=state.trait_id,
            )
        )
    return tuple(emblem.stat_id for emblem in emblems), tuple(emblem_multipliers(emblems, rules))


def evaluate_banner_teams(
    pool_result: PoolBuildResult,
    scenario_set: CommonScenarioSet,
    banner: BannerState,
    rules: dict[str, Any],
    *,
    coach: ValidatedCoachScenario | None = None,
) -> TeamOutcomeMatrix:
    if coach is not None and coach.scenario_sha256 != scenario_set.semantic_hash:
        raise ValueError("validated Coach candidate is not aligned to the common Scenario set")
    pools = _pool_map(pool_result)
    stat_ids, multipliers = _banner_score_inputs(banner, rules)
    rows: list[np.ndarray] = []
    team_ids = tuple(team_id for team_id in scenario_set.team_ids if (team_id, banner.role) in pools)
    if not team_ids:
        raise ValueError(f"no Fantasy Team is available for role {banner.role}")
    for team_id in team_ids:
        pool = pools[(team_id, banner.role)]
        coach_values = None if coach is None else coach.values_for(team_id, banner.role)
        rows.append(
            _period_outcomes_for_pool(
                pool,
                scenario_set,
                stat_indexes=_pool_stat_indexes(pool, stat_ids),
                score_multipliers=multipliers,
                coach_values=coach_values,
            )
        )
    coach_id = "coach-unavailable-excluded" if coach is None else coach.semantic_hash
    return TeamOutcomeMatrix(
        kind="banner",
        item_id=f"{_banner_identity(banner)}|{coach_id}",
        role=banner.role,
        scenario_sha256=scenario_set.semantic_hash,
        team_ids=team_ids,
        outcomes=np.stack(rows),
    )


@dataclass(frozen=True)
class MatchedOutcome:
    scope: str
    selected_team_ids: tuple[int, ...]
    scenario_sha256: str
    risk_sha256: str
    outcomes: np.ndarray = field(repr=False, compare=False)
    maximum_mean: float
    summary: dict[str, float]
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        outcomes = _readonly_array(self.outcomes)
        object.__setattr__(self, "outcomes", outcomes)
        if outcomes.ndim != 1 or not len(outcomes) or not np.isfinite(outcomes).all():
            raise ValueError("matched outcome must be a complete Scenario vector")
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "scope": self.scope,
                    "selected_team_ids": self.selected_team_ids,
                    "scenario_sha256": self.scenario_sha256,
                    "risk_sha256": self.risk_sha256,
                    "maximum_mean": self.maximum_mean,
                    "summary": self.summary,
                    "outcomes_sha256": _array_sha256(outcomes),
                }
            ),
        )


def _mean_floor(maximum_mean: float, epsilon: float) -> float:
    return maximum_mean - abs(maximum_mean) * epsilon - 1e-12


def match_one_banner(matrix: TeamOutcomeMatrix, risk: RiskConfiguration) -> MatchedOutcome:
    means = matrix.outcomes.mean(axis=1)
    maximum_mean = float(means.max())
    eligible = np.flatnonzero(means >= _mean_floor(maximum_mean, risk.mean_retention_epsilon))
    ranked = sorted(
        eligible,
        key=lambda index: (
            -lower_tail_cvar(matrix.outcomes[index], risk.cvar_alpha),
            -float(means[index]),
            int(matrix.team_ids[index]),
        ),
    )
    selected = int(ranked[0])
    outcomes = matrix.outcomes[selected]
    return MatchedOutcome(
        scope=f"banner:{matrix.role}",
        selected_team_ids=(int(matrix.team_ids[selected]),),
        scenario_sha256=matrix.scenario_sha256,
        risk_sha256=risk.semantic_hash,
        outcomes=outcomes,
        maximum_mean=maximum_mean,
        summary=distribution_summary(outcomes, cvar_alpha=risk.cvar_alpha),
    )


def match_group_roles(
    matrices: dict[str, TeamOutcomeMatrix],
    risk: RiskConfiguration,
) -> MatchedOutcome:
    if tuple(matrices) != ROLE_IDS:
        raise ValueError(f"Group matching requires matrices in canonical role order {ROLE_IDS}")
    first = matrices[ROLE_IDS[0]]
    for role in ROLE_IDS:
        matrix = matrices[role]
        if matrix.role != role:
            raise ValueError(f"matrix labelled {matrix.role} was supplied for {role}")
        if matrix.scenario_sha256 != first.scenario_sha256:
            raise ValueError("Group role matrices must use the same common Scenario set")
        if matrix.outcomes.shape[1] != first.outcomes.shape[1]:
            raise ValueError("Group role matrices must align on Scenario IDs")

    role_means = [matrices[role].outcomes.mean(axis=1) for role in ROLE_IDS]
    maximum_mean = float(sum(values.max() for values in role_means))
    floor = _mean_floor(maximum_mean, risk.mean_retention_epsilon)
    mean_loss_budget = max(0.0, maximum_mean - floor)
    eligible_indexes = [
        np.flatnonzero(values >= float(values.max()) - mean_loss_budget - 1e-12) for values in role_means
    ]
    selected_key: tuple[float, float, tuple[int, int, int]] | None = None
    selected_cvar: float | None = None
    selected_team_ids: tuple[int, int, int] | None = None
    selected_outcomes: np.ndarray | None = None
    for indexes in product(*eligible_indexes):
        mean = float(sum(role_means[offset][index] for offset, index in enumerate(indexes)))
        if mean < floor:
            continue
        outcomes = sum(
            (matrices[role].outcomes[index] for role, index in zip(ROLE_IDS, indexes, strict=True)),
            start=np.zeros(first.outcomes.shape[1], dtype=float),
        )
        team_ids = tuple(
            int(matrices[role].team_ids[index]) for role, index in zip(ROLE_IDS, indexes, strict=True)
        )
        cvar = lower_tail_cvar(outcomes, risk.cvar_alpha)
        rank_key = (-cvar, -mean, team_ids)
        if selected_key is None or rank_key < selected_key:
            selected_key = rank_key
            selected_cvar = cvar
            selected_team_ids = team_ids
            selected_outcomes = outcomes
    if selected_outcomes is None or selected_cvar is None or selected_team_ids is None:
        raise ValueError("no Group Team combination satisfies the mean-retention constraint")
    summary = distribution_summary(selected_outcomes, cvar_alpha=risk.cvar_alpha)
    if not np.isclose(summary["cvar"], selected_cvar):
        raise AssertionError("joint Group CVaR changed during deterministic selection")
    return MatchedOutcome(
        scope="group",
        selected_team_ids=selected_team_ids,
        scenario_sha256=first.scenario_sha256,
        risk_sha256=risk.semantic_hash,
        outcomes=selected_outcomes,
        maximum_mean=maximum_mean,
        summary=summary,
    )


class TerminalValueCache:
    """In-memory arithmetic cache; it contains no Roll or playbook policy."""

    def __init__(self) -> None:
        self._banner: dict[tuple[str, str, str, str, str], TeamOutcomeMatrix] = {}
        self._matched_banner: dict[tuple[str, str], MatchedOutcome] = {}
        self._matched_group: dict[tuple[tuple[str, ...], str], MatchedOutcome] = {}

    def banner(
        self,
        pool_result: PoolBuildResult,
        scenario_set: CommonScenarioSet,
        banner: BannerState,
        rules: dict[str, Any],
        *,
        coach: ValidatedCoachScenario | None = None,
    ) -> TeamOutcomeMatrix:
        coach_hash = "coach-unavailable-excluded" if coach is None else coach.semantic_hash
        rules_hash = sha256_json(
            {
                "stats": rules["fantasy"]["stats"],
                "qualities": rules["fantasy"]["qualities"],
                "traits": rules["fantasy"]["traits"],
                "role_banners": rules["fantasy"]["role_banners"],
            }
        )
        key = (
            scenario_set.semantic_hash,
            pool_result.semantic_hash,
            rules_hash,
            _banner_identity(banner),
            coach_hash,
        )
        if key not in self._banner:
            self._banner[key] = evaluate_banner_teams(
                pool_result,
                scenario_set,
                banner,
                rules,
                coach=coach,
            )
        return self._banner[key]

    def matched_banner(
        self,
        matrix: TeamOutcomeMatrix,
        risk: RiskConfiguration,
    ) -> MatchedOutcome:
        key = (matrix.semantic_hash, risk.semantic_hash)
        if key not in self._matched_banner:
            self._matched_banner[key] = match_one_banner(matrix, risk)
        return self._matched_banner[key]

    def matched_group(
        self,
        matrices: dict[str, TeamOutcomeMatrix],
        risk: RiskConfiguration,
    ) -> MatchedOutcome:
        key = (tuple(matrices[role].semantic_hash for role in ROLE_IDS), risk.semantic_hash)
        if key not in self._matched_group:
            self._matched_group[key] = match_group_roles(matrices, risk)
        return self._matched_group[key]


def _observed_stat_maximum(pool_result: PoolBuildResult, role: str, stat_id: str) -> float:
    maximum = -np.inf
    for pool in pool_result.pools:
        if pool.role != role:
            continue
        index = _pool_stat_indexes(pool, (stat_id,))[0]
        for block in pool.blocks:
            maximum = max(
                maximum,
                score_series_block(
                    block,
                    stat_indexes=(index,),
                    emblem_score_multipliers=(1.0,),
                ),
            )
    if not np.isfinite(maximum):
        raise ValueError(f"no observed Series value for role {role}, Stat {stat_id}")
    return float(maximum)


def build_stat_forecast_package(
    pool_result: PoolBuildResult,
    scenario_set: CommonScenarioSet,
    rules: dict[str, Any],
    *,
    cvar_alpha: float = 0.1,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    matrix_hashes: list[str] = []
    pools = pool_result.by_key()
    for role in ROLE_IDS:
        role_colors = set(rules["fantasy"]["role_banners"][role][:3])
        for stat_id, stat_rule in rules["fantasy"]["stats"].items():
            color = str(stat_rule["color"])
            if color not in role_colors:
                continue
            matrix = evaluate_stat_teams(pool_result, scenario_set, role=role, stat_id=stat_id)
            matrix_hashes.append(matrix.semantic_hash)
            means = matrix.outcomes.mean(axis=1)
            order = sorted(range(len(means)), key=lambda index: (-means[index], matrix.team_ids[index]))
            best_index, runner_up_index = order[:2]
            best_team_id = int(matrix.team_ids[best_index])
            team_values = [
                {
                    "team_id": int(team_id),
                    "mean": float(means[index]),
                    "cvar10": lower_tail_cvar(matrix.outcomes[index], cvar_alpha),
                    "series_blocks": len(pools[(int(team_id), role)].blocks),
                }
                for index, team_id in enumerate(matrix.team_ids)
            ]
            rows.append(
                {
                    "role": role,
                    "color": color,
                    "stat_id": stat_id,
                    "provenance": stat_rule["provenance"],
                    "eligible_row_provenance_coverage": float(
                        pool_result.audit["stat_provenance_coverage"][stat_id]["coverage"]
                    ),
                    "complete_block_provenance_coverage": 1.0,
                    "best_team_id": best_team_id,
                    "best_team_mean": float(means[best_index]),
                    "best_team_cvar10": lower_tail_cvar(matrix.outcomes[best_index], cvar_alpha),
                    "runner_up_team_id": int(matrix.team_ids[runner_up_index]),
                    "runner_up_mean": float(means[runner_up_index]),
                    "all_team_mean": float(means.mean()),
                    "observed_series_maximum": _observed_stat_maximum(pool_result, role, stat_id),
                    "best_team_series_blocks": len(pools[(best_team_id, role)].blocks),
                    "minimum_team_series_blocks": min(
                        len(pools[(int(team_id), role)].blocks) for team_id in matrix.team_ids
                    ),
                    "team_values": team_values,
                    "matrix_sha256": matrix.semantic_hash,
                }
            )

    for role in ROLE_IDS:
        colors = tuple(dict.fromkeys(rules["fantasy"]["role_banners"][role][:3]))
        for color in colors:
            group = [row for row in rows if row["role"] == role and row["color"] == color]
            best_value = max(float(row["best_team_mean"]) for row in group)
            for row in group:
                row["relative_to_best"] = float(row["best_team_mean"]) / best_value

    rows.sort(
        key=lambda row: (
            ROLE_IDS.index(str(row["role"])),
            str(row["color"]),
            -float(row["best_team_mean"]),
            str(row["stat_id"]),
        )
    )
    package_hash = sha256_json(
        {
            "scenario_sha256": scenario_set.semantic_hash,
            "pool_set_sha256": pool_result.semantic_hash,
            "cvar_alpha": cvar_alpha,
            "matrix_hashes": matrix_hashes,
            "rows": rows,
        }
    )
    return {
        "scenario_sha256": scenario_set.semantic_hash,
        "pool_set_sha256": pool_result.semantic_hash,
        "cvar_alpha": cvar_alpha,
        "rows": rows,
        "stat_forecast_sha256": package_hash,
    }


def _bootstrap_seed(seed: int, replicate: int, team_id: int, role: str) -> int:
    payload = f"{seed}:cluster-bootstrap:{replicate}:{team_id}:{role}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little", signed=False)


def _block_stat_values(pool: SeriesBlockPool) -> np.ndarray:
    values = np.stack(
        [np.sort(block.game_stat_scores, axis=0, kind="stable")[-2:].sum(axis=0) for block in pool.blocks]
    )
    return values


def cluster_bootstrap_stat_intervals(
    pool_result: PoolBuildResult,
    scenario_set: CommonScenarioSet,
    stat_forecasts: dict[str, Any],
    rules: dict[str, Any],
    policy: GroupScenarioPolicy,
    *,
    seed: int,
    include_team_rankings: bool = False,
) -> dict[str, Any]:
    """Bootstrap whole Series blocks and optionally retain team-rank probabilities."""

    if stat_forecasts.get("scenario_sha256") != scenario_set.semantic_hash:
        raise ValueError("Stat forecasts and bootstrap must use the same common Scenario set")
    if policy.scenario_count != len(scenario_set.scenario_ids):
        raise ValueError("bootstrap policy and common Scenario count do not match")
    replicates = policy.bootstrap.replicates
    scenario_count = policy.bootstrap.scenarios_per_replicate
    if scenario_count > len(scenario_set.scenario_ids):
        raise ValueError("bootstrap Scenario count exceeds the common Scenario set")
    pools = pool_result.by_key()
    stat_ids = tuple(rules["fantasy"]["stats"])
    stat_index = {stat_id: index for index, stat_id in enumerate(stat_ids)}
    precomputed = {key: _block_stat_values(pool) for key, pool in pools.items()}
    relative_samples: dict[tuple[str, str, str], np.ndarray] = {}
    for role in ROLE_IDS:
        for color in tuple(dict.fromkeys(rules["fantasy"]["role_banners"][role][:3])):
            for stat_id, rule in rules["fantasy"]["stats"].items():
                if rule["color"] == color:
                    relative_samples[(role, color, stat_id)] = np.empty(replicates, dtype=float)

    team_ids = np.asarray(scenario_set.team_ids, dtype=np.int64)
    if include_team_rankings and len(team_ids) < 3:
        raise ValueError("team-rank bootstrap requires at least three eligible teams")
    rank1_counts = (
        {key: np.zeros(len(team_ids), dtype=np.int64) for key in relative_samples}
        if include_team_rankings
        else None
    )
    top3_counts = (
        {key: np.zeros(len(team_ids), dtype=np.int64) for key in relative_samples}
        if include_team_rankings
        else None
    )

    group_rng = np.random.default_rng(seed)
    group_scenario_indexes = group_rng.integers(
        len(scenario_set.scenario_ids), size=(replicates, scenario_count), endpoint=False
    )
    team_indexes = {team_id: index for index, team_id in enumerate(scenario_set.team_ids)}
    for replicate in range(replicates):
        selected_scenarios = group_scenario_indexes[replicate]
        best_team_means = {role: np.full(len(stat_ids), -np.inf, dtype=float) for role in ROLE_IDS}
        team_stat_means = (
            {role: np.full((len(team_ids), len(stat_ids)), -np.inf, dtype=float) for role in ROLE_IDS}
            if include_team_rankings
            else None
        )
        for team_id in scenario_set.team_ids:
            team_index = team_indexes[team_id]
            counts = scenario_set.series_counts[selected_scenarios, team_index]
            max_series = int(scenario_set.series_counts.max())
            used = np.arange(max_series)[None, :] < counts[:, None]
            for role in ROLE_IDS:
                pool = pools.get((team_id, role))
                if pool is None:
                    continue
                rng = np.random.default_rng(_bootstrap_seed(seed, replicate, team_id, role))
                resampled_clusters = rng.choice(
                    len(pool.blocks), size=len(pool.blocks), replace=True, p=pool.weights
                )
                positions = rng.integers(
                    len(resampled_clusters), size=(scenario_count, max_series), endpoint=False
                )
                block_indexes = resampled_clusters[positions]
                sampled = precomputed[(team_id, role)][block_indexes]
                sampled[~used, :] = -np.inf
                means = sampled.max(axis=1).mean(axis=0)
                best_team_means[role] = np.maximum(best_team_means[role], means)
                if team_stat_means is not None:
                    team_stat_means[role][team_index] = means

        if team_stat_means is not None:
            assert rank1_counts is not None
            assert top3_counts is not None
            for key in relative_samples:
                role, _, stat_id = key
                values = team_stat_means[role][:, stat_index[stat_id]]
                available = np.flatnonzero(np.isfinite(values))
                if len(available) < 3:
                    raise ValueError(f"fewer than three team-rank values for {role}/{stat_id}")
                local_order = np.lexsort((team_ids[available], -values[available]))
                order = available[local_order]
                rank1_counts[key][order[0]] += 1
                top3_counts[key][order[:3]] += 1

        for role in ROLE_IDS:
            colors = tuple(dict.fromkeys(rules["fantasy"]["role_banners"][role][:3]))
            for color in colors:
                color_stats = [
                    stat_id for stat_id, rule in rules["fantasy"]["stats"].items() if rule["color"] == color
                ]
                denominator = max(best_team_means[role][stat_index[stat_id]] for stat_id in color_stats)
                for stat_id in color_stats:
                    relative_samples[(role, color, stat_id)][replicate] = (
                        best_team_means[role][stat_index[stat_id]] / denominator
                    )

    point_index = {
        (row["role"], row["color"], row["stat_id"]): float(row["relative_to_best"])
        for row in stat_forecasts["rows"]
    }
    tail = (1.0 - policy.bootstrap.confidence_level) / 2.0
    rows: list[dict[str, Any]] = []
    for key, values in relative_samples.items():
        lower, upper = np.quantile(values, [tail, 1.0 - tail])
        crossed = [boundary for boundary in (0.44, 0.846) if float(lower) < boundary < float(upper)]
        rows.append(
            {
                "role": key[0],
                "color": key[1],
                "stat_id": key[2],
                "point_relative_to_best": point_index[key],
                "confidence_level": policy.bootstrap.confidence_level,
                "interval_lower": float(lower),
                "interval_upper": float(upper),
                "boundary": bool(crossed),
                "crossed_grade_boundaries": crossed,
            }
        )
    rows.sort(key=lambda row: (ROLE_IDS.index(row["role"]), row["color"], row["stat_id"]))
    result: dict[str, Any] = {
        "method": "weighted_full_series_cluster_bootstrap",
        "seed": seed,
        "replicates": replicates,
        "scenarios_per_replicate": scenario_count,
        "confidence_level": policy.bootstrap.confidence_level,
        "rows": rows,
    }
    hash_material: dict[str, Any] = {
        "scenario_sha256": scenario_set.semantic_hash,
        "pool_set_sha256": pool_result.semantic_hash,
        "seed": seed,
        "replicates": replicates,
        "scenarios_per_replicate": scenario_count,
        "rows": rows,
    }
    if include_team_rankings:
        assert rank1_counts is not None
        assert top3_counts is not None
        team_index_by_id = {int(team_id): index for index, team_id in enumerate(team_ids)}
        ranking_rows: list[dict[str, Any]] = []
        for forecast in stat_forecasts["rows"]:
            key = (str(forecast["role"]), str(forecast["color"]), str(forecast["stat_id"]))
            point_values = sorted(
                forecast["team_values"],
                key=lambda row: (-float(row["mean"]), int(row["team_id"])),
            )
            best_mean = float(point_values[0]["mean"])
            for point_rank, point in enumerate(point_values, start=1):
                team_id = int(point["team_id"])
                team_index = team_index_by_id[team_id]
                gap = 0.0 if best_mean == 0.0 else (best_mean - float(point["mean"])) / best_mean
                ranking_rows.append(
                    {
                        "role": key[0],
                        "color": key[1],
                        "stat_id": key[2],
                        "provenance": forecast["provenance"],
                        "team_id": team_id,
                        "point_rank": point_rank,
                        "point_mean": float(point["mean"]),
                        "point_cvar10": float(point["cvar10"]),
                        "series_blocks": int(point["series_blocks"]),
                        "gap_to_point_best_fraction": max(0.0, float(gap)),
                        "rank1_probability": float(rank1_counts[key][team_index] / replicates),
                        "top3_probability": float(top3_counts[key][team_index] / replicates),
                    }
                )
        ranking_rows.sort(
            key=lambda row: (
                ROLE_IDS.index(row["role"]),
                row["color"],
                row["stat_id"],
                row["point_rank"],
            )
        )
        team_rankings = {
            "top_k": 3,
            "point_order": "descending_mean_then_team_id",
            "bootstrap_order": "descending_mean_then_team_id",
            "probability_interpretation": ("series_resampling_frequency_not_calibrated_future_probability"),
            "rank_probability_denominator": replicates,
            "rows": ranking_rows,
        }
        result["team_rankings"] = team_rankings
        hash_material["team_rankings"] = team_rankings
    result["bootstrap_sha256"] = sha256_json(hash_material)
    return result
