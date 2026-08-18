from __future__ import annotations

import numpy as np
import pytest

from ti_predictor.config import load_rules
from ti_predictor.fantasy.main_player_role_backtest import (
    EvaluationSeries,
    HistoricalSeriesTemplate,
    build_hash_fixed_banner_panel,
    empirical_crps,
    energy_score,
    paired_series_bootstrap_lower_bound,
    sample_v1_series,
    score_raw_games,
)


def test_empirical_crps_and_energy_have_deterministic_limits() -> None:
    assert empirical_crps([3.0], 5.0) == pytest.approx(2.0)
    assert empirical_crps([1.0, 3.0], 2.0) == pytest.approx(0.5)
    assert energy_score(np.asarray([[1.0, 2.0]]), np.asarray([4.0, 6.0])) == pytest.approx(5.0)


def test_hash_fixed_banner_panel_is_repeatable_and_color_legal() -> None:
    rules = load_rules()
    first = build_hash_fixed_banner_panel(rules)
    second = build_hash_fixed_banner_panel(rules)
    assert len(first) == 12
    assert [item.projection_id for item in first] == [item.projection_id for item in second]
    for left, right in zip(first, second, strict=True):
        assert left.stat_ids == right.stat_ids
        assert np.array_equal(left.multipliers, right.multipliers)
        colors = rules["fantasy"]["role_banners"][left.role]
        assert [rules["fantasy"]["stats"][stat_id]["color"] for stat_id in left.stat_ids] == colors


def test_raw_game_projection_preserves_leading_dimensions() -> None:
    rules = load_rules()
    projection = build_hash_fixed_banner_panel(rules, projections_per_role=1)[0]
    stat_ids = tuple(rules["fantasy"]["stats"])
    raw = np.ones((3, 2, 5, len(stat_ids)), dtype=float)
    scored = score_raw_games(raw, stat_ids=stat_ids, projection=projection, rules=rules)
    assert scored.shape == (3, 2)
    assert np.all(scored >= 0.0)


def test_v1_sampler_is_deterministic_and_matches_requested_game_results() -> None:
    stat_count = 2
    templates = (
        HistoricalSeriesTemplate(
            team_id=101,
            series_id=1,
            best_of=3,
            series_won=True,
            opponent_band=1,
            evidence_weight=1.0,
            won_games=(True, False, True),
            raw_stats=np.asarray(
                [
                    np.full((5, stat_count), 10.0),
                    np.full((5, stat_count), 1.0),
                    np.full((5, stat_count), 20.0),
                ]
            ),
        ),
    )
    target = EvaluationSeries(
        league_id=9,
        series_id=99,
        current_team_id=101,
        historical_team_id=101,
        opponent_team_id=202,
        best_of=3,
        series_won=True,
        opponent_probability=0.5,
        match_ids=(91, 92, 93),
        won_games=(True, False, True),
        durations=np.asarray([2000.0, 2100.0, 2200.0]),
        raw_stats=np.ones((3, 5, stat_count)),
    )
    first, level_a = sample_v1_series(
        templates,
        target,
        sample_count=20,
        seed=7,
        minimum_conditioned_series=1,
    )
    second, level_b = sample_v1_series(
        templates,
        target,
        sample_count=20,
        seed=7,
        minimum_conditioned_series=1,
    )
    assert level_a == level_b == 0
    assert np.array_equal(first, second)
    assert np.all(first[:, 1] == 1.0)
    assert np.all(np.isin(first[:, 0], [10.0, 20.0]))
    assert np.all(np.isin(first[:, 2], [10.0, 20.0]))


def test_paired_bootstrap_uses_series_blocks() -> None:
    records = [
        {"series_id": series_id, "team_id": 101, "v1_crps": 10.0, "b_crps": 8.0} for series_id in range(20)
    ]
    result = paired_series_bootstrap_lower_bound(
        records,
        confidence=0.95,
        seed=11,
        replicates=500,
    )
    assert result["paired_series_blocks"] == 20
    assert result["mean_absolute_improvement"] == pytest.approx(2.0)
    assert result["one_sided_lower_bound"] == pytest.approx(2.0)
