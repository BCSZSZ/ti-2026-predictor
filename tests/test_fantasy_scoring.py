from __future__ import annotations

import pytest

from ti_predictor.fantasy.scoring import (
    Emblem,
    aggregate_period,
    best_two_games,
    coach_multiplier,
    duo_game_score,
    emblem_multipliers,
    score_game,
    score_stat,
)


def test_all_eighteen_stat_rules_are_executable(rules_payload) -> None:
    stats = rules_payload["fantasy"]["stats"]
    assert len(stats) == 18
    for stat_id, rule in stats.items():
        result = score_stat(1.0, rule)
        assert result is not None, stat_id
        assert result >= 0
    assert score_stat(3, stats["deaths"]) == pytest.approx(1365.0)
    assert score_stat(10, stats["deaths"]) == pytest.approx(0.0)
    assert score_stat(11, stats["deaths"]) == pytest.approx(0.0)
    assert score_stat(0.75, stats["teamfight_participation"]) == pytest.approx(1593.0)
    assert score_stat(None, stats["kills"]) is None


def test_duo_best_two_and_best_series_preserve_missing() -> None:
    assert duo_game_score([8.0, 12.0]) == 10.0
    assert duo_game_score([8.0, None]) is None
    assert best_two_games([2.0, 8.0, 5.0]) == 13.0
    assert best_two_games([8.0, None]) is None
    assert aggregate_period([[2.0, 8.0, 5.0], [7.0, 7.0]]) == 14.0


def test_quality_and_traits_apply_to_emblems(rules_payload) -> None:
    emblems = [
        Emblem("kills", "red", 1, "benevolent"),
        Emblem("gpm", "red", 2, "vampiric"),
        Emblem("creep_score", "red", 3, "unique"),
    ]
    multipliers = emblem_multipliers(emblems, rules_payload)
    assert multipliers == pytest.approx([1.0, 2.0, 1.8])
    stats = {"kills": 10, "gpm": 500, "creep_score": 300}
    assert score_game(stats, emblems, rules_payload) == pytest.approx(
        10 * 107.0 * 1.0 + 500 * 2.0 * 2.0 + 300 * 3.0 * 1.8
    )


def test_fractal_requires_all_distinct_qualities(rules_payload) -> None:
    distinct = [
        Emblem("kills", "red", 1, "fractal"),
        Emblem("gpm", "red", 2),
        Emblem("creep_score", "red", 3),
    ]
    repeated = [distinct[0], Emblem("gpm", "red", 1), distinct[2]]
    assert emblem_multipliers(distinct, rules_payload)[0] == pytest.approx(1.7)
    assert emblem_multipliers(repeated, rules_payload)[0] == pytest.approx(1.1)


def test_coach_and_emblem_bonuses_stack_multiplicatively(rules_payload) -> None:
    emblems = [Emblem("kills", "red", 1, "unique")]
    stats = {"kills": 2}

    assert coach_multiplier(10, 20) == pytest.approx(1.32)
    assert score_game(
        stats,
        emblems,
        rules_payload,
        coach_bonus_percents=[10, 20],
    ) == pytest.approx(2 * 107.0 * (1.0 + 0.1 + 0.3) * 1.1 * 1.2)
