from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from ti_predictor.config import load_tournament_manifest
from ti_predictor.fantasy.scoring import best_two_games
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.tournament.bracket import BracketEngine
from ti_predictor.tournament.group import CATEGORY_CAPACITIES, GroupSimulator


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=12, deadline=None)
def test_group_capacity_property(seed: int) -> None:
    manifest = load_tournament_manifest()
    simulator = GroupSimulator(TeamStrengthModel({}), manifest)
    result = simulator.simulate(samples=8, seed=seed)
    for category, capacity in enumerate(CATEGORY_CAPACITIES):
        assert np.all((result.outcomes == category).sum(axis=1) == capacity)


@given(st.lists(st.integers(min_value=0, max_value=1), min_size=14, max_size=14))
@settings(max_examples=30, deadline=None)
def test_bracket_grid_property(bits: list[int]) -> None:
    seeds = list(range(1, 9))
    path = BracketEngine(seeds, TeamStrengthModel({})).resolve(bits)
    assert path.champion in seeds
    assert len(path.winners) == 14
    assert all(left != right for left, right in path.participants)


@given(st.lists(st.floats(min_value=0, max_value=1000, allow_nan=False), min_size=2, max_size=5))
def test_best_two_games_property(scores: list[float]) -> None:
    assert best_two_games(scores) == sum(sorted(scores, reverse=True)[:2])
