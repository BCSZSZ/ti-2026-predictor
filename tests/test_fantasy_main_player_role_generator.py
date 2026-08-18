from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from ti_predictor.fantasy.main_player_role_generator import (
    ContextEncoder,
    JointResidualModel,
    MainPlayerRoleGeneratorConfig,
    PlayerRoleEvidence,
    StatMarginalModel,
    bounded_recent_adjustment,
    cap_grouped_probability_mass,
    cap_probability_mass,
    fit_joint_residual_model,
    fit_player_role_generator_from_frame,
    load_main_player_role_generator_config,
)


def test_frozen_config_has_disjoint_time_ordered_folds() -> None:
    config = load_main_player_role_generator_config(
        "config/research/fantasy-main-player-role-generator-v1.json"
    )
    assert isinstance(config, MainPlayerRoleGeneratorConfig)
    assert config.research_only is True
    assert config.confirmation_fold.train_as_of > config.tuning_folds[-1].test_end
    assert len({fold.league_id for fold in config.tuning_folds}) == len(config.tuning_folds)
    assert config.confirmation_fold.league_id not in {fold.league_id for fold in config.tuning_folds}


def test_probability_cap_preserves_mass_and_hard_limit() -> None:
    values = np.asarray([100.0, 1.0, 1.0, 1.0, 1.0])
    capped = cap_probability_mass(values, maximum_mass=0.30)
    assert capped.sum() == pytest.approx(1.0)
    assert capped.max() <= 0.30 + 1e-12
    assert np.all(capped > 0.0)


def test_group_and_item_caps_hold_together() -> None:
    weights = np.asarray([50.0, 30.0, 10.0, 5.0, 3.0, 2.0])
    groups = np.asarray([1, 1, 2, 3, 4, 5])
    capped = cap_grouped_probability_mass(
        weights,
        groups,
        maximum_item_mass=0.25,
        maximum_group_mass=0.40,
    )
    assert capped.sum() == pytest.approx(1.0)
    assert capped.max() <= 0.25 + 1e-12
    assert max(capped[groups == group].sum() for group in np.unique(groups)) <= 0.40 + 1e-12


def test_recent_adjustment_shrinks_small_samples_and_respects_cap() -> None:
    small = bounded_recent_adjustment(2.0, effective_sample_size=2.0, shrinkage_constant=18.0, cap=0.5)
    large = bounded_recent_adjustment(2.0, effective_sample_size=180.0, shrinkage_constant=18.0, cap=0.5)
    assert abs(small) < abs(large)
    assert abs(large) <= 0.5


def test_context_encoder_is_stable_for_known_players_and_teams() -> None:
    encoder = ContextEncoder(
        player_ids=(11, 12, 13, 14, 15),
        player_roles=("core", "core", "mid", "support", "support"),
        current_team_ids=(101,),
        player_current_team_ids=(101, 101, 101, 101, 101),
        duration_center=8.0,
        duration_scale=0.2,
    )
    frame = pd.DataFrame(
        {
            "account_id": [11, 13],
            "current_team_id": [101, 101],
            "played_for_current_team": [1.0, 1.0],
            "won_game": [1.0, 0.0],
            "opponent_probability": [0.6, 0.4],
            "best_of": [3, 5],
            "series_won": [1.0, 0.0],
            "series_length": [2.0, 5.0],
            "game_index": [0.0, 4.0],
            "duration": [3000.0, 3600.0],
        }
    )
    first = encoder.transform(frame)
    second = encoder.transform(frame.copy())
    assert np.array_equal(first, second)
    assert first.shape == (2, encoder.feature_count)


def test_stat_marginal_sampling_is_nonnegative_and_deterministic() -> None:
    encoder = ContextEncoder(
        player_ids=(11,),
        player_roles=("mid",),
        current_team_ids=(101,),
        player_current_team_ids=(101,),
        duration_center=8.0,
        duration_scale=0.2,
    )
    feature_count = encoder.feature_count
    model = StatMarginalModel(
        stat_id="kills",
        mean_coefficients=np.zeros(feature_count),
        zero_coefficients=np.zeros(feature_count),
        positive_residual_quantiles={"mid": np.asarray([-0.2, 0.0, 0.3])},
        recent_mean_adjustments={11: 0.1},
        recent_zero_adjustments={11: 0.0},
        integer_output=True,
    )
    context = pd.DataFrame(
        {
            "account_id": [11],
            "current_team_id": [101],
            "played_for_current_team": [1.0],
            "won_game": [1.0],
            "opponent_probability": [0.55],
            "best_of": [3],
            "series_won": [1.0],
            "series_length": [3.0],
            "game_index": [1.0],
            "duration": [2800.0],
        }
    )
    latent = np.asarray([[0.7]])
    first = model.sample(context, encoder, latent)
    second = model.sample(context, encoder, latent)
    assert np.array_equal(first, second)
    assert first[0] >= 0.0
    assert first[0] == round(float(first[0]))


def test_joint_residual_fit_is_deterministic_and_has_unit_marginal_variance() -> None:
    rng = np.random.default_rng(7)
    values = rng.normal(size=(200, 6))
    weights = np.linspace(1.0, 2.0, len(values))
    first = fit_joint_residual_model(values, weights, factor_rank=3, covariance_shrinkage=0.25)
    second = fit_joint_residual_model(values, weights, factor_rank=3, covariance_shrinkage=0.25)
    assert isinstance(first, JointResidualModel)
    assert np.array_equal(first.loadings, second.loadings)
    reconstructed = first.loadings @ first.loadings.T + np.diag(first.idiosyncratic_variance)
    assert np.diag(reconstructed) == pytest.approx(np.ones(values.shape[1]), abs=1e-6)
    draw_a = first.sample(np.random.default_rng(99), size=8)
    draw_b = first.sample(np.random.default_rng(99), size=8)
    assert np.array_equal(draw_a, draw_b)


def test_complete_generator_fit_and_sampling_are_deterministic() -> None:
    as_of = datetime(2026, 8, 16, 15, 31, 30, tzinfo=UTC)
    team_ids = tuple(range(101, 109))
    roles = ("core", "core", "mid", "support", "support")
    player_ids_by_team = np.asarray(
        [[team_index * 10 + offset + 1 for offset in range(5)] for team_index in range(8)],
        dtype=np.int64,
    )
    rows: list[dict[str, object]] = []
    for team_index, team_id in enumerate(team_ids):
        for game_offset in range(20):
            match_id = team_index * 100 + game_offset + 1
            series_id = team_index * 10 + game_offset // 2 + 1
            won = game_offset % 3 != 0
            for player_offset, account_id in enumerate(player_ids_by_team[team_index]):
                rows.append(
                    {
                        "match_id": match_id,
                        "series_id": series_id,
                        "account_id": int(account_id),
                        "historical_team_id": team_id,
                        "current_team_id": team_id,
                        "played_for_current_team": 1.0,
                        "won_game": float(won),
                        "opponent_probability": 0.45 + 0.01 * team_index,
                        "best_of": 3,
                        "series_won": float(won),
                        "series_length": 2,
                        "game_index": game_offset % 2,
                        "duration": 2100.0 + 20.0 * game_offset,
                        "evidence_weight": 1.0,
                        "start_time": as_of - timedelta(days=120 - game_offset),
                        "kills": float((game_offset + player_offset) % 9),
                        "stuns": float((2 * game_offset + player_offset) % 13),
                    }
                )
    evidence = PlayerRoleEvidence(
        frame=pd.DataFrame(rows),
        team_ids=team_ids,
        stat_ids=("kills", "stuns"),
        player_ids_by_team=player_ids_by_team,
        player_roles_by_team=tuple(roles for _ in team_ids),
        as_of=as_of,
        audit={},
    )
    parameters = {
        "ridge_alpha": 10.0,
        "recent_effective_sample_constant": 16.0,
        "recent_residual_cap_sigma": 0.5,
        "factor_rank": 3,
        "covariance_shrinkage": 0.25,
        "maximum_game_parameter_mass": 0.01,
        "maximum_series_parameter_mass": 0.02,
        "maximum_residual_game_mass": 0.01,
        "maximum_residual_series_mass": 0.02,
    }
    first = fit_player_role_generator_from_frame(evidence, **parameters)
    second = fit_player_role_generator_from_frame(evidence, **parameters)
    assert first.semantic_hash == second.semantic_hash
    durations_a = first.sample_durations(
        opponent_probability=0.55,
        won_game=True,
        best_of=3,
        series_won=True,
        series_length=2,
        game_index=0,
        size=2,
        rng=np.random.default_rng(456),
    )
    durations_b = second.sample_durations(
        opponent_probability=0.55,
        won_game=True,
        best_of=3,
        series_won=True,
        series_length=2,
        game_index=0,
        size=2,
        rng=np.random.default_rng(456),
    )
    assert np.array_equal(durations_a, durations_b)
    assert np.all(durations_a > 0.0)
    first_draw = first.sample_team_games(
        team_id=101,
        opponent_probability=0.55,
        won_game=True,
        best_of=3,
        series_won=True,
        series_length=2,
        game_index=0,
        durations=durations_a,
        rng=np.random.default_rng(123),
    )
    second_draw = second.sample_team_games(
        team_id=101,
        opponent_probability=0.55,
        won_game=True,
        best_of=3,
        series_won=True,
        series_length=2,
        game_index=0,
        durations=durations_b,
        rng=np.random.default_rng(123),
    )
    assert first_draw.shape == (2, 5, 2)
    assert np.array_equal(first_draw, second_draw)
    assert np.all(first_draw >= 0.0)
