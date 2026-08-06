"""Reproducible P4 evidence entry point for frozen Group Roll playbooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from ti_predictor.config import (
    load_rules,
    load_team_strength_policy,
    load_tournament_manifest,
)
from ti_predictor.fantasy.playbook import build_stat_priorities, load_playbook
from ti_predictor.fantasy.playbook_validation import (
    load_playbook_validation_policy,
    validate_frozen_playbooks,
)
from ti_predictor.fantasy.roll import build_group_roll_rules
from ti_predictor.fantasy.scenarios import (
    build_common_scenario_set,
    build_series_block_pools,
    load_group_scenario_policy,
)
from ti_predictor.fantasy.valuation import (
    build_stat_forecast_package,
    cluster_bootstrap_stat_intervals,
)
from ti_predictor.forecasting import (
    _available_by_as_of,
    _load_strength_model,
    generate_group_fantasy_evidence,
)
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import latest_rule_snapshot, rule_snapshot_issues
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import ForecastRun, as_utc
from ti_predictor.storage import read_parquet_if_exists
from ti_predictor.tournament.group import GroupSimulator


@dataclass
class PlaybookEvidenceResult:
    run: ForecastRun
    run_path: Path
    evidence_path: Path
    evidence: dict[str, Any]
    runtime_seconds: dict[str, float]


def generate_group_playbook_evidence(
    *,
    as_of,
    paths: ProjectPaths = PATHS,
    progress=print,
) -> PlaybookEvidenceResult:
    """Build P4 from the frozen manual candidates and the exact P3 arithmetic context."""

    started = perf_counter()
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    validation_path = paths.config / "models" / "fantasy-group-playbook-validation-v1.json"
    rate_path = paths.config / "playbooks" / "group-rate-agnostic-v1.json"
    primary_path = paths.config / "playbooks" / "group-primary-model-v1.json"
    validation = load_playbook_validation_policy(validation_path)
    definitions = (load_playbook(rate_path), load_playbook(primary_path))
    if validation.as_of != cutoff.isoformat().replace("+00:00", "Z"):
        raise ValueError("P4 validation as_of differs from the explicit command cutoff")
    if any(definition.as_of != validation.as_of for definition in definitions):
        raise ValueError("frozen playbook as_of differs from the validation policy")

    progress("P4 verifying the complete P3 source evidence identity")
    p3_result = generate_group_fantasy_evidence(
        as_of=cutoff,
        seed=20260813,
        include_bootstrap=True,
        paths=paths,
    )
    p3_hash = str(p3_result.evidence["evidence_package_sha256"])
    if any(definition.source_evidence_sha256 != p3_hash for definition in definitions):
        raise ValueError("frozen playbook source hash no longer matches the reproduced P3 evidence")
    p3_verified = perf_counter()

    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    scenario_policy_path = paths.config / "models" / "fantasy-group-scenarios-v1.json"
    scenario_policy = load_group_scenario_policy(scenario_policy_path)
    matches_path = paths.processed / "matches.parquet"
    observations_path = paths.processed / "fantasy_performance_samples.parquet"
    patches_path = paths.processed / "patches.parquet"
    for required_path in (matches_path, observations_path, patches_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"P4 requires the processed snapshot file: {required_path}")
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
        raise ValueError("P4 Fantasy evidence is blocked: " + "; ".join(x.message for x in blocking))
    data_snapshot_sha256 = sha256_json(
        {
            "as_of": cutoff.isoformat().replace("+00:00", "Z"),
            "matches_sha256": sha256_file(matches_path),
            "observations_sha256": sha256_file(observations_path),
            "patches_sha256": sha256_file(patches_path),
            "rules_sha256": sha256_file(paths.rules),
            "manifest_sha256": sha256_file(paths.tournament),
            "scenario_policy_sha256": sha256_file(scenario_policy_path),
            "selected_match_ids_sha256": evidence.audit["selected_match_ids_sha256"],
            "target_patch_family": evidence.target_patch_family,
        }
    )
    pool_result = build_series_block_pools(
        observations,
        matches,
        evidence.matches,
        manifest,
        rules,
        scenario_policy,
        as_of=cutoff,
    )
    group_simulation = GroupSimulator(model, manifest).simulate(
        samples=scenario_policy.scenario_count,
        seed=20260813,
        scenario=scenario_policy.group_outcome_model,
    )
    scenario_set = build_common_scenario_set(
        pool_result,
        group_team_ids=group_simulation.team_ids,
        group_outcomes=group_simulation.outcomes,
        policy=scenario_policy,
        data_snapshot_sha256=data_snapshot_sha256,
        as_of=cutoff,
        seed=20260813,
    )
    stat_forecasts = build_stat_forecast_package(
        pool_result,
        scenario_set,
        rules,
        cvar_alpha=scenario_policy.risk.cvar_alpha,
    )
    bootstrap = cluster_bootstrap_stat_intervals(
        pool_result,
        scenario_set,
        stat_forecasts,
        rules,
        scenario_policy,
        seed=20260813 + 300_007,
    )
    priorities = build_stat_priorities(stat_forecasts, bootstrap)

    snapshot_result = latest_rule_snapshot(paths)
    if snapshot_result is None:
        raise ValueError("P4 requires the frozen Dota client Rule snapshot")
    snapshot, snapshot_path = snapshot_result
    snapshot_issues = rule_snapshot_issues(cutoff, paths)
    blocking_snapshot = [issue for issue in snapshot_issues if issue.severity == "blocking"]
    if blocking_snapshot:
        raise ValueError("P4 Rule snapshot is blocked: " + "; ".join(x.message for x in blocking_snapshot))
    client_roll = snapshot.observed.get("fantasy_roll")
    if not isinstance(client_roll, dict):
        raise ValueError("P4 Rule snapshot does not contain normalized Fantasy Roll operations")
    roll_rules = build_group_roll_rules(rules, client_roll)
    context_finished = perf_counter()

    progress("P4 starting frozen 40-Roll standalone validation")
    payload = validate_frozen_playbooks(
        definitions,
        roll_rules,
        rules,
        priorities,
        pool_result,
        scenario_set,
        validation,
        progress=progress,
    )
    validation_finished = perf_counter()
    runtime = {
        "p3_source_reproduction": p3_verified - started,
        "analysis_context_rebuild": context_finished - p3_verified,
        "standalone_validation": validation_finished - context_finished,
        "total": validation_finished - started,
    }
    runtime_gate = {
        "target_seconds": validation.runtime_target_seconds,
        "hard_ceiling_seconds": validation.runtime_hard_ceiling_seconds,
        "target_met": runtime["total"] <= validation.runtime_target_seconds,
        "hard_ceiling_met": runtime["total"] <= validation.runtime_hard_ceiling_seconds,
    }
    payload.update(
        {
            "p3_evidence_sha256": p3_hash,
            "data_snapshot_sha256": data_snapshot_sha256,
            "pool_set_sha256": pool_result.semantic_hash,
            "rule_snapshot_id": snapshot.snapshot_id,
            "rule_snapshot_sha256": snapshot.snapshot_sha256,
            "rule_snapshot_path": str(snapshot_path.relative_to(paths.root)).replace("\\", "/"),
        }
    )
    payload.pop("evidence_sha256", None)
    payload["evidence_sha256"] = sha256_json(payload)

    warnings = sorted(
        {
            *(issue.message for issue in evidence.issues if issue.severity == "warning"),
            *(issue.message for issue in model_report.issues if issue.severity == "warning"),
            *(issue.message for issue in snapshot_issues if issue.severity == "warning"),
            *(
                f"{edition} playbook remains {result['p4_status']} after standalone validation"
                for edition, result in payload["gate"].items()
                if result["p4_status"] not in {"baseline-reliable", "strict-reliable"}
            ),
        }
    )
    status = (
        "blocked"
        if not runtime_gate["hard_ceiling_met"]
        else "warning"
        if warnings or any(result["p4_status"] == "draft" for result in payload["gate"].values())
        else "publishable"
    )
    parameters = {
        "phase": "p4_independent_human_playbooks",
        "validation_policy_id": validation.policy_id,
        "validation_policy_sha256": validation.semantic_hash,
        "playbook_sha256": {definition.edition: definition.semantic_hash for definition in definitions},
        "p3_evidence_sha256": p3_hash,
        "scenario_subset_count": validation.scenario_subset_count,
        "session_replicates_per_stratum": validation.full_session_replicates_per_stratum,
    }
    run_id, hashes = make_run_id(
        kind="fantasy",
        as_of=cutoff,
        seed=validation.seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
    evidence_path = writer.write_json("group-playbook-evidence.json", payload)
    run = ForecastRun(
        run_id=run_id,
        kind="fantasy",
        as_of=cutoff,
        created_at=cutoff,
        status=status,
        seed=validation.seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=None if hashes["rule_snapshot_id"] == "missing" else hashes["rule_snapshot_id"],
        rule_snapshot_sha256=None if hashes["rule_snapshot"] == "missing" else hashes["rule_snapshot"],
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={"name": "frozen_group_human_playbooks_v1", "parameters": parameters},
        profiles=[],
        outputs=[evidence_path.name],
        warnings=warnings,
    )
    run_path = writer.write_run(run)
    return PlaybookEvidenceResult(
        run=run,
        run_path=run_path,
        evidence_path=evidence_path,
        evidence=payload,
        runtime_seconds=runtime,
    )
