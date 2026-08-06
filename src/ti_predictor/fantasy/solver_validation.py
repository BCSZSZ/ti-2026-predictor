"""Frozen P5 effectiveness validation for the branch-capped Group Roll solver."""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal

import numpy as np

from ti_predictor.fantasy.roll import (
    BannerState,
    EmblemState,
    GroupRollState,
    RefreshRollAction,
    RollAction,
    RollOffer,
    RollRuleSet,
    apply_realized_transition,
    draw_roll_offer,
    rank_rate_agnostic_actions,
    refresh_transition,
    sample_mutation,
)
from ti_predictor.fantasy.scenarios import CommonScenarioSet, ScenarioDraws
from ti_predictor.fantasy.solver import (
    BranchCappedRollSolver,
    BranchCappedSolverPolicy,
    ExactPotentialProvider,
    GroupTerminalProvider,
    SynergyContinuationPolicy,
)
from ti_predictor.fantasy.valuation import RiskConfiguration, distribution_summary, lower_tail_cvar
from ti_predictor.hashing import sha256_json


@dataclass(frozen=True)
class SolverCoverageCase:
    case_id: str
    state: GroupRollState
    readiness: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, order=True)
class SolverSessionKey:
    model_id: str
    epsilon: float
    case_id: str
    replicate: int


@dataclass(frozen=True)
class SolverSessionResult:
    key: SolverSessionKey
    policy_id: Literal["branch_capped", "one_step_greedy", "rate_agnostic_safety"]
    score: float
    selected_team_ids: tuple[int, ...]
    unresolved_decisions: int
    full_horizon_equivalent_paths: float
    situations: tuple[str, ...]
    action_sequence: tuple[str, ...] = field(repr=False)


def _seed(base_seed: int, *parts: Any) -> int:
    payload = ":".join([str(base_seed), *(str(part) for part in parts)]).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little", signed=False)


def subset_solver_scenarios(
    source: CommonScenarioSet,
    *,
    count: int,
    seed: int,
) -> CommonScenarioSet:
    if count > len(source.scenario_ids):
        raise ValueError("P5 Scenario subset exceeds the governed P3 Scenario set")
    rng = np.random.default_rng(_seed(seed, "p5-scenario-subset"))
    selected = np.sort(rng.choice(len(source.scenario_ids), size=count, replace=False))
    draws = tuple(
        ScenarioDraws(
            target_team_id=item.target_team_id,
            role=item.role,
            pool_sha256=item.pool_sha256,
            block_indexes=item.block_indexes[selected],
        )
        for item in source.draws
    )
    return CommonScenarioSet(
        policy_id=f"{source.policy_id}:p5-fixed-{count}",
        data_snapshot_sha256=source.data_snapshot_sha256,
        as_of=source.as_of,
        seed=seed,
        team_ids=source.team_ids,
        scenario_ids=np.arange(count, dtype=np.int64),
        group_categories=source.group_categories[selected],
        series_counts=source.series_counts[selected],
        draws=draws,
    )


def coverage_cases_from_p4(evidence: Mapping[str, Any]) -> tuple[SolverCoverageCase, ...]:
    rows = evidence.get("coverage_suite")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) != 9:
        raise ValueError("P5 requires the nine frozen P4 Starting-state coverage cases")
    cases = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("P4 coverage row is not a mapping")
        role_rows = row.get("roles")
        offer_ids = row.get("offer_operation_ids")
        if not isinstance(role_rows, Sequence) or len(role_rows) != 3:
            raise ValueError("P4 coverage case must contain three role rows")
        if not isinstance(offer_ids, Sequence) or len(offer_ids) != 3:
            raise ValueError("P4 coverage case must contain three offered operations")
        banners = []
        readiness = []
        for role_row in role_rows:
            if not isinstance(role_row, Mapping):
                raise ValueError("P4 coverage role row is not a mapping")
            emblem_rows = role_row.get("emblems")
            if not isinstance(emblem_rows, Sequence) or len(emblem_rows) != 3:
                raise ValueError("P4 coverage role requires three Emblems")
            role = str(role_row["role"])
            banners.append(
                BannerState(
                    role=role,
                    emblems=tuple(
                        EmblemState(
                            stat_id=str(emblem["stat_id"]),
                            quality_tier=int(emblem["quality_tier"]),
                            trait_id=str(emblem["trait_id"]),
                        )
                        for emblem in emblem_rows
                    ),
                )
            )
            readiness.append(
                (
                    role,
                    str(role_row["stat_readiness"]),
                    str(role_row["configuration_readiness"]),
                )
            )
        cases.append(
            SolverCoverageCase(
                case_id=str(row["case_id"]),
                state=GroupRollState(
                    banners=tuple(banners),
                    offer=RollOffer(tuple(int(value) for value in offer_ids)),
                    remaining_rolls=40,
                ),
                readiness=tuple(readiness),
            )
        )
    if tuple(case.case_id for case in cases) != tuple(f"coverage-{index:02d}" for index in range(1, 10)):
        raise ValueError("P4 coverage case IDs drifted")
    return tuple(cases)


def common_situations_by_case(evidence: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    result: dict[str, set[str]] = defaultdict(set)
    rows = evidence.get("common_situation_conditional_loss", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("P4 Common-situation evidence is malformed")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("P4 Common-situation row is malformed")
        case_id = str(row["case_id"])
        situation = f"{row['edition']}:{row['situation']}"
        result[case_id].add(situation)
    return {case_id: tuple(sorted(values)) for case_id, values in result.items()}


def _action_identity(action: RollAction) -> str:
    if isinstance(action, RefreshRollAction):
        return "refresh"
    return f"{action.banner_role}:{action.operation_id}"


def _transition(
    state: GroupRollState,
    action: RollAction,
    *,
    rules: RollRuleSet,
    model_id: str,
    seed: int,
    key: SolverSessionKey,
    step: int,
) -> GroupRollState:
    offer_rng = random.Random(
        _seed(seed, key.model_id, key.epsilon, key.case_id, key.replicate, step, "offer")
    )
    mutation_rng = random.Random(
        _seed(seed, key.model_id, key.epsilon, key.case_id, key.replicate, step, "mutation")
    )
    replacement_offer = draw_roll_offer(rules, model_id, offer_rng)
    if isinstance(action, RefreshRollAction):
        return refresh_transition(state, replacement_offer, rules)
    current = next(banner for banner in state.banners if banner.role == action.banner_role)
    realized = sample_mutation(current, action.operation_id, rules, model_id, mutation_rng)
    return apply_realized_transition(state, action, realized, replacement_offer, rules)


def _score_terminal(
    state: GroupRollState,
    *,
    terminal: GroupTerminalProvider,
    risk: RiskConfiguration,
    seed: int,
    key: SolverSessionKey,
) -> tuple[float, tuple[int, ...]]:
    matched = terminal.matched_group(state.banners, risk)
    scenario_index = _seed(
        seed,
        key.model_id,
        key.epsilon,
        key.case_id,
        key.replicate,
        "performance",
    ) % len(matched.outcomes)
    return float(matched.outcomes[scenario_index]), matched.selected_team_ids


def simulate_solver_session(
    solver: BranchCappedRollSolver,
    case: SolverCoverageCase,
    *,
    model_id: str,
    epsilon: float,
    replicate: int,
    situations: Sequence[str],
) -> SolverSessionResult:
    key = SolverSessionKey(model_id=model_id, epsilon=epsilon, case_id=case.case_id, replicate=replicate)
    state = case.state
    unresolved = 0
    equivalent_paths = 0.0
    actions = []
    while state.remaining_rolls:
        decision = solver.decide(state, model_id=model_id, epsilon=epsilon)
        unresolved += int(not decision.resolved)
        equivalent_paths += decision.full_horizon_equivalent_paths
        actions.append(_action_identity(decision.executed_action))
        state = _transition(
            state,
            decision.executed_action,
            rules=solver.rules,
            model_id=model_id,
            seed=solver.policy.seed,
            key=key,
            step=40 - state.remaining_rolls,
        )
    risk = RiskConfiguration(epsilon, solver.policy.cvar_alpha)
    score, teams = _score_terminal(
        state,
        terminal=solver.terminal,
        risk=risk,
        seed=solver.policy.seed,
        key=key,
    )
    return SolverSessionResult(
        key=key,
        policy_id="branch_capped",
        score=score,
        selected_team_ids=teams,
        unresolved_decisions=unresolved,
        full_horizon_equivalent_paths=equivalent_paths,
        situations=tuple(situations),
        action_sequence=tuple(actions),
    )


def simulate_baseline_session(
    policy_id: Literal["one_step_greedy", "rate_agnostic_safety"],
    case: SolverCoverageCase,
    *,
    rules: RollRuleSet,
    terminal: GroupTerminalProvider,
    potential_provider: ExactPotentialProvider,
    policy: BranchCappedSolverPolicy,
    model_id: str,
    epsilon: float,
    replicate: int,
    situations: Sequence[str],
) -> SolverSessionResult:
    key = SolverSessionKey(model_id=model_id, epsilon=epsilon, case_id=case.case_id, replicate=replicate)
    state = case.state
    risk = RiskConfiguration(epsilon, policy.cvar_alpha)
    actions = []
    while state.remaining_rolls:
        if policy_id == "rate_agnostic_safety":
            ranked = rank_rate_agnostic_actions(
                state,
                rules,
                lambda banner: terminal.banner_objective(banner, risk).mean,
            )
            action = ranked[0].action
        else:
            tables = {banner.role: potential_provider(banner, risk) for banner in state.banners}
            action = (
                SynergyContinuationPolicy(
                    rules,
                    terminal,
                    tables,
                    risk,
                    include_synergy=False,
                )
                .bind_model(model_id)
                .decide(state)
            )
        actions.append(_action_identity(action))
        state = _transition(
            state,
            action,
            rules=rules,
            model_id=model_id,
            seed=policy.seed,
            key=key,
            step=40 - state.remaining_rolls,
        )
    score, teams = _score_terminal(
        state,
        terminal=terminal,
        risk=risk,
        seed=policy.seed,
        key=key,
    )
    return SolverSessionResult(
        key=key,
        policy_id=policy_id,
        score=score,
        selected_team_ids=teams,
        unresolved_decisions=0,
        full_horizon_equivalent_paths=0.0,
        situations=tuple(situations),
        action_sequence=tuple(actions),
    )


def _paired_bootstrap(
    preferred: Sequence[float],
    comparator: Sequence[float],
    *,
    alpha: float,
    confidence_level: float,
    replicates: int,
    seed: int,
) -> dict[str, float]:
    left = np.asarray(preferred, dtype=float)
    right = np.asarray(comparator, dtype=float)
    if left.shape != right.shape or not len(left):
        raise ValueError("paired P5 comparison requires aligned non-empty sessions")
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(left), size=(replicates, len(left)))
    left_samples = left[indexes]
    right_samples = right[indexes]
    mean_differences = left_samples.mean(axis=1) - right_samples.mean(axis=1)
    cvar_differences = np.asarray(
        [
            lower_tail_cvar(left_sample, alpha) - lower_tail_cvar(right_sample, alpha)
            for left_sample, right_sample in zip(left_samples, right_samples, strict=True)
        ]
    )
    quantile = 1.0 - confidence_level
    return {
        "mean_difference": float(left.mean() - right.mean()),
        "mean_lower_one_sided": float(np.quantile(mean_differences, quantile)),
        "cvar_difference": float(lower_tail_cvar(left, alpha) - lower_tail_cvar(right, alpha)),
        "cvar_lower_one_sided": float(np.quantile(cvar_differences, quantile)),
    }


def summarize_solver_validation(
    sessions: Sequence[SolverSessionResult],
    *,
    policy: BranchCappedSolverPolicy,
    expected_solver_session_count: int,
    runtime_seconds: float,
    oracle: Mapping[str, Any],
) -> dict[str, Any]:
    by_policy: dict[str, list[SolverSessionResult]] = defaultdict(list)
    for session in sessions:
        by_policy[session.policy_id].append(session)
    solver_sessions = by_policy["branch_capped"]
    score_summaries = []
    for policy_id, rows in sorted(by_policy.items()):
        grouped: dict[tuple[str, float], list[float]] = defaultdict(list)
        for row in rows:
            grouped[(row.key.model_id, row.key.epsilon)].append(row.score)
        for (model_id, epsilon), scores in sorted(grouped.items()):
            score_summaries.append(
                {
                    "policy_id": policy_id,
                    "model_id": model_id,
                    "epsilon": epsilon,
                    "session_count": len(scores),
                    **distribution_summary(np.asarray(scores), cvar_alpha=policy.cvar_alpha),
                }
            )

    comparisons = []
    comparison_pass = True
    solver_map = {row.key: row for row in solver_sessions}
    for baseline_id in ("one_step_greedy", "rate_agnostic_safety"):
        baseline_map = {row.key: row for row in by_policy[baseline_id]}
        shared = sorted(set(solver_map) & set(baseline_map))
        if not shared:
            comparison_pass = False
            comparisons.append({"baseline_id": baseline_id, "status": "missing"})
            continue
        result = _paired_bootstrap(
            [solver_map[key].score for key in shared],
            [baseline_map[key].score for key in shared],
            alpha=policy.cvar_alpha,
            confidence_level=policy.decision_budget.confidence_level,
            replicates=policy.decision_budget.bootstrap_replicates,
            seed=_seed(policy.seed, "baseline", baseline_id),
        )
        passed = result["mean_lower_one_sided"] >= 0.0 and result["cvar_lower_one_sided"] >= 0.0
        comparison_pass &= passed
        comparisons.append(
            {
                "baseline_id": baseline_id,
                "status": "pass" if passed else "fail",
                "paired_session_count": len(shared),
                **result,
            }
        )

    situation_counts: dict[str, int] = defaultdict(int)
    unresolved_counts: dict[str, int] = defaultdict(int)
    for session in solver_sessions:
        for situation in session.situations:
            situation_counts[situation] += 1
            unresolved_counts[situation] += int(session.unresolved_decisions > 0)
    unresolved_rows = [
        {
            "situation": situation,
            "session_count": count,
            "unresolved_session_count": unresolved_counts[situation],
            "unresolved_session_fraction": unresolved_counts[situation] / count,
        }
        for situation, count in sorted(situation_counts.items())
    ]
    maximum_unresolved = max(
        (row["unresolved_session_fraction"] for row in unresolved_rows),
        default=1.0,
    )
    complete = len(solver_sessions) == expected_solver_session_count
    path_count = sum(row.full_horizon_equivalent_paths for row in solver_sessions)
    oracle_pass = bool(oracle.get("gate_pass", False))
    gate = {
        "validation_complete": complete,
        "oracle_regret_pass": oracle_pass,
        "baseline_noninferiority_pass": comparison_pass and complete,
        "common_unresolved_pass": (
            complete
            and bool(unresolved_rows)
            and maximum_unresolved <= policy.validation.common_unresolved_upper_bound
        ),
        "runtime_pass": complete and runtime_seconds <= policy.runtime_target_seconds,
        "path_ceiling_pass": (complete and path_count <= policy.full_horizon_equivalent_path_ceiling),
    }
    gate["p5_status"] = "passed" if all(gate.values()) else "failed-escalation-review-required"
    payload = {
        "artifact_type": "group_branch_capped_solver_validation",
        "schema_version": 1,
        "approximate_not_globally_optimal": True,
        "solver_policy": policy.model_dump(mode="json"),
        "solver_policy_sha256": policy.semantic_hash,
        "expected_solver_session_count": expected_solver_session_count,
        "completed_solver_session_count": len(solver_sessions),
        "full_horizon_equivalent_paths": path_count,
        "score_summaries": score_summaries,
        "baseline_comparisons": comparisons,
        "common_situation_unresolved": unresolved_rows,
        "maximum_common_unresolved_fraction": maximum_unresolved,
        "oracle": dict(oracle),
        "gate": gate,
    }
    payload["validation_sha256"] = sha256_json(payload)
    return payload


def run_full_session_validation(
    solver: BranchCappedRollSolver,
    cases: Sequence[SolverCoverageCase],
    common_situations: Mapping[str, Sequence[str]],
    potential_provider: ExactPotentialProvider,
    *,
    started_at: float | None = None,
    progress=print,
) -> tuple[tuple[SolverSessionResult, ...], dict[str, Any]]:
    started = perf_counter() if started_at is None else started_at
    sessions: list[SolverSessionResult] = []
    planned = [
        (model_id, epsilon, case, replicate)
        for model_id in solver.policy.transition_models
        for epsilon in solver.policy.mean_retention_epsilons
        for case in cases
        for replicate in range(solver.policy.validation.full_session_replicates_per_stratum)
    ]
    completed_durations: list[float] = []
    stop_reason = None
    for index, (model_id, epsilon, case, replicate) in enumerate(planned):
        elapsed = perf_counter() - started
        estimated_next = float(np.median(completed_durations[-5:])) if completed_durations else 0.0
        if elapsed + estimated_next >= solver.policy.runtime_target_seconds:
            stop_reason = "projected next solver session would exceed the frozen 60-minute target"
            break
        session_started = perf_counter()
        progress(
            f"P5 solver session {index + 1}/{len(planned)} "
            f"{model_id} epsilon={epsilon:.2f} {case.case_id} replicate={replicate}"
        )
        solver_result = simulate_solver_session(
            solver,
            case,
            model_id=model_id,
            epsilon=epsilon,
            replicate=replicate,
            situations=common_situations.get(case.case_id, ()),
        )
        sessions.append(solver_result)
        for baseline_id in ("one_step_greedy", "rate_agnostic_safety"):
            sessions.append(
                simulate_baseline_session(
                    baseline_id,
                    case,
                    rules=solver.rules,
                    terminal=solver.terminal,
                    potential_provider=potential_provider,
                    policy=solver.policy,
                    model_id=model_id,
                    epsilon=epsilon,
                    replicate=replicate,
                    situations=common_situations.get(case.case_id, ()),
                )
            )
        completed_durations.append(perf_counter() - session_started)
    audit = {
        "planned_solver_sessions": len(planned),
        "completed_solver_sessions": sum(row.policy_id == "branch_capped" for row in sessions),
        "stop_reason": stop_reason,
        "median_completed_triplet_seconds": (
            float(np.median(completed_durations)) if completed_durations else None
        ),
    }
    return tuple(sessions), audit
