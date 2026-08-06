from __future__ import annotations

import json
from pathlib import Path

from ti_predictor.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PACKAGE = PROJECT_ROOT / "docs/playbooks/group-roll/evidence-package-v1.json"


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
