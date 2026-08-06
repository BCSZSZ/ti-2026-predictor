"""Bounded, model-conditional Reference Roll solver for TI 2026 Group Fantasy.

The solver deliberately expands only the current legal actions.  Future decisions use one fixed
continuation heuristic and never recurse into another decision tree.  Human playbook code does not
import this module.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations, product
from typing import Any, Literal, Protocol

import numpy as np
from pydantic import Field, model_validator

from ti_predictor.fantasy.playbook import StrictModel
from ti_predictor.fantasy.roll import (
    BannerState,
    EmblemState,
    GroupRollState,
    RefreshRollAction,
    RollAction,
    RollOffer,
    RollRuleSet,
    apply_realized_transition,
    draw_roll_offer,
    enumerate_mutation_outcomes,
    legal_actions,
    mutation_distribution,
    rank_rate_agnostic_actions,
    refresh_transition,
    sample_mutation,
    validate_group_state,
)
from ti_predictor.fantasy.scenarios import CommonScenarioSet, PoolBuildResult, SeriesBlockPool
from ti_predictor.fantasy.scoring import Emblem, emblem_multipliers
from ti_predictor.fantasy.valuation import (
    MatchedOutcome,
    RiskConfiguration,
    TerminalValueCache,
    lower_tail_cvar,
)
from ti_predictor.hashing import sha256_bytes, sha256_json

CONFIGURATION_CARDINALITY = 5
CONFIGURATION_DIMENSIONS = 6
POSITIONED_CONFIGURATION_COUNT = CONFIGURATION_CARDINALITY**CONFIGURATION_DIMENSIONS


class SolverPolicyError(ValueError):
    """The frozen P5 solver policy is internally inconsistent."""


class SolverEvaluationError(ValueError):
    """A solver evaluator cannot safely value the supplied Group state."""


class SynergyPotentialPolicy(StrictModel):
    positioned_configuration_count: Literal[15625]
    maximum_attribute_differences: Literal[3]
    decay_denominator: Literal[39]
    last_roll_multiplier: Literal[0.0]
    fixed_stat_scope: Literal["observed_decision_root"]
    simulated_stat_change_potential: Literal["zero_until_observed_replan"]


class DecisionBudget(StrictModel):
    screening_paths_per_action: int = Field(ge=1)
    confirmation_paths_per_finalist: int = Field(ge=2)
    finalist_count: Literal[2]
    confidence_level: float = Field(gt=0.5, lt=1.0)
    bootstrap_replicates: int = Field(ge=100)
    unresolved_fallback: Literal["rate_agnostic_safety"]


class SolverValidationPolicy(StrictModel):
    starting_coverage_case_count: Literal[9]
    full_session_replicates_per_stratum: int = Field(ge=1)
    oracle_horizons: tuple[Literal[1, 2, 3], ...]
    oracle_states_per_horizon: int = Field(ge=1)
    oracle_regret_upper_bound: float = Field(gt=0.0, lt=1.0)
    common_unresolved_upper_bound: float = Field(gt=0.0, lt=1.0)
    baseline_comparators: tuple[Literal["one_step_greedy", "rate_agnostic_safety"], ...]


class BranchCappedSolverPolicy(StrictModel):
    schema_version: Literal[1]
    policy_id: str
    period: Literal["group"]
    as_of: str
    seed: int
    source_playbook_evidence_sha256: str
    source_validation_policy_sha256: str
    scenario_subset_count: int = Field(ge=32)
    scenario_subset_sampling: Literal["fixed_without_replacement"]
    transition_models: tuple[str, ...]
    mean_retention_epsilons: tuple[float, ...]
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    synergy_potential: SynergyPotentialPolicy
    decision_budget: DecisionBudget
    validation: SolverValidationPolicy
    full_horizon_equivalent_path_ceiling: int = Field(gt=0)
    runtime_target_seconds: int = Field(gt=0)
    outputs_must_not_claim_global_optimality: Literal[True]
    full_planner_auto_activation: Literal[False]

    @model_validator(mode="after")
    def validate_contract(self) -> BranchCappedSolverPolicy:
        if self.transition_models != (
            "client-weight-primary-v1",
            "flattened-weights-v1",
            "sharpened-weights-v1",
        ):
            raise SolverPolicyError("P5 transition models differ from the P2 preregistration")
        if self.mean_retention_epsilons != (0.0, 0.01, 0.02, 0.05):
            raise SolverPolicyError("P5 must retain the frozen 0/1/2/5 percent epsilon frontier")
        if self.validation.oracle_horizons != (1, 2, 3):
            raise SolverPolicyError("P5 exact-oracle horizons must be one, two and three Rolls")
        if self.validation.baseline_comparators != (
            "one_step_greedy",
            "rate_agnostic_safety",
        ):
            raise SolverPolicyError("P5 baseline comparators drifted")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


def load_solver_policy(path) -> BranchCappedSolverPolicy:
    return BranchCappedSolverPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _readonly_array(values: Any, *, dtype: str | np.dtype) -> np.ndarray:
    result = np.ascontiguousarray(values, dtype=dtype)
    result.setflags(write=False)
    return result


def _array_sha256(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values)
    header = f"{canonical.dtype.str}:{','.join(str(value) for value in canonical.shape)}".encode()
    return sha256_bytes(header + b"\0" + canonical.tobytes(order="C"))


@lru_cache(maxsize=1)
def configuration_digits() -> np.ndarray:
    """Return all positioned Q/Q/Q/T/T/T states in stable base-five order."""

    values = np.indices((CONFIGURATION_CARDINALITY,) * CONFIGURATION_DIMENSIONS, dtype=np.int8)
    return _readonly_array(values.reshape(CONFIGURATION_DIMENSIONS, -1).T, dtype="<i1")


def configuration_index(banner: BannerState, trait_order: Sequence[str]) -> int:
    if len(banner.emblems) != 3:
        raise SolverEvaluationError("P5 Group configuration lookup requires exactly three Emblems")
    traits = {trait_id: index for index, trait_id in enumerate(trait_order)}
    if len(traits) != CONFIGURATION_CARDINALITY:
        raise SolverEvaluationError("configuration lookup requires five unique Traits")
    digits = [emblem.quality_tier - 1 for emblem in banner.emblems]
    try:
        digits.extend(traits[emblem.trait_id] for emblem in banner.emblems)
    except KeyError as error:
        raise SolverEvaluationError(f"unknown Trait in configuration lookup: {error.args[0]}") from error
    if any(value < 0 or value >= CONFIGURATION_CARDINALITY for value in digits):
        raise SolverEvaluationError("configuration lookup requires Quality tiers T1 through T5")
    result = 0
    for value in digits:
        result = result * CONFIGURATION_CARDINALITY + value
    return result


def banner_from_configuration(
    role: str,
    stat_ids: tuple[str, str, str],
    trait_order: Sequence[str],
    index: int,
) -> BannerState:
    if index < 0 or index >= POSITIONED_CONFIGURATION_COUNT:
        raise SolverEvaluationError("positioned configuration index is outside 0..15,624")
    digits = configuration_digits()[index]
    return BannerState(
        role=role,
        emblems=tuple(
            EmblemState(
                stat_id=stat_ids[slot],
                quality_tier=int(digits[slot]) + 1,
                trait_id=str(trait_order[int(digits[slot + 3])]),
            )
            for slot in range(3)
        ),
    )


@lru_cache(maxsize=1)
def hamming_three_neighbor_indexes() -> np.ndarray:
    """Precompute every base-five configuration within three changed attributes."""

    digits = configuration_digits()
    place_values = np.asarray([5**power for power in range(5, -1, -1)], dtype=np.int32)
    rows: list[np.ndarray] = []
    chunk_size = 128
    target_cache = {
        count: np.asarray(tuple(product(range(5), repeat=count)), dtype=np.int8) for count in (1, 2, 3)
    }
    for start in range(0, POSITIONED_CONFIGURATION_COUNT, chunk_size):
        current = digits[start : start + chunk_size]
        original = np.arange(start, start + len(current), dtype=np.int32)
        parts = [original[:, None]]
        for difference_count in (1, 2, 3):
            targets = target_cache[difference_count]
            for dimensions in combinations(range(CONFIGURATION_DIMENSIONS), difference_count):
                selected = current[:, dimensions]
                valid = np.all(targets[None, :, :] != selected[:, None, :], axis=2)
                deltas = (
                    (targets[None, :, :] - selected[:, None, :])
                    * place_values[np.asarray(dimensions)][None, None, :]
                ).sum(axis=2)
                candidates = original[:, None] + deltas
                expected = (CONFIGURATION_CARDINALITY - 1) ** difference_count
                parts.append(candidates[valid].reshape(len(current), expected))
        neighbors = np.concatenate(parts, axis=1)
        if neighbors.shape[1] != 1545:
            raise AssertionError("Hamming-three neighborhood must contain exactly 1,545 states")
        rows.append(neighbors.astype(np.uint16, copy=False))
    result = np.concatenate(rows, axis=0)
    return _readonly_array(result, dtype="<u2")


@dataclass(frozen=True)
class FixedStatConfigurationValues:
    role: str
    stat_ids: tuple[str, str, str]
    trait_order: tuple[str, ...]
    selected_means: np.ndarray = field(repr=False, compare=False)
    selected_cvars: np.ndarray = field(repr=False, compare=False)
    maximum_means: np.ndarray = field(repr=False, compare=False)
    selected_team_ids: np.ndarray = field(repr=False, compare=False)
    scenario_sha256: str
    risk_sha256: str
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        means = _readonly_array(self.selected_means, dtype="<f8")
        cvars = _readonly_array(self.selected_cvars, dtype="<f8")
        maximums = _readonly_array(self.maximum_means, dtype="<f8")
        teams = _readonly_array(self.selected_team_ids, dtype="<i8")
        for values in (means, cvars, maximums, teams):
            if values.shape != (POSITIONED_CONFIGURATION_COUNT,):
                raise SolverEvaluationError("fixed-Stat table must contain exactly 15,625 values")
        if not all(np.isfinite(values).all() for values in (means, cvars, maximums)):
            raise SolverEvaluationError("fixed-Stat terminal values must be finite")
        object.__setattr__(self, "selected_means", means)
        object.__setattr__(self, "selected_cvars", cvars)
        object.__setattr__(self, "maximum_means", maximums)
        object.__setattr__(self, "selected_team_ids", teams)
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "role": self.role,
                    "stat_ids": self.stat_ids,
                    "trait_order": self.trait_order,
                    "scenario_sha256": self.scenario_sha256,
                    "risk_sha256": self.risk_sha256,
                    "selected_means_sha256": _array_sha256(means),
                    "selected_cvars_sha256": _array_sha256(cvars),
                    "maximum_means_sha256": _array_sha256(maximums),
                    "selected_team_ids_sha256": _array_sha256(teams),
                }
            ),
        )


@dataclass(frozen=True)
class SynergyPotentialTable:
    values: FixedStatConfigurationValues
    epsilon: float
    maximum_attribute_differences: int
    selected_neighbor_indexes: np.ndarray = field(repr=False, compare=False)
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        indexes = _readonly_array(self.selected_neighbor_indexes, dtype="<u2")
        if indexes.shape != (POSITIONED_CONFIGURATION_COUNT,):
            raise SolverEvaluationError("synergy lookup must select one neighbor per configuration")
        object.__setattr__(self, "selected_neighbor_indexes", indexes)
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "fixed_stat_values_sha256": self.values.semantic_hash,
                    "epsilon": self.epsilon,
                    "maximum_attribute_differences": self.maximum_attribute_differences,
                    "selected_neighbor_indexes_sha256": _array_sha256(indexes),
                }
            ),
        )

    @property
    def stat_ids(self) -> tuple[str, str, str]:
        return self.values.stat_ids

    def objective(self, banner: BannerState) -> tuple[float, float]:
        index = configuration_index(banner, self.values.trait_order)
        return float(self.values.selected_means[index]), float(self.values.selected_cvars[index])

    def gain(self, banner: BannerState) -> tuple[float, float]:
        index = configuration_index(banner, self.values.trait_order)
        selected = int(self.selected_neighbor_indexes[index])
        return (
            float(self.values.selected_means[selected] - self.values.selected_means[index]),
            float(self.values.selected_cvars[selected] - self.values.selected_cvars[index]),
        )


def build_synergy_potential_table(
    values: FixedStatConfigurationValues,
    *,
    epsilon: float,
    maximum_attribute_differences: int = 3,
) -> SynergyPotentialTable:
    if maximum_attribute_differences != 3:
        raise SolverPolicyError("P5 v1 only supports the frozen Hamming-three potential")
    if epsilon < 0.0 or epsilon >= 1.0:
        raise SolverPolicyError("mean-retention epsilon must be in [0, 1)")
    neighbors = hamming_three_neighbor_indexes()
    selected = np.empty(POSITIONED_CONFIGURATION_COUNT, dtype=np.uint16)
    chunk_size = 128
    for start in range(0, POSITIONED_CONFIGURATION_COUNT, chunk_size):
        indexes = neighbors[start : start + chunk_size]
        means = values.selected_means[indexes]
        cvars = values.selected_cvars[indexes]
        maximum_mean = means.max(axis=1)
        floor = maximum_mean - np.abs(maximum_mean) * epsilon - 1e-12
        eligible = means >= floor[:, None]
        eligible_cvars = np.where(eligible, cvars, -np.inf)
        maximum_cvar = eligible_cvars.max(axis=1)
        cvar_ties = eligible & np.isclose(eligible_cvars, maximum_cvar[:, None], rtol=0.0, atol=1e-12)
        tied_means = np.where(cvar_ties, means, -np.inf)
        maximum_tied_mean = tied_means.max(axis=1)
        finalists = cvar_ties & np.isclose(
            tied_means,
            maximum_tied_mean[:, None],
            rtol=0.0,
            atol=1e-12,
        )
        finalist_indexes = np.where(finalists, indexes, np.iinfo(np.uint16).max)
        selected[start : start + len(indexes)] = finalist_indexes.min(axis=1)
    return SynergyPotentialTable(
        values=values,
        epsilon=epsilon,
        maximum_attribute_differences=maximum_attribute_differences,
        selected_neighbor_indexes=selected,
    )


class ExactFixedStatConfigurationEvaluator:
    """Vectorized P3 terminal arithmetic for all 15,625 Q/T configurations."""

    def __init__(
        self,
        pool_result: PoolBuildResult,
        scenario_set: CommonScenarioSet,
        canonical_rules: dict[str, Any],
        roll_rules: RollRuleSet,
        *,
        chunk_size: int = 128,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("fixed-Stat evaluator chunk size must be positive")
        self.pool_result = pool_result
        self.scenario_set = scenario_set
        self.canonical_rules = canonical_rules
        self.roll_rules = roll_rules
        self.chunk_size = chunk_size
        self._pools = pool_result.by_key()
        self._multipliers = self._build_multiplier_grid()
        self._cache: dict[tuple[str, tuple[str, str, str], str], FixedStatConfigurationValues] = {}
        self._banner_cache: dict[tuple[BannerState, str], ObjectiveEstimate] = {}

    def _build_multiplier_grid(self) -> np.ndarray:
        rows = []
        for digits in configuration_digits():
            emblems = [
                Emblem(
                    stat_id=f"slot-{slot}",
                    color="unused",
                    quality_tier=int(digits[slot]) + 1,
                    trait=self.roll_rules.traits[int(digits[slot + 3])],
                )
                for slot in range(3)
            ]
            rows.append(emblem_multipliers(emblems, self.canonical_rules))
        return _readonly_array(rows, dtype="<f8")

    @staticmethod
    def _stat_indexes(pool: SeriesBlockPool, stat_ids: tuple[str, str, str]) -> tuple[int, int, int]:
        index = {stat_id: offset for offset, stat_id in enumerate(pool.stat_ids)}
        try:
            return tuple(index[stat_id] for stat_id in stat_ids)  # type: ignore[return-value]
        except KeyError as error:
            raise SolverEvaluationError(f"Series pool lacks Stat {error.args[0]}") from error

    @staticmethod
    def _vectorized_cvar(outcomes: np.ndarray, alpha: float) -> np.ndarray:
        scenario_count = outcomes.shape[-1]
        mass = alpha * scenario_count
        whole = int(np.floor(mass))
        fraction = mass - whole
        if whole == scenario_count:
            return outcomes.mean(axis=-1)
        boundary_index = whole if fraction > 0.0 else whole - 1
        partitioned = np.partition(outcomes, boundary_index, axis=-1)
        total = partitioned[..., :whole].sum(axis=-1)
        if fraction > 0.0:
            total = total + fraction * partitioned[..., whole]
        return total / mass

    def _team_chunk_outcomes(
        self,
        pool: SeriesBlockPool,
        stat_ids: tuple[str, str, str],
        multipliers: np.ndarray,
    ) -> np.ndarray:
        stat_indexes = self._stat_indexes(pool, stat_ids)
        block_values = np.empty((len(pool.blocks), len(multipliers)), dtype=float)
        for block_index, block in enumerate(pool.blocks):
            game_values = block.game_stat_scores[:, stat_indexes] @ multipliers.T
            if game_values.shape[0] < 2:
                raise SolverEvaluationError("Group Series block has fewer than two Games")
            partitioned = np.partition(game_values, game_values.shape[0] - 2, axis=0)
            block_values[block_index] = partitioned[-2:].sum(axis=0)
        draws = self.scenario_set.draw_record_for(pool.target_team_id, pool.role).block_indexes
        safe_draws = np.maximum(draws, 0)
        sampled = block_values[safe_draws]
        sampled[draws < 0] = -np.inf
        outcomes = sampled.max(axis=1)
        if not np.isfinite(outcomes).all():
            raise SolverEvaluationError("fixed-Stat scenario evaluation produced an incomplete outcome")
        return outcomes

    def _evaluate_multipliers(
        self,
        role: str,
        stat_ids: tuple[str, str, str],
        multipliers: np.ndarray,
        risk: RiskConfiguration,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        team_ids = self.scenario_set.team_ids
        team_outcomes = np.stack(
            [
                self._team_chunk_outcomes(
                    self._pools[(team_id, role)],
                    stat_ids,
                    multipliers,
                )
                for team_id in team_ids
            ]
        )
        means = team_outcomes.mean(axis=1)
        cvars = self._vectorized_cvar(
            np.transpose(team_outcomes, (0, 2, 1)),
            risk.cvar_alpha,
        )
        maximums = means.max(axis=0)
        floors = maximums - np.abs(maximums) * risk.mean_retention_epsilon - 1e-12
        selected_means = np.empty(len(multipliers), dtype=float)
        selected_cvars = np.empty(len(multipliers), dtype=float)
        selected_teams = np.empty(len(multipliers), dtype=np.int64)
        for offset in range(len(multipliers)):
            eligible = np.flatnonzero(means[:, offset] >= floors[offset])
            chosen = min(
                eligible,
                key=lambda team_index: (
                    -float(cvars[team_index, offset]),
                    -float(means[team_index, offset]),
                    int(team_ids[team_index]),
                ),
            )
            selected_means[offset] = means[chosen, offset]
            selected_cvars[offset] = cvars[chosen, offset]
            selected_teams[offset] = team_ids[chosen]
        return selected_means, selected_cvars, maximums, selected_teams

    def _banner_multiplier(self, banner: BannerState) -> np.ndarray:
        emblems = [
            Emblem(
                stat_id=state.stat_id,
                color=self.roll_rules.color_for_stat(state.stat_id),
                quality_tier=state.quality_tier,
                trait=state.trait_id,
            )
            for state in banner.emblems
        ]
        return np.asarray(emblem_multipliers(emblems, self.canonical_rules), dtype=float)

    def evaluate_banners(
        self,
        banners: Sequence[BannerState],
        risk: RiskConfiguration,
    ) -> dict[BannerState, ObjectiveEstimate]:
        """Batch exact single-configuration values by shared role and fixed Stat triple."""

        unique = tuple(dict.fromkeys(banners))
        missing: dict[tuple[str, tuple[str, str, str]], list[BannerState]] = {}
        for banner in unique:
            key = (banner, risk.semantic_hash)
            if key in self._banner_cache:
                continue
            if len(banner.emblems) != 3:
                raise SolverEvaluationError("P5 batch Banner evaluation requires three Emblems")
            stat_ids = tuple(emblem.stat_id for emblem in banner.emblems)
            missing.setdefault((banner.role, stat_ids), []).append(banner)  # type: ignore[arg-type]
        for (role, stat_ids), grouped in missing.items():
            multipliers = np.stack([self._banner_multiplier(banner) for banner in grouped])
            means, cvars, _, _ = self._evaluate_multipliers(role, stat_ids, multipliers, risk)
            for banner, mean, cvar in zip(grouped, means, cvars, strict=True):
                self._banner_cache[(banner, risk.semantic_hash)] = ObjectiveEstimate(
                    mean=float(mean),
                    cvar=float(cvar),
                )
        return {banner: self._banner_cache[(banner, risk.semantic_hash)] for banner in unique}

    def evaluate(
        self,
        banner: BannerState,
        risk: RiskConfiguration,
    ) -> FixedStatConfigurationValues:
        if len(banner.emblems) != 3:
            raise SolverEvaluationError("P5 fixed-Stat evaluation requires three Emblems")
        stat_ids = tuple(emblem.stat_id for emblem in banner.emblems)
        key = (banner.role, stat_ids, risk.semantic_hash)
        if key in self._cache:
            return self._cache[key]
        selected_means = np.empty(POSITIONED_CONFIGURATION_COUNT, dtype=float)
        selected_cvars = np.empty(POSITIONED_CONFIGURATION_COUNT, dtype=float)
        maximum_means = np.empty(POSITIONED_CONFIGURATION_COUNT, dtype=float)
        selected_teams = np.empty(POSITIONED_CONFIGURATION_COUNT, dtype=np.int64)
        for start in range(0, POSITIONED_CONFIGURATION_COUNT, self.chunk_size):
            multipliers = self._multipliers[start : start + self.chunk_size]
            means, cvars, maximums, teams = self._evaluate_multipliers(
                banner.role,
                stat_ids,  # type: ignore[arg-type]
                multipliers,
                risk,
            )
            stop = start + len(multipliers)
            selected_means[start:stop] = means
            selected_cvars[start:stop] = cvars
            maximum_means[start:stop] = maximums
            selected_teams[start:stop] = teams
        result = FixedStatConfigurationValues(
            role=banner.role,
            stat_ids=stat_ids,  # type: ignore[arg-type]
            trait_order=self.roll_rules.traits,
            selected_means=selected_means,
            selected_cvars=selected_cvars,
            maximum_means=maximum_means,
            selected_team_ids=selected_teams,
            scenario_sha256=self.scenario_set.semantic_hash,
            risk_sha256=risk.semantic_hash,
        )
        self._cache[key] = result
        return result


@dataclass(frozen=True)
class ObjectiveEstimate:
    mean: float
    cvar: float


class TerminalGroupEvaluator:
    """Exact P3 terminal Group scorer with repeated same-team matching."""

    def __init__(
        self,
        pool_result: PoolBuildResult,
        scenario_set: CommonScenarioSet,
        canonical_rules: dict[str, Any],
    ) -> None:
        self.pool_result = pool_result
        self.scenario_set = scenario_set
        self.canonical_rules = canonical_rules
        self.cache = TerminalValueCache()
        self._group: dict[tuple[tuple[BannerState, ...], str], MatchedOutcome] = {}
        self._banner: dict[tuple[BannerState, str], ObjectiveEstimate] = {}
        self._batch_evaluator: ExactFixedStatConfigurationEvaluator | None = None

    def attach_batch_evaluator(
        self,
        evaluator: ExactFixedStatConfigurationEvaluator,
    ) -> None:
        if (
            evaluator.pool_result.semantic_hash != self.pool_result.semantic_hash
            or evaluator.scenario_set.semantic_hash != self.scenario_set.semantic_hash
        ):
            raise SolverEvaluationError("batch Banner evaluator does not share the terminal context")
        self._batch_evaluator = evaluator

    def prime_banner_objectives(
        self,
        banners: Sequence[BannerState],
        risk: RiskConfiguration,
    ) -> None:
        missing = tuple(banner for banner in banners if (banner, risk.semantic_hash) not in self._banner)
        if not missing:
            return
        if self._batch_evaluator is None:
            for banner in missing:
                self.banner_objective(banner, risk)
            return
        self._banner.update(
            {
                (banner, risk.semantic_hash): value
                for banner, value in self._batch_evaluator.evaluate_banners(missing, risk).items()
            }
        )

    def matched_group(
        self,
        banners: tuple[BannerState, ...],
        risk: RiskConfiguration,
    ) -> MatchedOutcome:
        key = (banners, risk.semantic_hash)
        if key not in self._group:
            matrices = {
                banner.role: self.cache.banner(
                    self.pool_result,
                    self.scenario_set,
                    banner,
                    self.canonical_rules,
                )
                for banner in banners
            }
            self._group[key] = self.cache.matched_group(matrices, risk)
        return self._group[key]

    def banner_objective(self, banner: BannerState, risk: RiskConfiguration) -> ObjectiveEstimate:
        key = (banner, risk.semantic_hash)
        if key not in self._banner:
            if self._batch_evaluator is not None:
                self.prime_banner_objectives((banner,), risk)
                return self._banner[key]
            matrix = self.cache.banner(
                self.pool_result,
                self.scenario_set,
                banner,
                self.canonical_rules,
            )
            matched = self.cache.matched_banner(matrix, risk)
            self._banner[key] = ObjectiveEstimate(
                mean=float(matched.summary["mean"]),
                cvar=float(matched.summary["cvar"]),
            )
        return self._banner[key]


class PotentialProvider(Protocol):
    def __call__(self, banner: BannerState, risk: RiskConfiguration) -> SynergyPotentialTable: ...


class GroupTerminalProvider(Protocol):
    def matched_group(
        self,
        banners: tuple[BannerState, ...],
        risk: RiskConfiguration,
    ) -> MatchedOutcome: ...

    def banner_objective(self, banner: BannerState, risk: RiskConfiguration) -> ObjectiveEstimate: ...

    def prime_banner_objectives(
        self,
        banners: Sequence[BannerState],
        risk: RiskConfiguration,
    ) -> None: ...


def _replace_banner(banners: tuple[BannerState, ...], replacement: BannerState) -> tuple[BannerState, ...]:
    return tuple(replacement if banner.role == replacement.role else banner for banner in banners)


def _action_identity(action: RollAction) -> str:
    if isinstance(action, RefreshRollAction):
        return "refresh"
    return f"{action.banner_role}:{action.operation_id}"


def _state_identity(state: GroupRollState) -> str:
    return sha256_json(
        {
            "banners": [
                {
                    "role": banner.role,
                    "emblems": [
                        {
                            "stat_id": emblem.stat_id,
                            "quality_tier": emblem.quality_tier,
                            "trait_id": emblem.trait_id,
                        }
                        for emblem in banner.emblems
                    ],
                }
                for banner in state.banners
            ],
            "offer": state.offer.operation_ids,
            "remaining_rolls": state.remaining_rolls,
            "period": state.period,
            "slot_count": state.slot_count,
        }
    )


def _stream_seed(seed: int, *parts: Any) -> int:
    payload = ":".join([str(seed), *(str(part) for part in parts)]).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little", signed=False)


@dataclass(frozen=True)
class ContinuationActionValue:
    action: RollAction
    mean: float
    cvar: float
    safety_rank: int


class SynergyContinuationPolicy:
    """One-step fixed continuation; it never calls the root rollout solver recursively."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: GroupTerminalProvider,
        root_tables: Mapping[str, SynergyPotentialTable],
        risk: RiskConfiguration,
        *,
        decay_denominator: int = 39,
        include_synergy: bool = True,
    ) -> None:
        if decay_denominator != 39:
            raise SolverPolicyError("P5 v1 continuation decay denominator must be 39")
        self.rules = rules
        self.terminal = terminal
        self.root_tables = dict(root_tables)
        self.risk = risk
        self.decay_denominator = decay_denominator
        self.include_synergy = include_synergy

    def _banner_objective(self, banner: BannerState) -> ObjectiveEstimate:
        table = self.root_tables[banner.role]
        stat_ids = tuple(emblem.stat_id for emblem in banner.emblems)
        if stat_ids == table.stat_ids:
            mean, cvar = table.objective(banner)
            return ObjectiveEstimate(mean=mean, cvar=cvar)
        return self.terminal.banner_objective(banner, self.risk)

    def _potential(self, banners: tuple[BannerState, ...]) -> ObjectiveEstimate:
        if not self.include_synergy:
            return ObjectiveEstimate(mean=0.0, cvar=0.0)
        mean = 0.0
        cvar = 0.0
        for banner in banners:
            table = self.root_tables[banner.role]
            stat_ids = tuple(emblem.stat_id for emblem in banner.emblems)
            if stat_ids != table.stat_ids:
                continue
            mean_gain, cvar_gain = table.gain(banner)
            mean += mean_gain
            cvar += cvar_gain
        return ObjectiveEstimate(mean=mean, cvar=cvar)

    def _objective(self, banners: tuple[BannerState, ...]) -> ObjectiveEstimate:
        values = [self._banner_objective(banner) for banner in banners]
        return ObjectiveEstimate(
            mean=float(sum(value.mean for value in values)),
            cvar=float(sum(value.cvar for value in values)),
        )

    def _safety_ranks(self, state: GroupRollState) -> dict[RollAction, int]:
        ranked = rank_rate_agnostic_actions(
            state,
            self.rules,
            lambda banner: self._banner_objective(banner).mean,
        )
        return {item.action: index for index, item in enumerate(ranked)}

    def action_values(self, state: GroupRollState) -> tuple[ContinuationActionValue, ...]:
        validate_group_state(state, self.rules)
        if state.remaining_rolls == 0:
            return ()
        decay = (state.remaining_rolls - 1) / self.decay_denominator
        if decay < 0.0 or decay > 1.0 + 1e-12:
            raise SolverEvaluationError("synergy-potential decay escaped the frozen zero-to-one range")
        current_by_role = {banner.role: banner for banner in state.banners}
        outcomes_by_action: dict[
            RollAction,
            tuple[tuple[tuple[BannerState, ...], float], ...],
        ] = {}
        prime_candidates: list[BannerState] = list(state.banners)
        for action in legal_actions(state, self.rules):
            if isinstance(action, RefreshRollAction):
                outcomes = ((state.banners, 1.0),)
            else:
                outcomes = tuple(
                    (
                        _replace_banner(state.banners, outcome.banner),
                        outcome.probability,
                    )
                    for outcome in mutation_distribution(
                        current_by_role[action.banner_role],
                        action.operation_id,
                        self.rules,
                        self._model_id,
                    )
                )
            outcomes_by_action[action] = outcomes
            for banners, _ in outcomes:
                prime_candidates.extend(
                    banner
                    for banner in banners
                    if tuple(emblem.stat_id for emblem in banner.emblems)
                    != self.root_tables[banner.role].stat_ids
                )
        prime = getattr(self.terminal, "prime_banner_objectives", None)
        if prime is not None:
            prime(tuple(dict.fromkeys(prime_candidates)), self.risk)
        safety_ranks = self._safety_ranks(state)
        values = []
        for action, outcomes in outcomes_by_action.items():
            mean = 0.0
            cvar = 0.0
            for banners, probability in outcomes:
                immediate = self._objective(banners)
                potential = self._potential(banners)
                mean += probability * (immediate.mean + decay * potential.mean)
                cvar += probability * (immediate.cvar + decay * potential.cvar)
            values.append(
                ContinuationActionValue(
                    action=action,
                    mean=float(mean),
                    cvar=float(cvar),
                    safety_rank=safety_ranks[action],
                )
            )
        return tuple(values)

    def bind_model(self, model_id: str) -> SynergyContinuationPolicy:
        self.rules.model_power(model_id)
        self._model_id = model_id
        return self

    def decide(self, state: GroupRollState) -> RollAction:
        if not hasattr(self, "_model_id"):
            raise SolverEvaluationError("continuation model must be bound before deciding")
        values = self.action_values(state)
        if not values:
            raise SolverEvaluationError("continuation cannot decide with zero Rolls remaining")
        maximum_mean = max(item.mean for item in values)
        floor = maximum_mean - abs(maximum_mean) * self.risk.mean_retention_epsilon - 1e-12
        eligible = [item for item in values if item.mean >= floor]
        selected = min(
            eligible,
            key=lambda item: (-item.cvar, -item.mean, item.safety_rank, _action_identity(item.action)),
        )
        return selected.action


@dataclass(frozen=True)
class ActionEstimate:
    action: RollAction
    phase: Literal["screening", "confirmation"]
    scores: tuple[float, ...] = field(repr=False)
    mean: float
    cvar: float


@dataclass(frozen=True)
class ResolutionEvidence:
    comparator_action: RollAction | None
    mean_difference: float | None
    mean_lower_one_sided: float | None
    cvar_difference: float | None
    cvar_lower_one_sided: float | None
    mean_retention_confirmed: bool
    cvar_preference_confirmed: bool


@dataclass(frozen=True)
class SolverDecision:
    preferred_action: RollAction
    executed_action: RollAction
    resolved: bool
    resolution_reason: str
    model_id: str
    epsilon: float
    screening: tuple[ActionEstimate, ...]
    confirmation: tuple[ActionEstimate, ...]
    resolution_evidence: ResolutionEvidence
    full_horizon_equivalent_paths: float
    approximate_not_globally_optimal: Literal[True] = True


def _summarize_action(
    action: RollAction,
    phase: Literal["screening", "confirmation"],
    scores: Sequence[float],
    *,
    alpha: float,
) -> ActionEstimate:
    numeric = np.asarray(scores, dtype=float)
    if not len(numeric) or not np.isfinite(numeric).all():
        raise SolverEvaluationError("action estimate requires finite non-empty path scores")
    return ActionEstimate(
        action=action,
        phase=phase,
        scores=tuple(float(value) for value in numeric),
        mean=float(numeric.mean()),
        cvar=lower_tail_cvar(numeric, alpha),
    )


def _rank_estimates(
    estimates: Sequence[ActionEstimate],
    *,
    epsilon: float,
    safety_ranks: Mapping[RollAction, int],
) -> tuple[ActionEstimate, ...]:
    maximum_mean = max(item.mean for item in estimates)
    floor = maximum_mean - abs(maximum_mean) * epsilon - 1e-12
    eligible = [item for item in estimates if item.mean >= floor]
    ineligible = [item for item in estimates if item.mean < floor]
    return tuple(
        sorted(
            eligible,
            key=lambda item: (
                -item.cvar,
                -item.mean,
                safety_ranks[item.action],
                _action_identity(item.action),
            ),
        )
        + sorted(
            ineligible,
            key=lambda item: (
                -item.mean,
                -item.cvar,
                safety_ranks[item.action],
                _action_identity(item.action),
            ),
        )
    )


def _paired_resolution_evidence(
    preferred: ActionEstimate,
    comparator: ActionEstimate | None,
    *,
    epsilon: float,
    alpha: float,
    confidence_level: float,
    bootstrap_replicates: int,
    seed: int,
) -> ResolutionEvidence:
    if comparator is None:
        return ResolutionEvidence(
            comparator_action=None,
            mean_difference=None,
            mean_lower_one_sided=None,
            cvar_difference=None,
            cvar_lower_one_sided=None,
            mean_retention_confirmed=True,
            cvar_preference_confirmed=True,
        )
    left = np.asarray(preferred.scores, dtype=float)
    right = np.asarray(comparator.scores, dtype=float)
    if left.shape != right.shape:
        raise SolverEvaluationError("paired confirmation requires aligned path counts")
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(left), size=(bootstrap_replicates, len(left)))
    left_samples = left[indexes]
    right_samples = right[indexes]
    mean_differences = left_samples.mean(axis=1) - right_samples.mean(axis=1)
    cvar_differences = np.asarray(
        [
            lower_tail_cvar(left_sample, alpha) - lower_tail_cvar(right_sample, alpha)
            for left_sample, right_sample in zip(left_samples, right_samples, strict=True)
        ],
        dtype=float,
    )
    quantile = 1.0 - confidence_level
    mean_lower = float(np.quantile(mean_differences, quantile))
    cvar_lower = float(np.quantile(cvar_differences, quantile))
    retention_allowance = epsilon * abs(comparator.mean)
    mean_confirmed = mean_lower >= -retention_allowance - 1e-12
    comparator_is_mean_eligible = comparator.mean >= (
        max(preferred.mean, comparator.mean) - abs(max(preferred.mean, comparator.mean)) * epsilon - 1e-12
    )
    cvar_confirmed = (not comparator_is_mean_eligible) or cvar_lower >= -1e-12
    return ResolutionEvidence(
        comparator_action=comparator.action,
        mean_difference=float(preferred.mean - comparator.mean),
        mean_lower_one_sided=mean_lower,
        cvar_difference=float(preferred.cvar - comparator.cvar),
        cvar_lower_one_sided=cvar_lower,
        mean_retention_confirmed=mean_confirmed,
        cvar_preference_confirmed=cvar_confirmed,
    )


class BranchCappedRollSolver:
    """Bounded root-action evaluator with fresh independent confirmation."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: GroupTerminalProvider,
        potential_provider: PotentialProvider,
        policy: BranchCappedSolverPolicy,
    ) -> None:
        self.rules = rules
        self.terminal = terminal
        self.potential_provider = potential_provider
        self.policy = policy

    def _safety_ranks(
        self,
        state: GroupRollState,
        risk: RiskConfiguration,
    ) -> tuple[dict[RollAction, int], RollAction]:
        prime = getattr(self.terminal, "prime_banner_objectives", None)
        if prime is not None:
            current = {banner.role: banner for banner in state.banners}
            candidates = list(state.banners)
            for action in legal_actions(state, self.rules):
                if not isinstance(action, RefreshRollAction):
                    candidates.extend(
                        enumerate_mutation_outcomes(
                            current[action.banner_role],
                            action.operation_id,
                            self.rules,
                        )
                    )
            prime(tuple(dict.fromkeys(candidates)), risk)
        ranked = rank_rate_agnostic_actions(
            state,
            self.rules,
            lambda banner: self.terminal.banner_objective(banner, risk).mean,
        )
        return ({item.action: index for index, item in enumerate(ranked)}, ranked[0].action)

    def _sample_transition(
        self,
        state: GroupRollState,
        action: RollAction,
        *,
        model_id: str,
        offer_rng: random.Random,
        mutation_rng: random.Random,
    ) -> GroupRollState:
        replacement_offer = draw_roll_offer(self.rules, model_id, offer_rng)
        if isinstance(action, RefreshRollAction):
            return refresh_transition(state, replacement_offer, self.rules)
        current = next(banner for banner in state.banners if banner.role == action.banner_role)
        realized = sample_mutation(
            current,
            action.operation_id,
            self.rules,
            model_id,
            mutation_rng,
        )
        return apply_realized_transition(
            state,
            action,
            realized,
            replacement_offer,
            self.rules,
        )

    def _rollout(
        self,
        root_state: GroupRollState,
        root_action: RollAction,
        continuation: SynergyContinuationPolicy,
        *,
        model_id: str,
        risk: RiskConfiguration,
        phase: str,
        path_index: int,
    ) -> float:
        state = root_state
        root_identity = _state_identity(root_state)
        step = 0
        while state.remaining_rolls:
            action = root_action if step == 0 else continuation.decide(state)
            offer_rng = random.Random(
                _stream_seed(
                    self.policy.seed,
                    root_identity,
                    model_id,
                    risk.mean_retention_epsilon,
                    phase,
                    path_index,
                    step,
                    "offer",
                )
            )
            mutation_rng = random.Random(
                _stream_seed(
                    self.policy.seed,
                    root_identity,
                    model_id,
                    risk.mean_retention_epsilon,
                    phase,
                    path_index,
                    step,
                    "mutation",
                )
            )
            state = self._sample_transition(
                state,
                action,
                model_id=model_id,
                offer_rng=offer_rng,
                mutation_rng=mutation_rng,
            )
            step += 1
        matched = self.terminal.matched_group(state.banners, risk)
        scenario_index = _stream_seed(
            self.policy.seed,
            root_identity,
            model_id,
            risk.mean_retention_epsilon,
            phase,
            path_index,
            "performance",
        ) % len(matched.outcomes)
        return float(matched.outcomes[scenario_index])

    def decide(
        self,
        state: GroupRollState,
        *,
        model_id: str,
        epsilon: float,
    ) -> SolverDecision:
        validate_group_state(state, self.rules)
        self.rules.model_power(model_id)
        if model_id not in self.policy.transition_models:
            raise SolverPolicyError(f"model {model_id} is outside the frozen P5 scope")
        if epsilon not in self.policy.mean_retention_epsilons:
            raise SolverPolicyError(f"epsilon {epsilon} is outside the frozen P5 frontier")
        if state.remaining_rolls == 0:
            raise SolverEvaluationError("solver cannot decide after all Roll tokens are spent")
        risk = RiskConfiguration(mean_retention_epsilon=epsilon, cvar_alpha=self.policy.cvar_alpha)
        root_tables = {banner.role: self.potential_provider(banner, risk) for banner in state.banners}
        continuation = SynergyContinuationPolicy(
            self.rules,
            self.terminal,
            root_tables,
            risk,
            decay_denominator=self.policy.synergy_potential.decay_denominator,
        ).bind_model(model_id)
        safety_ranks, safety_action = self._safety_ranks(state, risk)
        actions = legal_actions(state, self.rules)
        screen_count = self.policy.decision_budget.screening_paths_per_action
        screening = tuple(
            _summarize_action(
                action,
                "screening",
                tuple(
                    self._rollout(
                        state,
                        action,
                        continuation,
                        model_id=model_id,
                        risk=risk,
                        phase="screening",
                        path_index=path_index,
                    )
                    for path_index in range(screen_count)
                ),
                alpha=self.policy.cvar_alpha,
            )
            for action in actions
        )
        ranked_screening = _rank_estimates(
            screening,
            epsilon=epsilon,
            safety_ranks=safety_ranks,
        )
        finalists = ranked_screening[: min(self.policy.decision_budget.finalist_count, len(actions))]
        confirmation_count = self.policy.decision_budget.confirmation_paths_per_finalist
        confirmation = tuple(
            _summarize_action(
                estimate.action,
                "confirmation",
                tuple(
                    self._rollout(
                        state,
                        estimate.action,
                        continuation,
                        model_id=model_id,
                        risk=risk,
                        phase="confirmation",
                        path_index=path_index,
                    )
                    for path_index in range(confirmation_count)
                ),
                alpha=self.policy.cvar_alpha,
            )
            for estimate in finalists
        )
        ranked_confirmation = _rank_estimates(
            confirmation,
            epsilon=epsilon,
            safety_ranks=safety_ranks,
        )
        preferred = ranked_confirmation[0]
        comparator = ranked_confirmation[1] if len(ranked_confirmation) > 1 else None
        evidence = _paired_resolution_evidence(
            preferred,
            comparator,
            epsilon=epsilon,
            alpha=self.policy.cvar_alpha,
            confidence_level=self.policy.decision_budget.confidence_level,
            bootstrap_replicates=self.policy.decision_budget.bootstrap_replicates,
            seed=_stream_seed(
                self.policy.seed,
                _state_identity(state),
                model_id,
                epsilon,
                "resolution-bootstrap",
            ),
        )
        resolved = evidence.mean_retention_confirmed and evidence.cvar_preference_confirmed
        executed = preferred.action if resolved else safety_action
        reason = (
            "independent confirmation separates the preferred action"
            if resolved
            else "confirmation cannot separate the finalists; use Rate-agnostic safety fallback"
        )
        horizon_fraction = state.remaining_rolls / self.rules.group_rolls
        equivalent_paths = horizon_fraction * (
            len(actions) * screen_count + len(finalists) * confirmation_count
        )
        return SolverDecision(
            preferred_action=preferred.action,
            executed_action=executed,
            resolved=resolved,
            resolution_reason=reason,
            model_id=model_id,
            epsilon=epsilon,
            screening=screening,
            confirmation=confirmation,
            resolution_evidence=evidence,
            full_horizon_equivalent_paths=float(equivalent_paths),
        )


class ExactPotentialProvider:
    """Cache one exact 15,625-row table per observed fixed Stat triple and risk setting."""

    def __init__(
        self,
        evaluator: ExactFixedStatConfigurationEvaluator,
        *,
        maximum_attribute_differences: int = 3,
    ) -> None:
        self.evaluator = evaluator
        self.maximum_attribute_differences = maximum_attribute_differences
        self._cache: dict[tuple[str, tuple[str, ...], str], SynergyPotentialTable] = {}

    def __call__(self, banner: BannerState, risk: RiskConfiguration) -> SynergyPotentialTable:
        stat_ids = tuple(emblem.stat_id for emblem in banner.emblems)
        key = (banner.role, stat_ids, risk.semantic_hash)
        if key not in self._cache:
            values = self.evaluator.evaluate(banner, risk)
            self._cache[key] = build_synergy_potential_table(
                values,
                epsilon=risk.mean_retention_epsilon,
                maximum_attribute_differences=self.maximum_attribute_differences,
            )
        return self._cache[key]


@dataclass(frozen=True)
class SavedSolverState:
    state: GroupRollState
    model_id: str
    epsilon: float
    rule_snapshot_sha256: str
    scenario_sha256: str
    solver_policy_sha256: str
    seed: int

    @property
    def semantic_hash(self) -> str:
        return sha256_json(
            {
                "state_sha256": _state_identity(self.state),
                "model_id": self.model_id,
                "epsilon": self.epsilon,
                "rule_snapshot_sha256": self.rule_snapshot_sha256,
                "scenario_sha256": self.scenario_sha256,
                "solver_policy_sha256": self.solver_policy_sha256,
                "seed": self.seed,
            }
        )


@dataclass(frozen=True)
class WeightedOutcomeDistribution:
    values: np.ndarray = field(repr=False, compare=False)
    weights: np.ndarray = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        values = _readonly_array(self.values, dtype="<f8")
        weights = _readonly_array(self.weights, dtype="<f8")
        if values.ndim != 1 or weights.shape != values.shape or not len(values):
            raise SolverEvaluationError("weighted outcome distribution must be non-empty and aligned")
        if not np.isfinite(values).all() or not np.isfinite(weights).all() or np.any(weights < 0.0):
            raise SolverEvaluationError("weighted outcome distribution must be finite and non-negative")
        total = float(weights.sum())
        if total <= 0.0:
            raise SolverEvaluationError("weighted outcome distribution must have positive mass")
        normalized = _readonly_array(weights / total, dtype="<f8")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "weights", normalized)

    @property
    def mean(self) -> float:
        return float(np.dot(self.values, self.weights))

    def cvar(self, alpha: float) -> float:
        if alpha <= 0.0 or alpha > 1.0:
            raise SolverEvaluationError("weighted CVaR alpha must be in (0, 1]")
        order = np.argsort(self.values, kind="stable")
        values = self.values[order]
        weights = self.weights[order]
        remaining = alpha
        total = 0.0
        for value, weight in zip(values, weights, strict=True):
            used = min(float(weight), remaining)
            total += used * float(value)
            remaining -= used
            if remaining <= 1e-15:
                break
        if remaining > 1e-12:
            raise SolverEvaluationError("weighted CVaR could not fill the requested lower-tail mass")
        return total / alpha


@dataclass(frozen=True)
class ExactOracleActionValue:
    action: RollAction
    distribution: WeightedOutcomeDistribution
    mean: float
    cvar: float


@dataclass(frozen=True)
class ExactOracleDecision:
    selected_action: RollAction | None
    distribution: WeightedOutcomeDistribution
    action_values: tuple[ExactOracleActionValue, ...]
    conditional_offer_schedule: tuple[tuple[int, ...], ...]
    exact_for_declared_condition: Literal[True] = True


def _mixture(
    weighted_distributions: Sequence[tuple[float, WeightedOutcomeDistribution]],
) -> WeightedOutcomeDistribution:
    values = []
    weights = []
    for probability, distribution in weighted_distributions:
        if probability < 0.0:
            raise SolverEvaluationError("mixture probability cannot be negative")
        values.append(distribution.values)
        weights.append(distribution.weights * probability)
    return WeightedOutcomeDistribution(np.concatenate(values), np.concatenate(weights))


def exact_fixed_offer_oracle(
    state: GroupRollState,
    replacement_offers: Sequence[RollOffer],
    *,
    rules: RollRuleSet,
    terminal: GroupTerminalProvider,
    model_id: str,
    risk: RiskConfiguration,
) -> ExactOracleDecision:
    """Solve one-to-three Rolls exactly, conditional on a declared future offer schedule.

    Mutation support, mutation probabilities, downstream actions and common performance scenarios
    are exhaustive.  Future offer randomness is deliberately conditioned, so callers must not
    describe this diagnostic as an unconditional oracle.
    """

    validate_group_state(state, rules)
    rules.model_power(model_id)
    initial_rolls = state.remaining_rolls
    if initial_rolls not in {1, 2, 3}:
        raise SolverEvaluationError("the exact P5 oracle only accepts one to three Rolls remaining")
    offers = tuple(replacement_offers)
    if len(offers) != initial_rolls:
        raise SolverEvaluationError("fixed oracle needs one replacement offer per remaining Roll")
    for offer in offers:
        for operation_id in offer.operation_ids:
            rules.operation(operation_id)

    memo: dict[GroupRollState, ExactOracleDecision] = {}

    def solve(current: GroupRollState) -> ExactOracleDecision:
        if current in memo:
            return memo[current]
        if current.remaining_rolls == 0:
            matched = terminal.matched_group(current.banners, risk)
            probability = np.full(len(matched.outcomes), 1.0 / len(matched.outcomes), dtype=float)
            distribution = WeightedOutcomeDistribution(matched.outcomes, probability)
            result = ExactOracleDecision(
                selected_action=None,
                distribution=distribution,
                action_values=(),
                conditional_offer_schedule=tuple(offer.operation_ids for offer in offers),
            )
            memo[current] = result
            return result

        schedule_index = initial_rolls - current.remaining_rolls
        replacement_offer = offers[schedule_index]
        current_banners = {banner.role: banner for banner in current.banners}
        action_values = []
        for action in legal_actions(current, rules):
            if isinstance(action, RefreshRollAction):
                child = refresh_transition(current, replacement_offer, rules)
                distribution = solve(child).distribution
            else:
                branches = []
                for outcome in mutation_distribution(
                    current_banners[action.banner_role],
                    action.operation_id,
                    rules,
                    model_id,
                ):
                    child = apply_realized_transition(
                        current,
                        action,
                        outcome.banner,
                        replacement_offer,
                        rules,
                    )
                    branches.append((outcome.probability, solve(child).distribution))
                distribution = _mixture(branches)
            action_values.append(
                ExactOracleActionValue(
                    action=action,
                    distribution=distribution,
                    mean=distribution.mean,
                    cvar=distribution.cvar(risk.cvar_alpha),
                )
            )
        maximum_mean = max(item.mean for item in action_values)
        floor = maximum_mean - abs(maximum_mean) * risk.mean_retention_epsilon - 1e-12
        eligible = [item for item in action_values if item.mean >= floor]
        selected = min(
            eligible,
            key=lambda item: (-item.cvar, -item.mean, _action_identity(item.action)),
        )
        result = ExactOracleDecision(
            selected_action=selected.action,
            distribution=selected.distribution,
            action_values=tuple(action_values),
            conditional_offer_schedule=tuple(offer.operation_ids for offer in offers),
        )
        memo[current] = result
        return result

    return solve(state)
