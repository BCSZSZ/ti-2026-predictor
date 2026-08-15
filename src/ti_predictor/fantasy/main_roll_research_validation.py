"""Exact short-horizon checks for the isolated Main Roll research simulator."""

from __future__ import annotations

from dataclasses import dataclass

from ti_predictor.fantasy.main_roll import (
    MainRollState,
    apply_realized_transition,
    refresh_transition,
)
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import (
    MainResearchPolicy,
    MainResearchTerminal,
    StopRollAction,
)
from ti_predictor.fantasy.roll import RefreshRollAction, RollRuleSet


class MainResearchValidationError(ValueError):
    """A short-horizon exact check exceeds or violates its preregistered contract."""


@dataclass(frozen=True)
class ExactPolicyValue:
    expected_terminal_mean: float
    horizon: int
    evaluated_states: int


def exact_policy_terminal_mean(
    state: MainRollState,
    policy: MainResearchPolicy,
    provider: MainRollProbabilityProvider,
    terminal: MainResearchTerminal,
    rules: RollRuleSet,
    *,
    horizon: int,
    maximum_evaluated_states: int = 1_000_000,
) -> ExactPolicyValue:
    """Integrate future mutation and offer randomness for a deterministic policy.

    Horizons are deliberately capped at three.  Unlike the retired fixed-offer check,
    every non-terminal step integrates the provider's replacement-offer distribution.
    A state budget makes an expensive full-client kernel fail explicitly instead of
    silently truncating branches.
    """

    if horizon not in {1, 2, 3}:
        raise MainResearchValidationError("exact validation horizon must be one, two, or three")
    if maximum_evaluated_states < 1:
        raise MainResearchValidationError("exact validation state budget must be positive")
    if provider.rules is not rules:
        raise MainResearchValidationError("exact validator and provider use different rules")
    cache: dict[tuple[MainRollState, int], float] = {}
    evaluated_states = 0

    def evaluate(current: MainRollState, remaining_horizon: int) -> float:
        nonlocal evaluated_states
        key = (current, remaining_horizon)
        if key in cache:
            return cache[key]
        evaluated_states += 1
        if evaluated_states > maximum_evaluated_states:
            raise MainResearchValidationError(
                "exact validation exceeded its state budget; no branches were truncated"
            )
        if remaining_horizon == 0 or current.remaining_rolls == 0:
            value = terminal.evaluate(current.banners).mean
            cache[key] = value
            return value

        action = policy.choose_action(current).action
        if isinstance(action, StopRollAction):
            value = terminal.evaluate(current.banners).mean
            cache[key] = value
            return value
        if isinstance(action, RefreshRollAction):
            if remaining_horizon == 1:
                value = terminal.evaluate(current.banners).mean
            else:
                value = sum(
                    offer_outcome.probability
                    * evaluate(
                        refresh_transition(current, offer_outcome.offer, rules),
                        remaining_horizon - 1,
                    )
                    for offer_outcome in provider.offer_distribution()
                )
            cache[key] = value
            return value

        banner = next(item for item in current.banners if item.role == action.banner_role)
        mutations = provider.mutation_distribution(banner, action.operation_id)
        if remaining_horizon == 1:
            value = sum(
                mutation.probability
                * terminal.evaluate(
                    tuple(
                        mutation.banner if item.role == action.banner_role else item
                        for item in current.banners
                    )
                ).mean
                for mutation in mutations
            )
            cache[key] = value
            return value

        value = 0.0
        for mutation in mutations:
            for offer_outcome in provider.offer_distribution():
                next_state = apply_realized_transition(
                    current,
                    action,
                    mutation.banner,
                    offer_outcome.offer,
                    rules,
                )
                value += (
                    mutation.probability
                    * offer_outcome.probability
                    * evaluate(next_state, remaining_horizon - 1)
                )
        cache[key] = value
        return value

    expected = evaluate(state, min(horizon, state.remaining_rolls))
    return ExactPolicyValue(expected, horizon, evaluated_states)


__all__ = [
    "ExactPolicyValue",
    "MainResearchValidationError",
    "exact_policy_terminal_mean",
]
