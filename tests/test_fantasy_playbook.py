from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.playbook import (
    PlaybookDefinition,
    PlaybookPolicy,
    build_stat_priorities,
    load_playbook,
    playbook_snapshot,
)
from ti_predictor.fantasy.playbook_validation import (
    StartingReadinessEvaluator,
    build_starting_coverage_suite,
    load_playbook_validation_policy,
    simulate_playbook_session,
)
from ti_predictor.fantasy.roll import (
    ApplyRollAction,
    BannerState,
    EmblemState,
    GroupRollState,
    RollOffer,
    build_group_roll_rules,
)
from ti_predictor.rules import _inspect_fantasy_crafting

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def frozen_playbooks() -> tuple[PlaybookDefinition, PlaybookDefinition]:
    return (
        load_playbook(ROOT / "config/playbooks/group-rate-agnostic-v1.json"),
        load_playbook(ROOT / "config/playbooks/group-primary-model-v1.json"),
    )


@pytest.fixture
def playbook_roll_rules(rules_payload):
    text = (ROOT / "tests/fixtures/fantasy_roll_rules_2026.vdata").read_text(encoding="utf-8")
    return build_group_roll_rules(rules_payload, _inspect_fantasy_crafting(text))


def _stat_packages(rules_payload, *, hard_best: tuple[str, str] | None = None):
    roles = {
        "core": ("red", "green"),
        "mid": ("red", "blue", "green"),
        "support": ("blue", "green"),
    }
    relative_values = (1.0, 0.9, 0.7, 0.5, 0.43, 0.2)
    rows = []
    bootstrap_rows = []
    for role, colors in roles.items():
        for color in colors:
            stat_ids = [
                stat_id
                for stat_id, definition in rules_payload["fantasy"]["stats"].items()
                if definition["color"] == color
            ]
            for index, (stat_id, relative) in enumerate(zip(stat_ids, relative_values, strict=True)):
                runner = 39.0 if hard_best == (role, color) and index == 0 else 90.0
                rows.append(
                    {
                        "role": role,
                        "color": color,
                        "stat_id": stat_id,
                        "relative_to_best": relative,
                        "best_team_mean": 100.0 * relative,
                        "runner_up_mean": runner * relative,
                        "all_team_mean": 70.0 * relative,
                        "eligible_row_provenance_coverage": 1.0,
                        "complete_block_provenance_coverage": 1.0,
                        "provenance": rules_payload["fantasy"]["stats"][stat_id]["provenance"],
                    }
                )
                bootstrap_rows.append(
                    {
                        "role": role,
                        "color": color,
                        "stat_id": stat_id,
                        "boundary": index == 2,
                    }
                )
    return {"rows": rows}, {"rows": bootstrap_rows}


def _policy(definition, rules_payload, playbook_roll_rules):
    forecasts, bootstrap = _stat_packages(rules_payload)
    return PlaybookPolicy(
        definition,
        playbook_roll_rules,
        rules_payload,
        build_stat_priorities(forecasts, bootstrap),
    )


def _low_state(playbook_roll_rules) -> GroupRollState:
    banners = []
    for role in playbook_roll_rules.group_roles:
        emblems = []
        for color in playbook_roll_rules.colors_for(role)[:3]:
            emblems.append(
                EmblemState(
                    stat_id=playbook_roll_rules.stats_for(color)[-1],
                    quality_tier=1,
                    trait_id="unique",
                )
            )
        banners.append(BannerState(role=role, emblems=tuple(emblems)))
    return GroupRollState(
        banners=tuple(banners),
        offer=RollOffer((23, 31, 11)),
        remaining_rolls=40,
    )


def _readiness(policy: PlaybookPolicy) -> StartingReadinessEvaluator:
    means = {
        key: np.asarray(
            [row.best_team_mean, 0.9 * row.best_team_mean, 0.8 * row.best_team_mean],
            dtype=float,
        )
        for key, row in policy.priority.items()
    }
    return StartingReadinessEvaluator(
        rules=policy.rules,
        canonical_rules=dict(policy.canonical_rules),
        team_ids=(1, 2, 3),
        stat_team_means=means,
    )


def test_frozen_playbooks_obey_human_complexity_contract(frozen_playbooks) -> None:
    rate_agnostic, primary = frozen_playbooks
    assert rate_agnostic.candidate_rule_counts == (8, 12, 16)
    assert primary.candidate_rule_counts == (8, 12, 16)
    assert all(len(rule.visible_conditions) <= 3 for book in frozen_playbooks for rule in book.rules)
    assert rate_agnostic.transition_model is None
    assert primary.transition_model == "client-weight-primary-v1"
    assert rate_agnostic.origin == primary.origin


def test_playbook_rejects_non_nested_candidate_frontier(frozen_playbooks) -> None:
    payload = frozen_playbooks[0].model_dump(mode="json")
    payload["candidate_rule_counts"] = [8, 10, 16]
    with pytest.raises(ValueError, match="8, 12 or 16"):
        PlaybookDefinition.model_validate_json(json.dumps(payload))


def test_point_grade_and_bootstrap_marker_are_independent(rules_payload) -> None:
    forecasts, bootstrap = _stat_packages(rules_payload, hard_best=("core", "red"))
    rows = build_stat_priorities(forecasts, bootstrap)
    core_red = [row for row in rows if row.role == "core" and row.color == "red"]
    assert [row.grade for row in core_red] == [
        "hard-protect",
        "keep",
        "conditional-reroll",
        "conditional-reroll",
        "priority-repair",
        "priority-repair",
    ]
    assert core_red[2].boundary is True
    assert core_red[2].grade == "conditional-reroll"


def test_rate_agnostic_rule_order_prefers_non_decreasing_quality(
    frozen_playbooks, rules_payload, playbook_roll_rules
) -> None:
    policy = _policy(frozen_playbooks[0], rules_payload, playbook_roll_rules)
    state = _low_state(playbook_roll_rules)
    decision = policy.decide(state)
    assert decision.rule_id == "RA01"
    assert isinstance(decision.action, ApplyRollAction)
    assert decision.action.operation_id == 23
    assert decision.metrics is not None
    assert decision.metrics.minimum_delta >= 0.0


def test_rule_ablation_moves_to_next_frozen_rule(
    frozen_playbooks, rules_payload, playbook_roll_rules
) -> None:
    policy = _policy(frozen_playbooks[0], rules_payload, playbook_roll_rules)
    decision = policy.decide(_low_state(playbook_roll_rules), omit_rule_id="RA01")
    assert decision.rule_id == "RA02"
    assert isinstance(decision.action, ApplyRollAction)
    assert decision.action.operation_id == 31


def test_primary_metrics_use_declared_model_only(
    frozen_playbooks, rules_payload, playbook_roll_rules
) -> None:
    policy = _policy(frozen_playbooks[1], rules_payload, playbook_roll_rules)
    decision = policy.decide(_low_state(playbook_roll_rules))
    assert decision.rule_id == "PM01"
    assert decision.metrics is not None
    assert decision.metrics.expected_delta is not None


def test_playbook_snapshot_is_deterministic(frozen_playbooks, rules_payload) -> None:
    forecasts, bootstrap = _stat_packages(rules_payload)
    priorities = build_stat_priorities(forecasts, bootstrap)
    first = playbook_snapshot(frozen_playbooks[0], priorities)
    second = playbook_snapshot(frozen_playbooks[0], copy.deepcopy(priorities))
    assert first == second
    assert len(first["snapshot_sha256"]) == 64


def test_validation_policy_and_nine_cell_coverage_are_frozen(
    frozen_playbooks, rules_payload, playbook_roll_rules
) -> None:
    validation = load_playbook_validation_policy(
        ROOT / "config/models/fantasy-group-playbook-validation-v1.json"
    )
    policy = _policy(frozen_playbooks[0], rules_payload, playbook_roll_rules)
    suite = build_starting_coverage_suite(policy, _readiness(policy))
    assert len(suite) == 9
    assert validation.mean_retention_epsilons == (0.0, 0.01, 0.02, 0.05)
    for role in playbook_roll_rules.group_roles:
        cells = {
            (cell.stat_readiness, cell.configuration_readiness)
            for case in suite
            for cell in case.role_cells
            if cell.role == role
        }
        assert len(cells) == 9


def test_complete_playbook_session_is_deterministic(
    frozen_playbooks, rules_payload, playbook_roll_rules
) -> None:
    policy = _policy(frozen_playbooks[0], rules_payload, playbook_roll_rules)
    start = build_starting_coverage_suite(policy, _readiness(policy))[0]
    first = simulate_playbook_session(
        policy,
        start,
        model_id="client-weight-primary-v1",
        replicate=3,
        seed=2026080604,
        candidate_rule_count=12,
        risk_preference="default-knee",
    )
    second = simulate_playbook_session(
        policy,
        start,
        model_id="client-weight-primary-v1",
        replicate=3,
        seed=2026080604,
        candidate_rule_count=12,
        risk_preference="default-knee",
    )
    assert first == second
    assert len(first.action_sequence) == 40
    assert len(first.offer_sequence) == 41


def test_future_shared_offers_are_paired_across_different_policies(
    frozen_playbooks, rules_payload, playbook_roll_rules
) -> None:
    rate_policy = _policy(frozen_playbooks[0], rules_payload, playbook_roll_rules)
    primary_policy = _policy(frozen_playbooks[1], rules_payload, playbook_roll_rules)
    start = build_starting_coverage_suite(rate_policy, _readiness(rate_policy))[1]
    common = {
        "start": start,
        "model_id": "client-weight-primary-v1",
        "replicate": 7,
        "seed": 2026080604,
        "candidate_rule_count": 12,
        "risk_preference": "default-knee",
    }
    rate_trace = simulate_playbook_session(rate_policy, **common)
    primary_trace = simulate_playbook_session(primary_policy, **common)
    assert rate_trace.action_sequence != primary_trace.action_sequence
    assert rate_trace.offer_sequence == primary_trace.offer_sequence
