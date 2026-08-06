from __future__ import annotations

import json
from pathlib import Path

from ti_predictor.fantasy.playbook import load_playbook
from ti_predictor.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PACKAGE = PROJECT_ROOT / "docs/playbooks/group-roll/evidence-package-v1.json"
CANDIDATE_FREEZE = PROJECT_ROOT / "docs/playbooks/group-roll/candidate-freeze-v2.json"


def test_group_roll_evidence_package_keeps_release_boundaries() -> None:
    package = json.loads(EVIDENCE_PACKAGE.read_text(encoding="utf-8"))

    assert package["manual_route_independent_of_solver"] is True
    assert package["release_status"] == {
        "rate-agnostic": "draft",
        "primary-model": "draft",
    }


def test_group_roll_evidence_package_tracked_file_hashes_match() -> None:
    package = json.loads(EVIDENCE_PACKAGE.read_text(encoding="utf-8"))
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

    assert not mismatches, "Evidence package drift:\n" + "\n".join(mismatches)


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
