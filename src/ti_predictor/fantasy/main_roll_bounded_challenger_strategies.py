"""Runtime-bounded challenger policies for isolated Main Roll research.

All policies in this module preserve immediate Greedy as their fallback.  They are not
imported by Web, OCR, the shared CLI, or the current-screen advisor.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable

import numpy as np

from ti_predictor.fantasy.main_roll import (
    MainRollState,
    apply_realized_transition,
    refresh_transition,
)
from ti_predictor.fantasy.main_roll_bounded_challenger_contract import (
    LocalTieStrategySpec,
    SafeBandStrategySpec,
    SelectiveTwoStepStrategySpec,
)
from ti_predictor.fantasy.main_roll_research_contract import GreedyStrategySpec
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import (
    MainResearchPolicy,
    MainResearchTerminal,
    PolicyDecision,
    StopRollAction,
    action_identity,
    state_sha256,
)
from ti_predictor.fantasy.main_roll_research_strategies import (
    ActionEvaluation,
    GreedyImmediatePolicy,
)
from ti_predictor.fantasy.roll import (
    ApplyRollAction,
    BannerState,
    RefreshRollAction,
    RollRuleSet,
)


class MainBoundedChallengerStrategyError(ValueError):
    """A bounded challenger cannot produce a reproducible legal action."""


def _row_for_action(
    rows: Iterable[ActionEvaluation],
    action_id: str,
) -> ActionEvaluation:
    for row in rows:
        if action_identity(row.action) == action_id:
            return row
    raise MainBoundedChallengerStrategyError(f"immediate action table does not contain {action_id}")


def _fallback_payload(decision: PolicyDecision, mode: str) -> PolicyDecision:
    return PolicyDecision(
        decision.action,
        "Bounded challenger retained the immediate Greedy decision.",
        {"mode": mode, "greedy": dict(decision.diagnostics)},
    )


def _non_stop_rows(
    rows: tuple[ActionEvaluation, ...],
    state: MainRollState,
) -> list[ActionEvaluation]:
    if state.remaining_rolls <= 1:
        return list(rows)
    return [row for row in rows if not isinstance(row.action, StopRollAction)]


class GreedySafeBandPolicy:
    """Retain near-best immediate means, then prefer lower-tail safety."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        provider: MainRollProbabilityProvider,
        specification: SafeBandStrategySpec,
        greedy_specification: GreedyStrategySpec,
    ) -> None:
        self.policy_id = specification.policy_id
        self.specification = specification
        self.greedy = GreedyImmediatePolicy(
            rules,
            terminal,
            provider,
            greedy_specification,
        )

    def choose_action(self, state: MainRollState) -> PolicyDecision:
        baseline = self.greedy.choose_action(state)
        current, rows = self.greedy.actions.evaluate(state)
        positive_apply = [
            row
            for row in rows
            if isinstance(row.action, ApplyRollAction)
            and row.mean_delta > self.specification.improvement_tolerance
        ]
        if not positive_apply:
            return _fallback_payload(baseline, "safe-band-fallback-greedy")

        candidates = _non_stop_rows(rows, state)
        maximum_mean = max(row.mean for row in candidates)
        floor = maximum_mean - abs(current.mean) * self.specification.mean_band_fraction
        eligible = [row for row in candidates if row.mean >= floor - 1e-12]
        selected = min(
            eligible,
            key=lambda row: (
                -row.cvar10,
                -row.support_lower,
                -row.mean,
                action_identity(row.action),
            ),
        )
        return PolicyDecision(
            selected.action,
            "Selected lower-tail safety inside the frozen near-best immediate-mean band.",
            {
                "mode": "greedy-safe-band",
                "current_mean": current.mean,
                "mean_floor": floor,
                "eligible_action_ids": [action_identity(row.action) for row in eligible],
                "greedy_action_id": action_identity(baseline.action),
                "selected": selected.payload(),
            },
        )


def local_configuration_score(banners: tuple[BannerState, ...]) -> float:
    """Cheap progress score for conditional Trait activation.

    It deliberately excludes always-active Benevolent/Vampiric effects because their
    current value is already present in exact terminal evaluation.  The score is used
    only after mean and CVaR retention guards, never as a substitute for terminal value.
    """

    score = 0.0
    for banner in banners:
        traits = tuple(emblem.trait_id for emblem in banner.emblems)
        qualities = tuple(emblem.quality_tier for emblem in banner.emblems)
        slot_count = len(banner.emblems)
        distinct_quality_fraction = len(set(qualities)) / slot_count

        fractal_count = traits.count("fractal")
        friendly_count = traits.count("friendly")
        unique_count = traits.count("unique")

        score += fractal_count * distinct_quality_fraction
        score += friendly_count * min(1.0, friendly_count / 3.0)
        if unique_count:
            score += 1.0 / unique_count
    return score


class GreedyLocalConfigurationTieBreakPolicy:
    """Use local conditional-Trait progress only inside strict G safety bands."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        provider: MainRollProbabilityProvider,
        specification: LocalTieStrategySpec,
        greedy_specification: GreedyStrategySpec,
    ) -> None:
        self.policy_id = specification.policy_id
        self.specification = specification
        self.provider = provider
        self.greedy = GreedyImmediatePolicy(
            rules,
            terminal,
            provider,
            greedy_specification,
        )

    @staticmethod
    def _replace_banner(
        banners: tuple[BannerState, ...],
        replacement: BannerState,
    ) -> tuple[BannerState, ...]:
        return tuple(replacement if banner.role == replacement.role else banner for banner in banners)

    def _expected_local_score(
        self,
        state: MainRollState,
        row: ActionEvaluation,
    ) -> float:
        if not isinstance(row.action, ApplyRollAction):
            return local_configuration_score(state.banners)
        banner = next(item for item in state.banners if item.role == row.action.banner_role)
        return float(
            sum(
                mutation.probability
                * local_configuration_score(self._replace_banner(state.banners, mutation.banner))
                for mutation in self.provider.mutation_distribution(
                    banner,
                    row.action.operation_id,
                )
            )
        )

    def choose_action(self, state: MainRollState) -> PolicyDecision:
        baseline = self.greedy.choose_action(state)
        if state.remaining_rolls <= 1:
            return _fallback_payload(baseline, "local-tie-last-roll-greedy")

        current, rows = self.greedy.actions.evaluate(state)
        baseline_row = _row_for_action(rows, action_identity(baseline.action))
        positive_apply = [
            row
            for row in rows
            if isinstance(row.action, ApplyRollAction)
            and row.mean_delta > self.specification.improvement_tolerance
        ]
        if not positive_apply:
            return _fallback_payload(baseline, "local-tie-fallback-greedy")

        mean_floor = baseline_row.mean - abs(current.mean) * self.specification.mean_band_fraction
        cvar_floor = baseline_row.cvar10 - (
            abs(baseline_row.cvar10) * self.specification.cvar_retention_fraction
        )
        eligible = [
            row
            for row in _non_stop_rows(rows, state)
            if row.mean >= mean_floor - 1e-12 and row.cvar10 >= cvar_floor - 1e-12
        ]
        if len(eligible) < 2:
            return _fallback_payload(baseline, "local-tie-no-safe-alternative")

        scored = [(self._expected_local_score(state, row), row) for row in eligible]
        selected_score, selected = min(
            scored,
            key=lambda item: (
                -item[0],
                -item[1].cvar10,
                -item[1].mean,
                -item[1].support_lower,
                action_identity(item[1].action),
            ),
        )
        return PolicyDecision(
            selected.action,
            "Used local conditional-Trait progress only after mean and CVaR retention guards.",
            {
                "mode": "greedy-local-configuration-tiebreak",
                "current_mean": current.mean,
                "mean_floor": mean_floor,
                "cvar_floor": cvar_floor,
                "greedy_action_id": action_identity(baseline.action),
                "selected_local_score": selected_score,
                "eligible": [{"local_score": score, **row.payload()} for score, row in scored],
                "selected": selected.payload(),
            },
        )


class GreedySelectiveTwoStepPolicy:
    """Use a fixed small two-step sample only for near-tied immediate actions."""

    def __init__(
        self,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        provider: MainRollProbabilityProvider,
        specification: SelectiveTwoStepStrategySpec,
        greedy_specification: GreedyStrategySpec,
    ) -> None:
        self.policy_id = specification.policy_id
        self.rules = rules
        self.provider = provider
        self.specification = specification
        self.greedy = GreedyImmediatePolicy(
            rules,
            terminal,
            provider,
            greedy_specification,
        )
        self._trigger_count = 0

    def _rng(self, state: MainRollState, sample_index: int, draw_kind: str) -> random.Random:
        digest = hashlib.sha256(
            (
                f"main-bounded-two-step:{self.specification.decision_seed}:"
                f"{state_sha256(state)}:{sample_index}:{draw_kind}"
            ).encode()
        ).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def _sample_first_transition(
        self,
        state: MainRollState,
        action: ApplyRollAction | RefreshRollAction,
        sample_index: int,
    ) -> MainRollState:
        replacement_offer = self.provider.draw_offer(self._rng(state, sample_index, "replacement-offer"))
        if isinstance(action, RefreshRollAction):
            return refresh_transition(state, replacement_offer, self.rules)
        current_banner = next(banner for banner in state.banners if banner.role == action.banner_role)
        realized = self.provider.sample_mutation(
            current_banner,
            action.operation_id,
            self._rng(state, sample_index, "mutation-uniform"),
        )
        return apply_realized_transition(
            state,
            action,
            realized,
            replacement_offer,
            self.rules,
        )

    def _greedy_one_step_value(self, state: MainRollState) -> tuple[float, float]:
        decision = self.greedy.choose_action(state)
        _, rows = self.greedy.actions.evaluate(state)
        row = _row_for_action(rows, action_identity(decision.action))
        return row.mean, row.cvar10

    def _candidate_value(
        self,
        state: MainRollState,
        row: ActionEvaluation,
    ) -> tuple[float, float]:
        if not isinstance(row.action, (ApplyRollAction, RefreshRollAction)):
            raise MainBoundedChallengerStrategyError("two-step candidates must spend one Roll token")
        values = [
            self._greedy_one_step_value(self._sample_first_transition(state, row.action, sample_index))
            for sample_index in range(self.specification.sample_count)
        ]
        return (
            float(np.mean([value[0] for value in values])),
            float(np.mean([value[1] for value in values])),
        )

    def choose_action(self, state: MainRollState) -> PolicyDecision:
        baseline = self.greedy.choose_action(state)
        if state.remaining_rolls <= 1 or self._trigger_count >= self.specification.max_triggers_per_episode:
            return _fallback_payload(baseline, "selective-two-step-budgeted-greedy")

        current, rows = self.greedy.actions.evaluate(state)
        baseline_row = _row_for_action(rows, action_identity(baseline.action))
        if not isinstance(baseline_row.action, (ApplyRollAction, RefreshRollAction)):
            return _fallback_payload(baseline, "selective-two-step-stop-greedy")

        alternatives = sorted(
            (
                row
                for row in _non_stop_rows(rows, state)
                if action_identity(row.action) != action_identity(baseline_row.action)
            ),
            key=lambda row: (
                -row.mean,
                -row.cvar10,
                -row.support_lower,
                action_identity(row.action),
            ),
        )
        if not alternatives:
            return _fallback_payload(baseline, "selective-two-step-no-alternative")
        candidate_rows = [baseline_row, *alternatives[: self.specification.candidate_limit - 1]]
        gap = baseline_row.mean - candidate_rows[1].mean
        ambiguity_limit = abs(current.mean) * self.specification.ambiguity_fraction
        if gap > ambiguity_limit + 1e-12:
            return _fallback_payload(baseline, "selective-two-step-clear-greedy-margin")

        self._trigger_count += 1
        scored = [(*self._candidate_value(state, row), row) for row in candidate_rows]
        baseline_value = next(
            item for item in scored if action_identity(item[2].action) == action_identity(baseline.action)
        )
        selected = min(
            scored,
            key=lambda item: (
                -item[0],
                -item[1],
                action_identity(item[2].action),
            ),
        )
        minimum_override = abs(current.mean) * self.specification.minimum_override_fraction
        if (
            action_identity(selected[2].action) != action_identity(baseline.action)
            and selected[0] < baseline_value[0] + minimum_override - 1e-12
        ):
            selected = baseline_value

        return PolicyDecision(
            selected[2].action,
            "Compared at most two near-tied actions with one bounded sampled next step.",
            {
                "mode": "greedy-selective-two-step",
                "trigger_index": self._trigger_count,
                "max_triggers_per_episode": self.specification.max_triggers_per_episode,
                "sample_count": self.specification.sample_count,
                "immediate_gap": gap,
                "ambiguity_limit": ambiguity_limit,
                "minimum_override": minimum_override,
                "greedy_action_id": action_identity(baseline.action),
                "candidates": [
                    {
                        "two_step_mean": mean,
                        "two_step_cvar_proxy": cvar,
                        **row.payload(),
                    }
                    for mean, cvar, row in scored
                ],
                "selected_action_id": action_identity(selected[2].action),
            },
        )


def build_bounded_challenger_policy(
    policy_id: str,
    *,
    rules: RollRuleSet,
    terminal: MainResearchTerminal,
    provider: MainRollProbabilityProvider,
    baseline_specification: GreedyStrategySpec,
    safe_band_specification: SafeBandStrategySpec,
    local_tie_specification: LocalTieStrategySpec,
    selective_two_step_specification: SelectiveTwoStepStrategySpec,
) -> MainResearchPolicy:
    if policy_id == baseline_specification.policy_id:
        return GreedyImmediatePolicy(
            rules,
            terminal,
            provider,
            baseline_specification,
        )
    if policy_id == safe_band_specification.policy_id:
        return GreedySafeBandPolicy(
            rules,
            terminal,
            provider,
            safe_band_specification,
            baseline_specification,
        )
    if policy_id == local_tie_specification.policy_id:
        return GreedyLocalConfigurationTieBreakPolicy(
            rules,
            terminal,
            provider,
            local_tie_specification,
            baseline_specification,
        )
    if policy_id == selective_two_step_specification.policy_id:
        return GreedySelectiveTwoStepPolicy(
            rules,
            terminal,
            provider,
            selective_two_step_specification,
            baseline_specification,
        )
    raise MainBoundedChallengerStrategyError(f"unknown bounded policy: {policy_id}")


__all__ = [
    "GreedyLocalConfigurationTieBreakPolicy",
    "GreedySafeBandPolicy",
    "GreedySelectiveTwoStepPolicy",
    "MainBoundedChallengerStrategyError",
    "build_bounded_challenger_policy",
    "local_configuration_score",
]
