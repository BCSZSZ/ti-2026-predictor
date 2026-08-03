from __future__ import annotations

import json
from typing import Any

import pandas as pd

from ti_predictor.config import (
    load_rules,
    load_tournament_manifest,
    manifest_hash,
    rules_hash,
    team_strength_policy_path,
)
from ti_predictor.hashing import sha256_file
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import latest_rule_snapshot, validate_rules
from ti_predictor.runs import source_version
from ti_predictor.schemas import AuditIssue, ForecastRun, RuleSnapshot
from ti_predictor.storage import DataStore, read_parquet_if_exists


def _status(issues: list[AuditIssue]) -> str:
    if any(item.severity == "blocking" for item in issues):
        return "blocked"
    if any(item.severity == "warning" for item in issues):
        return "warning"
    return "publishable"


def audit_run(run_id: str, paths: ProjectPaths = PATHS, *, write: bool = True) -> dict[str, Any]:
    folder = paths.artifacts / run_id
    run_path = folder / "run.json"
    if not run_path.exists():
        raise FileNotFoundError(f"run does not exist: {run_id}")
    run = ForecastRun.model_validate_json(run_path.read_text(encoding="utf-8"))
    issues = validate_rules(load_rules(paths.rules))

    comparisons = {
        "rule_sha256": (run.rule_sha256, rules_hash(paths.rules), "blocking"),
        "config_sha256": (run.config_sha256, manifest_hash(paths.tournament), "blocking"),
        "data_sha256": (run.data_sha256, DataStore(paths).data_hash(), "warning"),
        "source_version": (run.git_commit, source_version(paths), "blocking"),
    }
    for name, (recorded, current, severity) in comparisons.items():
        if recorded != current:
            issues.append(
                AuditIssue(
                    code=f"run-{name}-changed",
                    severity=severity,
                    message=f"Current {name} differs from the run manifest",
                    context={"recorded": recorded, "current": current},
                )
            )

    model_parameters = run.model.get("parameters", {})
    strength_parameters = model_parameters.get("team_strength", model_parameters)
    recorded_policy_sha256 = strength_parameters.get("policy_sha256")
    if run.model.get("name", "").startswith("patch_tier_time_weighted"):
        if not recorded_policy_sha256:
            issues.append(
                AuditIssue(
                    code="run-model-policy-missing",
                    severity="blocking",
                    message="Weighted model run does not record its policy SHA-256",
                )
            )
        else:
            manifest = load_tournament_manifest(paths.tournament)
            current_policy_sha256 = sha256_file(team_strength_policy_path(manifest, config_root=paths.config))
            if recorded_policy_sha256 != current_policy_sha256:
                issues.append(
                    AuditIssue(
                        code="run-model-policy-changed",
                        severity="blocking",
                        message="Current team-strength policy differs from the run manifest",
                        context={
                            "recorded": recorded_policy_sha256,
                            "current": current_policy_sha256,
                        },
                    )
                )

    if run.rule_snapshot_id is None or run.rule_snapshot_sha256 is None:
        issues.append(
            AuditIssue(
                code="run-rule-snapshot-missing",
                severity="blocking",
                message="Run manifest does not record a Dota client rule snapshot",
            )
        )
    else:
        recorded_path = paths.raw / "rules" / run.rule_snapshot_id / "rule_snapshot.json"
        if not recorded_path.is_file():
            issues.append(
                AuditIssue(
                    code="recorded-rule-snapshot-missing",
                    severity="blocking",
                    message="The exact client rule snapshot recorded by the run is missing",
                )
            )
        else:
            recorded = RuleSnapshot.model_validate_json(recorded_path.read_text(encoding="utf-8"))
            if recorded.snapshot_sha256 != run.rule_snapshot_sha256:
                issues.append(
                    AuditIssue(
                        code="recorded-rule-snapshot-hash",
                        severity="blocking",
                        message="Recorded client rule snapshot hash does not match the run",
                    )
                )
            if recorded.status == "blocked":
                issues.append(
                    AuditIssue(
                        code="recorded-rule-snapshot-blocked",
                        severity="blocking",
                        message="The client rule snapshot used by the run is blocked",
                    )
                )
        latest = latest_rule_snapshot(paths)
        if latest is not None and latest[0].snapshot_id != run.rule_snapshot_id:
            issues.append(
                AuditIssue(
                    code="rule-snapshot-superseded",
                    severity="warning",
                    message="A newer client rule snapshot exists; regenerate before final submission",
                    context={
                        "recorded_id": run.rule_snapshot_id,
                        "latest_id": latest[0].snapshot_id,
                    },
                )
            )

    if run.status == "blocked":
        issues.append(
            AuditIssue(
                code="run-status-blocked",
                severity="blocking",
                message="Run manifest is explicitly blocked",
            )
        )
    model_path = folder / "model.json"
    if model_path.is_file():
        model_payload = json.loads(model_path.read_text(encoding="utf-8"))
        for payload in model_payload.get("report", {}).get("issues", []):
            issue = AuditIssue.model_validate(payload)
            if not any(
                existing.code == issue.code and existing.message == issue.message for existing in issues
            ):
                issues.append(issue)
    backtest_path = folder / "backtest.json"
    if backtest_path.is_file():
        backtest_payload = json.loads(backtest_path.read_text(encoding="utf-8"))
        for payload in backtest_payload.get("issues", []):
            issue = AuditIssue.model_validate(payload)
            if not any(
                existing.code == issue.code and existing.message == issue.message for existing in issues
            ):
                issues.append(issue)
    existing_messages = {issue.message for issue in issues}
    for warning in run.warnings:
        if warning not in existing_messages:
            issues.append(
                AuditIssue(
                    code="run-warning",
                    severity="warning",
                    message=warning,
                )
            )

    output_hashes: dict[str, str] = {}
    for relative in run.outputs:
        output = folder / relative
        if not output.is_file():
            issues.append(
                AuditIssue(
                    code="run-output-missing",
                    severity="blocking",
                    message=f"Recorded output is missing: {relative}",
                )
            )
        else:
            output_hashes[relative] = sha256_file(output)

    cutoff = pd.Timestamp(run.as_of)
    for name in ("matches.parquet", "fantasy_performance_samples.parquet"):
        frame = read_parquet_if_exists(paths.processed / name)
        if frame.empty or "start_time" not in frame:
            continue
        future = pd.to_datetime(frame["start_time"], utc=True) > cutoff
        if future.any():
            issues.append(
                AuditIssue(
                    code="as-of-future-data",
                    severity="blocking",
                    message=f"{name} contains {int(future.sum())} rows after run as_of",
                )
            )
        if (
            "source_sha256" in frame
            and (frame["source_sha256"].isna() | (frame["source_sha256"].str.len() != 64)).any()
        ):
            issues.append(
                AuditIssue(
                    code="source-hash-invalid",
                    severity="blocking",
                    message=f"{name} contains rows without a valid source content hash",
                )
            )

    recommendation_path = folder / "recommendations.json"
    if recommendation_path.exists():
        recommendations = json.loads(recommendation_path.read_text(encoding="utf-8"))
        if any(item.get("status") == "blocked" for item in recommendations):
            issues.append(
                AuditIssue(
                    code="recommendation-blocked",
                    severity="blocking",
                    message="At least one recommendation is explicitly marked blocked",
                )
            )
    report = {
        "run_id": run_id,
        "status": _status(issues),
        "publishable": not any(item.severity == "blocking" for item in issues),
        "run_status": run.status,
        "as_of": run.as_of.isoformat().replace("+00:00", "Z"),
        "output_sha256": output_hashes,
        "issues": [item.model_dump(mode="json") for item in issues],
    }
    if write:
        output = folder / "audit.json"
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report
