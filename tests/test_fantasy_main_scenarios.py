from __future__ import annotations

import numpy as np
import pytest

from ti_predictor.fantasy.main_scenarios import (
    MainScenarioSet,
    build_main_scenario_set_from_model,
    build_projected_main_scenario_set_from_group,
)
from ti_predictor.fantasy.scenarios import ROLE_IDS, ScenarioDraws
from ti_predictor.fantasy.solver_release import load_solver_release_context
from ti_predictor.models.ratings import TeamStrengthModel


def _main_scenarios(*, team_ids: tuple[int, ...] = tuple(range(1, 9))) -> MainScenarioSet:
    counts = np.asarray(
        [
            [2, 2, 3, 3, 4, 4, 5, 5],
            [5, 4, 4, 3, 3, 2, 2, 2],
        ],
        dtype=np.int8,
    )
    draws = tuple(
        ScenarioDraws(
            target_team_id=team_ids[0],
            role=role,
            pool_sha256=str(index + 1) * 64,
            block_indexes=np.asarray(
                [[0, 1, -1, -1, -1], [1, 0, 1, 0, 1]],
                dtype=np.int32,
            ),
        )
        for index, role in enumerate(ROLE_IDS)
    )
    return MainScenarioSet(
        policy_id="main-bracket-series-v1",
        data_snapshot_sha256="a" * 64,
        model_sha256="b" * 64,
        as_of="2026-08-16T12:00:00Z",
        seed=20260816,
        team_ids=team_ids,
        scenario_ids=np.arange(2),
        series_counts=counts,
        draws=draws,
    )


def test_main_scenarios_have_an_independent_eight_team_contract() -> None:
    scenarios = _main_scenarios()

    assert len(scenarios.team_ids) == 8
    assert scenarios.series_counts.shape == (2, 8)
    assert scenarios.draw_record_for(1, "mid").block_indexes.shape == (2, 5)
    assert scenarios.semantic_hash == _main_scenarios().semantic_hash


def test_actual_main_scenarios_reject_sixteen_candidates() -> None:
    with pytest.raises(ValueError, match="8"):
        _main_scenarios(team_ids=tuple(range(1, 17)))


def test_main_scenarios_sample_coherent_bracket_series_deterministically() -> None:
    group = load_solver_release_context()
    team_ids = tuple(group.team_names)[:8]
    model = TeamStrengthModel({team_id: 1500.0 + index * 20 for index, team_id in enumerate(team_ids)})
    kwargs = {
        "team_ids": team_ids,
        "model": model,
        "scenario_count": 32,
        "policy_id": "main-bracket-series-v1",
        "data_snapshot_sha256": "c" * 64,
        "as_of": "2026-08-16T12:00:00Z",
        "seed": 20260816,
    }

    first = build_main_scenario_set_from_model(group.pool_result, **kwargs)
    second = build_main_scenario_set_from_model(group.pool_result, **kwargs)

    assert first.semantic_hash == second.semantic_hash
    assert first.series_counts.shape == (32, 8)
    assert int(first.series_counts.min()) == 2
    assert int(first.series_counts.max()) <= 6
    assert first.model_sha256 == second.model_sha256


def test_projected_main_scenarios_keep_sixteen_candidates_and_eight_entrants() -> None:
    group = load_solver_release_context()
    team_ids = tuple(group.team_names)
    model = TeamStrengthModel({team_id: 1500.0 + index * 20 for index, team_id in enumerate(team_ids)})
    kwargs = {
        "group_scenarios": group.scenarios,
        "model": model,
        "scenario_count": 32,
        "policy_id": "main-bracket-series-v1",
        "data_snapshot_sha256": "e" * 64,
        "as_of": "2026-08-13T12:00:00Z",
        "seed": 20260813,
    }

    first = build_projected_main_scenario_set_from_group(group.pool_result, **kwargs)
    second = build_projected_main_scenario_set_from_group(group.pool_result, **kwargs)

    assert first.semantic_hash == second.semantic_hash
    assert first.eligibility_mode == "projected"
    assert first.seeding_method == "projected_group_category_then_strength"
    assert first.team_ids == team_ids
    assert first.series_counts.shape == (32, 16)
    assert np.all((first.series_counts > 0).sum(axis=1) == 8)
    assert int(first.series_counts.min()) == 0
    draw = first.draw_record_for(team_ids[0], "core").block_indexes
    assert np.all(draw[first.series_counts[:, 0] == 0] == -1)
