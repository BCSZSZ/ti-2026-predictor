"""Production G and G-Lite decision primitives for Main current-screen advice."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ti_predictor.fantasy.advisor import action_identity
from ti_predictor.fantasy.main_advice_strategy import (
    G_LITE_MAIN_STRATEGY_ID,
    GREEDY_MAIN_STRATEGY_ID,
    MainAdviceStrategyCatalog,
)
from ti_predictor.fantasy.main_roll import (
    MainRollState,
    apply_realized_transition,
    mutation_distribution,
    refresh_transition,
)
from ti_predictor.fantasy.roll import (
    ApplyRollAction,
    RefreshRollAction,
    RollAction,
    RollRuleSet,
    draw_roll_offer,
)
from ti_predictor.hashing import sha256_json


class MainAdvicePolicyError(ValueError):
    """A production Main advice policy cannot make a reproducible legal decision."""


@dataclass(frozen=True)
class MainImmediateActionValue:
    action: RollAction
    mean: float
    cvar10: float
    mean_delta: float
    support_lower: float

    @property
    def action_id(self) -> str:
        return action_identity(self.action)


@dataclass(frozen=True)
class MainStrategyDecision:
    strategy_id: str
    action: RollAction
    baseline_action: RollAction
    triggered: bool
    diagnostics: dict[str, Any]


def main_state_payload(state: MainRollState) -> dict[str, Any]:
    return {
        "period": state.period,
        "slot_count": state.slot_count,
        "remaining_rolls": state.remaining_rolls,
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
        "offer": (
            {"operation_ids": list(state.offer.operation_ids)}
            if state.offer is not None
            else None
        ),
    }


def main_state_sha256(state: MainRollState) -> str:
    return sha256_json(main_state_payload(state))


def _weighted_pick(values: Sequence[Any], weights: Sequence[float], rng: random.Random) -> Any:
    total = float(sum(weights))
    if not values or len(values) != len(weights) or total <= 0.0 or not math.isfinite(total):
        raise MainAdvicePolicyError("G-Lite sampling requires aligned positive finite weights")
    threshold = rng.random() * total
    cumulative = 0.0
    for value, weight in zip(values, weights, strict=True):
        cumulative += float(weight)
        if threshold < cumulative:
            return value
    return values[-1]


def _g_lite_rng(
    state: MainRollState,
    *,
    decision_seed: int,
    sample_index: int,
    draw_kind: str,
) -> random.Random:
    digest = hashlib.sha256(
        (
            f"main-bounded-two-step:{decision_seed}:{main_state_sha256(state)}:{sample_index}:{draw_kind}"
        ).encode()
    ).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def sample_g_lite_transition(
    state: MainRollState,
    action: RollAction,
    sample_index: int,
    *,
    rules: RollRuleSet,
    model_id: str,
    decision_seed: int,
) -> MainRollState:
    replacement = draw_roll_offer(
        rules,
        model_id,
        _g_lite_rng(
            state,
            decision_seed=decision_seed,
            sample_index=sample_index,
            draw_kind="replacement-offer",
        ),
    )
    if isinstance(action, RefreshRollAction):
        return refresh_transition(state, replacement, rules)
    banner = next(item for item in state.banners if item.role == action.banner_role)
    outcomes = sorted(
        mutation_distribution(banner, action.operation_id, rules, model_id),
        key=lambda item: item.banner,
    )
    realized = _weighted_pick(
        tuple(item.banner for item in outcomes),
        tuple(item.probability for item in outcomes),
        _g_lite_rng(
            state,
            decision_seed=decision_seed,
            sample_index=sample_index,
            draw_kind="mutation-uniform",
        ),
    )
    return apply_realized_transition(state, action, realized, replacement, rules)


def choose_greedy_main_action(
    state: MainRollState,
    rows: Sequence[MainImmediateActionValue],
    *,
    mean_retention_epsilon: float,
    improvement_tolerance: float,
) -> MainImmediateActionValue:
    improvements = [
        row
        for row in rows
        if isinstance(row.action, ApplyRollAction) and row.mean_delta > improvement_tolerance
    ]
    if not improvements:
        try:
            return next(row for row in rows if isinstance(row.action, RefreshRollAction))
        except StopIteration as error:
            raise MainAdvicePolicyError("G requires a legal refresh fallback") from error
    maximum_mean = max(row.mean for row in improvements)
    floor = maximum_mean - abs(maximum_mean) * mean_retention_epsilon - 1e-12
    eligible = [row for row in improvements if row.mean >= floor]
    return min(
        eligible,
        key=lambda row: (
            -row.cvar10,
            -row.mean,
            -row.support_lower,
            row.action_id,
        ),
    )


def choose_main_strategy_action(
    catalog: MainAdviceStrategyCatalog,
    strategy_id: str,
    state: MainRollState,
    current_mean: float,
    rows: Sequence[MainImmediateActionValue],
    *,
    mean_retention_epsilon: float,
    g_lite_triggers_used: int,
    continuation_value: Callable[[RollAction, int], tuple[float, float]],
) -> MainStrategyDecision:
    greedy_spec = catalog.strategies.greedy
    baseline = choose_greedy_main_action(
        state,
        rows,
        mean_retention_epsilon=mean_retention_epsilon,
        improvement_tolerance=greedy_spec.improvement_tolerance,
    )
    if strategy_id == GREEDY_MAIN_STRATEGY_ID:
        return MainStrategyDecision(
            strategy_id,
            baseline.action,
            baseline.action,
            False,
            {
                "mode": "greedy-immediate",
                "greedy_action_id": baseline.action_id,
            },
        )
    if strategy_id != G_LITE_MAIN_STRATEGY_ID:
        raise MainAdvicePolicyError(f"unknown Main advice strategy: {strategy_id}")
    specification = catalog.strategies.g_lite
    if not 0 <= g_lite_triggers_used <= specification.max_triggers_per_episode:
        raise MainAdvicePolicyError("G-Lite trigger count is outside its frozen episode budget")
    if state.remaining_rolls <= 1 or g_lite_triggers_used >= specification.max_triggers_per_episode:
        return MainStrategyDecision(
            strategy_id,
            baseline.action,
            baseline.action,
            False,
            {
                "mode": "selective-two-step-budgeted-greedy",
                "greedy_action_id": baseline.action_id,
                "triggers_used": g_lite_triggers_used,
                "max_triggers_per_episode": specification.max_triggers_per_episode,
            },
        )
    alternatives = sorted(
        (row for row in rows if row.action_id != baseline.action_id),
        key=lambda row: (-row.mean, -row.cvar10, -row.support_lower, row.action_id),
    )
    if not alternatives:
        raise MainAdvicePolicyError("G-Lite requires one legal alternative to G")
    candidates = (baseline, *alternatives[: specification.candidate_limit - 1])
    gap = baseline.mean - candidates[1].mean
    ambiguity_limit = abs(current_mean) * specification.ambiguity_fraction
    if gap > ambiguity_limit + 1e-12:
        return MainStrategyDecision(
            strategy_id,
            baseline.action,
            baseline.action,
            False,
            {
                "mode": "selective-two-step-clear-greedy-margin",
                "greedy_action_id": baseline.action_id,
                "immediate_gap": gap,
                "ambiguity_limit": ambiguity_limit,
            },
        )
    scored = []
    for row in candidates:
        values = [continuation_value(row.action, index) for index in range(specification.sample_count)]
        scored.append(
            (
                float(np.mean([value[0] for value in values])),
                float(np.mean([value[1] for value in values])),
                row,
            )
        )
    selected = min(
        scored,
        key=lambda item: (-item[0], -item[1], item[2].action_id),
    )
    baseline_value = next(item for item in scored if item[2].action_id == baseline.action_id)
    minimum_override = abs(current_mean) * specification.minimum_override_fraction
    if (
        selected[2].action_id != baseline.action_id
        and selected[0] < baseline_value[0] + minimum_override - 1e-12
    ):
        selected = baseline_value
    return MainStrategyDecision(
        strategy_id,
        selected[2].action,
        baseline.action,
        True,
        {
            "mode": "greedy-selective-two-step",
            "trigger_index": g_lite_triggers_used + 1,
            "max_triggers_per_episode": specification.max_triggers_per_episode,
            "sample_count": specification.sample_count,
            "immediate_gap": gap,
            "ambiguity_limit": ambiguity_limit,
            "minimum_override": minimum_override,
            "greedy_action_id": baseline.action_id,
            "selected_action_id": selected[2].action_id,
            "candidates": [
                {
                    "action_id": row.action_id,
                    "two_step_mean": mean,
                    "two_step_cvar_proxy": cvar,
                }
                for mean, cvar, row in scored
            ],
        },
    )


__all__ = [
    "MainAdvicePolicyError",
    "MainImmediateActionValue",
    "MainStrategyDecision",
    "choose_greedy_main_action",
    "choose_main_strategy_action",
    "main_state_payload",
    "main_state_sha256",
    "sample_g_lite_transition",
]
