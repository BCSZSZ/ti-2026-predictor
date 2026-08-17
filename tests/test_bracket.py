from __future__ import annotations

import numpy as np
import pytest

from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.tournament.bracket import BracketEngine


def test_bracket_enumerates_all_coherent_grids() -> None:
    team_ids = list(range(1, 9))
    model = TeamStrengthModel({team_id: 1500 + team_id * 10 for team_id in team_ids})
    engine = BracketEngine(team_ids, model)
    paths = engine.enumerate()
    assert len(paths) == 16384
    assert sum(path.probability for path in paths) == pytest.approx(1.0)
    assert all(len(path.winners) == 14 for path in paths)
    assert all(left != right for path in paths for left, right in path.participants)


def test_bracket_rejects_duplicate_seeds() -> None:
    with pytest.raises(ValueError, match="unique"):
        BracketEngine([1, 1, 2, 3, 4, 5, 6, 7], TeamStrengthModel({}))


def test_bracket_direct_sampling_is_deterministic_and_coherent() -> None:
    team_ids = list(range(1, 9))
    engine = BracketEngine(
        team_ids,
        TeamStrengthModel({team_id: 1500 + team_id * 10 for team_id in team_ids}),
    )

    first = engine.sample(np.random.default_rng(42))
    second = engine.sample(np.random.default_rng(42))

    assert first == second
    assert len(first.bits) == 14
    assert len(first.participants) == 14
    assert all(
        winner in participants for winner, participants in zip(first.winners, first.participants, strict=True)
    )


def test_lower_round_two_crosses_upper_semifinal_losers() -> None:
    """Valve sends each upper-semifinal loser into the opposite lower-bracket half."""

    engine = BracketEngine(list(range(1, 9)), TeamStrengthModel({}))
    path = engine.resolve([0] * 14)

    upper_semifinal_a_loser = next(team_id for team_id in path.participants[6] if team_id != path.winners[6])
    upper_semifinal_b_loser = next(team_id for team_id in path.participants[7] if team_id != path.winners[7])

    assert path.participants[8] == (upper_semifinal_b_loser, path.winners[4])
    assert path.participants[9] == (upper_semifinal_a_loser, path.winners[5])
