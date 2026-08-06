"""Reproducible P6 entry point for the read-only Human Roll playbook audit."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import numpy as np

from ti_predictor.fantasy.cross_audit import (
    CrossAuditPolicyV2,
    audit_one_condition,
    build_held_out_scenarios,
    common_activation_frequencies,
    load_cross_audit_policy,
    release_labels,
)
from ti_predictor.fantasy.playbook import (
    PlaybookPolicy,
    build_stat_priorities,
    load_playbook,
)
from ti_predictor.fantasy.solver import (
    BranchCappedRollSolver,
    ExactFixedStatConfigurationEvaluator,
    ExactPotentialProvider,
    TerminalGroupEvaluator,
)
from ti_predictor.fantasy.solver_reporting import prepare_solver_context
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import ForecastRun, as_utc


@dataclass
class CrossAuditEvidenceResult:
    run: ForecastRun
    run_path: Path
    evidence_path: Path
    evidence: dict[str, Any]
    runtime_seconds: dict[str, float]


def _find_semantic_artifact(
    paths: ProjectPaths,
    *,
    filename: str,
    hash_field: str,
    expected_sha256: str,
    expected_relative_path: str | None = None,
) -> tuple[dict[str, Any], Path]:
    if expected_relative_path is not None:
        relative_path = Path(expected_relative_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("frozen artifact path must be relative and cannot traverse parents")
        path = paths.root / relative_path
        try:
            path.resolve().relative_to(paths.artifacts.resolve())
        except ValueError as exc:
            raise ValueError("frozen artifact path must stay under artifacts") from exc
        if path.name != filename:
            raise ValueError(f"frozen artifact path must end with {filename}")
        if not path.is_file():
            raise FileNotFoundError(f"frozen artifact is missing: {expected_relative_path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"frozen artifact is unreadable: {expected_relative_path}") from exc
        if payload.get(hash_field) != expected_sha256:
            raise ValueError(f"frozen artifact {hash_field} drifted: {expected_relative_path}")
        return payload, path

    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(paths.artifacts.glob(f"fantasy-*/{filename}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get(hash_field) == expected_sha256:
            matches.append((payload, path))
    if not matches:
        raise FileNotFoundError(f"P6 requires {filename} with {hash_field}={expected_sha256}")
    reference = sha256_json(matches[0][0])
    if any(sha256_json(payload) != reference for payload, _ in matches[1:]):
        raise ValueError(f"multiple {filename} artifacts claim one semantic hash but differ")
    return matches[-1]


def _source_manifest(
    paths: ProjectPaths,
    *,
    cross_audit_version: Literal["v1", "v2"],
    solver_policy_path: Path,
    cross_audit_policy_path: Path,
    p3_path: Path,
    p4_path: Path,
    p5_path: Path,
) -> list[dict[str, str]]:
    playbook_suffix = cross_audit_version
    files = [
        paths.config / "rules" / "ti2026.json",
        paths.config / "models" / "fantasy-group-scenarios-v1.json",
        paths.config / "models" / f"fantasy-group-playbook-validation-{playbook_suffix}.json",
        solver_policy_path,
        cross_audit_policy_path,
        paths.config / "playbooks" / f"group-rate-agnostic-{playbook_suffix}.json",
        paths.config / "playbooks" / f"group-primary-model-{playbook_suffix}.json",
        paths.root / "docs" / "playbooks" / "group-roll" / f"playbook-rate-agnostic-{playbook_suffix}.md",
        paths.root / "docs" / "playbooks" / "group-roll" / f"playbook-primary-model-{playbook_suffix}.md",
        paths.root
        / "docs"
        / "playbooks"
        / "group-roll"
        / f"stat-quality-trait-evidence-{playbook_suffix}.md",
        p3_path,
        p4_path,
        p5_path,
    ]
    if cross_audit_version == "v2":
        files.insert(
            10,
            paths.root / "docs" / "playbooks" / "group-roll" / "candidate-freeze-v2.json",
        )
    result = []
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"P6 evidence-package source is missing: {path}")
        result.append(
            {
                "path": str(path.relative_to(paths.root)).replace("\\", "/"),
                "sha256": sha256_file(path),
            }
        )
    return result


def _row_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({(row["edition"], row["model_id"]) for row in rows})
    result = []
    for edition, model_id in keys:
        selected = [row for row in rows if row["edition"] == edition and row["model_id"] == model_id]
        common = [row for row in selected if row["p4_common_activation"]]
        result.append(
            {
                "edition": edition,
                "model_id": model_id,
                "row_count": len(selected),
                "common_row_count": len(common),
                "solver_disagreement_count": sum(row["manual_solver_disagreement"] for row in selected),
                "oracle_disagreement_count": sum(row["manual_oracle_disagreement"] for row in selected),
                "solver_unresolved_count": sum(not row["solver_resolved"] for row in selected),
                "baseline_material_exception_count": sum(
                    row["baseline_material_exception"] for row in selected
                ),
                "strict_material_exception_count": sum(row["strict_material_exception"] for row in selected),
                "maximum_mean_loss_fraction": max(
                    (float(row["mean_loss_fraction"]) for row in selected),
                    default=0.0,
                ),
                "maximum_cvar10_loss_fraction": max(
                    (float(row["cvar10_loss_fraction"]) for row in selected),
                    default=0.0,
                ),
                "maximum_common_mean_loss_upper95_fraction": max(
                    (
                        float(row["mean_loss_upper95_fraction"])
                        for row in common
                        if row["mean_loss_upper95_fraction"] is not None
                    ),
                    default=None,
                ),
                "maximum_common_cvar10_loss_upper95_fraction": max(
                    (
                        float(row["cvar10_loss_upper95_fraction"])
                        for row in common
                        if row["cvar10_loss_upper95_fraction"] is not None
                    ),
                    default=None,
                ),
            }
        )
    return result


def generate_group_cross_audit_evidence(
    *,
    as_of,
    cross_audit_version: Literal["v1", "v2"] = "v1",
    paths: ProjectPaths = PATHS,
    progress=print,
) -> CrossAuditEvidenceResult:
    """Run the preregistered P6 audit without mutating either frozen playbook."""

    started = perf_counter()
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    if cross_audit_version not in {"v1", "v2"}:
        raise ValueError(f"unsupported Group cross-audit version: {cross_audit_version}")
    policy_path = paths.config / "models" / f"fantasy-group-read-only-cross-audit-{cross_audit_version}.json"
    solver_policy_path = (
        paths.config / "models" / "fantasy-group-branch-capped-solver-v1.json"
        if cross_audit_version == "v1"
        else paths.config / "models" / "fantasy-group-branch-capped-solver-audit-v2.json"
    )
    policy = load_cross_audit_policy(policy_path)
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    if cutoff_text != policy.as_of:
        raise ValueError("P6 policy as_of differs from the explicit command cutoff")

    progress("P6 verifying frozen P3/P4/P5 identities")
    context = prepare_solver_context(
        as_of=cutoff,
        solver_policy_path=solver_policy_path,
        playbook_evidence_path=(
            paths.root / policy.source_playbook_artifact if isinstance(policy, CrossAuditPolicyV2) else None
        ),
        paths=paths,
    )
    if context.policy.semantic_hash != policy.source_solver_policy_sha256:
        raise ValueError("P6 source solver policy hash drifted")
    if context.p4_evidence.get("evidence_sha256") != policy.source_playbook_evidence_sha256:
        raise ValueError("P6 source P4 evidence hash drifted")
    if context.p4_evidence.get("validation_policy_sha256") != policy.source_playbook_validation_policy_sha256:
        raise ValueError("P6 source P4 validation policy hash drifted")
    p5_evidence, p5_path = _find_semantic_artifact(
        paths,
        filename="group-solver-evidence.json",
        hash_field="evidence_sha256",
        expected_sha256=policy.source_solver_evidence_sha256,
        expected_relative_path=(
            policy.source_solver_artifact if isinstance(policy, CrossAuditPolicyV2) else None
        ),
    )
    source_solver_evidence_policy_sha256 = (
        policy.source_solver_evidence_policy_sha256
        if isinstance(policy, CrossAuditPolicyV2)
        else policy.source_solver_policy_sha256
    )
    if p5_evidence.get("solver_policy_sha256") != source_solver_evidence_policy_sha256:
        raise ValueError("P6 source P5 artifact uses another solver policy")
    if (
        not isinstance(policy, CrossAuditPolicyV2)
        and p5_evidence.get("source_playbook_evidence_sha256") != policy.source_playbook_evidence_sha256
    ):
        raise ValueError("P6 source P5 artifact uses another playbook evidence package")
    if p5_evidence.get("gate", {}).get("p5_status") != "failed-escalation-review-required":
        raise ValueError("P6 preregistration expects the recorded P5 failed escalation review")

    definitions = {
        "rate-agnostic": load_playbook(
            paths.config / "playbooks" / f"group-rate-agnostic-{cross_audit_version}.json"
        ),
        "primary-model": load_playbook(
            paths.config / "playbooks" / f"group-primary-model-{cross_audit_version}.json"
        ),
    }
    for edition, definition in definitions.items():
        if definition.semantic_hash != policy.playbook_sha256[edition]:
            raise ValueError(f"P6 frozen {edition} playbook hash drifted")
        recorded = context.p4_evidence.get("playbooks", {}).get(edition, {}).get("semantic_sha256")
        if recorded != definition.semantic_hash:
            raise ValueError(f"P6 current {edition} playbook differs from P4 evidence")

    p3_hashes = {definition.source_evidence_sha256 for definition in definitions.values()}
    if len(p3_hashes) != 1:
        raise ValueError("P6 playbooks no longer share one P3 evidence source")
    p3_evidence, p3_path = _find_semantic_artifact(
        paths,
        filename="group-fantasy-evidence.json",
        hash_field="evidence_package_sha256",
        expected_sha256=p3_hashes.pop(),
    )
    if context.source_scenarios.semantic_hash != policy.source_scenario_sha256:
        raise ValueError("P6 reconstructed P3 source Scenario hash drifted")
    priorities = build_stat_priorities(
        p3_evidence["stat_forecasts"],
        p3_evidence["cluster_bootstrap"],
    )
    manuals = {
        edition: PlaybookPolicy(definition, context.roll_rules, context.canonical_rules, priorities)
        for edition, definition in definitions.items()
    }

    p4_validation = context.p4_evidence.get("validation_policy", {})
    validation_scenarios, scenario_audit = build_held_out_scenarios(
        context.source_scenarios,
        policy,
        p4_seed=int(p4_validation["seed"]),
        p4_count=int(p4_validation["scenario_subset_count"]),
        p5_seed=context.policy.seed,
        p5_count=context.policy.scenario_subset_count,
    )
    context_finished = perf_counter()

    terminal = TerminalGroupEvaluator(
        context.pool_result,
        validation_scenarios,
        context.canonical_rules,
    )
    fixed_evaluator = ExactFixedStatConfigurationEvaluator(
        context.pool_result,
        validation_scenarios,
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
    common = common_activation_frequencies(context.p4_evidence)
    rows: list[dict[str, Any]] = []
    durations: list[float] = []
    stop_reason = None
    planned = [
        (edition, model_id, case_index, case, horizon)
        for edition in policy.editions
        for model_id in edition.models
        for case_index, case in enumerate(context.coverage_cases)
        for horizon in policy.conditional_states.remaining_rolls
    ]
    for index, (edition, model_id, case_index, case, horizon) in enumerate(planned):
        elapsed = perf_counter() - started
        estimated = float(np.median(durations[-5:])) if durations else 0.0
        stop_new_computation_seconds = (
            policy.stop_new_computation_seconds
            if isinstance(policy, CrossAuditPolicyV2)
            else policy.runtime_target_seconds
        )
        if elapsed + estimated >= stop_new_computation_seconds:
            stop_reason = (
                "projected next P6 row would exceed the frozen 30-minute target"
                if not isinstance(policy, CrossAuditPolicyV2)
                else "projected next v2 cross-audit row would exceed the frozen 59-minute stop point"
            )
            break
        progress(
            f"P6 cross-audit {index + 1}/{len(planned)} {edition.edition} {model_id} "
            f"{case.case_id} horizon={horizon}"
        )
        row_started = perf_counter()
        state = replace(case.state, remaining_rolls=horizon)
        replacement_offers = tuple(
            context.coverage_cases[(case_index + offset + 1) % len(context.coverage_cases)].state.offer
            for offset in range(horizon)
        )
        preview = manuals[edition.edition].decide(
            state,
            candidate_rule_count=policy.published_rule_count,
            risk_preference=edition.risk_preference,
        )
        situation = preview.rule_id or "fallback"
        frequency = common.get((edition.edition, model_id, case.case_id, situation))
        rows.append(
            audit_one_condition(
                policy=policy,
                manual=manuals[edition.edition],
                solver=solver,
                state=state,
                replacement_offers=replacement_offers,
                edition=edition,
                model_id=model_id,
                case_id=case.case_id,
                horizon=horizon,
                common_frequency=frequency,
            )
        )
        durations.append(perf_counter() - row_started)
    audit_finished = perf_counter()

    complete = len(rows) == policy.expected_row_count
    scenario_disjoint = scenario_audit.p4_p6_overlap_count == 0 and scenario_audit.p5_p6_overlap_count == 0
    manual_hashes_unchanged = all(
        definitions[edition].semantic_hash == policy.playbook_sha256[edition] for edition in definitions
    )
    labels = release_labels(
        context.p4_evidence["gate"],
        rows,
        complete=complete and scenario_disjoint and manual_hashes_unchanged,
    )
    source_manifest = _source_manifest(
        paths,
        cross_audit_version=cross_audit_version,
        solver_policy_path=solver_policy_path,
        cross_audit_policy_path=policy_path,
        p3_path=p3_path,
        p4_path=context.p4_evidence_path,
        p5_path=p5_path,
    )
    gate = {
        "source_identity_pass": True,
        "held_out_scenario_disjoint_pass": scenario_disjoint,
        "audit_complete": complete,
        "manual_hashes_unchanged": manual_hashes_unchanged,
        "p6_status": "complete-draft" if complete and scenario_disjoint else "partial-draft",
        "release_labels": labels,
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "group_fantasy_playbook_read_only_cross_audit",
        "as_of": policy.as_of,
        "seed": policy.seed,
        "cross_audit_policy": policy.model_dump(mode="json"),
        "cross_audit_policy_sha256": policy.semantic_hash,
        "source_playbook_evidence_sha256": policy.source_playbook_evidence_sha256,
        "source_playbook_artifact": str(context.p4_evidence_path.relative_to(paths.root)).replace("\\", "/"),
        "source_solver_evidence_sha256": policy.source_solver_evidence_sha256,
        "source_solver_artifact": str(p5_path.relative_to(paths.root)).replace("\\", "/"),
        "source_solver_effectiveness_status": p5_evidence["gate"]["p5_status"],
        "source_scenario_sha256": context.source_scenarios.semantic_hash,
        "validation_scenario_sha256": validation_scenarios.semantic_hash,
        "held_out_scenario_audit": scenario_audit.as_payload(),
        "data_snapshot_sha256": context.data_snapshot_sha256,
        "pool_set_sha256": context.pool_result.semantic_hash,
        "rule_snapshot_id": context.rule_snapshot_id,
        "rule_snapshot_sha256": context.rule_snapshot_sha256,
        "planned_row_count": policy.expected_row_count,
        "completed_row_count": len(rows),
        "stop_reason": stop_reason,
        "rows": rows,
        "summary": _row_summary(rows),
        "gate": gate,
        "source_manifest": source_manifest,
        "source_manifest_sha256": sha256_json(source_manifest),
        "limitations": [
            "the exact comparison covers only one to three Rolls remaining",
            "future replacement offers are fixed to a declared cyclic schedule rather than integrated",
            "the independent weighted-outcome bootstrap is diagnostic and is not P4 "
            "Series-cluster confirmation",
            "the P5 source solver failed its effectiveness gate and solver disagreement alone "
            "cannot edit a manual",
            "both frozen P4 editions already remain draft and P6 cannot promote them",
        ],
    }
    if isinstance(policy, CrossAuditPolicyV2):
        payload.update(
            {
                "audit_solver_policy_sha256": policy.source_solver_policy_sha256,
                "historical_solver_evidence_policy_sha256": (policy.source_solver_evidence_policy_sha256),
                "source_solver_evidence_scope": policy.source_solver_evidence_scope,
                "p5_validation_index_source": {
                    "seed": context.policy.seed,
                    "count": context.policy.scenario_subset_count,
                    "historical_evidence_sha256": policy.source_solver_evidence_sha256,
                },
            }
        )
        payload["limitations"] = [
            "the exact comparison covers only one to three Rolls remaining",
            "future replacement offers are fixed to a declared cyclic schedule rather than integrated",
            "the independent weighted-outcome bootstrap is diagnostic and is not standalone "
            "Series-cluster confirmation",
            "the v2 audit reuses the bounded-solver algorithm but has no new full-session "
            "effectiveness validation; the recorded failed P5 status is historical v1 evidence only",
            "both frozen v2 standalone editions already remain draft and this audit cannot promote them",
        ]
    payload["evidence_sha256"] = sha256_json(payload)
    runtime = {
        "identity_and_context": context_finished - started,
        "read_only_cross_audit": audit_finished - context_finished,
        "total": audit_finished - started,
        "median_completed_row": float(np.median(durations)) if durations else 0.0,
    }
    warnings = sorted(
        {
            *context.warnings,
            "P5 source solver failed its frozen effectiveness gate",
            "P6 conditional exact audit does not integrate future offer randomness",
            *(f"{edition} playbook remains {item['p6_status']}" for edition, item in labels.items()),
            *([stop_reason] if stop_reason else []),
        }
    )
    parameters = {
        "phase": (
            "p6_read_only_playbook_cross_audit"
            if cross_audit_version == "v1"
            else "p4_v2_read_only_playbook_cross_audit"
        ),
        "cross_audit_policy_id": policy.policy_id,
        "cross_audit_policy_sha256": policy.semantic_hash,
        "source_playbook_evidence_sha256": policy.source_playbook_evidence_sha256,
        "source_solver_evidence_sha256": policy.source_solver_evidence_sha256,
        "validation_scenario_sha256": validation_scenarios.semantic_hash,
        "manual_revision_allowed": False,
    }
    run_id, hashes = make_run_id(
        kind="fantasy",
        as_of=cutoff,
        seed=policy.seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
    evidence_path = writer.write_json("group-playbook-cross-audit.json", payload)
    run = ForecastRun(
        run_id=run_id,
        kind="fantasy",
        as_of=cutoff,
        created_at=cutoff,
        status="warning",
        seed=policy.seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=context.rule_snapshot_id,
        rule_snapshot_sha256=context.rule_snapshot_sha256,
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={
            "name": f"read_only_group_playbook_cross_audit_{cross_audit_version}",
            "parameters": parameters,
        },
        profiles=[],
        outputs=[evidence_path.name],
        warnings=warnings,
    )
    run_path = writer.write_run(run)
    return CrossAuditEvidenceResult(
        run=run,
        run_path=run_path,
        evidence_path=evidence_path,
        evidence=payload,
        runtime_seconds=runtime,
    )
