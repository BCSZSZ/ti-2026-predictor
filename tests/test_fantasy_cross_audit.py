from __future__ import annotations

import numpy as np

from ti_predictor.fantasy.cross_audit import (
    build_held_out_scenarios,
    common_activation_frequencies,
    independent_weighted_loss_bounds,
    load_cross_audit_policy,
    release_labels,
)
from ti_predictor.fantasy.scenarios import ROLE_IDS, CommonScenarioSet, ScenarioDraws
from ti_predictor.fantasy.solver import WeightedOutcomeDistribution
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
