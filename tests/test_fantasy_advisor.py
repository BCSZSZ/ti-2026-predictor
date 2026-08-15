from __future__ import annotations

import copy
from pathlib import Path

import pytest

from ti_predictor.fantasy.advisor import (
    AdvisorBaseline,
    AdvisorSession,
    AdvisorSessionError,
    action_label,
    load_advisor_policy,
    mutation_outcome_label,
    operation_label,
    state_sha256,
)
from ti_predictor.fantasy.roll import (
    ApplyRollAction,
    BannerState,
    EmblemState,
    GroupRollState,
    RollOffer,
    RollStateError,
    build_group_roll_rules,
    enumerate_mutation_outcomes,
)
from ti_predictor.rules import _inspect_fantasy_crafting


@pytest.fixture
def roll_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    client_roll = _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8"))
    return build_group_roll_rules(rules_payload, client_roll)


def _state(rules, *, remaining: int = 12, period: str = "group") -> GroupRollState:
    banners = []
    for role in rules.group_roles:
        colors = rules.colors_for(role)[:3]
        banners.append(
            BannerState(
                role=role,
                emblems=tuple(
                    EmblemState(
                        stat_id=rules.stats_for(color)[slot],
                        quality_tier=slot + 1,
                        trait_id=rules.traits[slot],
                    )
                    for slot, color in enumerate(colors)
                ),
            )
        )
    return GroupRollState(
        banners=tuple(banners),
        offer=RollOffer((23, 24, 25)),
        remaining_rolls=remaining,
        period=period,
        slot_count=3 if period == "group" else 5,
    )


def _baseline() -> AdvisorBaseline:
    return AdvisorBaseline(
        as_of="2026-08-06T08:15:00Z",
        data_snapshot_sha256="data",
        rule_snapshot_sha256="rules",
        scenario_sha256="scenarios",
        playbook_sha256=(("primary-model", "primary"), ("rate-agnostic", "agnostic")),
        transition_models=(
            "client-weight-primary-v1",
            "flattened-weights-v1",
            "sharpened-weights-v1",
        ),
        seeds=(("advisor", 1), ("solver", 2)),
    )


def test_advisor_policy_freezes_local_manual_first_boundaries(project_paths) -> None:
    policy = load_advisor_policy(
        project_paths.config / "models" / "fantasy-group-interactive-advisor-v1.json"
    )

    assert policy.period == "group"
    assert policy.quick_analysis.mean_retention_epsilons == (0.0, 0.01, 0.02, 0.05)
    assert policy.quick_analysis.future_offer_value_included is False
    assert policy.optional_solver.enabled_on_explicit_user_action_only is True
    assert policy.optional_solver.display_effectiveness_status == "failed-escalation-review-required"
    assert policy.boundaries.listen_address == "127.0.0.1"
    assert policy.boundaries.period_stack == "group"
    assert policy.session.in_session_rate_learning is False


def test_apply_and_refresh_events_preserve_baseline_and_consume_one_each(roll_rules) -> None:
    initial = _state(roll_rules)
    session = AdvisorSession.create(_baseline(), initial, roll_rules)
    action = ApplyRollAction("core", 23)
    realized = enumerate_mutation_outcomes(initial.banners[0], 23, roll_rules)[-1]

    applied = session.apply_observed(action, realized, RollOffer((10, 13, 16)), roll_rules)
    refreshed = applied.refresh_observed(RollOffer((9, 12, 15)), roll_rules)
    current = refreshed.current_state(roll_rules)

    assert refreshed.baseline == session.baseline
    assert current.remaining_rolls == initial.remaining_rolls - 2
    assert current.banners[0] == realized
    assert current.banners[1:] == initial.banners[1:]
    assert current.offer == RollOffer((9, 12, 15))
    assert tuple(event.event_type for event in refreshed.events) == ("apply", "refresh")


def test_saved_session_replays_deterministically_and_rejects_tampering(roll_rules) -> None:
    initial = _state(roll_rules)
    action = ApplyRollAction("core", 23)
    realized = enumerate_mutation_outcomes(initial.banners[0], 23, roll_rules)[0]
    session = AdvisorSession.create(_baseline(), initial, roll_rules).apply_observed(
        action,
        realized,
        RollOffer((10, 13, 16)),
        roll_rules,
    )
    payload = session.as_payload(roll_rules)

    replayed = AdvisorSession.from_payload(
        payload,
        roll_rules,
        expected_baseline=_baseline(),
    )
    assert replayed == session
    assert state_sha256(replayed.current_state(roll_rules)) == payload["final_state_sha256"]
    assert replayed.as_payload(roll_rules) == payload

    tampered = copy.deepcopy(payload)
    tampered["events"][0]["replacement_offer"] = [9, 12, 15]
    with pytest.raises(AdvisorSessionError, match="session_sha256"):
        AdvisorSession.from_payload(tampered, roll_rules)

    wrong_baseline = copy.deepcopy(payload)
    body = {key: value for key, value in wrong_baseline.items() if key != "session_sha256"}
    body["baseline"]["data_snapshot_sha256"] = "other"
    from ti_predictor.hashing import sha256_json

    wrong_baseline = {**body, "session_sha256": sha256_json(body)}
    with pytest.raises(AdvisorSessionError, match="baseline differs"):
        AdvisorSession.from_payload(
            wrong_baseline,
            roll_rules,
            expected_baseline=_baseline(),
        )


def test_main_state_fails_closed_before_session_creation(roll_rules) -> None:
    with pytest.raises(RollStateError, match="Main"):
        AdvisorSession.create(_baseline(), _state(roll_rules, period="main"), roll_rules)


def test_generated_labels_expose_operation_target_and_realised_change(roll_rules) -> None:
    state = _state(roll_rules)
    action = ApplyRollAction("core", 23)
    outcome = enumerate_mutation_outcomes(state.banners[0], 23, roll_rules)[-1]

    assert "#23" in operation_label(23, roll_rules)
    assert "Carry" in action_label(action, roll_rules)
    assert mutation_outcome_label(state.banners[0], outcome)
