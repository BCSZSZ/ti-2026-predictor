"""Three frozen policy families for isolated Main Roll simulation research."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, replace
from itertools import combinations, permutations, product
from typing import Any

import numpy as np

from ti_predictor.fantasy.main_roll import (
    MainRollState,
    apply_realized_transition,
    legal_actions,
    refresh_transition,
)
from ti_predictor.fantasy.main_roll_research_contract import (
    GreedyStrategySpec,
    HybridStrategySpec,
    TargetStrategySpec,
)
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import (
    STOP,
    MainResearchTerminal,
    PolicyDecision,
    ResearchAction,
    StopRollAction,
    TerminalEvaluation,
    action_identity,
    state_sha256,
)
from ti_predictor.fantasy.roll import (
    REFRESH,
    ApplyRollAction,
    BannerState,
    RefreshRollAction,
    RollRuleSet,
)
from ti_predictor.hashing import sha256_json


class MainResearchStrategyError(ValueError):
    """A research strategy cannot produce a reproducible legal decision."""


def weighted_lower_tail_cvar(
    values: np.ndarray,
    weights: np.ndarray,
    alpha: float,
) -> float:
    numeric = np.asarray(values, dtype=float).reshape(-1)
    probability = np.asarray(weights, dtype=float).reshape(-1)
    if (
        len(numeric) != len(probability)
        or not len(numeric)
        or not np.isfinite(numeric).all()
        or not np.isfinite(probability).all()
        or np.any(probability < 0.0)
        or not 0.0 < alpha <= 1.0
    ):
        raise MainResearchStrategyError("weighted CVaR requires aligned finite values and weights")
    total = float(probability.sum())
    if total <= 0.0:
        raise MainResearchStrategyError("weighted CVaR requires positive probability mass")
    probability = probability / total
    order = np.argsort(numeric, kind="stable")
    remaining = alpha
    weighted_sum = 0.0
    for index in order:
        mass = min(remaining, float(probability[index]))
        weighted_sum += mass * float(numeric[index])
        remaining -= mass
        if remaining <= 1e-15:
            break
    return weighted_sum / alpha


@dataclass(frozen=True)
class ActionEvaluation:
    action: ResearchAction
    mean: float
    cvar10: float
    mean_delta: float
    cvar10_delta: float
    support_lower: float
    support_upper: float

    def payload(self) -> dict[str, Any]:
        return {
            "action_id": action_identity(self.action),
            "mean": self.mean,
            "cvar10": self.cvar10,
            "mean_delta": self.mean_delta,
            "cvar10_delta": self.cvar10_delta,
            "support_lower": self.support_lower,
            "support_upper": self.support_upper,
        }


class ImmediateActionEvaluator:
    """Exact one-action value under one named research probability model."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        provider: MainRollProbabilityProvider,
        *,
        cvar_alpha: float,
    ) -> None:
        self.rules = rules
        self.terminal = terminal
        self.provider = provider
        self.cvar_alpha = cvar_alpha
        self._cache: dict[MainRollState, tuple[TerminalEvaluation, tuple[ActionEvaluation, ...]]] = {}

    @staticmethod
    def _replace_banner(
        banners: tuple[BannerState, ...],
        replacement: BannerState,
    ) -> tuple[BannerState, ...]:
        return tuple(replacement if banner.role == replacement.role else banner for banner in banners)

    def evaluate(self, state: MainRollState) -> tuple[TerminalEvaluation, tuple[ActionEvaluation, ...]]:
        if state in self._cache:
            return self._cache[state]
        current = self.terminal.evaluate(state.banners)
        rows: list[ActionEvaluation] = [
            ActionEvaluation(STOP, current.mean, current.cvar10, 0.0, 0.0, 0.0, 0.0)
        ]
        for action in legal_actions(state, self.rules):
            if isinstance(action, RefreshRollAction):
                rows.append(
                    ActionEvaluation(
                        action,
                        current.mean,
                        current.cvar10,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                    )
                )
                continue
            banner = next(item for item in state.banners if item.role == action.banner_role)
            mutations = self.provider.mutation_distribution(banner, action.operation_id)
            values: list[np.ndarray] = []
            weights: list[np.ndarray] = []
            means: list[float] = []
            for mutation in mutations:
                terminal = self.terminal.evaluate(self._replace_banner(state.banners, mutation.banner))
                values.append(terminal.outcomes)
                weights.append(
                    np.full(
                        len(terminal.outcomes),
                        mutation.probability / len(terminal.outcomes),
                        dtype=float,
                    )
                )
                means.append(terminal.mean)
            if not values:
                raise MainResearchStrategyError("legal Main action has no mutation distribution")
            all_values = np.concatenate(values)
            all_weights = np.concatenate(weights)
            mean = float(np.dot(all_values, all_weights) / all_weights.sum())
            cvar = weighted_lower_tail_cvar(all_values, all_weights, self.cvar_alpha)
            deltas = [value - current.mean for value in means]
            rows.append(
                ActionEvaluation(
                    action,
                    mean,
                    cvar,
                    mean - current.mean,
                    cvar - current.cvar10,
                    min(deltas),
                    max(deltas),
                )
            )
        result = current, tuple(rows)
        self._cache[state] = result
        return result


class GreedyImmediatePolicy:
    """Policy G: maximize exact one-step terminal value and ignore future offers."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        provider: MainRollProbabilityProvider,
        specification: GreedyStrategySpec,
    ) -> None:
        self.policy_id = specification.policy_id
        self.rules = rules
        self.provider = provider
        self.specification = specification
        self.actions = ImmediateActionEvaluator(
            rules,
            terminal,
            provider,
            cvar_alpha=specification.cvar_alpha,
        )

    def choose_action(self, state: MainRollState) -> PolicyDecision:
        current, rows = self.actions.evaluate(state)
        improvements = [
            row
            for row in rows
            if isinstance(row.action, ApplyRollAction)
            and row.mean_delta > self.specification.improvement_tolerance
        ]
        if not improvements:
            action: ResearchAction = STOP if state.remaining_rolls <= 1 else REFRESH
            return PolicyDecision(
                action,
                "No offered Apply action has positive immediate expected terminal value.",
                {
                    "mode": "greedy-immediate",
                    "current_mean": current.mean,
                    "selected_action_id": action_identity(action),
                },
            )

        maximum_mean = max(row.mean for row in improvements)
        floor = maximum_mean - abs(maximum_mean) * self.specification.mean_retention_epsilon - 1e-12
        eligible = [row for row in improvements if row.mean >= floor]
        selected = min(
            eligible,
            key=lambda row: (
                -row.cvar10,
                -row.mean,
                -row.support_lower,
                action_identity(row.action),
            ),
        )
        return PolicyDecision(
            selected.action,
            "Selected the greatest one-step expected terminal value; future offers are ignored.",
            {
                "mode": "greedy-immediate",
                "current_mean": current.mean,
                "selected": selected.payload(),
            },
        )


@dataclass(frozen=True, order=True)
class ConfigurationTarget:
    role: str
    qualities: tuple[int, int, int, int, int]
    traits: tuple[str, str, str, str, str]
    target_mean: float
    gain: float
    distance: int
    target_id: str

    def payload(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "role": self.role,
            "qualities": list(self.qualities),
            "traits": list(self.traits),
            "target_mean": self.target_mean,
            "gain": self.gain,
            "distance": self.distance,
        }


def configuration_distance(banner: BannerState, target: ConfigurationTarget) -> int:
    if banner.role != target.role:
        raise MainResearchStrategyError("configuration target applied to the wrong Main role")
    return sum(
        emblem.quality_tier != quality
        for emblem, quality in zip(banner.emblems, target.qualities, strict=True)
    ) + sum(emblem.trait_id != trait for emblem, trait in zip(banner.emblems, target.traits, strict=True))


def _banner_with_configuration(
    banner: BannerState,
    qualities: tuple[int, int, int, int, int],
    traits: tuple[str, str, str, str, str],
) -> BannerState:
    return BannerState(
        banner.role,
        tuple(
            replace(emblem, quality_tier=quality, trait_id=trait)
            for emblem, quality, trait in zip(
                banner.emblems,
                qualities,
                traits,
                strict=True,
            )
        ),
    )


class BoundedConfigurationTargetGenerator:
    """Generate a small structural Q/T challenger set, never a Trait tier list."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        specification: TargetStrategySpec,
    ) -> None:
        self.rules = rules
        self.terminal = terminal
        self.specification = specification
        self._cache: dict[tuple[BannerState, ...], tuple[ConfigurationTarget, ...]] = {}

    @staticmethod
    def _replace_banner(
        banners: tuple[BannerState, ...],
        replacement: BannerState,
    ) -> tuple[BannerState, ...]:
        return tuple(replacement if banner.role == replacement.role else banner for banner in banners)

    def _configurations(
        self,
        banner: BannerState,
    ) -> tuple[
        tuple[tuple[int, int, int, int, int], tuple[str, str, str, str, str]],
        ...,
    ]:
        qualities = tuple(emblem.quality_tier for emblem in banner.emblems)
        traits = tuple(emblem.trait_id for emblem in banner.emblems)
        if len(qualities) != 5 or len(traits) != 5:
            raise MainResearchStrategyError("Main targets require exactly five positioned Emblems")
        candidates: set[tuple[tuple[int, ...], tuple[str, ...]]] = {(qualities, traits)}

        for index in range(5):
            for quality in range(1, 6):
                candidate = list(qualities)
                candidate[index] = quality
                candidates.add((tuple(candidate), traits))
            for trait in self.rules.traits:
                candidate = list(traits)
                candidate[index] = trait
                candidates.add((qualities, tuple(candidate)))

        friendly = "friendly"
        unique = "unique"
        fractal = "fractal"
        if {friendly, unique, fractal}.issubset(self.rules.traits):
            for count in (3, 4, 5):
                for indexes in combinations(range(5), count):
                    candidate = list(traits)
                    for index in indexes:
                        candidate[index] = friendly
                    candidates.add((qualities, tuple(candidate)))
            for unique_index in range(5):
                candidate = [friendly if trait == unique else trait for trait in traits]
                candidate[unique_index] = unique
                candidates.add((qualities, tuple(candidate)))

        for trait in self.rules.traits:
            candidates.add((qualities, (trait,) * 5))
        for left, right in product(self.rules.traits, repeat=2):
            candidates.add((qualities, (left, right, left, right, left)))

        distinct = sorted(
            permutations(range(1, 6)),
            key=lambda candidate: (
                sum(abs(left - right) for left, right in zip(candidate, qualities, strict=True)),
                candidate,
            ),
        )[: self.specification.fractal_quality_permutation_limit]
        for candidate_qualities in distinct:
            candidates.add((candidate_qualities, traits))
            candidates.add((candidate_qualities, (fractal,) * 5))

        return tuple(
            (quality, trait)  # type: ignore[arg-type]
            for quality, trait in sorted(candidates)
        )

    def generate(self, state: MainRollState) -> tuple[ConfigurationTarget, ...]:
        if state.banners in self._cache:
            return self._cache[state.banners]
        current = self.terminal.evaluate(state.banners)
        candidates: list[ConfigurationTarget] = []
        for banner in state.banners:
            current_qualities = tuple(emblem.quality_tier for emblem in banner.emblems)
            current_traits = tuple(emblem.trait_id for emblem in banner.emblems)
            for qualities, traits in self._configurations(banner):
                if qualities == current_qualities and traits == current_traits:
                    continue
                configured = _banner_with_configuration(banner, qualities, traits)
                terminal = self.terminal.evaluate(self._replace_banner(state.banners, configured))
                gain = terminal.mean - current.mean
                if gain <= 1e-12:
                    continue
                distance = sum(
                    left != right for left, right in zip(qualities, current_qualities, strict=True)
                ) + sum(left != right for left, right in zip(traits, current_traits, strict=True))
                identity = {
                    "role": banner.role,
                    "qualities": qualities,
                    "traits": traits,
                }
                candidates.append(
                    ConfigurationTarget(
                        banner.role,
                        qualities,
                        traits,
                        terminal.mean,
                        gain,
                        distance,
                        sha256_json(identity),
                    )
                )
        ranked = sorted(
            candidates,
            key=lambda target: (
                -(target.gain / (1.0 + target.distance)),
                -target.gain,
                target.distance,
                target.target_id,
            ),
        )[: self.specification.candidate_limit]
        result = tuple(ranked)
        self._cache[state.banners] = result
        return result


@dataclass(frozen=True)
class ReachabilityEstimate:
    probability: float
    hit_times: tuple[int, ...]
    horizon: int
    sample_count: int

    @property
    def expected_hit_time(self) -> float:
        return float(np.mean(self.hit_times))

    def quantile(self, probability: float) -> float:
        return float(np.quantile(np.asarray(self.hit_times, dtype=float), probability))

    def payload(self) -> dict[str, Any]:
        return {
            "probability": self.probability,
            "expected_hit_time_censored": self.expected_hit_time,
            "hit_time_p80_censored": self.quantile(0.8),
            "horizon": self.horizon,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class TargetSelection:
    target: ConfigurationTarget
    reachability: ReachabilityEstimate | None
    potential: float


class TargetSeekingPolicy:
    """Policy T: trade bounded immediate value for reachable Q/T configuration value."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        provider: MainRollProbabilityProvider,
        specification: TargetStrategySpec,
        greedy_specification: GreedyStrategySpec,
    ) -> None:
        self.policy_id = specification.policy_id
        self.rules = rules
        self.terminal = terminal
        self.provider = provider
        self.specification = specification
        self.greedy = GreedyImmediatePolicy(
            rules,
            terminal,
            provider,
            greedy_specification,
        )
        self.actions = self.greedy.actions
        self.targets = BoundedConfigurationTargetGenerator(rules, terminal, specification)
        self._reachability_cache: dict[tuple[str, str, str], ReachabilityEstimate] = {}

    @staticmethod
    def _target_banner(state: MainRollState, target: ConfigurationTarget) -> BannerState:
        return next(banner for banner in state.banners if banner.role == target.role)

    def _target_directed_action(
        self,
        state: MainRollState,
        target: ConfigurationTarget,
    ) -> ResearchAction:
        banner = self._target_banner(state, target)
        current_distance = configuration_distance(banner, target)
        if current_distance == 0:
            return STOP
        candidates: list[tuple[float, int, float, str, ApplyRollAction]] = []
        for action in legal_actions(state, self.rules):
            if not isinstance(action, ApplyRollAction) or action.banner_role != target.role:
                continue
            distribution = self.provider.mutation_distribution(banner, action.operation_id)
            distances = [configuration_distance(outcome.banner, target) for outcome in distribution]
            expected = sum(
                outcome.probability * distance
                for outcome, distance in zip(distribution, distances, strict=True)
            )
            hit_probability = sum(
                outcome.probability
                for outcome, distance in zip(distribution, distances, strict=True)
                if distance == 0
            )
            candidates.append(
                (
                    expected,
                    max(distances),
                    -hit_probability,
                    action_identity(action),
                    action,
                )
            )
        if not candidates:
            return STOP if state.remaining_rolls <= 1 else REFRESH
        selected = min(candidates)
        expected, worst, negative_hit, _, action = selected
        if expected < current_distance - 1e-12:
            return action
        if -negative_hit > 0.0 and worst <= current_distance:
            return action
        return STOP if state.remaining_rolls <= 1 else REFRESH

    def _rng(
        self,
        state: MainRollState,
        target: ConfigurationTarget,
        first_action_id: str,
        sample: int,
        step: int,
        draw_kind: str,
    ) -> random.Random:
        key = ":".join(
            (
                str(self.specification.decision_seed),
                state_sha256(state),
                target.target_id,
                first_action_id,
                str(sample),
                str(step),
                draw_kind,
            )
        )
        return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))

    def _sample_transition(
        self,
        root: MainRollState,
        state: MainRollState,
        target: ConfigurationTarget,
        first_action_id: str,
        action: ResearchAction,
        sample: int,
        step: int,
    ) -> MainRollState:
        if isinstance(action, StopRollAction):
            return state
        offer = self.provider.draw_offer(self._rng(root, target, first_action_id, sample, step, "offer"))
        if isinstance(action, RefreshRollAction):
            return refresh_transition(state, offer, self.rules)
        banner = next(item for item in state.banners if item.role == action.banner_role)
        realized = self.provider.sample_mutation(
            banner,
            action.operation_id,
            self._rng(root, target, first_action_id, sample, step, "mutation"),
        )
        return apply_realized_transition(state, action, realized, offer, self.rules)

    def estimate_reachability(
        self,
        state: MainRollState,
        target: ConfigurationTarget,
        *,
        first_action: ResearchAction | None = None,
    ) -> ReachabilityEstimate:
        first_action_id = "continuation" if first_action is None else action_identity(first_action)
        cache_key = (state_sha256(state), target.target_id, first_action_id)
        if cache_key in self._reachability_cache:
            return self._reachability_cache[cache_key]
        horizon = state.remaining_rolls
        hit_times: list[int] = []
        hits = 0
        for sample in range(self.specification.reachability_samples):
            simulated = state
            spent = 0
            if configuration_distance(self._target_banner(simulated, target), target) == 0:
                hits += 1
                hit_times.append(0)
                continue
            if first_action is not None:
                if isinstance(first_action, StopRollAction):
                    hit_times.append(horizon + 1)
                    continue
                simulated = self._sample_transition(
                    state,
                    simulated,
                    target,
                    first_action_id,
                    first_action,
                    sample,
                    spent,
                )
                if not isinstance(first_action, StopRollAction):
                    spent += 1
            while simulated.remaining_rolls > 0:
                if configuration_distance(self._target_banner(simulated, target), target) == 0:
                    break
                action = self._target_directed_action(simulated, target)
                if isinstance(action, StopRollAction):
                    break
                simulated = self._sample_transition(
                    state,
                    simulated,
                    target,
                    first_action_id,
                    action,
                    sample,
                    spent,
                )
                spent += 1
            hit = configuration_distance(self._target_banner(simulated, target), target) == 0
            if hit:
                hits += 1
                hit_times.append(spent)
            else:
                hit_times.append(horizon + 1)
        estimate = ReachabilityEstimate(
            probability=hits / self.specification.reachability_samples,
            hit_times=tuple(hit_times),
            horizon=horizon,
            sample_count=self.specification.reachability_samples,
        )
        self._reachability_cache[cache_key] = estimate
        return estimate

    def best_target(self, state: MainRollState) -> TargetSelection | None:
        if self.specification.evaluation_mode == "exact-distance-potential":
            targets = self.targets.generate(state)
            if not targets:
                return None
            selected = min(
                targets,
                key=lambda target: (
                    -(target.gain / (1.0 + target.distance)),
                    -target.gain,
                    target.distance,
                    target.target_id,
                ),
            )
            potential = selected.gain / (1.0 + selected.distance)
            return TargetSelection(selected, None, potential) if potential > 0.0 else None
        selections: list[TargetSelection] = []
        for target in self.targets.generate(state):
            reachability = self.estimate_reachability(state, target)
            selections.append(
                TargetSelection(
                    target,
                    reachability,
                    target.gain * reachability.probability,
                )
            )
        if not selections:
            return None
        selected = min(
            selections,
            key=lambda item: (
                -item.potential,
                -item.target.gain,
                item.reachability.expected_hit_time,
                item.target.target_id,
            ),
        )
        return selected if selected.potential > 0.0 else None

    def choose_for_selection(
        self,
        state: MainRollState,
        selection: TargetSelection,
    ) -> PolicyDecision:
        current, rows = self.actions.evaluate(state)
        if self.specification.evaluation_mode == "exact-distance-potential":
            return self._choose_exact_distance(state, selection, current, rows)
        maximum_loss = abs(current.mean) * self.specification.maximum_immediate_loss_fraction
        eligible = [row for row in rows if row.mean_delta >= -maximum_loss - 1e-12]
        target_directed = self._target_directed_action(state, selection.target)
        priority_ids = {action_identity(target_directed), "refresh"}
        retained = sorted(
            eligible,
            key=lambda row: (
                0 if action_identity(row.action) in priority_ids else 1,
                -row.mean_delta,
                -row.cvar10,
                -row.support_lower,
                action_identity(row.action),
            ),
        )[: self.specification.reachability_action_limit]
        scored: list[tuple[float, float, float, str, ActionEvaluation, ReachabilityEstimate]] = []
        for row in retained:
            reachability = self.estimate_reachability(
                state,
                selection.target,
                first_action=row.action,
            )
            score = (
                row.mean_delta
                + self.specification.potential_weight * selection.target.gain * reachability.probability
            )
            scored.append(
                (
                    -score,
                    -row.cvar10,
                    -row.support_lower,
                    action_identity(row.action),
                    row,
                    reachability,
                )
            )
        if not scored:
            return self.greedy.choose_action(state)
        _, _, _, _, selected, reachability = min(scored)
        if isinstance(selected.action, StopRollAction) and state.remaining_rolls > 1:
            selected = next(row for row in rows if isinstance(row.action, RefreshRollAction))
            reachability = self.estimate_reachability(
                state,
                selection.target,
                first_action=selected.action,
            )
        return PolicyDecision(
            selected.action,
            "Selected bounded immediate value plus model-conditional target reachability.",
            {
                "mode": "target-seeking",
                "target": selection.target.payload(),
                "target_reachability_before": (
                    selection.reachability.payload() if selection.reachability is not None else None
                ),
                "selected_reachability": reachability.payload(),
                "selected_immediate": selected.payload(),
            },
        )

    def _choose_exact_distance(
        self,
        state: MainRollState,
        selection: TargetSelection,
        current: TerminalEvaluation,
        rows: tuple[ActionEvaluation, ...],
    ) -> PolicyDecision:
        target = selection.target
        banner = self._target_banner(state, target)
        current_distance = configuration_distance(banner, target)
        maximum_loss = abs(current.mean) * self.specification.maximum_immediate_loss_fraction
        scored: list[tuple[float, float, float, int, str, ActionEvaluation, float]] = []
        for row in rows:
            if isinstance(row.action, StopRollAction) and state.remaining_rolls > 1:
                continue
            if row.mean_delta < -maximum_loss - 1e-12:
                continue
            expected_distance = float(current_distance)
            if isinstance(row.action, ApplyRollAction) and row.action.banner_role == target.role:
                distribution = self.provider.mutation_distribution(
                    banner,
                    row.action.operation_id,
                )
                expected_distance = float(
                    sum(
                        outcome.probability * configuration_distance(outcome.banner, target)
                        for outcome in distribution
                    )
                )
            progress = current_distance - expected_distance
            shape_value = target.gain * progress / current_distance if current_distance > 0 else 0.0
            score = row.mean_delta + self.specification.potential_weight * shape_value
            scored.append(
                (
                    -score,
                    -row.cvar10,
                    -row.support_lower,
                    0 if isinstance(row.action, RefreshRollAction) else 1,
                    action_identity(row.action),
                    row,
                    expected_distance,
                )
            )
        if not scored:
            return self.greedy.choose_action(state)
        *_, selected, expected_distance = min(scored)
        return PolicyDecision(
            selected.action,
            "Selected exact expected progress toward the best bounded Q/T shape.",
            {
                "mode": "target-shape-distance",
                "target": target.payload(),
                "target_potential": selection.potential,
                "configuration_distance_before": current_distance,
                "expected_configuration_distance_after": expected_distance,
                "selected_immediate": selected.payload(),
            },
        )

    def choose_action(self, state: MainRollState) -> PolicyDecision:
        selection = self.best_target(state)
        if selection is None:
            fallback = self.greedy.choose_action(state)
            return PolicyDecision(
                fallback.action,
                "No positive reachable configuration target; fell back to immediate greedy.",
                {"mode": "target-fallback-greedy", **dict(fallback.diagnostics)},
            )
        return self.choose_for_selection(state, selection)


class HorizonHybridPolicy:
    """Policy H: use target pursuit only while the frozen remaining-horizon gate is open."""

    def __init__(
        self,
        greedy: GreedyImmediatePolicy,
        target: TargetSeekingPolicy,
        specification: HybridStrategySpec,
    ) -> None:
        if greedy.rules is not target.rules or greedy.provider is not target.provider:
            raise MainResearchStrategyError("hybrid policies must share rules and probability model")
        self.policy_id = specification.policy_id
        self.greedy = greedy
        self.target = target
        self.specification = specification

    def choose_action(self, state: MainRollState) -> PolicyDecision:
        if self.specification.switch_mode == "fixed":
            use_target = state.remaining_rolls > self.specification.fixed_remaining_threshold
            selection = self.target.best_target(state) if use_target else None
            gate = {
                "switch_mode": "fixed",
                "remaining_rolls": state.remaining_rolls,
                "fixed_remaining_threshold": self.specification.fixed_remaining_threshold,
            }
        else:
            selection = self.target.best_target(state)
            if selection is None:
                use_target = False
                required_rolls = None
            else:
                if selection.reachability is None:
                    raise MainResearchStrategyError("adaptive Hybrid requires sampled Target reachability")
                required_rolls = (
                    selection.reachability.quantile(self.specification.hit_time_quantile)
                    + self.specification.safety_buffer
                )
                use_target = (
                    selection.reachability.probability >= self.specification.minimum_reach_probability
                    and state.remaining_rolls >= required_rolls
                    and selection.potential > 0.0
                )
            gate = {
                "switch_mode": "adaptive-hit-time",
                "remaining_rolls": state.remaining_rolls,
                "required_rolls": required_rolls,
                "minimum_reach_probability": self.specification.minimum_reach_probability,
            }
        if use_target and selection is not None:
            decision = self.target.choose_for_selection(state, selection)
            return PolicyDecision(
                decision.action,
                "Hybrid gate selected target-seeking mode.",
                {**dict(decision.diagnostics), "mode": "hybrid-target", "gate": gate},
            )
        decision = self.greedy.choose_action(state)
        return PolicyDecision(
            decision.action,
            "Hybrid gate selected immediate-greedy mode.",
            {**dict(decision.diagnostics), "mode": "hybrid-greedy", "gate": gate},
        )


__all__ = [
    "ActionEvaluation",
    "BoundedConfigurationTargetGenerator",
    "ConfigurationTarget",
    "GreedyImmediatePolicy",
    "HorizonHybridPolicy",
    "ImmediateActionEvaluator",
    "MainResearchStrategyError",
    "ReachabilityEstimate",
    "TargetSeekingPolicy",
    "TargetSelection",
    "configuration_distance",
    "weighted_lower_tail_cvar",
]
