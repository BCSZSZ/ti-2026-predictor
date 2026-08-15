from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_roll import build_main_roll_rules
from ti_predictor.fantasy.main_roll_bounded_challenger_contract import (
    load_main_roll_bounded_challenger_manifest,
)
from ti_predictor.fantasy.main_roll_bounded_challenger_experiment import (
    analyze_bounded_records,
    prepare_bundle,
    run_bounded_task,
    screen_development,
)
from ti_predictor.fantasy.main_roll_research_simulator import TerminalEvaluation
from ti_predictor.fantasy.main_roll_research_states import load_base_research_manifest
from ti_predictor.fantasy.roll import BannerState
from ti_predictor.hashing import canonical_json, sha256_json
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
def bounded_manifest():
    return load_main_roll_bounded_challenger_manifest(
        Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-bounded-challengers-v1.json"
    )


@pytest.fixture(scope="module")
def base_manifest(bounded_manifest):
    return load_base_research_manifest(
        bounded_manifest,  # type: ignore[arg-type]
        repository_root=Path(__file__).resolve().parents[1],
    )[1]


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def test_prepare_bundle_proves_new_suite_does_not_overlap_prior_suite(
    tmp_path,
    bounded_manifest,
    base_manifest,
    main_rules,
) -> None:
    root = Path(__file__).resolve().parents[1]
    records = prepare_bundle(
        bounded_manifest,
        base_manifest,
        main_rules,
        manifest_path=root / "config/research/fantasy-main-roll-bounded-challengers-v1.json",
        artifact_root=tmp_path / "artifacts/research/main-roll-bounded-challengers/test",
    )

    assert len(records) == 1000
    summary = json.loads(
        (
            tmp_path
            / "artifacts/research/main-roll-bounded-challengers/test"
            / "starting-state-index-summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["prior_state_overlap_count"] == 0


def test_bounded_task_runs_all_policies_on_one_paired_tape(
    bounded_manifest,
    base_manifest,
    main_rules,
) -> None:
    output = run_bounded_task(
        bounded_manifest,
        base_manifest,
        main_rules,
        _QualityTerminal(),
        state_index=3,
        probability_model_id=bounded_manifest.primary_probability_model,
        policy_ids=bounded_manifest.strategies.policy_ids,
        source_version_id="test-source",
        remaining_rolls=1,
    )

    assert tuple(output.record["paired_policy_ids"]) == bounded_manifest.strategies.policy_ids
    assert len(output.traces) == 4
    assert len({trace["episode_seed"] for _, trace in output.traces}) == 1
    assert all(
        output.record["policies"][policy_id]["active_elapsed_seconds"] >= 0.0
        for policy_id in bounded_manifest.strategies.policy_ids
    )


def _fake_record(manifest, state_index: int) -> dict:
    baseline = manifest.strategies.baseline.policy_id
    values = {
        baseline: 100.0,
        manifest.strategies.safe_band.policy_id: 101.0,
        manifest.strategies.local_tie.policy_id: 100.5,
        manifest.strategies.selective_two_step.policy_id: 99.0,
    }
    return {
        "probability_model_id": manifest.primary_probability_model,
        "state_index": state_index,
        "initial_terminal": {"mean": float(state_index)},
        "paired_policy_ids": list(values),
        "starting_state_strata": {
            "average-quality-band": ("low", "central", "high")[state_index % 3],
            "direct-quality-increment-offer": ("absent", "available")[state_index % 2],
            "conditional-trait-ready-banner-band": ("none", "one", "two")[state_index % 3],
        },
        "policies": {
            policy_id: {
                "final_terminal": {"mean": value, "cvar10": value - 10.0},
                "final_by_roster_fold": {
                    str(fold): {"mean": value, "cvar10": value - 10.0} for fold in range(1, 8)
                },
                "spent_rolls": 30,
                "stop_reason": "roll-budget-exhausted",
                "active_elapsed_seconds": 1.0,
                "decision_mode_counts": {"test": 30},
            }
            for policy_id, value in values.items()
        },
    }


def test_generic_analysis_compares_every_challenger_to_greedy(bounded_manifest) -> None:
    report = analyze_bounded_records(
        [_fake_record(bounded_manifest, index) for index in range(10)],
        bounded_manifest,
        include_starting_strata=True,
    )

    primary = report["model_reports"][bounded_manifest.primary_probability_model]
    assert set(primary["paired_vs_baseline"]) == set(bounded_manifest.strategies.candidate_policy_ids)
    assert primary["paired_vs_baseline"][bounded_manifest.strategies.safe_band.policy_id]["mean_difference"][
        "mean"
    ] == pytest.approx(1.0)


def test_development_screen_advances_only_positive_runtime_bounded_candidates(
    tmp_path,
    bounded_manifest,
) -> None:
    records = [_fake_record(bounded_manifest, index) for index in range(100)]
    analysis = analyze_bounded_records(
        records,
        bounded_manifest,
        include_starting_strata=True,
    )
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-stage",
        "stage": "development",
        "model_reports": analysis["model_reports"],
    }
    report = {**body, "stage_report_sha256": sha256_json(body)}
    path = tmp_path / "stages/development-primary/report.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical_json(report) + b"\n")

    screen_path = screen_development(bounded_manifest, artifact_root=tmp_path)
    screen = json.loads(screen_path.read_text(encoding="utf-8"))

    assert screen["advanced_policy_ids"] == [
        bounded_manifest.strategies.safe_band.policy_id,
        bounded_manifest.strategies.local_tie.policy_id,
    ]
