"""Standalone validation for frozen human Group Roll playbooks.

The validation route compares only preregistered manual candidates and rule ablations.  It does
not import, invoke, or inspect the Reference Roll solver.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Literal

import numpy as np
from pydantic import Field, model_validator

from ti_predictor.fantasy.playbook import (
    PlaybookDefinition,
    PlaybookPolicy,
    StatPriority,
    StrictModel,
)
from ti_predictor.fantasy.roll import (
    BannerState,
    EmblemState,
    GroupRollState,
    RefreshRollAction,
    RollOffer,
    RollRuleSet,
    apply_realized_transition,
    draw_roll_offer,
    refresh_transition,
    sample_mutation,
)
from ti_predictor.fantasy.scenarios import CommonScenarioSet, PoolBuildResult, ScenarioDraws
from ti_predictor.fantasy.scoring import Emblem, emblem_multipliers
from ti_predictor.fantasy.valuation import (
    RiskConfiguration,
    TerminalValueCache,
    distribution_summary,
    evaluate_stat_teams,
)
from ti_predictor.hashing import sha256_json

ROLE_ORDER = ("core", "mid", "support")
READINESS_LEVELS = ("low", "middle", "high")
FIXED_START_OFFERS = (
    (23, 31, 11),
    (24, 25, 13),
    (9, 28, 17),
    (10, 26, 14),
    (12, 29, 15),
    (16, 27, 33),
    (23, 30, 32),
    (24, 11, 13),
    (9, 14, 17),
)


class PlaybookValidationPolicy(StrictModel):
    schema_version: Literal[1]
    policy_id: str
    period: Literal["group"]
    as_of: str
    seed: int
    source_scenario_policy_id: str
    scenario_subset_count: int = Field(ge=128)
    scenario_subset_sampling: Literal["fixed_without_replacement"]
    full_session_replicates_per_stratum: int = Field(ge=2)
    screening_replicates_per_stratum: int = Field(ge=0)
    confirmation_replicates_per_stratum: int = Field(ge=2)
    ablation_replicates_per_stratum: int = Field(ge=2)
    rolls_per_session: Literal[40]
    candidate_rule_counts: tuple[Literal[8, 12, 16], ...]
    published_rule_count: Literal[12]
    risk_preference: Literal["mean-first", "default-knee", "downside-first"]
    mean_retention_epsilons: tuple[float, ...]
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    common_session_frequency: float = Field(gt=0.0, lt=1.0)
    baseline_material_loss: float = Field(gt=0.0, lt=1.0)
    strict_material_loss: float = Field(gt=0.0, lt=1.0)
    confidence_level: float = Field(gt=0.5, lt=1.0)
    bootstrap_replicates: int = Field(ge=100)
    primary_model: str
    transition_variants: tuple[str, ...]
    release_scope: dict[str, tuple[str, ...]]
    sensitivity_scope: dict[str, tuple[str, ...]]
    runtime_target_seconds: int = Field(gt=0)
    runtime_hard_ceiling_seconds: int = Field(gt=0)
    stop_new_computation_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_contract(self) -> PlaybookValidationPolicy:
        if self.candidate_rule_counts != (8, 12, 16):
            raise ValueError("validation candidates must be the frozen 8/12/16 frontier")
        if self.screening_replicates_per_stratum + self.confirmation_replicates_per_stratum != (
            self.full_session_replicates_per_stratum
        ):
            raise ValueError("screening and confirmation replicates must partition full sessions")
        if self.ablation_replicates_per_stratum > self.confirmation_replicates_per_stratum:
            raise ValueError("ablations must fit inside the fresh confirmation replicate range")
        if self.mean_retention_epsilons != (0.0, 0.01, 0.02, 0.05):
            raise ValueError("P4 must report the preregistered 0/1/2/5 percent epsilon frontier")
        if self.strict_material_loss >= self.baseline_material_loss:
            raise ValueError("strict material-loss threshold must be below the baseline threshold")
        if not (
            self.runtime_target_seconds
            < self.stop_new_computation_seconds
            < self.runtime_hard_ceiling_seconds
        ):
            raise ValueError("runtime target, stop-new-work point and hard ceiling are inconsistent")
        expected_models = (self.primary_model, *self.transition_variants)
        if self.release_scope != {
            "rate-agnostic": expected_models,
            "primary-model": (self.primary_model,),
        }:
            raise ValueError("playbook release scopes differ from the frozen model contract")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


@dataclass(frozen=True)
class RoleCoverageCell:
    role: str
    stat_readiness: str
    configuration_readiness: str
    banner: BannerState
    stat_readiness_ratio: float
    configuration_readiness_ratio: float


@dataclass(frozen=True)
class StartingCoverageCase:
    case_id: str
    state: GroupRollState
    role_cells: tuple[RoleCoverageCell, ...]


@dataclass(frozen=True)
class StartingReadinessEvaluator:
    """Exact same-team Expected-value ranking used only to build coverage labels."""

    rules: RollRuleSet
    canonical_rules: dict[str, Any]
    team_ids: tuple[int, ...]
    stat_team_means: Mapping[tuple[str, str], np.ndarray] = field(repr=False, compare=False)

    @classmethod
    def from_scenarios(
        cls,
        pool_result: PoolBuildResult,
        scenario_set: CommonScenarioSet,
        rules: RollRuleSet,
        canonical_rules: dict[str, Any],
    ) -> StartingReadinessEvaluator:
        means = {}
        for role in ROLE_ORDER:
            for color in set(rules.colors_for(role)[:3]):
                for stat_id in rules.stats_for(color):
                    matrix = evaluate_stat_teams(
                        pool_result,
                        scenario_set,
                        role=role,
                        stat_id=stat_id,
                    )
                    means[(role, stat_id)] = matrix.outcomes.mean(axis=1)
        return cls(
            rules=rules,
            canonical_rules=canonical_rules,
            team_ids=scenario_set.team_ids,
            stat_team_means=means,
        )

    def stat_value(self, role: str, stats: Sequence[str]) -> float:
        team_values = sum(
            (self.stat_team_means[(role, stat_id)] for stat_id in stats),
            start=np.zeros(len(self.team_ids), dtype=float),
        )
        return float(team_values.max())

    def configuration_value(self, banner: BannerState) -> float:
        emblems = [
            Emblem(
                stat_id=state.stat_id,
                color=self.rules.color_for_stat(state.stat_id),
                quality_tier=state.quality_tier,
                trait=state.trait_id,
            )
            for state in banner.emblems
        ]
        multipliers = emblem_multipliers(emblems, self.canonical_rules)
        team_values = sum(
            (
                self.stat_team_means[(banner.role, state.stat_id)] * multiplier
                for state, multiplier in zip(banner.emblems, multipliers, strict=True)
            ),
            start=np.zeros(len(self.team_ids), dtype=float),
        )
        return float(team_values.max())


@dataclass(frozen=True)
class SessionKey:
    model_id: str
    case_id: str
    replicate: int


@dataclass(frozen=True)
class SessionTrace:
    key: SessionKey
    terminal_banners: tuple[BannerState, ...]
    rule_activations: tuple[tuple[str, int], ...]
    fallback_count: int
    action_sequence: tuple[str, ...] = field(repr=False)
    offer_sequence: tuple[tuple[int, ...], ...] = field(repr=False)

    @property
    def situations(self) -> tuple[str, ...]:
        values = [rule_id for rule_id, count in self.rule_activations if count > 0]
        if self.fallback_count:
            values.append("fallback")
        return tuple(values)


@dataclass(frozen=True)
class ScoredSession:
    key: SessionKey
    epsilon: float
    score: float
    selected_team_ids: tuple[int, ...]
    situations: tuple[str, ...]
    action_sequence: tuple[str, ...] = field(repr=False)


def load_playbook_validation_policy(path) -> PlaybookValidationPolicy:
    return PlaybookValidationPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _seed(base_seed: int, *parts: Any) -> int:
    payload = ":".join([str(base_seed), *(str(part) for part in parts)]).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little", signed=False)


def subset_common_scenarios(
    source: CommonScenarioSet,
    *,
    count: int,
    seed: int,
) -> CommonScenarioSet:
    """Select an immutable fixed validation subset while preserving shared scenario pairing."""

    if count > len(source.scenario_ids):
        raise ValueError("validation Scenario subset exceeds the governed P3 Scenario set")
    rng = np.random.default_rng(_seed(seed, "scenario-subset"))
    selected = np.sort(rng.choice(len(source.scenario_ids), size=count, replace=False))
    draws = tuple(
        ScenarioDraws(
            target_team_id=item.target_team_id,
            role=item.role,
            pool_sha256=item.pool_sha256,
            block_indexes=item.block_indexes[selected],
        )
        for item in source.draws
    )
    return CommonScenarioSet(
        policy_id=f"{source.policy_id}:p4-fixed-{count}",
        data_snapshot_sha256=source.data_snapshot_sha256,
        as_of=source.as_of,
        seed=seed,
        team_ids=source.team_ids,
        scenario_ids=np.arange(count, dtype=np.int64),
        group_categories=source.group_categories[selected],
        series_counts=source.series_counts[selected],
        draws=draws,
    )


def _rank_representatives(values: Sequence[tuple[float, Any]]) -> tuple[tuple[float, Any], ...]:
    if len(values) < 6:
        raise ValueError("readiness ranking needs at least six legal configurations")
    ordered = sorted(values, key=lambda item: (item[0], repr(item[1])))
    indexes = (len(ordered) // 6, len(ordered) // 2, 5 * len(ordered) // 6)
    return tuple(ordered[index] for index in indexes)


def _stat_representatives(
    role: str,
    rules: RollRuleSet,
    readiness: StartingReadinessEvaluator,
) -> tuple[tuple[float, tuple[str, ...]], ...]:
    stat_choices = [rules.stats_for(color) for color in rules.colors_for(role)[:3]]
    candidates = []
    for stats in product(*stat_choices):
        value = readiness.stat_value(role, stats)
        candidates.append((float(value), tuple(stats)))
    return _rank_representatives(candidates)


def _configuration_representatives(
    role: str,
    stats: tuple[str, ...],
    policy: PlaybookPolicy,
    readiness: StartingReadinessEvaluator,
) -> tuple[tuple[float, tuple[tuple[int, ...], tuple[str, ...]]], ...]:
    candidates = []
    for qualities in product(range(1, 6), repeat=3):
        for traits in product(policy.rules.traits, repeat=3):
            banner = BannerState(
                role=role,
                emblems=tuple(
                    EmblemState(stat_id=stat_id, quality_tier=quality, trait_id=trait)
                    for stat_id, quality, trait in zip(stats, qualities, traits, strict=True)
                ),
            )
            candidates.append((readiness.configuration_value(banner), (tuple(qualities), tuple(traits))))
    return _rank_representatives(candidates)


def build_starting_coverage_suite(
    policy: PlaybookPolicy,
    readiness: StartingReadinessEvaluator,
) -> tuple[StartingCoverageCase, ...]:
    """Build nine balanced full starts covering all 3×3 readiness cells for every role."""

    role_cells: dict[str, list[RoleCoverageCell]] = {}
    for role in ROLE_ORDER:
        stat_candidates = []
        all_stat_values = []
        choices = [policy.rules.stats_for(color) for color in policy.rules.colors_for(role)[:3]]
        for stats in product(*choices):
            value = readiness.stat_value(role, stats)
            all_stat_values.append(float(value))
        stat_max = max(all_stat_values)
        for stat_level, (stat_value, stats) in zip(
            READINESS_LEVELS,
            _stat_representatives(role, policy.rules, readiness),
            strict=True,
        ):
            configurations = _configuration_representatives(role, stats, policy, readiness)
            config_values = []
            for qualities in product(range(1, 6), repeat=3):
                for traits in product(policy.rules.traits, repeat=3):
                    banner = BannerState(
                        role=role,
                        emblems=tuple(
                            EmblemState(stat_id=stat_id, quality_tier=quality, trait_id=trait)
                            for stat_id, quality, trait in zip(stats, qualities, traits, strict=True)
                        ),
                    )
                    config_values.append(readiness.configuration_value(banner))
            config_max = max(config_values)
            for config_level, (config_value, (qualities, traits)) in zip(
                READINESS_LEVELS,
                configurations,
                strict=True,
            ):
                banner = BannerState(
                    role=role,
                    emblems=tuple(
                        EmblemState(stat_id=stat_id, quality_tier=quality, trait_id=trait)
                        for stat_id, quality, trait in zip(stats, qualities, traits, strict=True)
                    ),
                )
                stat_ratio = stat_value / max(stat_max, 1e-12)
                config_ratio = config_value / max(config_max, 1e-12)
                stat_candidates.append(
                    RoleCoverageCell(
                        role=role,
                        stat_readiness=stat_level,
                        configuration_readiness=config_level,
                        banner=banner,
                        stat_readiness_ratio=float(stat_ratio),
                        configuration_readiness_ratio=float(config_ratio),
                    )
                )
        if len(stat_candidates) != 9:
            raise AssertionError("each role must expose exactly nine readiness cells")
        role_cells[role] = stat_candidates

    cases = []
    rotations = {"core": 0, "mid": 3, "support": 6}
    for index, offer_ids in enumerate(FIXED_START_OFFERS):
        cells = tuple(role_cells[role][(index + rotations[role]) % 9] for role in ROLE_ORDER)
        cases.append(
            StartingCoverageCase(
                case_id=f"coverage-{index + 1:02d}",
                state=GroupRollState(
                    banners=tuple(cell.banner for cell in cells),
                    offer=RollOffer(offer_ids),
                    remaining_rolls=40,
                ),
                role_cells=cells,
            )
        )
    for role in ROLE_ORDER:
        labels = {
            (cell.stat_readiness, cell.configuration_readiness)
            for case in cases
            for cell in case.role_cells
            if cell.role == role
        }
        if labels != set(product(READINESS_LEVELS, repeat=2)):
            raise AssertionError(f"coverage balancing failed for {role}")
    return tuple(cases)


def simulate_playbook_session(
    policy: PlaybookPolicy,
    start: StartingCoverageCase,
    *,
    model_id: str,
    replicate: int,
    seed: int,
    candidate_rule_count: Literal[8, 12, 16],
    risk_preference: str,
    omit_rule_id: str | None = None,
) -> SessionTrace:
    state = start.state
    activations: Counter[str] = Counter()
    fallback_count = 0
    action_sequence = []
    offer_sequence = [state.offer.operation_ids]
    while state.remaining_rolls:
        decision = policy.decide(
            state,
            candidate_rule_count=candidate_rule_count,
            risk_preference=risk_preference,
            omit_rule_id=omit_rule_id,
        )
        step = 40 - state.remaining_rolls
        offer_rng = random.Random(_seed(seed, model_id, start.case_id, replicate, step, "offer"))
        replacement_offer = draw_roll_offer(policy.rules, model_id, offer_rng)
        if isinstance(decision.action, RefreshRollAction):
            fallback_count += 1
            action_sequence.append("refresh")
            state = refresh_transition(state, replacement_offer, policy.rules)
        else:
            if decision.rule_id is None:
                raise AssertionError("applied playbook action has no frozen rule identity")
            activations[decision.rule_id] += 1
            action_sequence.append(f"{decision.action.banner_role}:{decision.action.operation_id}")
            mutation_rng = random.Random(_seed(seed, model_id, start.case_id, replicate, step, "mutation"))
            current_banner = next(
                banner for banner in state.banners if banner.role == decision.action.banner_role
            )
            realized = sample_mutation(
                current_banner,
                decision.action.operation_id,
                policy.rules,
                model_id,
                mutation_rng,
            )
            state = apply_realized_transition(
                state,
                decision.action,
                realized,
                replacement_offer,
                policy.rules,
            )
        offer_sequence.append(state.offer.operation_ids)
    return SessionTrace(
        key=SessionKey(model_id=model_id, case_id=start.case_id, replicate=replicate),
        terminal_banners=state.banners,
        rule_activations=tuple(sorted(activations.items())),
        fallback_count=fallback_count,
        action_sequence=tuple(action_sequence),
        offer_sequence=tuple(offer_sequence),
    )


class ExactTerminalScorer:
    """Cache exact P3 terminal matrices and sample paired Group-performance scenarios."""

    def __init__(
        self,
        pool_result: PoolBuildResult,
        scenario_set: CommonScenarioSet,
        canonical_rules: dict[str, Any],
        *,
        seed: int,
        cvar_alpha: float,
    ) -> None:
        self.pool_result = pool_result
        self.scenario_set = scenario_set
        self.canonical_rules = canonical_rules
        self.seed = seed
        self.cvar_alpha = cvar_alpha
        self.cache = TerminalValueCache()

    def score(self, trace: SessionTrace, epsilon: float) -> ScoredSession:
        matrices = {
            banner.role: self.cache.banner(
                self.pool_result,
                self.scenario_set,
                banner,
                self.canonical_rules,
            )
            for banner in trace.terminal_banners
        }
        matched = self.cache.matched_group(
            matrices,
            RiskConfiguration(mean_retention_epsilon=epsilon, cvar_alpha=self.cvar_alpha),
        )
        scenario_index = _seed(
            self.seed,
            trace.key.model_id,
            trace.key.case_id,
            trace.key.replicate,
            "performance",
        ) % len(self.scenario_set.scenario_ids)
        return ScoredSession(
            key=trace.key,
            epsilon=epsilon,
            score=float(matched.outcomes[scenario_index]),
            selected_team_ids=matched.selected_team_ids,
            situations=trace.situations,
            action_sequence=trace.action_sequence,
        )


def _summary(scores: Sequence[float], *, alpha: float) -> dict[str, float]:
    if not scores:
        raise ValueError("cannot summarize an empty playbook score set")
    return distribution_summary(np.asarray(scores, dtype=float), cvar_alpha=alpha)


def _bootstrap_difference_interval(
    preferred: Sequence[float],
    comparator: Sequence[float],
    *,
    alpha: float,
    confidence_level: float,
    replicates: int,
    seed: int,
) -> dict[str, float]:
    left = np.asarray(preferred, dtype=float)
    right = np.asarray(comparator, dtype=float)
    if left.shape != right.shape or not len(left):
        raise ValueError("paired bootstrap requires non-empty aligned score vectors")
    point_mean = float(left.mean() - right.mean())
    point_cvar = float(
        distribution_summary(left, cvar_alpha=alpha)["cvar"]
        - distribution_summary(right, cvar_alpha=alpha)["cvar"]
    )
    rng = np.random.default_rng(seed)
    mean_samples = np.empty(replicates, dtype=float)
    cvar_samples = np.empty(replicates, dtype=float)
    for replicate in range(replicates):
        indexes = rng.integers(len(left), size=len(left), endpoint=False)
        sample_left = left[indexes]
        sample_right = right[indexes]
        mean_samples[replicate] = sample_left.mean() - sample_right.mean()
        cvar_samples[replicate] = (
            distribution_summary(sample_left, cvar_alpha=alpha)["cvar"]
            - distribution_summary(sample_right, cvar_alpha=alpha)["cvar"]
        )
    tail = 1.0 - confidence_level
    return {
        "sample_count": int(len(left)),
        "mean_difference": point_mean,
        "mean_lower_one_sided": float(np.quantile(mean_samples, tail)),
        "mean_upper_one_sided": float(np.quantile(mean_samples, confidence_level)),
        "cvar10_difference": point_cvar,
        "cvar10_lower_one_sided": float(np.quantile(cvar_samples, tail)),
        "cvar10_upper_one_sided": float(np.quantile(cvar_samples, confidence_level)),
    }


def _conditional_loss_bounds(
    published: Sequence[float],
    comparator: Sequence[float],
    *,
    alpha: float,
    confidence_level: float,
    replicates: int,
    seed: int,
) -> dict[str, float]:
    difference = _bootstrap_difference_interval(
        comparator,
        published,
        alpha=alpha,
        confidence_level=confidence_level,
        replicates=replicates,
        seed=seed,
    )
    comparator_summary = _summary(comparator, alpha=alpha)
    mean_scale = max(abs(comparator_summary["mean"]), 1e-12)
    cvar_scale = max(abs(comparator_summary["cvar"]), 1e-12)
    return {
        **difference,
        "mean_loss_fraction": difference["mean_difference"] / mean_scale,
        "mean_loss_upper95_fraction": difference["mean_upper_one_sided"] / mean_scale,
        "cvar10_loss_fraction": difference["cvar10_difference"] / cvar_scale,
        "cvar10_loss_upper95_fraction": difference["cvar10_upper_one_sided"] / cvar_scale,
    }


def _score_map(values: Sequence[ScoredSession]) -> dict[SessionKey, ScoredSession]:
    result = {item.key: item for item in values}
    if len(result) != len(values):
        raise ValueError("scored playbook sessions repeat a pairing key")
    return result


def _paired_vectors(
    left: Sequence[ScoredSession],
    right: Sequence[ScoredSession],
    *,
    predicate: Callable[[ScoredSession], bool] | None = None,
) -> tuple[list[float], list[float]]:
    left_map = _score_map(left)
    right_map = _score_map(right)
    keys = sorted(set(left_map) & set(right_map), key=lambda key: (key.model_id, key.case_id, key.replicate))
    if predicate is not None:
        keys = [key for key in keys if predicate(left_map[key])]
    return [left_map[key].score for key in keys], [right_map[key].score for key in keys]


def _trace_summary(traces: Sequence[SessionTrace]) -> dict[str, Any]:
    activations: Counter[str] = Counter()
    sessions_with: Counter[str] = Counter()
    fallback = 0
    for trace in traces:
        fallback += trace.fallback_count
        for rule_id, count in trace.rule_activations:
            activations[rule_id] += count
            sessions_with[rule_id] += 1
        if trace.fallback_count:
            sessions_with["fallback"] += 1
    session_count = len(traces)
    return {
        "session_count": session_count,
        "rule_activation_counts": dict(sorted(activations.items())),
        "session_activation_frequency": {
            key: value / session_count for key, value in sorted(sessions_with.items())
        },
        "fallback_decision_frequency": fallback / (session_count * 40),
        "fallback_session_frequency": sessions_with["fallback"] / session_count,
    }


def validate_frozen_playbooks(
    definitions: Sequence[PlaybookDefinition],
    roll_rules: RollRuleSet,
    canonical_rules: dict[str, Any],
    priorities: Sequence[StatPriority],
    pool_result: PoolBuildResult,
    source_scenario_set: CommonScenarioSet,
    validation: PlaybookValidationPolicy,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the preregistered manual-only 40-Roll validation and return JSON-safe evidence."""

    notify = progress or (lambda message: None)
    by_edition = {definition.edition: definition for definition in definitions}
    if set(by_edition) != {"rate-agnostic", "primary-model"}:
        raise ValueError("P4 requires one frozen definition for each playbook edition")
    policies = {
        edition: PlaybookPolicy(definition, roll_rules, canonical_rules, priorities)
        for edition, definition in by_edition.items()
    }
    scenario_set = subset_common_scenarios(
        source_scenario_set,
        count=validation.scenario_subset_count,
        seed=validation.seed,
    )
    readiness = StartingReadinessEvaluator.from_scenarios(
        pool_result,
        scenario_set,
        roll_rules,
        canonical_rules,
    )
    coverage = build_starting_coverage_suite(policies["rate-agnostic"], readiness)
    scorer = ExactTerminalScorer(
        pool_result,
        scenario_set,
        canonical_rules,
        seed=validation.seed,
        cvar_alpha=validation.cvar_alpha,
    )
    all_models = (validation.primary_model, *validation.transition_variants)
    traces: dict[tuple[str, int, str], list[SessionTrace]] = {}
    scores: dict[tuple[str, int, str, float], list[ScoredSession]] = {}
    for edition, policy in policies.items():
        for candidate_count in validation.candidate_rule_counts:
            for model_id in all_models:
                key = (edition, candidate_count, model_id)
                notify(f"P4 sessions {edition} rules={candidate_count} model={model_id}")
                batch = [
                    simulate_playbook_session(
                        policy,
                        case,
                        model_id=model_id,
                        replicate=replicate,
                        seed=validation.seed,
                        candidate_rule_count=candidate_count,
                        risk_preference=validation.risk_preference,
                    )
                    for case in coverage
                    for replicate in range(validation.full_session_replicates_per_stratum)
                ]
                traces[key] = batch
                confirmation = [
                    trace
                    for trace in batch
                    if trace.key.replicate >= validation.screening_replicates_per_stratum
                ]
                for epsilon in validation.mean_retention_epsilons:
                    notify(
                        f"P4 terminal {edition} rules={candidate_count} model={model_id} "
                        f"epsilon={epsilon:.2f}"
                    )
                    scores[(*key, epsilon)] = [scorer.score(trace, epsilon) for trace in confirmation]

    summaries = []
    for (edition, candidate_count, model_id, epsilon), batch in scores.items():
        for case in coverage:
            values = [item.score for item in batch if item.key.case_id == case.case_id]
            summaries.append(
                {
                    "edition": edition,
                    "candidate_rule_count": candidate_count,
                    "model_id": model_id,
                    "epsilon": epsilon,
                    "scope": case.case_id,
                    **_summary(values, alpha=validation.cvar_alpha),
                }
            )
        summaries.append(
            {
                "edition": edition,
                "candidate_rule_count": candidate_count,
                "model_id": model_id,
                "epsilon": epsilon,
                "scope": "balanced-coverage-diagnostic-not-population",
                **_summary([item.score for item in batch], alpha=validation.cvar_alpha),
            }
        )

    activation = [
        {
            "edition": edition,
            "candidate_rule_count": count,
            "model_id": model,
            **_trace_summary(batch),
        }
        for (edition, count, model), batch in traces.items()
    ]

    common_losses = []
    for edition in policies:
        for model_id in validation.release_scope[edition]:
            published = scores[(edition, 12, model_id, 0.0)]
            comparator = scores[(edition, 16, model_id, 0.0)]
            for case in coverage:
                case_published = [item for item in published if item.key.case_id == case.case_id]
                case_comparator = [item for item in comparator if item.key.case_id == case.case_id]
                for situation in (*[rule.rule_id for rule in by_edition[edition].rules[:12]], "fallback"):
                    activated = [item for item in case_published if situation in item.situations]
                    frequency = len(activated) / len(case_published)
                    if frequency < validation.common_session_frequency:
                        continue
                    left, right = _paired_vectors(
                        case_published,
                        case_comparator,
                        predicate=lambda item, selected=situation: selected in item.situations,
                    )
                    common_losses.append(
                        {
                            "edition": edition,
                            "model_id": model_id,
                            "case_id": case.case_id,
                            "situation": situation,
                            "session_frequency": frequency,
                            **_conditional_loss_bounds(
                                left,
                                right,
                                alpha=validation.cvar_alpha,
                                confidence_level=validation.confidence_level,
                                replicates=validation.bootstrap_replicates,
                                seed=_seed(
                                    validation.seed,
                                    "common-loss",
                                    edition,
                                    model_id,
                                    case.case_id,
                                    situation,
                                ),
                            ),
                        }
                    )

    ablations = []
    confirmation_start = validation.full_session_replicates_per_stratum - (
        validation.ablation_replicates_per_stratum
    )
    for edition, policy in policies.items():
        for model_id in validation.release_scope[edition]:
            full = [
                item
                for item in scores[(edition, 12, model_id, 0.0)]
                if item.key.replicate >= confirmation_start
            ]
            for rule in by_edition[edition].rules[:12]:
                notify(f"P4 ablation {edition} {model_id} omit={rule.rule_id}")
                omitted_traces = [
                    simulate_playbook_session(
                        policy,
                        case,
                        model_id=model_id,
                        replicate=replicate,
                        seed=validation.seed,
                        candidate_rule_count=12,
                        risk_preference=validation.risk_preference,
                        omit_rule_id=rule.rule_id,
                    )
                    for case in coverage
                    for replicate in range(
                        confirmation_start,
                        validation.full_session_replicates_per_stratum,
                    )
                ]
                omitted = [scorer.score(trace, 0.0) for trace in omitted_traces]
                full_values, omitted_values = _paired_vectors(full, omitted)
                interval = _bootstrap_difference_interval(
                    full_values,
                    omitted_values,
                    alpha=validation.cvar_alpha,
                    confidence_level=validation.confidence_level,
                    replicates=validation.bootstrap_replicates,
                    seed=_seed(validation.seed, "ablation", edition, model_id, rule.rule_id),
                )
                ablations.append(
                    {
                        "edition": edition,
                        "model_id": model_id,
                        "rule_id": rule.rule_id,
                        **interval,
                        "no_loss_supported": interval["mean_lower_one_sided"] >= 0.0
                        and interval["cvar10_lower_one_sided"] >= 0.0,
                        "strict_point_improvement": interval["mean_difference"] > 0.0
                        or interval["cvar10_difference"] > 0.0,
                    }
                )

    complexity = []
    diagnostic_scope = "balanced-coverage-diagnostic-not-population"
    for edition in policies:
        for model_id in all_models:
            for epsilon in validation.mean_retention_epsilons:
                rows = [
                    row
                    for row in summaries
                    if row["edition"] == edition
                    and row["model_id"] == model_id
                    and row["epsilon"] == epsilon
                    and row["scope"] == diagnostic_scope
                ]
                best_mean = max(float(row["mean"]) for row in rows)
                best_cvar = max(float(row["cvar"]) for row in rows)
                complexity.append(
                    {
                        "edition": edition,
                        "model_id": model_id,
                        "epsilon": epsilon,
                        "candidates": [
                            {
                                "rule_count": row["candidate_rule_count"],
                                "mean_loss_from_best": (best_mean - float(row["mean"]))
                                / max(abs(best_mean), 1e-12),
                                "cvar10_loss_from_best": (best_cvar - float(row["cvar"]))
                                / max(abs(best_cvar), 1e-12),
                                "within_1_percent": float(row["mean"]) >= 0.99 * best_mean
                                and float(row["cvar"]) >= 0.99 * best_cvar,
                                "within_2_percent": float(row["mean"]) >= 0.98 * best_mean
                                and float(row["cvar"]) >= 0.98 * best_cvar,
                                "within_5_percent": float(row["mean"]) >= 0.95 * best_mean
                                and float(row["cvar"]) >= 0.95 * best_cvar,
                            }
                            for row in sorted(rows, key=lambda item: item["candidate_rule_count"])
                        ],
                    }
                )

    disagreement = []
    for model_id in all_models:
        left = traces[("rate-agnostic", 12, model_id)]
        right = traces[("primary-model", 12, model_id)]
        right_map = {trace.key: trace for trace in right}
        compared = [(trace, right_map[trace.key]) for trace in left]
        disagreement.append(
            {
                "model_id": model_id,
                "session_count": len(compared),
                "session_disagreement_frequency": sum(
                    first.action_sequence != second.action_sequence for first, second in compared
                )
                / len(compared),
                "first_decision_disagreement_frequency": sum(
                    first.action_sequence[0] != second.action_sequence[0] for first, second in compared
                )
                / len(compared),
            }
        )

    gate = {}
    for edition in policies:
        scoped_losses = [row for row in common_losses if row["edition"] == edition]
        scoped_ablations = [row for row in ablations if row["edition"] == edition]
        baseline_failures = [
            row
            for row in scoped_losses
            if max(row["mean_loss_upper95_fraction"], row["cvar10_loss_upper95_fraction"])
            > validation.baseline_material_loss
        ]
        strict_failures = [
            row
            for row in scoped_losses
            if max(row["mean_loss_upper95_fraction"], row["cvar10_loss_upper95_fraction"])
            > validation.strict_material_loss
        ]
        ablation_failures = [
            row
            for row in scoped_ablations
            if not (row["no_loss_supported"] and row["strict_point_improvement"])
        ]
        if not scoped_losses:
            status = "unresolved"
        elif baseline_failures or ablation_failures:
            status = "draft"
        elif strict_failures:
            status = "baseline-reliable"
        else:
            status = "strict-reliable"
        gate[edition] = {
            "p4_status": status,
            "common_situation_count": len(scoped_losses),
            "baseline_10_percent_failure_count": len(baseline_failures),
            "strict_5_percent_failure_count": len(strict_failures),
            "rule_ablation_failure_count": len(ablation_failures),
            "baseline_failures": [
                {
                    "model_id": row["model_id"],
                    "case_id": row["case_id"],
                    "situation": row["situation"],
                }
                for row in baseline_failures
            ],
            "ablation_failures": [row["rule_id"] for row in ablation_failures],
        }

    coverage_payload = [
        {
            "case_id": case.case_id,
            "offer_operation_ids": list(case.state.offer.operation_ids),
            "roles": [
                {
                    "role": cell.role,
                    "stat_readiness": cell.stat_readiness,
                    "configuration_readiness": cell.configuration_readiness,
                    "stat_readiness_ratio": cell.stat_readiness_ratio,
                    "configuration_readiness_ratio": cell.configuration_readiness_ratio,
                    "emblems": [
                        {
                            "stat_id": emblem.stat_id,
                            "quality_tier": emblem.quality_tier,
                            "trait_id": emblem.trait_id,
                        }
                        for emblem in cell.banner.emblems
                    ],
                }
                for cell in case.role_cells
            ],
        }
        for case in coverage
    ]
    payload = {
        "schema_version": 1,
        "artifact_type": "group_fantasy_playbook_standalone_validation",
        "as_of": validation.as_of,
        "seed": validation.seed,
        "validation_policy": validation.model_dump(mode="json"),
        "validation_policy_sha256": validation.semantic_hash,
        "source_scenario_sha256": source_scenario_set.semantic_hash,
        "validation_scenario_sha256": scenario_set.semantic_hash,
        "starting_readiness_method": "exact_same_team_expected_value_rank_thirds",
        "playbooks": {
            edition: {
                "playbook_id": definition.playbook_id,
                "semantic_sha256": definition.semantic_hash,
                "source_evidence_sha256": definition.source_evidence_sha256,
            }
            for edition, definition in by_edition.items()
        },
        "coverage_suite": coverage_payload,
        "score_summaries": summaries,
        "activation": activation,
        "manual_complexity_frontier": complexity,
        "common_situation_conditional_loss": common_losses,
        "rule_ablations": ablations,
        "rate_sensitive_disagreement": disagreement,
        "gate": gate,
        "limitations": [
            "Balanced coverage averages are diagnostics, not a population-weighted "
            "starting-state expectation.",
            "Standalone material loss uses the independently frozen 16-rule candidate, not the P5 solver.",
            "Coach remains unavailable/excluded and is not interpreted as a zero-bonus title.",
        ],
    }
    payload["evidence_sha256"] = sha256_json(payload)
    return payload
