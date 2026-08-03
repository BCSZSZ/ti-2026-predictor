from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Emblem:
    stat_id: str
    color: str
    quality_tier: int
    trait: str | None = None


def score_stat(value: float | None, rule: dict[str, Any]) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    numeric = float(value)
    mode = rule["mode"]
    if mode == "linear":
        result = numeric * float(rule["factor"])
    elif mode == "inverse":
        result = float(rule["base"]) - numeric * float(rule["factor"])
        result = max(float(rule.get("floor", -float("inf"))), result)
    else:
        raise ValueError(f"unknown Fantasy scoring mode: {mode}")
    if "cap" in rule:
        result = min(float(rule["cap"]), result)
    return result


def _trait_modifiers(emblems: list[Emblem]) -> list[float]:
    modifiers = [0.0] * len(emblems)
    quality_counts = {emblem.quality_tier for emblem in emblems}
    trait_counts: dict[str, int] = {}
    for emblem in emblems:
        if emblem.trait:
            trait_counts[emblem.trait] = trait_counts.get(emblem.trait, 0) + 1
    friendly_count = trait_counts.get("friendly", 0)

    for index, emblem in enumerate(emblems):
        trait = emblem.trait
        if trait == "fractal" and len(quality_counts) == len(emblems):
            modifiers[index] += 0.60
        elif trait == "benevolent":
            if index > 0:
                modifiers[index - 1] += 0.20
            if index + 1 < len(emblems):
                modifiers[index + 1] += 0.20
        elif trait == "vampiric":
            modifiers[index] += 0.50
            if index > 0:
                modifiers[index - 1] -= 0.10
            if index + 1 < len(emblems):
                modifiers[index + 1] -= 0.10
        elif trait == "unique" and trait_counts.get("unique") == 1:
            modifiers[index] += 0.30
        elif trait == "friendly" and friendly_count >= 3:
            modifiers[index] += 0.50
    return modifiers


def emblem_multipliers(emblems: list[Emblem], rules: dict[str, Any]) -> list[float]:
    qualities = {
        int(item["tier"]): float(item["bonus_percent"]) / 100.0 for item in rules["fantasy"]["qualities"]
    }
    trait_modifiers = _trait_modifiers(emblems)
    result: list[float] = []
    for index, emblem in enumerate(emblems):
        if emblem.quality_tier not in qualities:
            raise ValueError(f"unknown emblem quality tier: {emblem.quality_tier}")
        result.append(max(0.0, 1.0 + qualities[emblem.quality_tier] + trait_modifiers[index]))
    return result


def score_game(
    stats: dict[str, float | None],
    emblems: list[Emblem],
    rules: dict[str, Any],
    *,
    coach_bonus_percents: Iterable[float] = (),
) -> float | None:
    multipliers = emblem_multipliers(emblems, rules)
    total = 0.0
    for emblem, multiplier in zip(emblems, multipliers, strict=True):
        stat_rule = rules["fantasy"]["stats"].get(emblem.stat_id)
        if stat_rule is None:
            raise ValueError(f"unknown Fantasy stat: {emblem.stat_id}")
        if stat_rule["color"] != emblem.color:
            raise ValueError(f"{emblem.stat_id} belongs to {stat_rule['color']}, not {emblem.color}")
        value = score_stat(stats.get(emblem.stat_id), stat_rule)
        if value is None:
            return None
        total += value * multiplier
    for bonus_percent in coach_bonus_percents:
        total *= 1.0 + float(bonus_percent) / 100.0
    return total


def duo_game_score(player_scores: Iterable[float | None]) -> float | None:
    values = list(player_scores)
    if len(values) != 2:
        raise ValueError("a duo role must contain exactly two player scores")
    if any(value is None or (isinstance(value, float) and np.isnan(value)) for value in values):
        return None
    return float(np.mean(values))


def best_two_games(game_scores: Iterable[float | None]) -> float | None:
    values = [float(value) for value in game_scores if value is not None and not np.isnan(value)]
    if len(values) < 2:
        return None
    return float(sum(sorted(values, reverse=True)[:2]))


def aggregate_period(series_game_scores: Iterable[Iterable[float | None]]) -> float | None:
    series_scores = [best_two_games(games) for games in series_game_scores]
    available = [score for score in series_scores if score is not None]
    return max(available) if available else None


def coach_multiplier(prefix_bonus_percent: float, suffix_bonus_percent: float) -> float:
    return (1.0 + float(prefix_bonus_percent) / 100.0) * (1.0 + float(suffix_bonus_percent) / 100.0)
