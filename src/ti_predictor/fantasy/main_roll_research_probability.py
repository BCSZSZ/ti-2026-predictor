"""Probability providers for the isolated Main Roll simulator.

The client-backed Main module remains the owner of legal support.  This research module
only assigns named, replaceable probabilities to that support and verifies that every
positive-probability model retains the same legal outcomes.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from itertools import combinations, permutations, product
from typing import Any

from ti_predictor.fantasy.main_roll import enumerate_mutation_outcomes
from ti_predictor.fantasy.main_roll_research_contract import ProbabilityModelSpec
from ti_predictor.fantasy.roll import (
    COLOR_TARGETS,
    INCREASE_ONE_QUALITY,
    INCREASE_TWO_DECREASE_ONE,
    ROLL_QUALITY,
    ROLL_STAT,
    ROLL_TRAIT,
    TARGET_ALL,
    TARGET_ALL_COLOR,
    TARGET_FIRST_COLOR,
    TARGET_LAST_COLOR,
    TARGET_ONE_COLOR,
    BannerState,
    MutationOutcome,
    RollOffer,
    RollOperation,
    RollRuleError,
    RollRuleSet,
)


class ResearchProbabilityError(ValueError):
    """A probability model cannot be reconciled with client-legal support."""


class OfferOutcome(tuple):
    """Small immutable `(offer, probability)` record without another dataclass layer."""

    __slots__ = ()

    def __new__(cls, offer: RollOffer, probability: float):
        return super().__new__(cls, (offer, probability))

    @property
    def offer(self) -> RollOffer:
        return self[0]

    @property
    def probability(self) -> float:
        return self[1]


def _weighted_pick(values: tuple[Any, ...], weights: tuple[float, ...], rng: random.Random) -> Any:
    total = float(sum(weights))
    if not values or len(values) != len(weights) or total <= 0.0 or not math.isfinite(total):
        raise ResearchProbabilityError("weighted draw requires aligned positive finite weights")
    threshold = rng.random() * total
    cumulative = 0.0
    for value, weight in zip(values, weights, strict=True):
        cumulative += weight
        if threshold < cumulative:
            return value
    return values[-1]


def _normalize(weighted: tuple[tuple[Any, float], ...]) -> tuple[tuple[Any, float], ...]:
    total = float(sum(weight for _, weight in weighted))
    if total <= 0.0 or not math.isfinite(total):
        raise ResearchProbabilityError("probability weights must have a positive finite sum")
    return tuple((value, weight / total) for value, weight in weighted)


def _replace_attributes(
    banner: BannerState,
    indexes: tuple[int, ...],
    attribute: str,
    values: tuple[Any, ...],
) -> BannerState:
    emblems = list(banner.emblems)
    for index, value in zip(indexes, values, strict=True):
        emblems[index] = replace(emblems[index], **{attribute: value})
    return BannerState(role=banner.role, emblems=tuple(emblems))


def _target_options(
    banner: BannerState,
    operation: RollOperation,
    rules: RollRuleSet,
) -> tuple[tuple[int, ...], ...]:
    targets = set(operation.targets)
    if operation.mutation in {INCREASE_ONE_QUALITY, INCREASE_TWO_DECREASE_ONE}:
        if targets != {TARGET_ALL}:
            raise ResearchProbabilityError("quality increment operation target drifted")
        return (tuple(range(len(banner.emblems))),)

    colors = [color for flag, color in COLOR_TARGETS.items() if flag in targets]
    selectors = targets & {
        TARGET_ALL_COLOR,
        TARGET_ONE_COLOR,
        TARGET_FIRST_COLOR,
        TARGET_LAST_COLOR,
    }
    if len(colors) != 1 or len(selectors) != 1:
        raise ResearchProbabilityError(f"operation {operation.operation_id} target is ambiguous")
    banner_colors = rules.colors_for(banner.role)[: len(banner.emblems)]
    matching = tuple(index for index, color in enumerate(banner_colors) if color == colors[0])
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
    raise ResearchProbabilityError(f"unsupported target selector: {selector}")


class MainRollProbabilityProvider:
    """Assign and sample one explicitly named model over Main legal support."""

    def __init__(self, rules: RollRuleSet, specification: ProbabilityModelSpec) -> None:
        self.rules = rules
        self.specification = specification
        self.model_id = specification.model_id
        self._mutation_cache: dict[tuple[BannerState, int], tuple[MutationOutcome, ...]] = {}
        self._offer_distribution: tuple[OfferOutcome, ...] | None = None

    def draw_offer(self, rng: random.Random) -> RollOffer:
        remaining = list(self.rules.offered_operations)
        selected: list[int] = []
        for _ in range(self.rules.offer_size):
            weights = tuple(
                operation.roll_weight**self.specification.offer_weight_power for operation in remaining
            )
            chosen = _weighted_pick(tuple(remaining), weights, rng)
            selected.append(chosen.operation_id)
            remaining.remove(chosen)
        return RollOffer(tuple(selected))

    def offer_distribution(self) -> tuple[OfferOutcome, ...]:
        """Return the exact ordered-offer distribution for short-horizon validation."""

        if self._offer_distribution is not None:
            return self._offer_distribution
        operations = self.rules.offered_operations
        powered = {
            operation.operation_id: operation.roll_weight**self.specification.offer_weight_power
            for operation in operations
        }
        total = sum(powered.values())
        rows: list[OfferOutcome] = []
        for selected in permutations(tuple(powered), self.rules.offer_size):
            remaining_total = total
            probability = 1.0
            for operation_id in selected:
                weight = powered[operation_id]
                probability *= weight / remaining_total
                remaining_total -= weight
            rows.append(OfferOutcome(RollOffer(selected), probability))
        probability_sum = sum(row.probability for row in rows)
        if not math.isclose(probability_sum, 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise ResearchProbabilityError("ordered offer probabilities do not sum to one")
        self._offer_distribution = tuple(rows)
        return self._offer_distribution

    def _attribute_choices(
        self,
        banner: BannerState,
        index: int,
        mutation: str,
    ) -> tuple[tuple[Any, float], ...]:
        emblem = banner.emblems[index]
        if mutation == ROLL_QUALITY:
            choices = tuple(
                (tier, weight**self.specification.quality_weight_power)
                for tier, weight in self.rules.quality_weights
            )
            current = emblem.quality_tier
        elif mutation == ROLL_TRAIT:
            choices = tuple((trait, 1.0) for trait in self.rules.traits)
            current = emblem.trait_id
        elif mutation == ROLL_STAT:
            color = self.rules.colors_for(banner.role)[index]
            choices = tuple((stat_id, 1.0) for stat_id in self.rules.stats_for(color))
            current = emblem.stat_id
        else:
            raise ResearchProbabilityError(f"unsupported attribute mutation: {mutation}")
        adjusted = tuple(
            (
                value,
                weight * (self.specification.repeat_current_factor if value == current else 1.0),
            )
            for value, weight in choices
        )
        return _normalize(adjusted)

    def _attribute_distribution(
        self,
        banner: BannerState,
        operation: RollOperation,
        probabilities: dict[BannerState, float],
    ) -> None:
        attribute = {
            ROLL_QUALITY: "quality_tier",
            ROLL_TRAIT: "trait_id",
            ROLL_STAT: "stat_id",
        }[operation.mutation]
        target_options = _target_options(banner, operation, self.rules)
        target_probability = 1.0 / len(target_options)
        rho = self.specification.multi_target_correlation

        def add(outcome: BannerState, probability: float) -> None:
            probabilities[outcome] = probabilities.get(outcome, 0.0) + probability

        for indexes in target_options:
            choices = tuple(self._attribute_choices(banner, index, operation.mutation) for index in indexes)
            independent_scale = target_probability * (1.0 - rho if len(indexes) > 1 else 1.0)
            for selections in product(*choices):
                values = tuple(value for value, _ in selections)
                probability = independent_scale * math.prod(weight for _, weight in selections)
                add(_replace_attributes(banner, indexes, attribute, values), probability)

            if len(indexes) <= 1 or rho == 0.0:
                continue
            common_values = set(value for value, _ in choices[0])
            for item in choices[1:]:
                common_values &= {value for value, _ in item}
            correlated_weights: list[tuple[Any, float]] = []
            for value in sorted(common_values, key=str):
                weight = math.prod(dict(item)[value] for item in choices)
                correlated_weights.append((value, weight))
            for value, probability in _normalize(tuple(correlated_weights)):
                add(
                    _replace_attributes(
                        banner,
                        indexes,
                        attribute,
                        (value,) * len(indexes),
                    ),
                    target_probability * rho * probability,
                )

    def mutation_distribution(
        self,
        banner: BannerState,
        operation_id: int,
    ) -> tuple[MutationOutcome, ...]:
        key = (banner, operation_id)
        if key in self._mutation_cache:
            return self._mutation_cache[key]
        operation = self.rules.operation(operation_id)
        legal_support = set(enumerate_mutation_outcomes(banner, operation_id, self.rules))
        if not legal_support:
            self._mutation_cache[key] = ()
            return ()
        probabilities: dict[BannerState, float] = {}

        def add(outcome: BannerState, probability: float) -> None:
            probabilities[outcome] = probabilities.get(outcome, 0.0) + probability

        if operation.mutation == INCREASE_ONE_QUALITY:
            probability = 1.0 / len(banner.emblems)
            for index, emblem in enumerate(banner.emblems):
                quality = min(5, emblem.quality_tier + 1)
                add(_replace_attributes(banner, (index,), "quality_tier", (quality,)), probability)
        elif operation.mutation == INCREASE_TWO_DECREASE_ONE:
            assignments = tuple(
                (decreased, increased)
                for decreased in range(len(banner.emblems))
                for increased in combinations(
                    (index for index in range(len(banner.emblems)) if index != decreased),
                    2,
                )
            )
            probability = 1.0 / len(assignments)
            for decreased, increased in assignments:
                increased_set = set(increased)
                qualities = tuple(
                    max(1, emblem.quality_tier - 1)
                    if index == decreased
                    else min(5, emblem.quality_tier + 1)
                    if index in increased_set
                    else emblem.quality_tier
                    for index, emblem in enumerate(banner.emblems)
                )
                add(
                    _replace_attributes(
                        banner,
                        tuple(range(len(banner.emblems))),
                        "quality_tier",
                        qualities,
                    ),
                    probability,
                )
        elif operation.mutation in {ROLL_QUALITY, ROLL_TRAIT, ROLL_STAT}:
            self._attribute_distribution(banner, operation, probabilities)
        else:
            raise RollRuleError(f"unsupported Main mutation: {operation.mutation}")

        total = sum(probabilities.values())
        if not math.isclose(total, 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise ResearchProbabilityError(f"mutation probabilities sum to {total}, not one")
        if set(probabilities) != legal_support:
            raise ResearchProbabilityError(
                f"{self.model_id} changed client-legal support for operation {operation_id}"
            )
        result = tuple(
            MutationOutcome(banner=outcome, probability=probability)
            for outcome, probability in sorted(probabilities.items())
        )
        self._mutation_cache[key] = result
        return result

    def sample_mutation(
        self,
        banner: BannerState,
        operation_id: int,
        rng: random.Random,
    ) -> BannerState:
        distribution = self.mutation_distribution(banner, operation_id)
        return _weighted_pick(
            tuple(outcome.banner for outcome in distribution),
            tuple(outcome.probability for outcome in distribution),
            rng,
        )


__all__ = [
    "MainRollProbabilityProvider",
    "OfferOutcome",
    "ResearchProbabilityError",
]
