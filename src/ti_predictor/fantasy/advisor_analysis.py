"""Frozen-source context and bounded diagnostics for the local Group Roll advisor."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.fantasy.advisor import (
    AdvisorBaseline,
    AdvisorPolicyError,
    InteractiveAdvisorPolicy,
    action_identity,
    action_label,
    load_advisor_policy,
    state_sha256,
)
from ti_predictor.fantasy.cross_audit import build_held_out_scenarios, load_cross_audit_policy
from ti_predictor.fantasy.playbook import (
    PlaybookDefinition,
    PlaybookPolicy,
    build_stat_priorities,
    load_playbook,
)
from ti_predictor.fantasy.roll import (
    BannerState,
    GroupRollState,
    RefreshRollAction,
    RollRuleSet,
    build_group_roll_rules,
    legal_actions,
    mutation_distribution,
    rank_rate_agnostic_actions,
    validate_group_state,
)
from ti_predictor.fantasy.scenarios import CommonScenarioSet
from ti_predictor.fantasy.solver import (
    BranchCappedRollSolver,
    ExactFixedStatConfigurationEvaluator,
    ExactPotentialProvider,
    TerminalGroupEvaluator,
    WeightedOutcomeDistribution,
)
from ti_predictor.fantasy.solver_reporting import PreparedSolverContext, prepare_solver_context
from ti_predictor.fantasy.valuation import RiskConfiguration
from ti_predictor.hashing import sha256_json
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import latest_rule_snapshot
from ti_predictor.schemas import as_utc


@dataclass(frozen=True)
class AdvisorContext:
    policy: InteractiveAdvisorPolicy
    solver_context: PreparedSolverContext
    scenarios: CommonScenarioSet
    manuals: Mapping[str, PlaybookPolicy]
    definitions: Mapping[str, PlaybookDefinition]
    terminal: TerminalGroupEvaluator
    solver: BranchCappedRollSolver
    baseline: AdvisorBaseline
    team_names: Mapping[int, str]
    p5_status: str
    p6_status: str
    manual_statuses: Mapping[str, str]
    warnings: tuple[str, ...]
    context_load_seconds: float


def _find_semantic_artifact(
    paths: ProjectPaths,
    *,
    filename: str,
    hash_field: str,
    expected_sha256: str,
) -> tuple[dict[str, Any], Path]:
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(paths.artifacts.glob(f"fantasy-*/{filename}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get(hash_field) == expected_sha256:
            matches.append((payload, path))
    if not matches:
        raise FileNotFoundError(
            f"P7 requires {filename} with {hash_field}={expected_sha256}"
        )
    reference = sha256_json(matches[0][0])
    if any(sha256_json(payload) != reference for payload, _ in matches[1:]):
        raise AdvisorPolicyError(f"multiple {filename} artifacts claim one semantic hash but differ")
    return matches[-1]


def load_advisor_roll_rules(*, paths: ProjectPaths = PATHS) -> RollRuleSet:
    """Load only canonical and client-snapshot Roll rules for the manual input form."""

    snapshot_result = latest_rule_snapshot(paths)
    if snapshot_result is None:
        raise FileNotFoundError("P7 requires the frozen local Dota Rule snapshot")
    snapshot, _ = snapshot_result
    client_roll = snapshot.observed.get("fantasy_roll")
    if not isinstance(client_roll, dict):
        raise AdvisorPolicyError("local Rule snapshot lacks normalized Fantasy Roll operations")
    return build_group_roll_rules(load_rules(paths.rules), client_roll)


def prepare_advisor_context(
    *,
    as_of,
    paths: ProjectPaths = PATHS,
) -> AdvisorContext:
    """Reconstruct P3–P6 identities before enabling any recommendation diagnostic."""

    started = perf_counter()
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    policy = load_advisor_policy(
        paths.config / "models" / "fantasy-group-interactive-advisor-v1.json"
    )
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    if policy.as_of != cutoff_text:
        raise AdvisorPolicyError("P7 advisor as_of differs from the explicit cutoff")

    solver_context = prepare_solver_context(as_of=cutoff, paths=paths)
    if solver_context.p4_evidence.get("evidence_sha256") != policy.source_p4_evidence_sha256:
        raise AdvisorPolicyError("P7 P4 evidence identity drifted")

    p3_evidence, _ = _find_semantic_artifact(
        paths,
        filename="group-fantasy-evidence.json",
        hash_field="evidence_package_sha256",
        expected_sha256=policy.source_p3_evidence_sha256,
    )
    p5_evidence, _ = _find_semantic_artifact(
        paths,
        filename="group-solver-evidence.json",
        hash_field="evidence_sha256",
        expected_sha256=policy.source_p5_evidence_sha256,
    )
    p6_evidence, _ = _find_semantic_artifact(
        paths,
        filename="group-playbook-cross-audit.json",
        hash_field="evidence_sha256",
        expected_sha256=policy.source_p6_evidence_sha256,
    )
    p5_status = str(p5_evidence.get("gate", {}).get("p5_status"))
    if p5_status != policy.optional_solver.display_effectiveness_status:
        raise AdvisorPolicyError("P7 expected the frozen failed P5 effectiveness status")
    p6_status = str(p6_evidence.get("gate", {}).get("p6_status"))
    if p6_status not in {"partial-draft", "complete-draft"}:
        raise AdvisorPolicyError("P7 requires a draft P6 audit status")

    definitions = {
        "rate-agnostic": load_playbook(
            paths.config / "playbooks" / "group-rate-agnostic-v1.json"
        ),
        "primary-model": load_playbook(
            paths.config / "playbooks" / "group-primary-model-v1.json"
        ),
    }
    for edition, definition in definitions.items():
        if definition.semantic_hash != policy.playbook_sha256[edition]:
            raise AdvisorPolicyError(f"P7 {edition} playbook identity drifted")
        recorded = solver_context.p4_evidence.get("playbooks", {}).get(edition, {})
        if recorded.get("semantic_sha256") != definition.semantic_hash:
            raise AdvisorPolicyError(f"P7 {edition} playbook differs from frozen P4")
    priorities = build_stat_priorities(
        p3_evidence["stat_forecasts"],
        p3_evidence["cluster_bootstrap"],
    )
    manuals = {
        edition: PlaybookPolicy(
            definition,
            solver_context.roll_rules,
            solver_context.canonical_rules,
            priorities,
        )
        for edition, definition in definitions.items()
    }

    cross_policy = load_cross_audit_policy(
        paths.config / "models" / "fantasy-group-read-only-cross-audit-v1.json"
    )
    p4_validation = solver_context.p4_evidence.get("validation_policy", {})
    scenarios, _ = build_held_out_scenarios(
        solver_context.source_scenarios,
        cross_policy,
        p4_seed=int(p4_validation["seed"]),
        p4_count=int(p4_validation["scenario_subset_count"]),
        p5_seed=solver_context.policy.seed,
        p5_count=solver_context.policy.scenario_subset_count,
    )
    if scenarios.semantic_hash != policy.scenario.sha256:
        raise AdvisorPolicyError("P7 held-out Scenario identity drifted")
    if len(scenarios.scenario_ids) != policy.scenario.count:
        raise AdvisorPolicyError("P7 held-out Scenario count drifted")
    if p6_evidence.get("validation_scenario_sha256") != scenarios.semantic_hash:
        raise AdvisorPolicyError("P7 and P6 do not share the declared diagnostic Scenario set")

    terminal = TerminalGroupEvaluator(
        solver_context.pool_result,
        scenarios,
        solver_context.canonical_rules,
    )
    fixed_evaluator = ExactFixedStatConfigurationEvaluator(
        solver_context.pool_result,
        scenarios,
        solver_context.canonical_rules,
        solver_context.roll_rules,
    )
    terminal.attach_batch_evaluator(fixed_evaluator)
    potential = ExactPotentialProvider(
        fixed_evaluator,
        maximum_attribute_differences=(
            solver_context.policy.synergy_potential.maximum_attribute_differences
        ),
    )
    solver = BranchCappedRollSolver(
        solver_context.roll_rules,
        terminal,
        potential,
        solver_context.policy,
    )
    baseline = AdvisorBaseline(
        as_of=policy.as_of,
        data_snapshot_sha256=solver_context.data_snapshot_sha256,
        rule_snapshot_sha256=solver_context.rule_snapshot_sha256,
        scenario_sha256=scenarios.semantic_hash,
        playbook_sha256=tuple(sorted(policy.playbook_sha256.items())),
        transition_models=policy.quick_analysis.models,
        seeds=(
            ("advisor", policy.seed),
            ("held_out_scenarios", cross_policy.seed),
            ("solver", solver_context.policy.seed),
        ),
    )
    release_labels = p6_evidence.get("gate", {}).get("release_labels", {})
    manual_statuses = {
        edition: str(release_labels.get(edition, {}).get("p6_status", "draft"))
        for edition in definitions
    }
    manifest = load_tournament_manifest(paths.tournament)
    warnings = tuple(
        sorted(
            {
                *solver_context.warnings,
                f"P5 solver effectiveness: {p5_status}",
                f"P6 cross-audit: {p6_status}",
                *(f"{edition} manual: {status}" for edition, status in manual_statuses.items()),
            }
        )
    )
    return AdvisorContext(
        policy=policy,
        solver_context=solver_context,
        scenarios=scenarios,
        manuals=manuals,
        definitions=definitions,
        terminal=terminal,
        solver=solver,
        baseline=baseline,
        team_names={team.team_id: team.name for team in manifest.teams},
        p5_status=p5_status,
        p6_status=p6_status,
        manual_statuses=manual_statuses,
        warnings=warnings,
        context_load_seconds=perf_counter() - started,
    )


def _replace_banner(
    banners: tuple[BannerState, ...],
    replacement: BannerState,
) -> tuple[BannerState, ...]:
    return tuple(replacement if item.role == replacement.role else item for item in banners)


def _distribution_payload(distribution: WeightedOutcomeDistribution, *, alpha: float) -> dict[str, float]:
    return {
        "mean": distribution.mean,
        "cvar10": distribution.cvar(alpha),
    }


def _preferred_action(
    rows: list[dict[str, Any]],
    *,
    epsilon: float,
    safety_order: Mapping[str, int],
) -> str:
    maximum_mean = max(float(row["mean"]) for row in rows)
    floor = maximum_mean - abs(maximum_mean) * epsilon - 1e-12
    eligible = [row for row in rows if float(row["mean"]) >= floor]
    chosen = min(
        eligible,
        key=lambda row: (
            -float(row["cvar10"]),
            -float(row["mean"]),
            safety_order[str(row["action_id"])],
            str(row["action_id"]),
        ),
    )
    return str(chosen["action_id"])


def analyze_advisor_state(
    context: AdvisorContext,
    state: GroupRollState,
    *,
    edition: str,
    risk_preference: str,
) -> dict[str, Any]:
    """Evaluate exact one-step mutation support; do not estimate future offers or reachability."""

    started = perf_counter()
    validate_group_state(state, context.solver_context.roll_rules)
    if edition not in context.manuals:
        raise ValueError(f"unknown manual edition: {edition}")
    manual = context.manuals[edition]
    rules = context.solver_context.roll_rules
    actions = legal_actions(state, rules)
    intervals = rank_rate_agnostic_actions(
        state,
        rules,
        context.manuals["rate-agnostic"].banner_value,
    )
    interval_by_action = {
        action_identity(item.action): {"lower": item.lower, "upper": item.upper}
        for item in intervals
    }
    safety_order = {
        action_identity(item.action): index for index, item in enumerate(intervals)
    }
    if state.remaining_rolls:
        manual_decision = manual.decide(
            state,
            candidate_rule_count=12,
            risk_preference=risk_preference,
        )
        manual_payload: dict[str, Any] = {
            "action_id": action_identity(manual_decision.action),
            "action_label": action_label(manual_decision.action, rules),
            "rule_id": manual_decision.rule_id,
            "rule_title": manual_decision.rule_title,
            "explanation": manual_decision.explanation,
            "edition": edition,
            "status": context.manual_statuses[edition],
        }
    else:
        manual_payload = {
            "action_id": None,
            "action_label": "Roll 已用完；只显示最终队伍匹配",
            "rule_id": None,
            "rule_title": None,
            "explanation": "没有剩余 Roll",
            "edition": edition,
            "status": context.manual_statuses[edition],
        }

    rows: list[dict[str, Any]] = []
    current_matching: list[dict[str, Any]] = []
    preferred: list[dict[str, Any]] = []
    epsilon_runtimes: dict[str, float] = {}
    for epsilon in context.policy.quick_analysis.mean_retention_epsilons:
        epsilon_started = perf_counter()
        risk = RiskConfiguration(
            mean_retention_epsilon=epsilon,
            cvar_alpha=context.policy.quick_analysis.cvar_alpha,
        )
        current = context.terminal.matched_group(state.banners, risk)
        current_distribution = WeightedOutcomeDistribution(
            current.outcomes,
            np.full(len(current.outcomes), 1.0 / len(current.outcomes)),
        )
        current_summary = _distribution_payload(
            current_distribution,
            alpha=context.policy.quick_analysis.cvar_alpha,
        )
        current_matching.append(
            {
                "epsilon": epsilon,
                "selected_team_ids": list(current.selected_team_ids),
                "selected_teams": [
                    context.team_names.get(team_id, str(team_id))
                    for team_id in current.selected_team_ids
                ],
                **current_summary,
                "maximum_mean": current.maximum_mean,
            }
        )

        outcome_cache: dict[BannerState, WeightedOutcomeDistribution] = {}
        for action in actions:
            if isinstance(action, RefreshRollAction):
                continue
            banner = next(item for item in state.banners if item.role == action.banner_role)
            for outcome in mutation_distribution(
                banner,
                action.operation_id,
                rules,
                context.policy.quick_analysis.models[0],
            ):
                if outcome.banner not in outcome_cache:
                    matched = context.terminal.matched_group(
                        _replace_banner(state.banners, outcome.banner),
                        risk,
                    )
                    outcome_cache[outcome.banner] = WeightedOutcomeDistribution(
                        matched.outcomes,
                        np.full(len(matched.outcomes), 1.0 / len(matched.outcomes)),
                    )

        for model_id in context.policy.quick_analysis.models:
            model_rows: list[dict[str, Any]] = []
            for action in actions:
                identity = action_identity(action)
                if isinstance(action, RefreshRollAction):
                    distribution = current_distribution
                    support_count = 1
                else:
                    banner = next(item for item in state.banners if item.role == action.banner_role)
                    mutation = mutation_distribution(
                        banner,
                        action.operation_id,
                        rules,
                        model_id,
                    )
                    values = np.concatenate(
                        [outcome_cache[item.banner].values for item in mutation]
                    )
                    weights = np.concatenate(
                        [outcome_cache[item.banner].weights * item.probability for item in mutation]
                    )
                    distribution = WeightedOutcomeDistribution(values, weights)
                    support_count = len(mutation)
                summary = _distribution_payload(
                    distribution,
                    alpha=context.policy.quick_analysis.cvar_alpha,
                )
                row = {
                    "epsilon": epsilon,
                    "model_id": model_id,
                    "action_id": identity,
                    "action_label": action_label(action, rules),
                    "support_count": support_count,
                    "mean": summary["mean"],
                    "cvar10": summary["cvar10"],
                    "mean_delta": summary["mean"] - current_summary["mean"],
                    "cvar10_delta": summary["cvar10"] - current_summary["cvar10"],
                    "rate_agnostic_lower": interval_by_action[identity]["lower"],
                    "rate_agnostic_upper": interval_by_action[identity]["upper"],
                }
                rows.append(row)
                model_rows.append(row)
            if model_rows:
                selected = _preferred_action(
                    model_rows,
                    epsilon=epsilon,
                    safety_order=safety_order,
                )
                preferred.append(
                    {
                        "epsilon": epsilon,
                        "model_id": model_id,
                        "action_id": selected,
                        "action_label": next(
                            str(row["action_label"])
                            for row in model_rows
                            if row["action_id"] == selected
                        ),
                    }
                )
        epsilon_runtimes[str(epsilon)] = perf_counter() - epsilon_started

    sensitivity = []
    for epsilon in context.policy.quick_analysis.mean_retention_epsilons:
        selected = [row for row in preferred if row["epsilon"] == epsilon]
        identities = sorted({str(row["action_id"]) for row in selected})
        sensitivity.append(
            {
                "epsilon": epsilon,
                "preferred_action_ids": identities,
                "model_disagreement": len(identities) > 1,
            }
        )
    payload = {
        "schema_version": 1,
        "analysis_type": "p7_exact_one_step_no_future_offer_value",
        "state_sha256": state_sha256(state),
        "remaining_rolls": state.remaining_rolls,
        "manual": manual_payload,
        "current_matching": current_matching,
        "action_values": rows,
        "preferred_actions": preferred,
        "model_sensitivity": sensitivity,
        "source_status": {
            "p5_solver": context.p5_status,
            "p6_cross_audit": context.p6_status,
            "manuals": dict(context.manual_statuses),
        },
        "limitations": [
            "one-step only: future replacement-offer option value is excluded",
            "remaining-Roll reachability is excluded",
            "P6 held-out Scenarios are diagnostic and do not promote either draft manual",
        ],
        "runtime_seconds": {
            "by_epsilon": epsilon_runtimes,
            "total": perf_counter() - started,
        },
    }
    semantic_payload = {key: value for key, value in payload.items() if key != "runtime_seconds"}
    payload["analysis_sha256"] = sha256_json(semantic_payload)
    return payload


def run_optional_solver(
    context: AdvisorContext,
    state: GroupRollState,
    *,
    model_id: str,
    epsilon: float,
) -> dict[str, Any]:
    """Run the failed-gate P5 solver only after an explicit UI/CLI action."""

    if model_id not in context.policy.quick_analysis.models:
        raise ValueError(f"unknown transition model: {model_id}")
    if epsilon not in context.policy.quick_analysis.mean_retention_epsilons:
        raise ValueError(f"epsilon {epsilon} is outside the frozen P7 frontier")
    validate_group_state(state, context.solver_context.roll_rules)
    if state.remaining_rolls == 0:
        raise ValueError("the optional solver cannot act after all Rolls are spent")
    started = perf_counter()
    decision = context.solver.decide(state, model_id=model_id, epsilon=epsilon)
    result = {
        "schema_version": 1,
        "state_sha256": state_sha256(state),
        "model_id": model_id,
        "epsilon": epsilon,
        "preferred_action_id": action_identity(decision.preferred_action),
        "preferred_action_label": action_label(
            decision.preferred_action,
            context.solver_context.roll_rules,
        ),
        "executed_action_id": action_identity(decision.executed_action),
        "executed_action_label": action_label(
            decision.executed_action,
            context.solver_context.roll_rules,
        ),
        "resolved": decision.resolved,
        "resolution_reason": decision.resolution_reason,
        "screening_paths_per_action": (
            context.solver_context.policy.decision_budget.screening_paths_per_action
        ),
        "confirmation_paths_per_finalist": (
            context.solver_context.policy.decision_budget.confirmation_paths_per_finalist
        ),
        "screening": [
            {
                "action_id": action_identity(item.action),
                "mean": item.mean,
                "cvar10": item.cvar,
            }
            for item in decision.screening
        ],
        "confirmation": [
            {
                "action_id": action_identity(item.action),
                "mean": item.mean,
                "cvar10": item.cvar,
            }
            for item in decision.confirmation
        ],
        "full_horizon_equivalent_paths": decision.full_horizon_equivalent_paths,
        "effectiveness_status": context.p5_status,
        "approximate_not_globally_optimal": decision.approximate_not_globally_optimal,
        "runtime_seconds": perf_counter() - started,
    }
    semantic_result = {key: value for key, value in result.items() if key != "runtime_seconds"}
    result["solver_result_sha256"] = sha256_json(semantic_result)
    return result
