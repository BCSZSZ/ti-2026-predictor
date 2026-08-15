"""Shared immutable Emblem primitives and the TI 2026 Group Roll stack.

Client-visible operation definitions are supplied by a rule snapshot.  The pure support route
does not assign probabilities; model-conditional sampling is kept in separate functions. Main
owns its state and transition entry points in :mod:`ti_predictor.fantasy.main_roll`.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cached_property
from itertools import combinations, product
from types import MappingProxyType
from typing import Any

GROUP_PERIOD = "group"
GROUP_SLOT_COUNT = 3

ROLL_QUALITY = "k_eFantasyMutationOperation_RollQuality"
ROLL_TRAIT = "k_eFantasyMutationOperation_RollShape"
ROLL_STAT = "k_eFantasyMutationOperation_RollStat"
INCREASE_ONE_QUALITY = "k_eFantasyMutationOperation_IncreaseOneQuality"
INCREASE_TWO_DECREASE_ONE = "k_eFantasyMutationOperation_IncreaseTwoQualitiesDecreaseOne"

TARGET_ALL = "k_eFantasyMutationTarget_All"
TARGET_ALL_COLOR = "k_eFantasyMutationTarget_AllColor"
TARGET_ONE_COLOR = "k_eFantasyMutationTarget_OneColor"
TARGET_FIRST_COLOR = "k_eFantasyMutationTarget_FirstColor"
TARGET_LAST_COLOR = "k_eFantasyMutationTarget_LastColor"

COLOR_TARGETS = {
    "k_eFantasyMutationTarget_Rubies": "red",
    "k_eFantasyMutationTarget_Sapphires": "blue",
    "k_eFantasyMutationTarget_Emeralds": "green",
}
SUPPORTED_MUTATIONS = {
    ROLL_QUALITY,
    ROLL_TRAIT,
    ROLL_STAT,
    INCREASE_ONE_QUALITY,
    INCREASE_TWO_DECREASE_ONE,
}
SUPPORTED_TARGETS = set(COLOR_TARGETS) | {
    TARGET_ALL,
    TARGET_ALL_COLOR,
    TARGET_ONE_COLOR,
    TARGET_FIRST_COLOR,
    TARGET_LAST_COLOR,
}


class RollRuleError(ValueError):
    """The client snapshot and canonical Roll contract cannot form a safe rule set."""


class RollStateError(ValueError):
    """A Roll state violates its frozen Period contract."""


class RollActionError(ValueError):
    """A requested transition is not legal from the supplied state."""


@dataclass(frozen=True, order=True)
class EmblemState:
    stat_id: str
    quality_tier: int
    trait_id: str


@dataclass(frozen=True, order=True)
class BannerState:
    role: str
    emblems: tuple[EmblemState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "emblems", tuple(self.emblems))


@dataclass(frozen=True, order=True)
class RollOffer:
    operation_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        values = tuple(self.operation_ids)
        object.__setattr__(self, "operation_ids", values)
        if len(values) != 3:
            raise RollStateError("a Roll offer must contain exactly three operations")
        if len(set(values)) != len(values):
            raise RollStateError("a Roll offer must contain three unique operations")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise RollStateError("Roll operation IDs must be integers")


@dataclass(frozen=True)
class GroupRollState:
    banners: tuple[BannerState, ...]
    offer: RollOffer
    remaining_rolls: int
    period: str = GROUP_PERIOD
    slot_count: int = GROUP_SLOT_COUNT

    def __post_init__(self) -> None:
        object.__setattr__(self, "banners", tuple(self.banners))


@dataclass(frozen=True, order=True)
class ApplyRollAction:
    banner_role: str
    operation_id: int


@dataclass(frozen=True, order=True)
class RefreshRollAction:
    """Spend one token to replace the shared offer without changing a Banner."""


type RollAction = ApplyRollAction | RefreshRollAction
REFRESH = RefreshRollAction()


@dataclass(frozen=True)
class RollOperation:
    operation_id: int
    roll_weight: float
    operation_target: str | None
    description_key: str | None
    mutation: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class RollRuleSet:
    stats_by_color: tuple[tuple[str, tuple[str, ...]], ...]
    traits: tuple[str, ...]
    quality_weights: tuple[tuple[int, float], ...]
    banner_colors: tuple[tuple[str, tuple[str, ...]], ...]
    operations: tuple[RollOperation, ...]
    model_powers: tuple[tuple[str, float], ...]
    offer_size: int
    group_rolls: int
    main_rolls: int

    @cached_property
    def _stat_index(self) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(dict(self.stats_by_color))

    @cached_property
    def _stat_color_index(self) -> Mapping[str, str]:
        return MappingProxyType(
            {stat_id: color for color, stat_ids in self.stats_by_color for stat_id in stat_ids}
        )

    @cached_property
    def _banner_index(self) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(dict(self.banner_colors))

    @cached_property
    def _operation_index(self) -> Mapping[int, RollOperation]:
        return MappingProxyType({item.operation_id: item for item in self.operations})

    @cached_property
    def _model_index(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self.model_powers))

    def stats_for(self, color: str) -> tuple[str, ...]:
        try:
            return self._stat_index[color]
        except KeyError as error:
            raise RollRuleError(f"unknown Emblem color: {color}") from error

    def color_for_stat(self, stat_id: str) -> str:
        try:
            return self._stat_color_index[stat_id]
        except KeyError as error:
            raise RollRuleError(f"unknown Fantasy Stat: {stat_id}") from error

    def colors_for(self, role: str) -> tuple[str, ...]:
        try:
            return self._banner_index[role]
        except KeyError as error:
            raise RollRuleError(f"unknown War Banner role: {role}") from error

    def operation(self, operation_id: int, *, offered: bool = True) -> RollOperation:
        try:
            operation = self._operation_index[operation_id]
        except KeyError as error:
            raise RollRuleError(f"unknown Roll operation ID: {operation_id}") from error
        if offered and operation.roll_weight <= 0:
            raise RollRuleError(f"operation {operation_id} is a zero-weight audit template")
        return operation

    def model_power(self, model_id: str) -> float:
        try:
            return self._model_index[model_id]
        except KeyError as error:
            raise RollRuleError(f"unknown Roll transition model: {model_id}") from error

    @property
    def offered_operations(self) -> tuple[RollOperation, ...]:
        return tuple(item for item in self.operations if item.roll_weight > 0)

    @property
    def group_roles(self) -> tuple[str, ...]:
        return tuple(role for role, _ in self.banner_colors)

    @property
    def roles(self) -> tuple[str, ...]:
        """Canonical role order shared by the two independently validated Period stacks."""

        return self.group_roles


@dataclass(frozen=True)
class MutationOutcome:
    banner: BannerState
    probability: float


@dataclass(frozen=True)
class ActionInterval:
    action: RollAction
    lower: float
    upper: float


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RollRuleError(message)


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RollRuleError(f"{label} must be a mapping")
    return value


def _as_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RollRuleError(f"{label} must be a sequence")
    return value


def _targets_are_unambiguous(mutation: str, targets: tuple[str, ...]) -> bool:
    target_set = set(targets)
    if len(target_set) != len(targets):
        return False
    if mutation in {INCREASE_ONE_QUALITY, INCREASE_TWO_DECREASE_ONE}:
        return target_set == {TARGET_ALL}
    color_count = sum(flag in target_set for flag in COLOR_TARGETS)
    selector_count = sum(
        flag in target_set
        for flag in (TARGET_ALL_COLOR, TARGET_ONE_COLOR, TARGET_FIRST_COLOR, TARGET_LAST_COLOR)
    )
    return len(target_set) == 2 and color_count == 1 and selector_count == 1


def _build_roll_rules(canonical_rules: Mapping[str, Any], client_roll: Mapping[str, Any]) -> RollRuleSet:
    """Parse period-independent client evidence for the two isolated Roll stacks."""

    fantasy = _as_mapping(canonical_rules.get("fantasy"), "fantasy rules")
    roll = _as_mapping(fantasy.get("roll"), "fantasy.roll")
    _require(
        roll.get("supported_periods") == ["group", "main"],
        "Group and Main Roll execution must both be declared",
    )
    offer = _as_mapping(roll.get("offer"), "fantasy.roll.offer")
    _require(
        offer
        == {
            "count": 3,
            "unique": True,
            "shared_across_banners": True,
            "apply_replaces_all": True,
            "refresh_replaces_all": True,
        },
        "canonical Roll offer contract is not supported",
    )
    _require(roll.get("token_cost") == {"apply": 1, "refresh": 1}, "Roll token costs must both be one")
    _require(
        roll.get("application_scope") == "selected_banner_only",
        "Roll application must affect the selected Banner only",
    )
    _require(
        roll.get("outcome_assumptions")
        == {
            "reroll_may_repeat_current": True,
            "multi_target_draws": "independent",
            "one_color_target": "all_matching_slots_in_support",
            "increase_one_quality": "each_slot_increment_clamped",
            "increase_two_decrease_one": "uniform_distinct_two_increased_one_decreased_clamped",
            "quality_bounds": [1, 5],
            "unweighted_model_choices": "uniform",
        },
        "canonical outcome assumptions differ from the implemented support model",
    )
    _require(client_roll.get("offer_size") == 3, "client Roll offer size must be three")

    canonical_stats = _as_mapping(fantasy.get("stats"), "fantasy.stats")
    canonical_stats_by_color: dict[str, tuple[str, ...]] = {}
    for color in ("red", "blue", "green"):
        values = tuple(
            stat_id
            for stat_id, definition in canonical_stats.items()
            if _as_mapping(definition, f"stat {stat_id}").get("color") == color
        )
        _require(bool(values), f"canonical rules expose no {color} Stats")
        canonical_stats_by_color[color] = values
    _require(
        all(len(values) == 6 for values in canonical_stats_by_color.values())
        and len({stat for values in canonical_stats_by_color.values() for stat in values}) == 18,
        "canonical rules must expose six unique Stats per color",
    )
    observed_gems = {
        item.get("color"): (item.get("client_type"), tuple(item.get("stat_ids", ())))
        for item in _as_sequence(client_roll.get("gems"), "client gems")
        if isinstance(item, Mapping)
    }
    expected_gem_types = {
        color: client_type
        for color, client_type in zip(
            ("red", "blue", "green"),
            ("FANTASY_GEM_TYPE_RUBY", "FANTASY_GEM_TYPE_SAPPHIRE", "FANTASY_GEM_TYPE_EMERALD"),
            strict=True,
        )
    }
    _require(
        set(observed_gems) == set(expected_gem_types)
        and all(
            observed_gems[color][0] == expected_gem_types[color]
            and set(observed_gems[color][1]) == set(canonical_stats_by_color[color])
            and len(observed_gems[color][1]) == 6
            for color in expected_gem_types
        ),
        "client Gem Stats differ from canonical rules",
    )
    # The client contract is the authoritative order for deterministic draws;
    # canonical JSON object key sorting must not silently reorder these choices.
    stats_by_color = tuple((color, observed_gems[color][1]) for color in ("red", "blue", "green"))

    canonical_traits = _as_sequence(fantasy.get("traits"), "fantasy.traits")
    traits = tuple(str(_as_mapping(item, "trait").get("id")) for item in canonical_traits)
    _require(len(traits) == 5 and len(set(traits)) == 5, "canonical rules must expose five unique Traits")
    expected_shapes = {
        int(_as_mapping(item, "trait")["shape_id"]): str(_as_mapping(item, "trait")["client_behavior"])
        for item in canonical_traits
    }
    observed_shapes = {
        int(item["shape_id"]): str(item["client_behavior"])
        for item in _as_sequence(client_roll.get("traits"), "client traits")
        if isinstance(item, Mapping) and item.get("shape_id") is not None
    }
    _require(observed_shapes == expected_shapes, "client Trait Shapes differ from canonical rules")

    canonical_qualities = _as_sequence(fantasy.get("qualities"), "fantasy.qualities")
    quality_definitions = tuple(
        (
            int(_as_mapping(item, "quality")["tier"]),
            int(_as_mapping(item, "quality")["bonus_percent"]),
            float(_as_mapping(item, "quality")["roll_weight"]),
        )
        for item in canonical_qualities
    )
    quality_weights = tuple((tier, weight) for tier, _, weight in quality_definitions)
    _require(tuple(tier for tier, _ in quality_weights) == (1, 2, 3, 4, 5), "Quality tiers must be T1-T5")
    _require(all(weight > 0 for _, weight in quality_weights), "Quality weights must be positive")
    observed_qualities = tuple(
        (int(item["tier"]), int(item["bonus_percent"]), float(item["roll_weight"]))
        for item in _as_sequence(client_roll.get("qualities"), "client qualities")
        if isinstance(item, Mapping)
    )
    _require(
        observed_qualities == quality_definitions,
        "client Quality definitions differ from canonical rules",
    )

    canonical_banners = _as_mapping(fantasy.get("role_banners"), "fantasy.role_banners")
    banner_colors = tuple(
        (str(role), tuple(str(color) for color in colors)) for role, colors in canonical_banners.items()
    )
    required_levels = (1, 1, 1, 2, 3)
    observed_banners = {
        item.get("role"): tuple(
            (slot.get("slot"), slot.get("color"), slot.get("required_tablet_level"))
            for slot in item.get("slots", ())
        )
        for item in _as_sequence(client_roll.get("banners"), "client banners")
        if isinstance(item, Mapping)
    }
    expected_banners = {
        role: tuple((index, color, required_levels[index - 1]) for index, color in enumerate(colors, start=1))
        for role, colors in banner_colors
    }
    _require(observed_banners == expected_banners, "client Banner slots differ from canonical rules")
    _require(
        all(len(colors) >= 5 for _, colors in banner_colors),
        "every role needs all five declared Banner slots",
    )

    raw_operations = _as_sequence(client_roll.get("operations"), "client operations")
    operations: list[RollOperation] = []
    for raw in raw_operations:
        item = _as_mapping(raw, "Roll operation")
        mutations = _as_sequence(item.get("mutations"), "Roll mutations")
        _require(len(mutations) == 1, "each Roll operation must contain exactly one mutation")
        mutation = _as_mapping(mutations[0], "Roll mutation")
        operation_id = item.get("operation_id")
        weight = item.get("roll_weight")
        _require(
            isinstance(operation_id, int) and not isinstance(operation_id, bool), "operation ID is invalid"
        )
        _require(
            isinstance(weight, int) and not isinstance(weight, bool) and weight >= 0,
            "operation weight is invalid",
        )
        operations.append(
            RollOperation(
                operation_id=operation_id,
                roll_weight=float(weight),
                operation_target=str(item["operation_target"]) if item.get("operation_target") else None,
                description_key=str(item["description_key"]) if item.get("description_key") else None,
                mutation=str(mutation.get("operation")),
                targets=tuple(
                    str(value) for value in _as_sequence(mutation.get("targets"), "mutation targets")
                ),
            )
        )
    operation_ids = tuple(item.operation_id for item in operations)
    _require(len(operation_ids) == len(set(operation_ids)), "Roll operation IDs must be unique")
    contract = _as_mapping(roll.get("client_contract"), "Roll client contract")
    expected_positive = tuple(int(value) for value in contract.get("positive_operation_ids", ()))
    expected_zero = tuple(int(value) for value in contract.get("zero_weight_template_ids", ()))
    positive = tuple(item for item in operations if item.roll_weight > 0)
    zero = tuple(item for item in operations if item.roll_weight == 0)
    _require(
        tuple(item.operation_id for item in positive) == expected_positive, "positive operation IDs drifted"
    )
    _require(tuple(item.operation_id for item in zero) == expected_zero, "zero-weight operation IDs drifted")
    _require(
        math.isclose(sum(item.roll_weight for item in positive), float(contract.get("positive_weight_sum"))),
        "positive operation weights drifted",
    )
    for operation in positive:
        _require(operation.mutation in SUPPORTED_MUTATIONS, f"unsupported mutation: {operation.mutation}")
        _require(bool(operation.targets), f"operation {operation.operation_id} has no targets")
        _require(
            set(operation.targets) <= SUPPORTED_TARGETS,
            f"operation {operation.operation_id} has unknown targets",
        )
        _require(
            _targets_are_unambiguous(operation.mutation, operation.targets),
            f"operation {operation.operation_id} has ambiguous targets",
        )
        _require(
            bool(operation.description_key), f"operation {operation.operation_id} has no description key"
        )

    model_powers = tuple(
        (str(item["id"]), float(item["exposed_weight_power"]))
        for item in _as_sequence(roll.get("transition_models"), "Roll transition models")
        if isinstance(item, Mapping)
    )
    _require(
        dict(model_powers)
        == {
            "client-weight-primary-v1": 1.0,
            "flattened-weights-v1": 0.5,
            "sharpened-weights-v1": 2.0,
        },
        "transition model preregistration drifted",
    )
    periods = {
        item.get("id"): item
        for item in _as_sequence(fantasy.get("periods"), "fantasy.periods")
        if isinstance(item, Mapping)
    }
    group_rolls = int(_as_mapping(periods.get(GROUP_PERIOD), "Group period").get("new_rolls", -1))
    _require(group_rolls == 40, "Group period must grant 40 Rolls")
    main_rolls = int(_as_mapping(periods.get("main"), "Main period").get("new_rolls", -1))
    _require(main_rolls == 30, "Main period must grant 30 Rolls")

    return RollRuleSet(
        stats_by_color=stats_by_color,
        traits=traits,
        quality_weights=quality_weights,
        banner_colors=banner_colors,
        operations=tuple(operations),
        model_powers=model_powers,
        offer_size=3,
        group_rolls=group_rolls,
        main_rolls=main_rolls,
    )


def build_group_roll_rules(canonical_rules: Mapping[str, Any], client_roll: Mapping[str, Any]) -> RollRuleSet:
    """Build the shared evidence contract consumed by the isolated Group stack."""

    return _build_roll_rules(canonical_rules, client_roll)


def validate_banner(
    banner: BannerState,
    rules: RollRuleSet,
    *,
    slot_count: int = GROUP_SLOT_COUNT,
    period_label: str = "Group",
) -> None:
    try:
        expected_colors = rules.colors_for(banner.role)[:slot_count]
    except RollRuleError as error:
        raise RollStateError(str(error)) from error
    if len(banner.emblems) != slot_count:
        number = {3: "three", 5: "five"}.get(slot_count, str(slot_count))
        raise RollStateError(f"a {period_label} War Banner must contain exactly {number} Emblems")
    legal_qualities = {tier for tier, _ in rules.quality_weights}
    for index, (emblem, expected_color) in enumerate(zip(banner.emblems, expected_colors, strict=True)):
        try:
            stat_color = rules.color_for_stat(emblem.stat_id)
        except RollRuleError:
            stat_color = None
        if stat_color != expected_color:
            raise RollStateError(
                f"{banner.role} slot {index + 1} requires a {expected_color} Stat, got {emblem.stat_id}"
            )
        if emblem.quality_tier not in legal_qualities:
            raise RollStateError(f"unknown Quality tier: {emblem.quality_tier}")
        if emblem.trait_id not in rules.traits:
            raise RollStateError(f"unknown Trait: {emblem.trait_id}")


def validate_offer(offer: RollOffer, rules: RollRuleSet) -> None:
    if len(offer.operation_ids) != rules.offer_size:
        raise RollStateError("Roll offer size differs from the client snapshot")
    for operation_id in offer.operation_ids:
        try:
            rules.operation(operation_id)
        except RollRuleError as error:
            raise RollStateError(str(error)) from error


def validate_group_state(state: GroupRollState, rules: RollRuleSet) -> None:
    if state.period != GROUP_PERIOD:
        raise RollStateError("Group state requires period=group; route Main through MainRollState")
    if state.slot_count != GROUP_SLOT_COUNT:
        raise RollStateError("Group execution requires exactly three active slots")
    if not isinstance(state.remaining_rolls, int) or isinstance(state.remaining_rolls, bool):
        raise RollStateError("remaining Rolls must be an integer")
    if not 0 <= state.remaining_rolls <= rules.group_rolls:
        raise RollStateError(f"remaining Rolls must be between 0 and {rules.group_rolls}")
    roles = tuple(banner.role for banner in state.banners)
    if roles != rules.group_roles:
        raise RollStateError(f"Group state Banner order must be {rules.group_roles}")
    for banner in state.banners:
        validate_banner(banner, rules)
    validate_offer(state.offer, rules)


def _operation_target_options(
    banner: BannerState, operation: RollOperation, rules: RollRuleSet
) -> tuple[tuple[int, ...], ...]:
    targets = set(operation.targets)
    if operation.mutation in {INCREASE_ONE_QUALITY, INCREASE_TWO_DECREASE_ONE}:
        if targets != {TARGET_ALL}:
            raise RollRuleError(f"operation {operation.operation_id} has ambiguous all-Banner targets")
        return (tuple(range(len(banner.emblems))),)

    colors = [color for flag, color in COLOR_TARGETS.items() if flag in targets]
    selectors = targets & {
        TARGET_ALL_COLOR,
        TARGET_ONE_COLOR,
        TARGET_FIRST_COLOR,
        TARGET_LAST_COLOR,
    }
    if len(colors) != 1 or len(selectors) != 1 or len(targets) != 2:
        raise RollRuleError(f"operation {operation.operation_id} has ambiguous color targets")
    expected_colors = rules.colors_for(banner.role)[: len(banner.emblems)]
    matching = tuple(index for index, color in enumerate(expected_colors) if color == colors[0])
    if not matching:
        return ()
    selector = next(iter(selectors))
    if selector == TARGET_ALL_COLOR:
        return (matching,)
    if selector == TARGET_ONE_COLOR:
        return tuple((index,) for index in matching)
    if selector == TARGET_FIRST_COLOR:
        return ((matching[0],),)
    if selector == TARGET_LAST_COLOR:
        return ((matching[-1],),)
    raise RollRuleError(f"unsupported target selector: {selector}")


def operation_applies(
    banner: BannerState,
    operation: RollOperation,
    rules: RollRuleSet,
    *,
    slot_count: int = GROUP_SLOT_COUNT,
) -> bool:
    validate_banner(banner, rules, slot_count=slot_count)
    if operation.roll_weight <= 0:
        return False
    return bool(_operation_target_options(banner, operation, rules))


def _replace_attributes(
    banner: BannerState,
    indices: tuple[int, ...],
    attribute: str,
    values: tuple[Any, ...],
) -> BannerState:
    emblems = list(banner.emblems)
    for index, value in zip(indices, values, strict=True):
        emblems[index] = replace(emblems[index], **{attribute: value})
    return BannerState(role=banner.role, emblems=tuple(emblems))


def _increase_two_decrease_targets(slot_count: int) -> tuple[tuple[int, tuple[int, int]], ...]:
    if slot_count < 3:
        raise RollRuleError("increase-two-decrease-one requires at least three Emblems")
    return tuple(
        (decreased, increased)
        for decreased in range(slot_count)
        for increased in combinations(
            (index for index in range(slot_count) if index != decreased),
            2,
        )
    )


def _increase_two_decrease_qualities(
    banner: BannerState,
    decreased: int,
    increased: tuple[int, int],
) -> tuple[int, ...]:
    increased_set = set(increased)
    return tuple(
        max(1, emblem.quality_tier - 1)
        if index == decreased
        else min(5, emblem.quality_tier + 1)
        if index in increased_set
        else emblem.quality_tier
        for index, emblem in enumerate(banner.emblems)
    )


def enumerate_mutation_outcomes(
    banner: BannerState,
    operation_id: int,
    rules: RollRuleSet,
    *,
    slot_count: int = GROUP_SLOT_COUNT,
) -> tuple[BannerState, ...]:
    """Return exact legal support without assigning any outcome probability."""

    validate_banner(banner, rules, slot_count=slot_count)
    operation = rules.operation(operation_id)
    target_options = _operation_target_options(banner, operation, rules)
    if not target_options:
        return ()
    outcomes: dict[BannerState, None] = {}
    if operation.mutation == INCREASE_ONE_QUALITY:
        for index in range(len(banner.emblems)):
            quality = min(5, banner.emblems[index].quality_tier + 1)
            outcomes[_replace_attributes(banner, (index,), "quality_tier", (quality,))] = None
    elif operation.mutation == INCREASE_TWO_DECREASE_ONE:
        for decreased, increased in _increase_two_decrease_targets(len(banner.emblems)):
            qualities = _increase_two_decrease_qualities(banner, decreased, increased)
            outcomes[_replace_attributes(banner, tuple(range(len(qualities))), "quality_tier", qualities)] = (
                None
            )
    else:
        attribute = {
            ROLL_QUALITY: "quality_tier",
            ROLL_TRAIT: "trait_id",
            ROLL_STAT: "stat_id",
        }[operation.mutation]
        for indices in target_options:
            choices: list[tuple[Any, ...]] = []
            for index in indices:
                if operation.mutation == ROLL_QUALITY:
                    choices.append(tuple(tier for tier, _ in rules.quality_weights))
                elif operation.mutation == ROLL_TRAIT:
                    choices.append(rules.traits)
                else:
                    color = rules.colors_for(banner.role)[index]
                    choices.append(rules.stats_for(color))
            for values in product(*choices):
                outcomes[_replace_attributes(banner, indices, attribute, tuple(values))] = None
    return tuple(outcomes)


def _normalized_weighted_values(
    values: Sequence[tuple[Any, float]], power: float
) -> tuple[tuple[Any, float], ...]:
    powered = tuple((value, float(weight) ** power) for value, weight in values)
    total = sum(weight for _, weight in powered)
    if total <= 0 or not math.isfinite(total):
        raise RollRuleError("model-transformed weights must have a finite positive sum")
    return tuple((value, weight / total) for value, weight in powered)


def mutation_distribution(
    banner: BannerState,
    operation_id: int,
    rules: RollRuleSet,
    model_id: str,
    *,
    slot_count: int = GROUP_SLOT_COUNT,
) -> tuple[MutationOutcome, ...]:
    """Assign probabilities only under one explicitly named transition model."""

    validate_banner(banner, rules, slot_count=slot_count)
    power = rules.model_power(model_id)
    operation = rules.operation(operation_id)
    target_options = _operation_target_options(banner, operation, rules)
    if not target_options:
        return ()
    probabilities: dict[BannerState, float] = {}

    def add(outcome: BannerState, probability: float) -> None:
        probabilities[outcome] = probabilities.get(outcome, 0.0) + probability

    if operation.mutation == INCREASE_ONE_QUALITY:
        probability = 1.0 / len(banner.emblems)
        for index in range(len(banner.emblems)):
            quality = min(5, banner.emblems[index].quality_tier + 1)
            add(_replace_attributes(banner, (index,), "quality_tier", (quality,)), probability)
    elif operation.mutation == INCREASE_TWO_DECREASE_ONE:
        targets = _increase_two_decrease_targets(len(banner.emblems))
        probability = 1.0 / len(targets)
        for decreased, increased in targets:
            qualities = _increase_two_decrease_qualities(banner, decreased, increased)
            add(
                _replace_attributes(banner, tuple(range(len(qualities))), "quality_tier", qualities),
                probability,
            )
    else:
        attribute = {
            ROLL_QUALITY: "quality_tier",
            ROLL_TRAIT: "trait_id",
            ROLL_STAT: "stat_id",
        }[operation.mutation]
        target_probability = 1.0 / len(target_options)
        for indices in target_options:
            choices: list[tuple[tuple[Any, float], ...]] = []
            for index in indices:
                if operation.mutation == ROLL_QUALITY:
                    choices.append(_normalized_weighted_values(rules.quality_weights, power))
                elif operation.mutation == ROLL_TRAIT:
                    choices.append(tuple((trait, 1.0 / len(rules.traits)) for trait in rules.traits))
                else:
                    color = rules.colors_for(banner.role)[index]
                    stats = rules.stats_for(color)
                    choices.append(tuple((stat, 1.0 / len(stats)) for stat in stats))
            for selections in product(*choices):
                values = tuple(value for value, _ in selections)
                probability = target_probability * math.prod(
                    value_probability for _, value_probability in selections
                )
                add(_replace_attributes(banner, indices, attribute, values), probability)

    total = sum(probabilities.values())
    if not math.isclose(total, 1.0, rel_tol=1e-12, abs_tol=1e-12):
        raise RollRuleError(f"mutation probabilities sum to {total}, not one")
    return tuple(
        MutationOutcome(banner=outcome, probability=probability)
        for outcome, probability in probabilities.items()
    )


def _weighted_pick(values: Sequence[Any], weights: Sequence[float], rng: random.Random) -> Any:
    total = float(sum(weights))
    if len(values) != len(weights) or not values or total <= 0 or not math.isfinite(total):
        raise RollRuleError("weighted draw requires aligned finite positive weights")
    threshold = rng.random() * total
    cumulative = 0.0
    for value, weight in zip(values, weights, strict=True):
        cumulative += float(weight)
        if threshold < cumulative:
            return value
    return values[-1]


def draw_roll_offer(rules: RollRuleSet, model_id: str, rng: random.Random) -> RollOffer:
    """Draw three unique operations using exposed client weights without replacement."""

    power = rules.model_power(model_id)
    remaining = list(rules.offered_operations)
    selected: list[int] = []
    for _ in range(rules.offer_size):
        weights = [item.roll_weight**power for item in remaining]
        chosen = _weighted_pick(remaining, weights, rng)
        selected.append(chosen.operation_id)
        remaining.remove(chosen)
    return RollOffer(tuple(selected))


def sample_mutation(
    banner: BannerState,
    operation_id: int,
    rules: RollRuleSet,
    model_id: str,
    rng: random.Random,
    *,
    slot_count: int = GROUP_SLOT_COUNT,
) -> BannerState:
    validate_banner(banner, rules, slot_count=slot_count)
    power = rules.model_power(model_id)
    operation = rules.operation(operation_id)
    target_options = _operation_target_options(banner, operation, rules)
    if not target_options:
        raise RollActionError(f"operation {operation_id} does not apply to {banner.role}")
    if operation.mutation == INCREASE_ONE_QUALITY:
        index = _weighted_pick(
            tuple(range(len(banner.emblems))),
            (1.0,) * len(banner.emblems),
            rng,
        )
        quality = min(5, banner.emblems[index].quality_tier + 1)
        return _replace_attributes(banner, (index,), "quality_tier", (quality,))
    if operation.mutation == INCREASE_TWO_DECREASE_ONE:
        decreased = _weighted_pick(
            tuple(range(len(banner.emblems))),
            (1.0,) * len(banner.emblems),
            rng,
        )
        available_pairs = tuple(
            combinations(
                (index for index in range(len(banner.emblems)) if index != decreased),
                2,
            )
        )
        increased = (
            available_pairs[0]
            if len(available_pairs) == 1
            else _weighted_pick(available_pairs, (1.0,) * len(available_pairs), rng)
        )
        qualities = _increase_two_decrease_qualities(banner, decreased, increased)
        return _replace_attributes(
            banner,
            tuple(range(len(qualities))),
            "quality_tier",
            qualities,
        )

    indices = _weighted_pick(target_options, (1.0,) * len(target_options), rng)
    attribute = {
        ROLL_QUALITY: "quality_tier",
        ROLL_TRAIT: "trait_id",
        ROLL_STAT: "stat_id",
    }[operation.mutation]
    values: list[Any] = []
    for index in indices:
        if operation.mutation == ROLL_QUALITY:
            choices = _normalized_weighted_values(rules.quality_weights, power)
        elif operation.mutation == ROLL_TRAIT:
            choices = tuple((trait, 1.0) for trait in rules.traits)
        else:
            color = rules.colors_for(banner.role)[index]
            choices = tuple((stat, 1.0) for stat in rules.stats_for(color))
        values.append(
            _weighted_pick(
                tuple(value for value, _ in choices),
                tuple(weight for _, weight in choices),
                rng,
            )
        )
    return _replace_attributes(banner, indices, attribute, tuple(values))


def legal_actions(state: GroupRollState, rules: RollRuleSet) -> tuple[RollAction, ...]:
    validate_group_state(state, rules)
    if state.remaining_rolls == 0:
        return ()
    actions: list[RollAction] = [REFRESH]
    for banner in state.banners:
        for operation_id in state.offer.operation_ids:
            operation = rules.operation(operation_id)
            if operation_applies(banner, operation, rules):
                actions.append(ApplyRollAction(banner.role, operation_id))
    return tuple(actions)


def _require_legal_apply(state: GroupRollState, action: ApplyRollAction, rules: RollRuleSet) -> BannerState:
    validate_group_state(state, rules)
    if state.remaining_rolls == 0 or action.operation_id not in state.offer.operation_ids:
        raise RollActionError(f"operation {action.operation_id} is not legal for {action.banner_role}")
    banner = next((item for item in state.banners if item.role == action.banner_role), None)
    if banner is None or not operation_applies(banner, rules.operation(action.operation_id), rules):
        raise RollActionError(f"operation {action.operation_id} is not legal for {action.banner_role}")
    return banner


def apply_realized_transition(
    state: GroupRollState,
    action: ApplyRollAction,
    realized_banner: BannerState,
    replacement_offer: RollOffer,
    rules: RollRuleSet,
) -> GroupRollState:
    """Construct the exact next state from an already realized legal mutation and offer."""

    current_banner = _require_legal_apply(state, action, rules)
    validate_offer(replacement_offer, rules)
    support = enumerate_mutation_outcomes(current_banner, action.operation_id, rules)
    if realized_banner not in support:
        raise RollActionError("realized Banner is outside this operation's legal support")
    return _construct_applied_state(state, action, realized_banner, replacement_offer)


def _construct_applied_state(
    state: GroupRollState,
    action: ApplyRollAction,
    realized_banner: BannerState,
    replacement_offer: RollOffer,
) -> GroupRollState:
    banners = tuple(
        realized_banner if banner.role == action.banner_role else banner for banner in state.banners
    )
    return GroupRollState(
        banners=banners,
        offer=replacement_offer,
        remaining_rolls=state.remaining_rolls - 1,
        period=state.period,
        slot_count=state.slot_count,
    )


def refresh_transition(
    state: GroupRollState, replacement_offer: RollOffer, rules: RollRuleSet
) -> GroupRollState:
    validate_group_state(state, rules)
    if state.remaining_rolls == 0:
        raise RollActionError("no Roll token remains")
    validate_offer(replacement_offer, rules)
    return _construct_refreshed_state(state, replacement_offer)


def _construct_refreshed_state(state: GroupRollState, replacement_offer: RollOffer) -> GroupRollState:
    return GroupRollState(
        banners=state.banners,
        offer=replacement_offer,
        remaining_rolls=state.remaining_rolls - 1,
        period=state.period,
        slot_count=state.slot_count,
    )


def sample_apply_transition(
    state: GroupRollState,
    action: ApplyRollAction,
    rules: RollRuleSet,
    model_id: str,
    rng: random.Random,
) -> GroupRollState:
    current_banner = _require_legal_apply(state, action, rules)
    realized = sample_mutation(current_banner, action.operation_id, rules, model_id, rng)
    replacement_offer = draw_roll_offer(rules, model_id, rng)
    return _construct_applied_state(state, action, realized, replacement_offer)


def sample_refresh_transition(
    state: GroupRollState,
    rules: RollRuleSet,
    model_id: str,
    rng: random.Random,
) -> GroupRollState:
    validate_group_state(state, rules)
    if state.remaining_rolls == 0:
        raise RollActionError("no Roll token remains")
    replacement_offer = draw_roll_offer(rules, model_id, rng)
    return _construct_refreshed_state(state, replacement_offer)


def rank_rate_agnostic_actions(
    state: GroupRollState,
    rules: RollRuleSet,
    banner_value: Callable[[BannerState], float],
) -> tuple[ActionInterval, ...]:
    """Rank worst/best value deltas over full legal support, without outcome rates."""

    intervals: list[ActionInterval] = []
    banners = {banner.role: banner for banner in state.banners}
    for action in legal_actions(state, rules):
        if isinstance(action, RefreshRollAction):
            intervals.append(ActionInterval(action=action, lower=0.0, upper=0.0))
            continue
        current = float(banner_value(banners[action.banner_role]))
        values = [
            float(banner_value(outcome)) - current
            for outcome in enumerate_mutation_outcomes(
                banners[action.banner_role], action.operation_id, rules
            )
        ]
        if not values or not all(math.isfinite(value) for value in values):
            raise RollActionError("Rate-agnostic valuation must return finite values for all outcomes")
        intervals.append(ActionInterval(action=action, lower=min(values), upper=max(values)))

    def tie_breaker(item: ActionInterval) -> tuple[Any, ...]:
        refresh_priority = 0 if isinstance(item.action, RefreshRollAction) else 1
        if isinstance(item.action, RefreshRollAction):
            identity: tuple[Any, ...] = ("", -1)
        else:
            identity = (item.action.banner_role, item.action.operation_id)
        return (-item.lower, -item.upper, refresh_priority, identity)

    return tuple(sorted(intervals, key=tie_breaker))
