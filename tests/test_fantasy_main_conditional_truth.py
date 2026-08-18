from __future__ import annotations

import numpy as np
import pytest

from ti_predictor.fantasy.main_conditional_truth import (
    GAME_TEMPLATE_SENTINEL,
    SERIES_NODE_COUNT,
    _period_outcomes,
    build_exact_main_outer_paths,
    legal_series_sequences,
    series_win_probability,
    weighted_lower_tail_cvar,
)
from ti_predictor.models.ratings import TeamStrengthModel


def test_series_probability_transforms_single_game_probability() -> None:
    assert series_win_probability(0.5, 3) == pytest.approx(0.5)
    assert series_win_probability(0.5, 5) == pytest.approx(0.5)
    assert series_win_probability(0.6, 3) == pytest.approx(0.648)
    assert series_win_probability(0.6, 5) == pytest.approx(0.68256)


@pytest.mark.parametrize(("best_of", "target_wins"), [(3, True), (3, False), (5, True), (5, False)])
def test_legal_series_sequences_end_at_first_deciding_game(best_of: int, target_wins: bool) -> None:
    sequences, probabilities = legal_series_sequences(
        0.61,
        best_of=best_of,
        target_wins=target_wins,
    )
    needed = best_of // 2 + 1
    assert probabilities.sum() == pytest.approx(1.0)
    assert all(needed <= len(sequence) <= best_of for sequence in sequences)
    for sequence in sequences:
        target = sum(sequence)
        opponent = len(sequence) - target
        assert (target == needed) is target_wins
        assert (opponent == needed) is (not target_wins)
        assert sum(sequence[:-1]) < needed
        assert len(sequence[:-1]) - sum(sequence[:-1]) < needed


def test_exact_outer_uses_all_paths_and_normalized_series_weights() -> None:
    model = TeamStrengthModel({team_id: 1450.0 + team_id * 10.0 for team_id in range(1, 9)})
    outer = build_exact_main_outer_paths(tuple(range(1, 9)), model)
    assert outer.participants.shape == (16384, 14, 2)
    assert outer.winners.shape == (16384, 14)
    assert outer.probabilities.sum() == pytest.approx(1.0)
    assert np.all(outer.probabilities > 0.0)


def test_weighted_lower_tail_cvar_consumes_fractional_boundary_mass() -> None:
    values = np.asarray([10.0, 20.0, 100.0])
    weights = np.asarray([0.05, 0.10, 0.85])
    # Worst 10% = all five percent at 10 plus five percent at 20.
    assert weighted_lower_tail_cvar(values, weights, 0.10) == pytest.approx(15.0)


def test_period_outcome_takes_top_two_games_then_best_series() -> None:
    game_ids = np.full(
        (1, 1, SERIES_NODE_COUNT, 2, 5),
        GAME_TEMPLATE_SENTINEL,
        dtype=np.uint16,
    )
    participants = np.tile(np.asarray([[[0, 1]]], dtype=np.int16), (1, SERIES_NODE_COUNT, 1))
    game_ids[0, 0, 0, 0, :3] = (0, 1, 2)
    game_ids[0, 0, 1, 0, :2] = (3, 4)
    game_ids[0, 0, 2, 0, :2] = (5, 6)
    template_values = np.asarray([1.0, 10.0, 5.0, 7.0, 8.0, 20.0, 1.0])

    outcomes = _period_outcomes(game_ids, participants, template_values, team_count=2)

    assert outcomes.shape == (2, 1)
    assert outcomes[0, 0] == pytest.approx(21.0)
    assert outcomes[1, 0] == pytest.approx(0.0)
