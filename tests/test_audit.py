from __future__ import annotations

from datetime import UTC, datetime

from ti_predictor.audit import audit_run
from ti_predictor.config import manifest_hash, rules_hash
from ti_predictor.runs import source_version
from ti_predictor.schemas import ForecastRun, RuleSnapshot
from ti_predictor.storage import DataStore


def _write_snapshot(
    project_paths,
    *,
    snapshot_id: str,
    created_at: str,
    snapshot_sha256: str,
) -> None:
    snapshot = RuleSnapshot(
        snapshot_id=snapshot_id,
        event_id="international_2026",
        as_of=created_at,
        created_at=created_at,
        source="dota_client",
        source_files=[],
        canonical_rules_sha256=rules_hash(project_paths.rules),
        snapshot_sha256=snapshot_sha256,
        status="publishable",
        observed={},
    )
    path = project_paths.raw / "rules" / snapshot_id / "rule_snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")


def test_audit_ignores_rule_snapshot_captured_after_run_as_of(project_paths) -> None:
    recorded_id = "20260810T134439Z-aaaaaaaaaaaa"
    recorded_sha256 = "a" * 64
    _write_snapshot(
        project_paths,
        snapshot_id=recorded_id,
        created_at="2026-08-10T13:44:39Z",
        snapshot_sha256=recorded_sha256,
    )
    _write_snapshot(
        project_paths,
        snapshot_id="20260811T025356Z-bbbbbbbbbbbb",
        created_at="2026-08-11T02:53:56Z",
        snapshot_sha256="b" * 64,
    )

    run = ForecastRun(
        run_id="group-historical-rule-snapshot",
        kind="group",
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        created_at=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        status="publishable",
        seed=20260813,
        rule_sha256=rules_hash(project_paths.rules),
        rule_snapshot_id=recorded_id,
        rule_snapshot_sha256=recorded_sha256,
        data_sha256=DataStore(project_paths).data_hash(),
        config_sha256=manifest_hash(project_paths.tournament),
        git_commit=source_version(project_paths),
    )
    folder = project_paths.artifacts / run.run_id
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")

    report = audit_run(run.run_id, project_paths, write=False)

    assert not [issue for issue in report["issues"] if issue["code"] == "rule-snapshot-superseded"]
