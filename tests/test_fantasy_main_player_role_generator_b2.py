from __future__ import annotations

import numpy as np
import pytest

from ti_predictor.fantasy.main_player_role_generator import (
    fit_joint_residual_model,
)
from ti_predictor.fantasy.main_player_role_generator_b2 import (
    EmpiricalCopulaResidualModel,
    MainPlayerRoleGeneratorB2Config,
    load_main_player_role_generator_b2_config,
)


def test_b2_frozen_config_has_disjoint_event_blocks() -> None:
    config = load_main_player_role_generator_b2_config(
        "config/research/fantasy-main-player-role-generator-v2.json"
    )
    assert isinstance(config, MainPlayerRoleGeneratorB2Config)
    assert config.research_only is True
    assert len(config.confirmation_folds) == 4
    league_ids = {
        fold.league_id
        for fold in [
            *config.tuning_folds,
            *config.confirmation_folds,
            config.diagnostic_fold,
        ]
    }
    assert len(league_ids) == 9
    assert all(0.0 < value < 1.0 for value in config.copula_tuning.empirical_mixes)


def test_empirical_copula_is_deterministic_and_does_not_repeat_a_source_row() -> None:
    source_rng = np.random.default_rng(41)
    rows = source_rng.normal(size=(80, 12))
    probabilities = np.full(len(rows), 1.0 / len(rows))
    smooth = fit_joint_residual_model(
        rows,
        probabilities,
        factor_rank=4,
        covariance_shrinkage=0.25,
    )
    standardized = (rows - smooth.training_center[None, :]) / smooth.training_scale[None, :]
    model = EmpiricalCopulaResidualModel(
        standardized_rows=standardized,
        probabilities=probabilities,
        source_match_ids=np.arange(len(rows)),
        source_series_ids=np.arange(len(rows)) // 2,
        smooth_model=smooth,
        empirical_mix=0.75,
        sample_scale=1.1,
        training_set_sha256="fixture",
    )
    first = model.sample(np.random.default_rng(99), size=200)
    second = model.sample(np.random.default_rng(99), size=200)
    assert np.array_equal(first, second)
    assert first.shape == (200, 12)
    assert np.isfinite(first).all()
    assert not any(np.array_equal(generated, source) for generated in first for source in standardized)


def test_empirical_copula_preserves_variance_scale_in_large_draw() -> None:
    source_rng = np.random.default_rng(17)
    rows = source_rng.normal(size=(500, 8))
    probabilities = np.full(len(rows), 1.0 / len(rows))
    smooth = fit_joint_residual_model(
        rows,
        probabilities,
        factor_rank=3,
        covariance_shrinkage=0.25,
    )
    standardized = (rows - smooth.training_center[None, :]) / smooth.training_scale[None, :]
    model = EmpiricalCopulaResidualModel(
        standardized_rows=standardized,
        probabilities=probabilities,
        source_match_ids=np.arange(len(rows)),
        source_series_ids=np.arange(len(rows)) // 5,
        smooth_model=smooth,
        empirical_mix=0.5,
        sample_scale=1.0,
        training_set_sha256="fixture",
    )
    draws = model.sample(np.random.default_rng(1234), size=50_000)
    assert draws.mean(axis=0) == pytest.approx(np.zeros(8), abs=0.03)
    assert draws.var(axis=0) == pytest.approx(np.ones(8), abs=0.06)
