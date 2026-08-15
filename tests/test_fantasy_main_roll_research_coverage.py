from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_roll import build_main_roll_rules
from ti_predictor.fantasy.main_roll_research_coverage import (
    _build_final_report,
    analyze_coverage_records,
    prepare_coverage_bundle,
    run_coverage_task,
)
from ti_predictor.fantasy.main_roll_research_simulator import TerminalEvaluation
from ti_predictor.fantasy.main_roll_research_states import (
    load_base_research_manifest,
    load_starting_state_coverage_manifest,
    sensitivity_state_indices,
)
from ti_predictor.fantasy.roll import BannerState
from ti_predictor.rules import _inspect_fantasy_crafting


class _QualityTerminal:
    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        value = float(sum(emblem.quality_tier for banner in banners for emblem in banner.emblems))
        return TerminalEvaluation(
            np.asarray([value - 1.0, value, value + 1.0, value + 2.0]),
            (101, 102, 103),
            cohort_ids=(1, 1, 2, 2),
        )


@pytest.fixture(scope="module")
def coverage_manifest():
    return load_starting_state_coverage_manifest(
        Path(__file__).resolve().parents[1] / "config/research/fantasy-main-starting-state-coverage-v1.json"
    )


@pytest.fixture(scope="module")
def base_manifest(coverage_manifest):
    return load_base_research_manifest(
        coverage_manifest,
        repository_root=Path(__file__).resolve().parents[1],
    )[1]


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def test_coverage_task_runs_paired_policies_deterministically(
    coverage_manifest,
    base_manifest,
    main_rules,
) -> None:
    arguments = dict(
        state_index=7,
        probability_model_id="client-weight-primary-v1",
        source_version_id="test-source",
        remaining_rolls=1,
    )

    first = run_coverage_task(
        coverage_manifest,
        base_manifest,
        main_rules,
        _QualityTerminal(),
        **arguments,
    )
    second = run_coverage_task(
        coverage_manifest,
        base_manifest,
        main_rules,
        _QualityTerminal(),
        **arguments,
    )

    assert first == second
    assert len(first.traces) == 3
    assert first.record["remaining_rolls"] == 1
    assert first.record["generated_state_sha256"] != first.record["state_sha256"]
    assert len({trace["episode_seed"] for _, trace in first.traces}) == 1
    assert set(first.record["policies"]) == {
        base_manifest.strategies.greedy.policy_id,
        base_manifest.strategies.target.policy_id,
        base_manifest.strategies.hybrid.policy_id,
    }


def test_prepare_bundle_is_exact_and_contains_no_runtime_write(
    tmp_path,
    coverage_manifest,
    base_manifest,
    main_rules,
) -> None:
    root = Path(__file__).resolve().parents[1]
    coverage_path = root / "config/research/fantasy-main-starting-state-coverage-v1.json"
    artifact_root = tmp_path / "artifacts/research/main-roll-starting-state-coverage/test"

    first = prepare_coverage_bundle(
        coverage_manifest,
        base_manifest,
        main_rules,
        coverage_manifest_path=coverage_path,
        artifact_root=artifact_root,
    )
    second = prepare_coverage_bundle(
        coverage_manifest,
        base_manifest,
        main_rules,
        coverage_manifest_path=coverage_path,
        artifact_root=artifact_root,
    )

    assert first == second
    assert len(first) == 1_000
    assert len((artifact_root / "starting-states.jsonl").read_text(encoding="utf-8").splitlines()) == 1_000
    assert not (tmp_path / "deploy/runtime").exists()


def _fake_record(
    coverage_manifest,
    base_manifest,
    *,
    state_index: int,
    model_id: str,
) -> dict:
    greedy_id = base_manifest.strategies.greedy.policy_id
    target_id = base_manifest.strategies.target.policy_id
    hybrid_id = base_manifest.strategies.hybrid.policy_id
    values = {greedy_id: 100.0, target_id: 101.0, hybrid_id: 99.0}
    policies = {
        policy_id: {
            "final_terminal": {"mean": value, "cvar10": value - 10.0},
            "final_by_roster_fold": {
                str(fold): {"mean": value, "cvar10": value - 10.0} for fold in range(1, 8)
            },
            "spent_rolls": 30,
            "stop_reason": "roll-budget-exhausted",
        }
        for policy_id, value in values.items()
    }
    return {
        "source_version": "test-source",
        "probability_model_id": model_id,
        "state_index": state_index,
        "initial_terminal": {"mean": float(state_index)},
        "paired_policy_ids": [greedy_id, target_id, hybrid_id],
        "starting_state_strata": {
            "average-quality-band": ("low", "central", "high")[state_index % 3],
            "direct-quality-increment-offer": ("absent", "available")[state_index % 2],
            "conditional-trait-ready-banner-band": ("none", "one", "two")[state_index % 3],
        },
        "sensitivity_selected": state_index in set(sensitivity_state_indices(coverage_manifest)),
        "policies": policies,
    }


def test_final_gate_uses_900_state_units_and_same_100_state_sensitivity_subset(
    coverage_manifest,
    base_manifest,
) -> None:
    primary_records = [
        _fake_record(
            coverage_manifest,
            base_manifest,
            state_index=state_index,
            model_id=coverage_manifest.primary_probability_model,
        )
        for state_index in coverage_manifest.splits.confirmation.values
    ]
    selected = sensitivity_state_indices(coverage_manifest)
    sensitivity_records = [
        _fake_record(
            coverage_manifest,
            base_manifest,
            state_index=state_index,
            model_id=model_id,
        )
        for model_id in coverage_manifest.sensitivity_panel.probability_model_ids[1:]
        for state_index in selected
    ]

    report = _build_final_report(
        coverage_manifest,
        base_manifest,
        state_index_hash="a" * 64,
        primary_records=primary_records,
        sensitivity_records=sensitivity_records,
    )

    target_id = base_manifest.strategies.target.policy_id
    hybrid_id = base_manifest.strategies.hybrid.policy_id
    assert report["confirmation_state_count"] == 900
    assert report["sensitivity_state_count"] == 100
    assert report["coverage_gates"][target_id]["status"] == "pass"
    assert report["coverage_gates"][hybrid_id]["status"] == "fail"
    assert report["strategy_selection"]["selected_policy_id"] == target_id
    assert all(
        comparison["paired_state_count"] == 100
        for model in report["sensitivity_panel"]["model_reports"].values()
        for comparison in model["paired_vs_greedy"].values()
    )


def test_analysis_rejects_an_empty_record_set(base_manifest) -> None:
    with pytest.raises(ValueError, match="requires records"):
        analyze_coverage_records([], base_manifest, include_starting_strata=False)
