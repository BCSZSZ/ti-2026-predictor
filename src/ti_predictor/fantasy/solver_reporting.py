"""Reproducible P5 entry point for the branch-capped Group Roll solver."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from ti_predictor.config import load_rules, load_team_strength_policy, load_tournament_manifest
from ti_predictor.fantasy.roll import (
    RefreshRollAction,
    RollOffer,
    RollRuleSet,
    build_group_roll_rules,
    validate_group_state,
)
from ti_predictor.fantasy.scenarios import (
    CommonScenarioSet,
    PoolBuildResult,
    build_common_scenario_set,
    build_series_block_pools,
    load_group_scenario_policy,
)
from ti_predictor.fantasy.solver import (
    BranchCappedRollSolver,
    BranchCappedSolverPolicy,
    ExactFixedStatConfigurationEvaluator,
    ExactPotentialProvider,
    TerminalGroupEvaluator,
    exact_fixed_offer_oracle,
    load_solver_policy,
)
from ti_predictor.fantasy.solver_validation import (
    SolverCoverageCase,
    common_situations_by_case,
    coverage_cases_from_p4,
    run_full_session_validation,
    subset_solver_scenarios,
    summarize_solver_validation,
)
from ti_predictor.fantasy.valuation import RiskConfiguration
from ti_predictor.forecasting import _available_by_as_of, _load_strength_model
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import rule_snapshot_at, rule_snapshot_issues
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import ForecastRun, as_utc
from ti_predictor.storage import read_parquet_if_exists
from ti_predictor.tournament.group import GroupSimulator


@dataclass(frozen=True)
class PreparedSolverContext:
    policy: BranchCappedSolverPolicy
    p4_evidence: dict[str, Any]
    p4_evidence_path: Path
    coverage_cases: tuple[SolverCoverageCase, ...]
    common_situations: dict[str, tuple[str, ...]]
    canonical_rules: dict[str, Any]
    roll_rules: RollRuleSet
    pool_result: PoolBuildResult
    source_scenarios: CommonScenarioSet
    validation_scenarios: CommonScenarioSet
    data_snapshot_sha256: str
    rule_snapshot_id: str
    rule_snapshot_sha256: str
    warnings: tuple[str, ...]


@dataclass
class SolverEvidenceResult:
    run: ForecastRun
    run_path: Path
    evidence_path: Path
    evidence: dict[str, Any]
    runtime_seconds: dict[str, float]


def _find_p4_evidence(
    paths: ProjectPaths,
    expected_sha256: str,
    *,
    expected_path: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    if expected_path is not None:
        try:
            expected_path.resolve().relative_to(paths.artifacts.resolve())
        except ValueError as exc:
            raise ValueError("frozen P4 artifact path must stay under artifacts") from exc
        if expected_path.name != "group-playbook-evidence.json":
            raise ValueError("frozen P4 artifact path has the wrong filename")
        if not expected_path.is_file():
            raise FileNotFoundError(f"frozen P4 artifact is missing: {expected_path}")
        try:
            payload = json.loads(expected_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"frozen P4 artifact is unreadable: {expected_path}") from exc
        if payload.get("evidence_sha256") != expected_sha256:
            raise ValueError("frozen P4 artifact semantic hash drifted")
        return payload, expected_path

    matches = []
    for path in sorted(paths.artifacts.glob("fantasy-*/group-playbook-evidence.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("evidence_sha256") == expected_sha256:
            matches.append((payload, path))
    if not matches:
        raise FileNotFoundError(
            f"P5 requires the immutable P4 playbook evidence artifact with semantic hash {expected_sha256}"
        )
    reference = sha256_json(matches[0][0])
    if any(sha256_json(payload) != reference for payload, _ in matches[1:]):
        raise ValueError("multiple P4 artifacts claim the same semantic hash but differ in content")
    return matches[-1]


def prepare_solver_context(
    *,
    as_of,
    solver_policy_path: Path | None = None,
    playbook_evidence_path: Path | None = None,
    paths: ProjectPaths = PATHS,
) -> PreparedSolverContext:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    policy_path = solver_policy_path or (
        paths.config / "models" / "fantasy-group-branch-capped-solver-v1.json"
    )
    policy = load_solver_policy(policy_path)
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    if policy.as_of != cutoff_text:
        raise ValueError("P5 solver as_of differs from the explicit command cutoff")
    p4_evidence, p4_path = _find_p4_evidence(
        paths,
        policy.source_playbook_evidence_sha256,
        expected_path=playbook_evidence_path,
    )
    if p4_evidence.get("validation_policy_sha256") != policy.source_validation_policy_sha256:
        raise ValueError("P5 source P4 validation policy hash drifted")

    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    scenario_policy_path = paths.config / "models" / "fantasy-group-scenarios-v1.json"
    scenario_policy = load_group_scenario_policy(scenario_policy_path)
    matches_path = paths.processed / "matches.parquet"
    observations_path = paths.processed / "fantasy_performance_samples.parquet"
    patches_path = paths.processed / "patches.parquet"
    for required_path in (matches_path, observations_path, patches_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"P5 requires the processed snapshot file: {required_path}")
    matches = _available_by_as_of(read_parquet_if_exists(matches_path), cutoff)
    observations = _available_by_as_of(read_parquet_if_exists(observations_path), cutoff)
    patches = _available_by_as_of(read_parquet_if_exists(patches_path), cutoff)
    model, model_report = _load_strength_model(paths, cutoff)
    strength_policy = load_team_strength_policy(manifest, config_root=paths.config)
    fantasy_policy = strength_policy.model_copy(
        update={
            "policy_id": f"{strength_policy.policy_id}-fantasy-player-history",
            "evidence_scope": EvidenceScopePolicy(mode="global"),
        }
    )
    evidence = build_evidence_set(
        matches,
        patches,
        as_of=cutoff,
        policy=fantasy_policy,
        target_patch_family=model.target_patch_family,
    )
    blocking = [issue for issue in evidence.issues if issue.severity == "blocking"]
    if blocking:
        raise ValueError("P5 Fantasy evidence is blocked: " + "; ".join(x.message for x in blocking))
    data_snapshot_sha256 = sha256_json(
        {
            "as_of": cutoff_text,
            "matches_sha256": sha256_file(matches_path),
            "observations_sha256": sha256_file(observations_path),
            "patches_sha256": sha256_file(patches_path),
            "rules_sha256": sha256_file(paths.rules),
            "manifest_sha256": sha256_file(paths.tournament),
            "scenario_policy_sha256": sha256_file(scenario_policy_path),
            "selected_match_ids_sha256": evidence.audit["selected_match_ids_sha256"],
            "weight_policy_sha256": evidence.audit["weight_policy_sha256"],
            "target_patch_family": evidence.target_patch_family,
        }
    )
    if data_snapshot_sha256 != p4_evidence.get("data_snapshot_sha256"):
        raise ValueError("P5 reconstructed data snapshot differs from frozen P4")
    pool_result = build_series_block_pools(
        observations,
        matches,
        evidence.matches,
        manifest,
        rules,
        scenario_policy,
        as_of=cutoff,
    )
    if pool_result.semantic_hash != p4_evidence.get("pool_set_sha256"):
        raise ValueError("P5 reconstructed Series pools differ from frozen P4")
    if p4_evidence.get("validation_policy", {}).get("source_scenario_policy_id") is None:
        raise ValueError("P4 evidence does not identify its governed source Scenario policy")
    source_seed = 20260813
    group_simulation = GroupSimulator(model, manifest).simulate(
        samples=scenario_policy.scenario_count,
        seed=source_seed,
        scenario=scenario_policy.group_outcome_model,
    )
    source_scenarios = build_common_scenario_set(
        pool_result,
        group_team_ids=group_simulation.team_ids,
        group_outcomes=group_simulation.outcomes,
        policy=scenario_policy,
        data_snapshot_sha256=data_snapshot_sha256,
        as_of=cutoff,
        seed=source_seed,
    )
    if source_scenarios.semantic_hash != p4_evidence.get("source_scenario_sha256"):
        raise ValueError("P5 reconstructed common Scenarios differ from frozen P4")
    validation_scenarios = subset_solver_scenarios(
        source_scenarios,
        count=policy.scenario_subset_count,
        seed=policy.seed,
    )

    snapshot_result = rule_snapshot_at(cutoff, paths)
    if snapshot_result is None:
        raise ValueError("P5 requires the frozen Dota client Rule snapshot")
    snapshot, _ = snapshot_result
    snapshot_issues = rule_snapshot_issues(cutoff, paths)
    blocking_snapshot = [issue for issue in snapshot_issues if issue.severity == "blocking"]
    if blocking_snapshot:
        raise ValueError("P5 Rule snapshot is blocked: " + "; ".join(x.message for x in blocking_snapshot))
    if snapshot.snapshot_sha256 != p4_evidence.get("rule_snapshot_sha256"):
        raise ValueError("P5 Rule snapshot differs from frozen P4")
    client_roll = snapshot.observed.get("fantasy_roll")
    if not isinstance(client_roll, dict):
        raise ValueError("P5 Rule snapshot lacks normalized Fantasy Roll operations")
    roll_rules = build_group_roll_rules(rules, client_roll)
    coverage = coverage_cases_from_p4(p4_evidence)
    for case in coverage:
        validate_group_state(case.state, roll_rules)
    warnings = sorted(
        {
            *(issue.message for issue in evidence.issues if issue.severity == "warning"),
            *(issue.message for issue in model_report.issues if issue.severity == "warning"),
            *(issue.message for issue in snapshot_issues if issue.severity == "warning"),
        }
    )
    return PreparedSolverContext(
        policy=policy,
        p4_evidence=p4_evidence,
        p4_evidence_path=p4_path,
        coverage_cases=coverage,
        common_situations=common_situations_by_case(p4_evidence),
        canonical_rules=rules,
        roll_rules=roll_rules,
        pool_result=pool_result,
        source_scenarios=source_scenarios,
        validation_scenarios=validation_scenarios,
        data_snapshot_sha256=data_snapshot_sha256,
        rule_snapshot_id=snapshot.snapshot_id,
        rule_snapshot_sha256=snapshot.snapshot_sha256,
        warnings=tuple(warnings),
    )


def _action_identity(action) -> str:
    if isinstance(action, RefreshRollAction):
        return "refresh"
    return f"{action.banner_role}:{action.operation_id}"


def _run_conditional_oracles(
    solver: BranchCappedRollSolver,
    context: PreparedSolverContext,
    *,
    started_at: float,
    progress=print,
) -> dict[str, Any]:
    rows = []
    durations = []
    stopped = None
    fixed_offer = RollOffer((23, 24, 26))
    planned = [
        (horizon, context.coverage_cases[index])
        for horizon in context.policy.validation.oracle_horizons
        for index in range(context.policy.validation.oracle_states_per_horizon)
    ]
    for item_index, (horizon, case) in enumerate(planned):
        elapsed = perf_counter() - started_at
        estimated = float(np.median(durations[-3:])) if durations else 0.0
        if elapsed + estimated >= context.policy.runtime_target_seconds:
            stopped = "projected next conditional oracle would exceed the frozen 60-minute target"
            break
        progress(f"P5 conditional oracle {item_index + 1}/{len(planned)} horizon={horizon} {case.case_id}")
        item_started = perf_counter()
        state = replace(case.state, offer=fixed_offer, remaining_rolls=horizon)
        risk = RiskConfiguration(mean_retention_epsilon=0.0, cvar_alpha=context.policy.cvar_alpha)
        decision = solver.decide(state, model_id="client-weight-primary-v1", epsilon=0.0)
        oracle = exact_fixed_offer_oracle(
            state,
            (fixed_offer,) * horizon,
            rules=context.roll_rules,
            terminal=solver.terminal,
            model_id="client-weight-primary-v1",
            risk=risk,
        )
        oracle_value = next(item for item in oracle.action_values if item.action == oracle.selected_action)
        candidate_value = next(
            item for item in oracle.action_values if item.action == decision.preferred_action
        )
        mean_regret = max(0.0, oracle_value.mean - candidate_value.mean) / max(abs(oracle_value.mean), 1e-12)
        cvar_regret = max(0.0, oracle_value.cvar - candidate_value.cvar) / max(abs(oracle_value.cvar), 1e-12)
        rows.append(
            {
                "horizon": horizon,
                "case_id": case.case_id,
                "model_id": "client-weight-primary-v1",
                "epsilon": 0.0,
                "solver_preferred_action": _action_identity(decision.preferred_action),
                "oracle_action": _action_identity(oracle.selected_action),
                "mean_regret_fraction": mean_regret,
                "cvar_regret_fraction": cvar_regret,
                "conditional_offer_schedule": [list(item) for item in oracle.conditional_offer_schedule],
            }
        )
        durations.append(perf_counter() - item_started)
    regret = np.asarray(
        [max(row["mean_regret_fraction"], row["cvar_regret_fraction"]) for row in rows],
        dtype=float,
    )
    if len(regret):
        rng = np.random.default_rng(context.policy.seed + 991)
        indexes = rng.integers(
            0,
            len(regret),
            size=(context.policy.decision_budget.bootstrap_replicates, len(regret)),
        )
        upper = float(
            np.quantile(
                regret[indexes].mean(axis=1),
                context.policy.decision_budget.confidence_level,
            )
        )
    else:
        upper = None
    complete = len(rows) == len(planned)
    numerical_pass = bool(
        complete and upper is not None and upper <= context.policy.validation.oracle_regret_upper_bound
    )
    return {
        "scope": "exact_mutations_actions_and_performance_conditional_on_fixed_future_offers",
        "unconditional_future_offer_probability_integrated": False,
        "planned_case_count": len(planned),
        "completed_case_count": len(rows),
        "stop_reason": stopped,
        "rows": rows,
        "mean_regret_one_sided_95_upper": upper,
        "numerical_threshold_pass": numerical_pass,
        "gate_pass": False,
        "gate_failure_reason": (
            "the frozen one-to-three-Roll gate requires unconditional future-offer integration; "
            "this bounded diagnostic is exact only after conditioning on an offer schedule"
        ),
    }


def _session_payload(sessions) -> list[dict[str, Any]]:
    return [
        {
            "model_id": row.key.model_id,
            "epsilon": row.key.epsilon,
            "case_id": row.key.case_id,
            "replicate": row.key.replicate,
            "policy_id": row.policy_id,
            "score": row.score,
            "selected_team_ids": list(row.selected_team_ids),
            "unresolved_decisions": row.unresolved_decisions,
            "full_horizon_equivalent_paths": row.full_horizon_equivalent_paths,
            "situations": list(row.situations),
            "action_sequence_sha256": sha256_json(row.action_sequence),
        }
        for row in sessions
    ]


def generate_group_solver_evidence(
    *,
    as_of,
    paths: ProjectPaths = PATHS,
    progress=print,
) -> SolverEvidenceResult:
    started = perf_counter()
    context = prepare_solver_context(as_of=as_of, paths=paths)
    context_finished = perf_counter()
    terminal = TerminalGroupEvaluator(
        context.pool_result,
        context.validation_scenarios,
        context.canonical_rules,
    )
    fixed_evaluator = ExactFixedStatConfigurationEvaluator(
        context.pool_result,
        context.validation_scenarios,
        context.canonical_rules,
        context.roll_rules,
    )
    terminal.attach_batch_evaluator(fixed_evaluator)
    potential_provider = ExactPotentialProvider(
        fixed_evaluator,
        maximum_attribute_differences=context.policy.synergy_potential.maximum_attribute_differences,
    )
    solver = BranchCappedRollSolver(
        context.roll_rules,
        terminal,
        potential_provider,
        context.policy,
    )
    oracle = _run_conditional_oracles(solver, context, started_at=started, progress=progress)
    oracle_finished = perf_counter()
    sessions, session_audit = run_full_session_validation(
        solver,
        context.coverage_cases,
        context.common_situations,
        potential_provider,
        started_at=started,
        progress=progress,
    )
    validation_finished = perf_counter()
    expected_sessions = (
        len(context.policy.transition_models)
        * len(context.policy.mean_retention_epsilons)
        * len(context.coverage_cases)
        * context.policy.validation.full_session_replicates_per_stratum
    )
    payload = summarize_solver_validation(
        sessions,
        policy=context.policy,
        expected_solver_session_count=expected_sessions,
        runtime_seconds=validation_finished - started,
        oracle=oracle,
    )
    payload.update(
        {
            "as_of": context.policy.as_of,
            "seed": context.policy.seed,
            "source_playbook_evidence_sha256": context.policy.source_playbook_evidence_sha256,
            "source_playbook_artifact": str(context.p4_evidence_path.relative_to(paths.root)).replace(
                "\\", "/"
            ),
            "data_snapshot_sha256": context.data_snapshot_sha256,
            "pool_set_sha256": context.pool_result.semantic_hash,
            "source_scenario_sha256": context.source_scenarios.semantic_hash,
            "validation_scenario_sha256": context.validation_scenarios.semantic_hash,
            "rule_snapshot_id": context.rule_snapshot_id,
            "rule_snapshot_sha256": context.rule_snapshot_sha256,
            "session_audit": {
                "planned_solver_sessions": session_audit["planned_solver_sessions"],
                "completed_solver_sessions": session_audit["completed_solver_sessions"],
                "stop_reason": session_audit["stop_reason"],
            },
            "session_results": _session_payload(sessions),
            "limitations": [
                "the fixed continuation sums exact per-Banner mean/CVaR objectives; final path "
                "scoring repeats exact joint Group Team matching",
                "simulated Stat changes receive no synergy-potential table until an observed-state replan",
                "the short-horizon diagnostic conditions on fixed future offers and therefore "
                "cannot pass the unconditional oracle gate",
                "Common-situation unresolved is a conservative case-level join to the frozen P4 "
                "conditions, not a reconstructed per-decision manual activation trace",
                "P4 manuals remain independent and were not modified from solver traces",
            ],
        }
    )
    payload.pop("validation_sha256", None)
    payload["evidence_sha256"] = sha256_json(payload)
    runtime = {
        "context_rebuild": context_finished - started,
        "conditional_oracles": oracle_finished - context_finished,
        "full_session_validation": validation_finished - oracle_finished,
        "total": validation_finished - started,
        "median_completed_triplet": float(session_audit["median_completed_triplet_seconds"] or 0.0),
    }
    gate = payload["gate"]
    warnings = sorted(
        {
            *context.warnings,
            "P5 branch-capped effectiveness gate failed; explicit escalation review is required",
            "P5 exact short-horizon evidence is conditional on fixed future offers",
            *([str(session_audit["stop_reason"])] if session_audit.get("stop_reason") else []),
        }
    )
    status = "warning" if gate["p5_status"] != "passed" or warnings else "publishable"
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise AssertionError("prepare_solver_context accepted a missing cutoff")
    parameters = {
        "phase": "p5_branch_capped_reference_solver",
        "solver_policy_id": context.policy.policy_id,
        "solver_policy_sha256": context.policy.semantic_hash,
        "source_playbook_evidence_sha256": context.policy.source_playbook_evidence_sha256,
        "validation_scenario_sha256": context.validation_scenarios.semantic_hash,
        "approximate_not_globally_optimal": True,
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
    evidence_path = writer.write_json("group-solver-evidence.json", payload)
    run = ForecastRun(
        run_id=run_id,
        kind="fantasy",
        as_of=cutoff,
        created_at=cutoff,
        status=status,
        seed=context.policy.seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=context.rule_snapshot_id,
        rule_snapshot_sha256=context.rule_snapshot_sha256,
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={"name": "branch_capped_group_roll_solver_v1", "parameters": parameters},
        profiles=[],
        outputs=[evidence_path.name],
        warnings=warnings,
    )
    run_path = writer.write_run(run)
    return SolverEvidenceResult(
        run=run,
        run_path=run_path,
        evidence_path=evidence_path,
        evidence=payload,
        runtime_seconds=runtime,
    )
