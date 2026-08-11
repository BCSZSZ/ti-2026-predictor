from __future__ import annotations

import numpy as np
import pytest

from ti_predictor.config import (
    load_swiss_format,
    load_swiss_simulation_policy,
    load_tournament_manifest,
)
from ti_predictor.forecasting import generate_group
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.schemas import StrategyProfile
from ti_predictor.tournament.group import (
    CATEGORY_CAPACITIES,
    GroupSimulator,
    SwissGroupSimulator,
    scenario_probability_tables,
)
from ti_predictor.tournament.swiss import bo3_probability


def test_group_forecast_rejects_nonpositive_sample_budget() -> None:
    with pytest.raises(ValueError, match="sample counts must be positive"):
        generate_group(as_of="2026-08-10T13:45:12Z", samples=0)


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
    expected_correct = recommendation.selections["expected_correct"]
    selected_probability_sum = sum(
        item["category_probability"]
        for category in recommendation.selections["slots"].values()
        for item in category
    )
    assert expected_correct["count"] == pytest.approx(selected_probability_sum, abs=1e-5)
    assert expected_correct["rate_percent"] == pytest.approx(expected_correct["count"] / 16 * 100, abs=0.01)
    assert len(expected_correct["monte_carlo_confidence_interval_95"]) == 2
    assert sum(item["probability"] for item in expected_correct["distribution"]) == pytest.approx(1.0)
    assert all(
        item["category_probability_percent"]
        == pytest.approx(
            item["category_probability"] * 100,
            abs=0.01,
        )
        for category in recommendation.selections["slots"].values()
        for item in category
    )


def test_swiss_group_simulator_applies_lgd_shock_without_mutating_ratings(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    cutoff = "2026-08-10T13:45:12Z"
    swiss_format = load_swiss_format(
        as_of=cutoff,
        manifest=manifest,
        path=project_paths.swiss,
    )
    policy = load_swiss_simulation_policy(
        as_of=cutoff,
        manifest=manifest,
        path=project_paths.swiss_policy,
    )
    ratings = {team.team_id: 1400 + index * 20 for index, team in enumerate(manifest.teams)}
    model = TeamStrengthModel(ratings)
    original_lgd_rating = model.rating(10150538)
    simulator = SwissGroupSimulator(
        model,
        manifest,
        swiss_format=swiss_format,
        policy=policy,
        as_of=cutoff,
        series_probability_mode="direct_series",
    )

    baseline = simulator.adjusted_game_probability(10150538, 9247354, scenario="baseline_1_00")
    primary_scenario = policy.primary_scenario
    primary = simulator.adjusted_game_probability(10150538, 9247354, scenario=primary_scenario)
    primary_series = simulator.series_win_probability(
        10150538,
        9247354,
        scenario=primary_scenario,
    )
    scoreline_game = simulator.scoreline_game_probability(
        10150538,
        9247354,
        scenario=primary_scenario,
    )
    first = simulator.simulate(samples=30, seed=11)
    second = simulator.simulate(samples=30, seed=11)

    assert primary < baseline
    baseline_odds = baseline / (1.0 - baseline)
    primary_odds = primary / (1.0 - primary)
    assert simulator.roster_strength_multiplier(10150538, scenario=primary_scenario) == 0.6
    assert primary_odds == pytest.approx(baseline_odds * 0.6)
    assert primary_series == primary
    assert scoreline_game != pytest.approx(primary)
    assert bo3_probability(scoreline_game) == pytest.approx(primary_series)
    assert model.rating(10150538) == original_lgd_rating
    assert np.array_equal(first.outcomes, second.outcomes)
    assert first.metadata["engine"] == "official_swiss_v1"
    assert first.metadata["roster_shock"]["multiplier"] == 0.6

    tables = scenario_probability_tables([first], simulator.team_names)
    lgd = next(item for item in tables[0]["teams"] if item["team_id"] == 10150538)
    assert tables[0]["scenario"] == "roster_shock_0_60"
    assert tables[0]["sample_count"] == 30
    assert lgd["percentages"]["four_zero"] == pytest.approx(lgd["four_zero"] * 100, abs=0.01)
