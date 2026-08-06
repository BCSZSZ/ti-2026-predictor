from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ti_predictor.fantasy.cross_audit import (
    build_held_out_scenarios,
    common_activation_frequencies,
    independent_weighted_loss_bounds,
    load_cross_audit_policy,
    release_labels,
)
from ti_predictor.fantasy.cross_audit_reporting import _find_semantic_artifact
from ti_predictor.fantasy.scenarios import ROLE_IDS, CommonScenarioSet, ScenarioDraws
from ti_predictor.fantasy.solver import WeightedOutcomeDistribution, load_solver_policy
from ti_predictor.tournament.group import SLOT_CATEGORIES


def _scenario_set(count: int = 1024) -> CommonScenarioSet:
    team_ids = tuple(range(1, 17))
    categories = np.tile(np.asarray(SLOT_CATEGORIES, dtype=np.int8), (count, 1))
    series_counts = np.ones((count, len(team_ids)), dtype=np.int8)
    draws = tuple(
        ScenarioDraws(
            target_team_id=team_id,
            role=role,
            pool_sha256=f"{team_id:02d}{role}".ljust(64, "a")[:64],
            block_indexes=np.zeros((count, 1), dtype=np.int32),
        )
        for team_id in team_ids
        for role in ROLE_IDS
    )
    return CommonScenarioSet(
        policy_id="toy-source",
        data_snapshot_sha256="d" * 64,
        as_of="2026-08-06T08:15:00Z",
        seed=1,
        team_ids=team_ids,
        scenario_ids=np.arange(count, dtype=np.int64),
        group_categories=categories,
        series_counts=series_counts,
        draws=draws,
    )


def test_p6_policy_freezes_expected_108_rows(project_paths) -> None:
    policy = load_cross_audit_policy(
        project_paths.config / "models" / "fantasy-group-read-only-cross-audit-v1.json"
    )

    assert policy.expected_row_count == 108
    assert policy.editions[0].mean_retention_epsilon == 0.01
    assert policy.editions[1].mean_retention_epsilon == 0.02
    assert len(policy.semantic_hash) == 64


def test_v2_cross_audit_extends_runtime_without_drifting_v1_semantics() -> None:
    legacy = load_cross_audit_policy(Path("config/models/fantasy-group-read-only-cross-audit-v1.json"))
    current = load_cross_audit_policy(Path("config/models/fantasy-group-read-only-cross-audit-v2.json"))

    assert legacy.semantic_hash == "803ffeb46c1b340badeeb213a8b1229eba3b7e66dfe5160a643c04206c0e7b35"
    assert current.expected_row_count == 108
    assert current.as_of == "2026-08-06T17:27:00Z"
    assert current.runtime_target_seconds == 1800
    assert current.stop_new_computation_seconds == 3540
    assert current.runtime_hard_ceiling_seconds == 3600
    assert current.source_solver_evidence_scope == "historical-v1-effectiveness-only"
    assert current.semantic_hash == "5aee998b6aab224fbe986fe894558c604db9e96625790cfc3f1847bd36a834d7"
    assert (
        current.source_playbook_artifact == "artifacts/fantasy-1c8871c419f59f08/group-playbook-evidence.json"
    )
    assert current.source_solver_artifact == "artifacts/fantasy-afa5cb6f3b665fd1/group-solver-evidence.json"


def test_v2_cross_audit_can_pin_one_artifact_when_semantic_duplicates_exist(project_paths) -> None:
    payload = {"evidence_sha256": "a" * 64, "value": 1}
    frozen = project_paths.artifacts / "fantasy-1111111111111111" / "evidence.json"
    duplicate = project_paths.artifacts / "fantasy-ffffffffffffffff" / "evidence.json"
    frozen.parent.mkdir()
    duplicate.parent.mkdir()
    frozen.write_text(json.dumps(payload), encoding="utf-8")
    duplicate.write_text(json.dumps(payload), encoding="utf-8")

    loaded, path = _find_semantic_artifact(
        project_paths,
        filename="evidence.json",
        hash_field="evidence_sha256",
        expected_sha256="a" * 64,
        expected_relative_path="artifacts/fantasy-1111111111111111/evidence.json",
    )

    assert loaded == payload
    assert path == frozen


def test_v2_audit_solver_changes_context_identity_not_algorithm() -> None:
    legacy = load_solver_policy(Path("config/models/fantasy-group-branch-capped-solver-v1.json"))
    current = load_solver_policy(Path("config/models/fantasy-group-branch-capped-solver-audit-v2.json"))
    ignored = {
        "policy_id",
        "as_of",
        "source_playbook_evidence_sha256",
        "source_validation_policy_sha256",
    }
    legacy_algorithm = {
        key: value for key, value in legacy.model_dump(mode="json").items() if key not in ignored
    }
    current_algorithm = {
        key: value for key, value in current.model_dump(mode="json").items() if key not in ignored
    }

    assert legacy.semantic_hash == "9466049f426e10c03926152c9cf60ecd9a4b96c155c19389456f2a5b73e5d3d9"
    assert current.semantic_hash == "6b067754c1caf6e5f866e3c86bc0358eb30e4fd789a497239577ea3d094e8f9c"
    assert current_algorithm == legacy_algorithm


def test_p6_scenarios_are_explicitly_disjoint_from_p4_and_p5(project_paths) -> None:
    policy = load_cross_audit_policy(
        project_paths.config / "models" / "fantasy-group-read-only-cross-audit-v1.json"
    )

    first, audit = build_held_out_scenarios(
        _scenario_set(),
        policy,
        p4_seed=2026080604,
        p4_count=512,
        p5_seed=2026080605,
        p5_count=128,
    )
    repeated, repeated_audit = build_held_out_scenarios(
        _scenario_set(),
        policy,
        p4_seed=2026080604,
        p4_count=512,
        p5_seed=2026080605,
        p5_count=128,
    )

    assert first.semantic_hash == repeated.semantic_hash
    assert audit == repeated_audit
    assert audit.selected_count == 128
    assert audit.p4_p6_overlap_count == 0
    assert audit.p5_p6_overlap_count == 0
    assert audit.p4_p5_overlap_count > 0


def test_v2_scenarios_are_disjoint_from_v2_p3_and_recorded_p5_indexes() -> None:
    policy = load_cross_audit_policy(Path("config/models/fantasy-group-read-only-cross-audit-v2.json"))

    first, audit = build_held_out_scenarios(
        _scenario_set(count=8192),
        policy,
        p4_seed=2026080704,
        p4_count=512,
        p5_seed=2026080605,
        p5_count=128,
    )
    repeated, repeated_audit = build_held_out_scenarios(
        _scenario_set(count=8192),
        policy,
        p4_seed=2026080704,
        p4_count=512,
        p5_seed=2026080605,
        p5_count=128,
    )

    assert first.semantic_hash == repeated.semantic_hash
    assert audit == repeated_audit
    assert audit.selected_count == 128
    assert audit.p4_p6_overlap_count == 0
    assert audit.p5_p6_overlap_count == 0


def test_independent_weighted_loss_bounds_are_deterministic_and_detect_loss(project_paths) -> None:
    policy = load_cross_audit_policy(
        project_paths.config / "models" / "fantasy-group-read-only-cross-audit-v1.json"
    )
    reference = WeightedOutcomeDistribution(
        values=np.asarray([90.0, 100.0, 110.0]),
        weights=np.asarray([0.2, 0.6, 0.2]),
    )
    candidate = WeightedOutcomeDistribution(
        values=np.asarray([70.0, 80.0, 90.0]),
        weights=np.asarray([0.2, 0.6, 0.2]),
    )

    first = independent_weighted_loss_bounds(
        reference,
        candidate,
        alpha=policy.cvar_alpha,
        confidence=policy.confidence,
        seed=17,
    )
    repeated = independent_weighted_loss_bounds(
        reference,
        candidate,
        alpha=policy.cvar_alpha,
        confidence=policy.confidence,
        seed=17,
    )

    assert first == repeated
    assert first["mean_loss_upper95_fraction"] > 0.1
    assert first["cvar10_loss_upper95_fraction"] > 0.1


def test_common_activation_index_keeps_exact_edition_model_case_scope() -> None:
    evidence = {
        "common_situation_conditional_loss": [
            {
                "edition": "rate-agnostic",
                "model_id": "flattened-weights-v1",
                "case_id": "coverage-02",
                "situation": "RA08",
                "session_frequency": 0.25,
            },
            {
                "edition": "rate-agnostic",
                "model_id": "flattened-weights-v1",
                "case_id": "coverage-02",
                "situation": "RA08",
                "session_frequency": 0.2,
            },
        ]
    }

    result = common_activation_frequencies(evidence)

    assert result[("rate-agnostic", "flattened-weights-v1", "coverage-02", "RA08")] == 0.25


def test_p6_never_promotes_a_frozen_draft_and_downgrades_a_reliable_exception() -> None:
    p4_gate = {
        "rate-agnostic": {"p4_status": "draft"},
        "primary-model": {"p4_status": "baseline-reliable"},
    }
    rows = [
        {
            "edition": "primary-model",
            "baseline_material_exception": True,
        }
    ]

    result = release_labels(p4_gate, rows, complete=True)

    assert result["rate-agnostic"]["p6_status"] == "draft"
    assert result["rate-agnostic"]["promotion_permitted"] is False
    assert result["primary-model"]["p6_status"] == "draft"
