from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from ti_predictor.backtesting import evaluate_bo3_probability_transform
from ti_predictor.config import load_swiss_format, load_tournament_manifest
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.tournament.swiss import (
    SWISS_CATEGORY_CAPACITIES,
    SwissEngine,
    adjust_strength_probability,
    bo3_probability,
    canonical_pair,
    inverse_bo3_probability,
    select_pairings,
)


def _format(project_paths):
    manifest = load_tournament_manifest(project_paths.tournament)
    return load_swiss_format(
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        manifest=manifest,
        path=project_paths.swiss,
    )


def test_swiss_simulation_is_repeatable_and_obeys_round_constraints(project_paths) -> None:
    swiss_format = _format(project_paths)
    engine = SwissEngine(swiss_format, lambda _left, _right: 0.5)

    first = engine.simulate(seed=17)
    second = engine.simulate(seed=17)

    assert np.array_equal(first.outcomes, second.outcomes)
    assert tuple(np.bincount(first.outcomes, minlength=6)) == SWISS_CATEGORY_CAPACITIES
    swiss_series = [series for series in first.series if series.phase == "swiss"]
    expected_round_one = {
        canonical_pair(series.team_a_id, series.team_b_id) for series in swiss_format.first_round
    }
    assert {series.pair for series in swiss_series if series.round_number == 1} == expected_round_one
    assert len({series.pair for series in swiss_series}) == len(swiss_series)
    for series in swiss_series:
        assert series.team_a_record_before == series.team_b_record_before
        if series.round_number in (2, 3):
            assert engine.initial_groups[series.team_a_id] == engine.initial_groups[series.team_b_id]
        elif series.round_number == 4:
            assert engine.initial_groups[series.team_a_id] != engine.initial_groups[series.team_b_id]


def test_round_five_loser_elimination_maximizes_ranking_distance() -> None:
    teams = (1, 2, 3, 4)
    pairings = select_pairings(
        teams,
        round_number=5,
        rank_positions={1: 0, 2: 1, 3: 2, 4: 3},
        prior_pairs=set(),
        initial_groups={team_id: "A" for team_id in teams},
        maximize_rank_distance=True,
        rng=np.random.default_rng(1),
        tie_break="canonical",
    )

    assert pairings == ((1, 4), (2, 3))


def test_model_optimal_elimination_choice_uses_best_available_matchup(project_paths) -> None:
    swiss_format = _format(project_paths)

    def probability(left: int, right: int) -> float:
        return 0.8 if right == 10149530 else 0.55

    engine = SwissEngine(swiss_format, probability, elimination_choice_strategy="model_optimal")
    selected = engine._choose_elimination_opponent(
        9247354,
        [10149530, 10150538],
        rank_positions={10149530: 15, 10150538: 14},
        rng=np.random.default_rng(1),
    )

    assert selected == 10149530


def test_swiss_batch_preserves_capacities_for_every_sample(project_paths) -> None:
    engine = SwissEngine(_format(project_paths), lambda _left, _right: 0.5)

    outcomes = engine.simulate_many(samples=25, seed=29)

    assert outcomes.shape == (25, 16)
    for category, expected in enumerate(SWISS_CATEGORY_CAPACITIES):
        assert np.all((outcomes == category).sum(axis=1) == expected)


def test_swiss_batch_caches_static_pair_probabilities(project_paths) -> None:
    calls: list[tuple[int, int]] = []

    def probability(left: int, right: int) -> float:
        calls.append((left, right))
        return 0.5

    engine = SwissEngine(_format(project_paths), probability, series_probability_mode="direct_series")
    engine.simulate_many(samples=5, seed=29)

    assert len(calls) == len(set(calls))
    assert len(calls) <= len(engine.team_ids) * (len(engine.team_ids) - 1)


def test_strength_multiplier_is_scale_invariant_and_complementary() -> None:
    base = 0.3468
    adjusted = adjust_strength_probability(base, multiplier_a=0.9, multiplier_b=1.0)

    np.testing.assert_allclose(adjusted, 0.323333, atol=1e-6)
    reverse = adjust_strength_probability(
        1.0 - base,
        multiplier_a=1.0,
        multiplier_b=0.9,
    )
    np.testing.assert_allclose(reverse, 1.0 - adjusted, atol=1e-12)
    assert bo3_probability(0.5) == 0.5
    np.testing.assert_allclose(bo3_probability(0.7), 0.784, atol=1e-12)
    for series_probability in (0.01, 0.25, 0.5, 0.75, 0.99):
        np.testing.assert_allclose(
            bo3_probability(inverse_bo3_probability(series_probability)),
            series_probability,
            atol=1e-12,
        )


def test_bo3_holdout_selects_conservative_direct_series_probability() -> None:
    rows: list[dict] = []
    start = datetime(2025, 9, 1, tzinfo=UTC)
    match_id = 1
    for series_id in range(1, 11):
        team_a_wins = series_id <= 6
        game_winners = [team_a_wins, team_a_wins]
        for game_index, radiant_win in enumerate(game_winners):
            rows.append(
                {
                    "match_id": match_id,
                    "series_id": series_id,
                    "series_type": 1,
                    "start_time": start + timedelta(days=series_id, minutes=game_index),
                    "radiant_team_id": 1,
                    "dire_team_id": 2,
                    "radiant_win": radiant_win,
                }
            )
            match_id += 1
    model = TeamStrengthModel({1: 1570.4365, 2: 1500.0})

    result = evaluate_bo3_probability_transform(model, pd.DataFrame(rows))

    assert result["evaluated_series"] == 10
    assert result["selected_mode"] == "direct_series"
    assert result["metrics"]["direct_series"]["log_loss"] < result["metrics"]["independent_games"][
        "log_loss"
    ]
