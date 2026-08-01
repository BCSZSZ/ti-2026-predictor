from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ti_predictor.paths import ProjectPaths


@pytest.fixture
def project_paths(tmp_path: Path) -> ProjectPaths:
    source_root = Path(__file__).resolve().parents[1]
    (tmp_path / "config/rules").mkdir(parents=True)
    shutil.copy2(source_root / "config/rules/ti2026.json", tmp_path / "config/rules/ti2026.json")
    shutil.copy2(source_root / "config/ti2026.yaml", tmp_path / "config/ti2026.yaml")
    (tmp_path / "artifacts").mkdir()
    return ProjectPaths(root=tmp_path)


@pytest.fixture
def rules_payload() -> dict:
    path = Path(__file__).resolve().parents[1] / "config/rules/ti2026.json"
    return json.loads(path.read_text(encoding="utf-8"))
