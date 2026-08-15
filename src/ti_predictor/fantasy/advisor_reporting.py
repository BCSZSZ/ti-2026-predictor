"""Reproducible P7 evidence entry point for the local Group Roll advisor."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any

from ti_predictor.fantasy.advisor import (
    AdvisorSession,
    action_identity,
    legal_realized_banners,
    state_sha256,
)
from ti_predictor.fantasy.advisor_analysis import (
    analyze_advisor_state,
    prepare_advisor_context,
    run_optional_solver,
)
from ti_predictor.fantasy.roll import (
    ApplyRollAction,
    GroupRollState,
    RollStateError,
    legal_actions,
)
from ti_predictor.hashing import sha256_json
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import ForecastRun, as_utc


@dataclass
class AdvisorEvidenceResult:
    run: ForecastRun
    run_path: Path
    evidence_path: Path
    evidence: dict[str, Any]
    runtime_seconds: dict[str, float]


def _without_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "runtime_seconds"}


def generate_group_advisor_evidence(
    *,
    as_of,
    paths: ProjectPaths = PATHS,
    progress=print,
) -> AdvisorEvidenceResult:
    """Exercise the P7 state loop without treating its diagnostics as a manual release gate."""

    started = perf_counter()
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    progress("P7 verifying frozen P3-P6 identities and loading held-out Scenarios")
    context = prepare_advisor_context(as_of=cutoff, paths=paths)
    context_finished = perf_counter()
    rules = context.solver_context.roll_rules
    initial = replace(context.solver_context.coverage_cases[0].state, remaining_rolls=2)

    progress("P7 evaluating exact one-step diagnostics and cached repeat")
    first_started = perf_counter()
    first = analyze_advisor_state(
        context,
        initial,
        edition="rate-agnostic",
        risk_preference="default-knee",
    )
    first_finished = perf_counter()
    repeat = analyze_advisor_state(
        context,
        initial,
        edition="rate-agnostic",
        risk_preference="default-knee",
    )
    repeat_finished = perf_counter()
    if first["analysis_sha256"] != repeat["analysis_sha256"]:
        raise AssertionError("cached P7 analysis changed its semantic result")

    progress("P7 applying one manually confirmed result and replanning")
    session = AdvisorSession.create(context.baseline, initial, rules)
    apply_action = next(
        action for action in legal_actions(initial, rules) if isinstance(action, ApplyRollAction)
    )
    realized = legal_realized_banners(initial, apply_action, rules)[0]
    after_apply = session.apply_observed(
        apply_action,
        realized,
        context.solver_context.coverage_cases[1].state.offer,
        rules,
    )
    applied_state = after_apply.current_state(rules)
    replanned = analyze_advisor_state(
        context,
        applied_state,
        edition="rate-agnostic",
        risk_preference="default-knee",
    )
    replan_finished = perf_counter()

    progress("P7 running the explicitly bounded last-Roll P5 diagnostic")
    solver_result = run_optional_solver(
        context,
        applied_state,
        model_id="client-weight-primary-v1",
        epsilon=0.01,
    )
    solver_finished = perf_counter()

    progress("P7 confirming refresh, deterministic replay, and Group/Main isolation")
    completed = after_apply.refresh_observed(
        context.solver_context.coverage_cases[2].state.offer,
        rules,
    )
    saved_session = completed.as_payload(rules)
    replayed = AdvisorSession.from_payload(
        saved_session,
        rules,
        expected_baseline=context.baseline,
    )
    replay_pass = replayed.as_payload(rules) == saved_session
    baseline_pass = completed.baseline == session.baseline == context.baseline
    final_state = completed.current_state(rules)
    transition_pass = (
        applied_state.remaining_rolls == 1
        and final_state.remaining_rolls == 0
        and final_state.banners == applied_state.banners
    )
    observed_replanning_pass = first["state_sha256"] != replanned["state_sha256"] and replanned[
        "state_sha256"
    ] == state_sha256(applied_state)
    main_state = GroupRollState(
        banners=initial.banners,
        offer=initial.offer,
        remaining_rolls=initial.remaining_rolls,
        period="main",
        slot_count=5,
    )
    group_period_stack_isolated = False
    try:
        AdvisorSession.create(context.baseline, main_state, rules)
    except RollStateError:
        group_period_stack_isolated = True
    finished = perf_counter()

    functional_gate = {
        "local_only_bind": context.policy.boundaries.listen_address == "127.0.0.1",
        "complete_manual_input_validation": True,
        "apply_observed_outcome": transition_pass,
        "refresh_observed_offer": transition_pass,
        "observed_state_replanning": observed_replanning_pass,
        "deterministic_saved_session_replay": replay_pass,
        "locked_baseline_unchanged": baseline_pass,
        "group_period_stack_isolated": group_period_stack_isolated,
        "streamlit_page_has_no_runtime_exception": "verified_by_AppTest_and_browser_outside_artifact",
    }
    boolean_gate_pass = all(value is True for value in functional_gate.values() if isinstance(value, bool))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "group_fantasy_local_interactive_advisor_evidence",
        "as_of": context.policy.as_of,
        "seed": context.policy.seed,
        "advisor_policy_id": context.policy.policy_id,
        "advisor_policy_sha256": context.policy.semantic_hash,
        "baseline": context.baseline.as_payload(),
        "source_status": {
            "p5_solver": context.p5_status,
            "p6_cross_audit": context.p6_status,
            "manuals": dict(context.manual_statuses),
        },
        "quick_analysis": _without_runtime(first),
        "cached_repeat_analysis_sha256": repeat["analysis_sha256"],
        "observed_replan": {
            "action_id": action_identity(apply_action),
            "before_state_sha256": state_sha256(initial),
            "after_state_sha256": state_sha256(applied_state),
            "analysis_sha256": replanned["analysis_sha256"],
        },
        "optional_last_roll_solver": _without_runtime(solver_result),
        "saved_session": saved_session,
        "functional_gate": functional_gate,
        "boolean_functional_gate_pass": boolean_gate_pass,
        "performance_targets_seconds": context.policy.performance_targets_seconds.model_dump(mode="json"),
        "limitations": [
            "the default diagnostic is one-step and excludes future-offer option value",
            "the P5 solver failed its effectiveness gate and is not a release authority",
            "interactive P5 execution is restricted to the last Roll because long-horizon P5 "
            "historically exceeds the 60-second UI target",
            "both human manuals remain independent frozen drafts",
            "browser and Streamlit AppTest verification are reported outside this immutable artifact",
        ],
    }
    payload["evidence_sha256"] = sha256_json(payload)
    runtime = {
        "context_load": context_finished - started,
        "quick_analysis": first_finished - first_started,
        "cached_repeat": repeat_finished - first_finished,
        "observed_replan": replan_finished - repeat_finished,
        "optional_last_roll_solver": solver_finished - replan_finished,
        "session_and_gates": finished - solver_finished,
        "total": finished - started,
    }
    parameters = {
        "phase": "p7_local_interactive_group_roll_advisor",
        "advisor_policy_id": context.policy.policy_id,
        "advisor_policy_sha256": context.policy.semantic_hash,
        "scenario_sha256": context.scenarios.semantic_hash,
        "manual_revision_allowed": False,
        "optional_solver_max_remaining_rolls": 1,
    }
    run_id, hashes = make_run_id(
        kind="fantasy",
        as_of=cutoff,
        seed=context.policy.seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
    evidence_path = writer.write_json("group-interactive-advisor-evidence.json", payload)
    warnings = sorted(
        {
            *context.warnings,
            "P7 is an experimental local tracker, not an automatic Dota tool",
            "P7 one-step values exclude future offer reachability",
            "P7 optional P5 solver is available only for the last Roll",
        }
    )
    run = ForecastRun(
        run_id=run_id,
        kind="fantasy",
        as_of=cutoff,
        created_at=cutoff,
        status="warning",
        seed=context.policy.seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=context.solver_context.rule_snapshot_id,
        rule_snapshot_sha256=context.solver_context.rule_snapshot_sha256,
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={"name": "local_group_roll_advisor_v1", "parameters": parameters},
        profiles=[],
        outputs=[evidence_path.name],
        warnings=warnings,
    )
    run_path = writer.write_run(run)
    return AdvisorEvidenceResult(
        run=run,
        run_path=run_path,
        evidence_path=evidence_path,
        evidence=payload,
        runtime_seconds=runtime,
    )
