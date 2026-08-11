from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import zstandard as zstd

from ti_predictor.paths import PATHS, ProjectPaths

_CURRENT_ADVISOR_RULE_SHA256 = "eb3c30f542a2ee7fde1d101fdf57bd9f2f729730ccf6707c893d4e9b938cccb3"


@pytest.fixture(scope="session", autouse=True)
def _install_current_advisor_rule_fixture() -> Iterator[None]:
    """Make the pinned client Rule freeze available without depending on local raw data."""

    fixture = Path(__file__).parent / "fixtures/current_advisor_rule_snapshot-v2.json.zst"
    payload = zstd.ZstdDecompressor().decompress(fixture.read_bytes())
    assert hashlib.sha256(payload).hexdigest() == _CURRENT_ADVISOR_RULE_SHA256

    target_dir = PATHS.raw / "rules" / "zzzz-pytest-current-advisor-v2"
    target = target_dir / "rule_snapshot.json"
    previous = target.read_bytes() if target.is_file() else None
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    try:
        yield
    finally:
        if previous is None:
            target.unlink(missing_ok=True)
            try:
                target_dir.rmdir()
            except OSError:
                pass
        else:
            target.write_bytes(previous)


@pytest.fixture
def project_paths(tmp_path: Path) -> ProjectPaths:
    source_root = Path(__file__).resolve().parents[1]
    (tmp_path / "config/rules").mkdir(parents=True)
    (tmp_path / "config/models").mkdir(parents=True)
    (tmp_path / "config/playbooks").mkdir(parents=True)
    (tmp_path / "config/tournaments").mkdir(parents=True)
    shutil.copy2(source_root / "config/rules/ti2026.json", tmp_path / "config/rules/ti2026.json")
    for policy_name in (
        "team-strength-v1.json",
        "team-strength-v2.json",
        "group-swiss-v1.json",
        "fantasy-group-scenarios-v1.json",
        "fantasy-group-scenarios-v2.json",
        "fantasy-group-playbook-validation-v1.json",
        "fantasy-group-branch-capped-solver-v1.json",
        "fantasy-group-read-only-cross-audit-v1.json",
        "fantasy-group-interactive-advisor-v1.json",
        "fantasy-group-current-screen-advisor-v2.json",
    ):
        shutil.copy2(
            source_root / "config/models" / policy_name,
            tmp_path / "config/models" / policy_name,
        )
    for playbook_name in ("group-rate-agnostic-v1.json", "group-primary-model-v1.json"):
        shutil.copy2(
            source_root / "config/playbooks" / playbook_name,
            tmp_path / "config/playbooks" / playbook_name,
        )
    shutil.copy2(source_root / "config/ti2026.yaml", tmp_path / "config/ti2026.yaml")
    shutil.copy2(
        source_root / "config/tournaments/ti2026-swiss-v1.json",
        tmp_path / "config/tournaments/ti2026-swiss-v1.json",
    )
    (tmp_path / "artifacts").mkdir()
    return ProjectPaths(root=tmp_path)


@pytest.fixture
def rules_payload() -> dict:
    path = Path(__file__).resolve().parents[1] / "config/rules/ti2026.json"
    return json.loads(path.read_text(encoding="utf-8"))
