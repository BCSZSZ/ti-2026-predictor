from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from ti_predictor.fantasy.main_roll_research_contract import load_main_roll_research_manifest
from ti_predictor.fantasy.main_roll_research_experiment import load_frozen_main_research_context
from ti_predictor.fantasy.main_roll_research_rosters import (
    INNER_EVALUATION,
    INNER_SELECTION,
    ProjectedRosterConditionalTerminal,
    build_projected_roster_panel,
    derive_projected_roster_records,
)
from ti_predictor.fantasy.main_roll_research_simulator import state_from_payload
from ti_predictor.fantasy.main_roll_research_terminal import VectorizedMainResearchTerminal
from ti_predictor.fantasy.solver_release import load_solver_release_context
from ti_predictor.hashing import sha256_json
from ti_predictor.models.ratings import TeamStrengthModel


def _frozen_inputs():
    root = Path(__file__).resolve().parents[1]
    manifest = load_main_roll_research_manifest(root / "config/research/fantasy-main-roll-simulator-v1.json")
    group = load_solver_release_context()
    main = load_frozen_main_research_context(
        group,
        manifest,
        rule_snapshot_path=root / "tests/fixtures/fantasy_main_rule_snapshot_identity_20260813.json",
    )
    assert main.terminal.scenario_set.model_sha256 == manifest.source.team_strength_model_sha256
    model = TeamStrengthModel(
        {team_id: 1500.0 + index * 15.0 for index, team_id in enumerate(main.terminal.scenario_set.team_ids)}
    )
    return root, manifest, group, main, model


def test_projected_roster_records_preserve_all_weighted_rows_and_balance_folds() -> None:
    _, manifest, group, main, model = _frozen_inputs()

    records = derive_projected_roster_records(
        group.scenarios,
        main.terminal.scenario_set,
        model,
        manifest.projected_roster_validation,
    )

    assert len(records) == 256
    assert len({record.entrant_team_ids for record in records}) == 240
    assert Counter(record.fold_id for record in records) == {fold: 32 for fold in range(8)}
    assert sum(record.empirical_weight for record in records) == 1.0
    assert all(len(record.entrant_team_ids) == 8 for record in records)
    assert all(set(record.projected_seed_order) == set(record.entrant_team_ids) for record in records)


def test_projected_roster_panel_separates_team_selection_and_evaluation() -> None:
    root, manifest, group, main, model = _frozen_inputs()
    panel = build_projected_roster_panel(
        main.terminal.pool_result,
        group.scenarios,
        main.terminal.scenario_set,
        model,
        manifest.projected_roster_validation,
        selected_fold_ids=(0,),
        inner_scenarios_per_phase=4,
    )
    repeated = build_projected_roster_panel(
        main.terminal.pool_result,
        group.scenarios,
        main.terminal.scenario_set,
        model,
        manifest.projected_roster_validation,
        selected_fold_ids=(0,),
        inner_scenarios_per_phase=4,
    )

    assert panel.semantic_hash == repeated.semantic_hash
    assert len(panel.records) == 32
    assert len(panel.scenarios.scenario_ids) == 32 * 2 * 4
    assert set(panel.inner_phases.tolist()) == {INNER_SELECTION, INNER_EVALUATION}
    assert np.all((panel.scenarios.series_counts > 0).sum(axis=1) == 8)

    state = state_from_payload(
        json.loads((root / manifest.starting_state.relative_path).read_text(encoding="utf-8")),
        main.roll_rules,
    )
    terminal = ProjectedRosterConditionalTerminal(
        VectorizedMainResearchTerminal(
            main.terminal.pool_result,
            panel.scenarios,
            main.terminal.canonical_rules,
        ),
        panel,
        cvar_alpha=0.1,
    )
    result = terminal.evaluate(state.banners)

    assert result.selection_mode == "projected-roster-conditional"
    assert result.selected_team_ids == ()
    assert len(result.outcomes) == 32 * 4
    assert len(result.cohort_ids) == len(result.outcomes)
    assert len(set(result.roster_ids)) == 32
    assert result == terminal.evaluate(state.banners)


def test_vectorized_conditional_terminal_matches_scalar_reference() -> None:
    root, manifest, group, main, model = _frozen_inputs()
    panel = build_projected_roster_panel(
        main.terminal.pool_result,
        group.scenarios,
        main.terminal.scenario_set,
        model,
        manifest.projected_roster_validation,
        selected_fold_ids=manifest.projected_roster_validation.confirmation_folds,
        inner_scenarios_per_phase=4,
    )
    state = state_from_payload(
        json.loads((root / manifest.starting_state.relative_path).read_text(encoding="utf-8")),
        main.roll_rules,
    )
    terminal = ProjectedRosterConditionalTerminal(
        VectorizedMainResearchTerminal(
            main.terminal.pool_result,
            panel.scenarios,
            main.terminal.canonical_rules,
        ),
        panel,
        cvar_alpha=0.1,
    )
    banner_by_role = {banner.role: banner for banner in state.banners}
    matrices = {role: terminal.terminal.banner(banner_by_role[role]) for role in ("core", "mid", "support")}
    expected_outcomes: list[np.ndarray] = []
    expected_plan = []
    expected_cohorts: list[int] = []
    expected_rosters: list[int] = []
    for record in panel.records:
        outer = panel.outer_scenario_ids == record.source_group_scenario_id
        selection_columns = np.flatnonzero(outer & (panel.inner_phases == INNER_SELECTION))
        evaluation_columns = np.flatnonzero(outer & (panel.inner_phases == INNER_EVALUATION))
        lineup = terminal._select_lineup(matrices, record, selection_columns)
        values = sum(
            (
                matrices[role].outcomes[matrices[role].team_ids.index(team_id), evaluation_columns]
                for role, team_id in zip(("core", "mid", "support"), lineup, strict=True)
            ),
            start=np.zeros(len(evaluation_columns), dtype=float),
        )
        expected_outcomes.append(values)
        expected_cohorts.extend([record.fold_id] * len(values))
        expected_rosters.extend([record.source_group_scenario_id] * len(values))
        expected_plan.append(
            {
                "source_group_scenario_id": record.source_group_scenario_id,
                "selected_team_ids": lineup,
            }
        )

    result = terminal.evaluate(state.banners)

    np.testing.assert_array_equal(result.outcomes, np.concatenate(expected_outcomes))
    assert result.cohort_ids == tuple(expected_cohorts)
    assert result.roster_ids == tuple(expected_rosters)
    assert result.selection_plan_sha256 == sha256_json(expected_plan)
