from __future__ import annotations

import json
from pathlib import Path

from ti_predictor.fantasy.cross_audit import load_cross_audit_policy
from ti_predictor.fantasy.playbook import load_playbook
from ti_predictor.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PACKAGE = PROJECT_ROOT / "docs/playbooks/group-roll/evidence-package-v1.json"
EVIDENCE_PACKAGE_V2 = PROJECT_ROOT / "docs/playbooks/group-roll/evidence-package-v2.json"
CANDIDATE_FREEZE = PROJECT_ROOT / "docs/playbooks/group-roll/candidate-freeze-v2.json"


def _tracked_file_mismatches(package: dict) -> list[str]:
    entries = package["tracked_files"]
    relative_paths = [Path(entry["path"]) for entry in entries]

    assert len(relative_paths) == len(set(relative_paths))
    assert all(not path.is_absolute() and ".." not in path.parts for path in relative_paths)

    mismatches: list[str] = []
    for entry, relative_path in zip(entries, relative_paths, strict=True):
        target = PROJECT_ROOT / relative_path
        if not target.is_file():
            mismatches.append(f"{entry['path']}: missing")
            continue
        actual = sha256_file(target)
        if actual != entry["sha256"]:
            mismatches.append(f"{entry['path']}: expected {entry['sha256']}, got {actual}")
    return mismatches


def test_group_roll_evidence_package_keeps_release_boundaries() -> None:
    package = json.loads(EVIDENCE_PACKAGE.read_text(encoding="utf-8"))

    assert package["manual_route_independent_of_solver"] is True
    assert package["release_status"] == {
        "rate-agnostic": "draft",
        "primary-model": "draft",
    }


def test_group_roll_evidence_package_tracked_file_hashes_match() -> None:
    package = json.loads(EVIDENCE_PACKAGE.read_text(encoding="utf-8"))
    mismatches = _tracked_file_mismatches(package)
    assert not mismatches, "Evidence package drift:\n" + "\n".join(mismatches)


def test_group_roll_v2_evidence_package_keeps_release_and_derivation_boundaries() -> None:
    package = json.loads(EVIDENCE_PACKAGE_V2.read_text(encoding="utf-8"))

    assert package["package_id"] == "ti2026-group-roll-playbook-evidence-v2"
    assert package["as_of"] == "2026-08-06T17:27:00Z"
    assert package["manual_route_independent_of_solver"] is True
    assert package["solver_sources_used_for_derivation"] == []
    assert package["release_status"] == {
        "rate-agnostic": "draft",
        "primary-model": "draft",
    }
    assert package["cross_audit_gate"]["completed_rows"] == 108
    assert package["cross_audit_gate"]["planned_rows"] == 108
    assert package["cross_audit_gate"]["promotion_permitted"] is False
    assert package["stat_provenance"] == {
        "unique_exact_stats": 16,
        "unique_approved_derived_stats": 2,
        "formal_proxy_stats": 0,
        "formal_unavailable_stats": 0,
        "coach": "unavailable-excluded",
    }


def test_group_roll_v2_evidence_package_tracked_file_hashes_match() -> None:
    package = json.loads(EVIDENCE_PACKAGE_V2.read_text(encoding="utf-8"))
    mismatches = _tracked_file_mismatches(package)

    assert not mismatches, "V2 evidence package drift:\n" + "\n".join(mismatches)


def test_group_roll_v2_evidence_package_freezes_playbooks_and_artifact_paths() -> None:
    package = json.loads(EVIDENCE_PACKAGE_V2.read_text(encoding="utf-8"))
    playbooks = {
        "rate-agnostic": PROJECT_ROOT / "config/playbooks/group-rate-agnostic-v2.json",
        "primary-model": PROJECT_ROOT / "config/playbooks/group-primary-model-v2.json",
    }
    assert (
        load_playbook(playbooks["rate-agnostic"]).semantic_hash
        == package["identities"]["rate_agnostic_playbook_sha256"]
    )
    assert (
        load_playbook(playbooks["primary-model"]).semantic_hash
        == package["identities"]["primary_model_playbook_sha256"]
    )

    policy = load_cross_audit_policy(
        PROJECT_ROOT / "config/models/fantasy-group-read-only-cross-audit-v2.json"
    )
    artifacts = {item["phase"]: item for item in package["artifacts"]}
    historical_p5 = package["historical_dependencies"]["v1_p5"]
    assert policy.semantic_hash == package["policies"]["cross_audit_semantic_sha256"]
    assert policy.source_playbook_artifact == artifacts["p3-standalone"]["path"]
    assert policy.source_solver_artifact == historical_p5["path"]
    assert policy.source_playbook_evidence_sha256 == artifacts["p3-standalone"]["semantic_sha256"]
    assert policy.source_solver_evidence_sha256 == historical_p5["semantic_sha256"]


def test_group_roll_v2_evidence_package_records_byte_identical_long_reruns() -> None:
    package = json.loads(EVIDENCE_PACKAGE_V2.read_text(encoding="utf-8"))
    reproducibility = package["reproducibility"]

    assert reproducibility["standalone"]["semantic_sha256_match"] is True
    assert reproducibility["standalone"]["file_sha256_match"] is True
    assert reproducibility["cross_audit"]["first_run_id"] == reproducibility["cross_audit"]["second_run_id"]
    assert reproducibility["cross_audit"]["semantic_sha256_match"] is True
    assert reproducibility["cross_audit"]["file_sha256_match"] is True
    assert reproducibility["cross_audit"]["immutable_writer_byte_match"] is True


def test_group_roll_v2_candidate_freeze_preserves_derivation_boundary() -> None:
    package = json.loads(CANDIDATE_FREEZE.read_text(encoding="utf-8"))

    assert package["manual_route_independent_of_solver"] is True
    assert package["solver_sources_used_for_derivation"] == []
    assert package["candidate_status"] == {
        "rate-agnostic": "candidate-frozen-unvalidated",
        "primary-model": "candidate-frozen-unvalidated",
    }
    assert all("P5" not in entry["path"] and "P6" not in entry["path"] for entry in package["tracked_files"])


def test_group_roll_v2_candidate_freeze_hashes_match() -> None:
    package = json.loads(CANDIDATE_FREEZE.read_text(encoding="utf-8"))
    entries = package["tracked_files"]
    relative_paths = [Path(entry["path"]) for entry in entries]

    assert len(relative_paths) == len(set(relative_paths))
    assert all(not path.is_absolute() and ".." not in path.parts for path in relative_paths)
    assert all(
        sha256_file(PROJECT_ROOT / path) == entry["sha256"]
        for entry, path in zip(entries, relative_paths, strict=True)
    )

    for playbook in package["playbooks"].values():
        path = PROJECT_ROOT / playbook["path"]
        assert sha256_file(path) == playbook["file_sha256"]
        assert load_playbook(path).semantic_hash == playbook["semantic_sha256"]
