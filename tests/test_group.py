from __future__ import annotations

import numpy as np

from ti_predictor.config import load_tournament_manifest
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.schemas import StrategyProfile
from ti_predictor.tournament.group import CATEGORY_CAPACITIES, GroupSimulator


def test_group_simulation_is_joint_capacity_preserving_and_repeatable(project_paths, rules_payload) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    ratings = {team.team_id: 1400 + index * 20 for index, team in enumerate(manifest.teams)}
    simulator = GroupSimulator(TeamStrengthModel(ratings), manifest)
    first = simulator.simulate(samples=300, seed=7)
    second = simulator.simulate(samples=300, seed=7)
    assert np.array_equal(first.outcomes, second.outcomes)
    for category, capacity in enumerate(CATEGORY_CAPACITIES):
        assert np.all((first.outcomes == category).sum(axis=1) == capacity)
    recommendation = simulator.recommend(
        first,
        profile=StrategyProfile.EXPECTED_POINTS,
        cumulative_points=rules_payload["prediction"]["group"]["cumulative_points"],
        as_of="2026-08-12T23:00:00Z",
        search_steps=30,
    )
    selected = [
        item["team_id"] for category in recommendation.selections["slots"].values() for item in category
    ]
    assert len(selected) == 16
    assert len(set(selected)) == 16
