from __future__ import annotations

import numpy as np
import pytest

import ti_predictor.fantasy.main_series_quota_hybrid as hybrid
from ti_predictor.fantasy.main_player_role_backtest import (
    EvaluationSeries,
    HistoricalSeriesTemplate,
)
from ti_predictor.fantasy.main_series_quota_hybrid import (
    MainSeriesQuotaHybridConfig,
    load_main_series_quota_hybrid_config,
    sample_series_quota_hybrid,
)


def _target() -> EvaluationSeries:
    return EvaluationSeries(
        league_id=9,
        series_id=99,
        current_team_id=101,
        historical_team_id=101,
        opponent_team_id=202,
        best_of=3,
        series_won=True,
        opponent_probability=0.5,
        match_ids=(91, 92),
        won_games=(True, False),
        durations=np.asarray([2000.0, 2100.0]),
        raw_stats=np.ones((2, 5, 2)),
    )


def _templates() -> tuple[HistoricalSeriesTemplate, ...]:
    return tuple(
        HistoricalSeriesTemplate(
            team_id=101,
            series_id=series_id,
            best_of=3,
            series_won=True,
            opponent_band=1,
            evidence_weight=weight,
            won_games=(True, False),
            raw_stats=np.asarray(
                [
                    np.full((5, 2), float(series_id)),
                    np.full((5, 2), float(series_id + 100)),
                ]
            ),
        )
        for series_id, weight in ((1, 10.0), (2, 1.0), (3, 1.0))
    )


def test_frozen_quota_config_routes_truncated_mass_to_b1() -> None:
    config = load_main_series_quota_hybrid_config(
        "config/research/fantasy-main-series-quota-hybrid-v1.json"
    )
    assert isinstance(config, MainSeriesQuotaHybridConfig)
    assert config.maximum_final_series_mass == pytest.approx(0.10)
    assert config.truncated_mass_destination == "frozen-b1"
    assert config.research_only is True
    precision = load_main_series_quota_hybrid_config(
        "config/research/fantasy-main-series-quota-hybrid-v1-precision.json"
    )
    assert precision.maximum_final_series_mass == config.maximum_final_series_mass
    assert precision.simulation.seeds == config.simulation.seeds
    assert precision.simulation.inner_samples_per_path == 64


def test_quota_hybrid_caps_series_without_renormalizing_excess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_b1(*args: object, sample_count: int, **kwargs: object) -> np.ndarray:
        return np.zeros((sample_count, 2, 5, 2), dtype=np.float32)

    monkeypatch.setattr(hybrid, "sample_player_role_series", fake_b1)
    first, first_audit = sample_series_quota_hybrid(
        object(),  # type: ignore[arg-type]
        _templates(),
        _target(),
        sample_count=10_000,
        seed=7,
        maximum_final_series_mass=0.10,
    )
    second, second_audit = sample_series_quota_hybrid(
        object(),  # type: ignore[arg-type]
        _templates(),
        _target(),
        sample_count=10_000,
        seed=7,
        maximum_final_series_mass=0.10,
    )
    assert np.array_equal(first, second)
    assert first_audit == second_audit
    # Original mass is 10/12, 1/12, 1/12. Only the first Series is
    # truncated, and its excess becomes B1 rather than being redistributed.
    assert first_audit.theoretical_v1_mass == pytest.approx(0.10 + 1 / 12 + 1 / 12)
    assert first_audit.theoretical_b1_mass == pytest.approx(1.0 - (0.10 + 2 / 12))
    assert first_audit.theoretical_max_primary_series_mass == pytest.approx(0.10)
    assert first_audit.realized_v1_draws / first_audit.draws == pytest.approx(
        first_audit.theoretical_v1_mass, abs=0.02
    )
    assert np.any(first == 0.0)
    assert np.any(first > 0.0)


def test_quota_hybrid_uses_pure_b1_when_team_has_no_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = np.full((20, 2, 5, 2), 7.0, dtype=np.float32)

    def fake_b1(*args: object, **kwargs: object) -> np.ndarray:
        return expected.copy()

    monkeypatch.setattr(hybrid, "sample_player_role_series", fake_b1)
    values, audit = sample_series_quota_hybrid(
        object(),  # type: ignore[arg-type]
        (),
        _target(),
        sample_count=20,
        seed=9,
        maximum_final_series_mass=0.10,
    )
    assert np.array_equal(values, expected)
    assert audit.theoretical_v1_mass == 0.0
    assert audit.theoretical_b1_mass == 1.0
    assert audit.realized_v1_draws == 0


def test_quota_hybrid_keeps_b1_instead_of_borrowing_from_another_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_b1(*args: object, sample_count: int, **kwargs: object) -> np.ndarray:
        return np.zeros((sample_count, 2, 5, 2), dtype=np.float32)

    monkeypatch.setattr(hybrid, "sample_player_role_series", fake_b1)
    win_only = tuple(
        HistoricalSeriesTemplate(
            team_id=101,
            series_id=series_id,
            best_of=3,
            series_won=True,
            opponent_band=1,
            evidence_weight=1.0,
            won_games=(True,),
            raw_stats=np.full((1, 5, 2), float(series_id)),
        )
        for series_id in (1, 2, 3)
    )
    values, audit = sample_series_quota_hybrid(
        object(),  # type: ignore[arg-type]
        win_only,
        _target(),
        sample_count=2_000,
        seed=17,
        maximum_final_series_mass=0.10,
    )
    # v1-selected samples can fill the requested win, but the requested loss
    # remains B1 because no selected source Series contains a loss.
    assert np.any(values[:, 0] > 0.0)
    assert np.all(values[:, 1] == 0.0)
    assert all(key.split(":", maxsplit=1)[0] in {"1", "2", "3"} for key in audit.actual_game_source_counts)
