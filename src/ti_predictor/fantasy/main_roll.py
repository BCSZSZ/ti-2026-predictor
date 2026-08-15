"""Independent TI 2026 Main Fantasy Roll state and transition entry points."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ti_predictor.fantasy.roll import (
    REFRESH,
    ApplyRollAction,
    BannerState,
    MutationOutcome,
    RollAction,
    RollActionError,
    RollOffer,
    RollRuleSet,
    RollStateError,
    _build_roll_rules,
    draw_roll_offer,
    validate_banner,
    validate_offer,
)
from ti_predictor.fantasy.roll import (
    enumerate_mutation_outcomes as _enumerate_mutation_outcomes,
)
from ti_predictor.fantasy.roll import (
    mutation_distribution as _mutation_distribution,
)
from ti_predictor.fantasy.roll import (
    operation_applies as _operation_applies,
)
from ti_predictor.fantasy.roll import (
    sample_mutation as _sample_mutation,
)

MAIN_PERIOD = "main"
MAIN_SLOT_COUNT = 5
MAIN_ROLL_COUNT = 30


@dataclass(frozen=True)
class MainRollState:
    banners: tuple[BannerState, ...]
    offer: RollOffer
    remaining_rolls: int
    period: str = MAIN_PERIOD
    slot_count: int = MAIN_SLOT_COUNT

    def __post_init__(self) -> None:
        object.__setattr__(self, "banners", tuple(self.banners))


def build_main_roll_rules(
    canonical_rules: Mapping[str, Any],
    client_roll: Mapping[str, Any],
) -> RollRuleSet:
    """Build the client-backed rules consumed only through the Main stack."""

    rules = _build_roll_rules(canonical_rules, client_roll)
    if rules.main_rolls != MAIN_ROLL_COUNT:
        raise RollStateError(f"Main execution requires exactly {MAIN_ROLL_COUNT} Rolls")
    return rules


def validate_main_state(state: MainRollState, rules: RollRuleSet) -> None:
    if state.period != MAIN_PERIOD:
        raise RollStateError("Main execution requires period=main")
    if state.slot_count != MAIN_SLOT_COUNT:
        raise RollStateError("Main execution requires exactly five active slots")
    if not isinstance(state.remaining_rolls, int) or isinstance(state.remaining_rolls, bool):
        raise RollStateError("remaining Rolls must be an integer")
    if not 0 <= state.remaining_rolls <= rules.main_rolls:
        raise RollStateError(f"remaining Rolls must be between 0 and {rules.main_rolls}")
    roles = tuple(banner.role for banner in state.banners)
    if roles != rules.roles:
        raise RollStateError(f"Main state Banner order must be {rules.roles}")
    for banner in state.banners:
        validate_banner(
            banner,
            rules,
            slot_count=MAIN_SLOT_COUNT,
            period_label="Main",
        )
    validate_offer(state.offer, rules)


def operation_applies(banner: BannerState, operation, rules: RollRuleSet) -> bool:
    return _operation_applies(
        banner,
        operation,
        rules,
        slot_count=MAIN_SLOT_COUNT,
    )


def enumerate_mutation_outcomes(
    banner: BannerState,
    operation_id: int,
    rules: RollRuleSet,
) -> tuple[BannerState, ...]:
    return _enumerate_mutation_outcomes(
        banner,
        operation_id,
        rules,
        slot_count=MAIN_SLOT_COUNT,
    )


def mutation_distribution(
    banner: BannerState,
    operation_id: int,
    rules: RollRuleSet,
    model_id: str,
) -> tuple[MutationOutcome, ...]:
    return _mutation_distribution(
        banner,
        operation_id,
        rules,
        model_id,
        slot_count=MAIN_SLOT_COUNT,
    )


def sample_mutation(
    banner: BannerState,
    operation_id: int,
    rules: RollRuleSet,
    model_id: str,
    rng: random.Random,
) -> BannerState:
    return _sample_mutation(
        banner,
        operation_id,
        rules,
        model_id,
        rng,
        slot_count=MAIN_SLOT_COUNT,
    )


def legal_actions(state: MainRollState, rules: RollRuleSet) -> tuple[RollAction, ...]:
    validate_main_state(state, rules)
    if state.remaining_rolls == 0:
        return ()
    actions: list[RollAction] = [REFRESH]
    for banner in state.banners:
        for operation_id in state.offer.operation_ids:
            operation = rules.operation(operation_id)
            if operation_applies(banner, operation, rules):
                actions.append(ApplyRollAction(banner.role, operation_id))
    return tuple(actions)


def _require_legal_apply(
    state: MainRollState,
    action: ApplyRollAction,
    rules: RollRuleSet,
) -> BannerState:
    validate_main_state(state, rules)
    if state.remaining_rolls == 0 or action.operation_id not in state.offer.operation_ids:
        raise RollActionError(f"operation {action.operation_id} is not legal for {action.banner_role}")
    banner = next((item for item in state.banners if item.role == action.banner_role), None)
    if banner is None or not operation_applies(banner, rules.operation(action.operation_id), rules):
        raise RollActionError(f"operation {action.operation_id} is not legal for {action.banner_role}")
    return banner


def _construct_applied_state(
    state: MainRollState,
    action: ApplyRollAction,
    realized_banner: BannerState,
    replacement_offer: RollOffer,
) -> MainRollState:
    banners = tuple(
        realized_banner if banner.role == action.banner_role else banner for banner in state.banners
    )
    return MainRollState(
        banners=banners,
        offer=replacement_offer,
        remaining_rolls=state.remaining_rolls - 1,
    )


def apply_realized_transition(
    state: MainRollState,
    action: ApplyRollAction,
    realized_banner: BannerState,
    replacement_offer: RollOffer,
    rules: RollRuleSet,
) -> MainRollState:
    current_banner = _require_legal_apply(state, action, rules)
    validate_offer(replacement_offer, rules)
    if realized_banner not in enumerate_mutation_outcomes(current_banner, action.operation_id, rules):
        raise RollActionError("realized Banner is outside this Main operation's legal support")
    return _construct_applied_state(state, action, realized_banner, replacement_offer)


def refresh_transition(
    state: MainRollState,
    replacement_offer: RollOffer,
    rules: RollRuleSet,
) -> MainRollState:
    validate_main_state(state, rules)
    if state.remaining_rolls == 0:
        raise RollActionError("no Roll token remains")
    validate_offer(replacement_offer, rules)
    return MainRollState(
        banners=state.banners,
        offer=replacement_offer,
        remaining_rolls=state.remaining_rolls - 1,
    )


def sample_apply_transition(
    state: MainRollState,
    action: ApplyRollAction,
    rules: RollRuleSet,
    model_id: str,
    rng: random.Random,
) -> MainRollState:
    current_banner = _require_legal_apply(state, action, rules)
    realized = sample_mutation(current_banner, action.operation_id, rules, model_id, rng)
    replacement_offer = draw_roll_offer(rules, model_id, rng)
    return _construct_applied_state(state, action, realized, replacement_offer)


def sample_refresh_transition(
    state: MainRollState,
    rules: RollRuleSet,
    model_id: str,
    rng: random.Random,
) -> MainRollState:
    validate_main_state(state, rules)
    if state.remaining_rolls == 0:
        raise RollActionError("no Roll token remains")
    replacement_offer = draw_roll_offer(rules, model_id, rng)
    return refresh_transition(state, replacement_offer, rules)


__all__ = [
    "MAIN_PERIOD",
    "MAIN_ROLL_COUNT",
    "MAIN_SLOT_COUNT",
    "MainRollState",
    "apply_realized_transition",
    "build_main_roll_rules",
    "enumerate_mutation_outcomes",
    "legal_actions",
    "mutation_distribution",
    "operation_applies",
    "refresh_transition",
    "sample_apply_transition",
    "sample_mutation",
    "sample_refresh_transition",
    "validate_main_state",
]
