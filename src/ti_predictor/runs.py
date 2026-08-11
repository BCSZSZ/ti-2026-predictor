from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from ti_predictor.config import manifest_hash, rules_hash
from ti_predictor.hashing import file_manifest, sha256_json
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import rule_snapshot_at
from ti_predictor.schemas import ForecastRun, StrategyProfile, as_utc
from ti_predictor.storage import DataStore


def source_version(paths: ProjectPaths = PATHS) -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=paths.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=paths.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if dirty:
            return f"{commit}-dirty-{source_tree_hash(paths)[:12]}"
        return commit
    except (FileNotFoundError, subprocess.CalledProcessError):
        return f"source-{source_tree_hash(paths)}"


def source_tree_hash(paths: ProjectPaths = PATHS) -> str:
    material: list[dict[str, Any]] = []
    for base in (paths.root / "src", paths.root / "config"):
        if not base.exists():
            continue
        for item in sorted(
            path
            for path in base.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix.lower() in {".py", ".json", ".yaml", ".yml"}
        ):
            material.append(
                {
                    "path": item.relative_to(paths.root).as_posix(),
                    "bytes": item.stat().st_size,
                    "content": item.read_bytes().hex(),
                }
            )
    return sha256_json(material)


def make_run_id(
    *,
    kind: str,
    as_of: datetime,
    seed: int,
    profiles: list[StrategyProfile],
    parameters: dict[str, Any],
    paths: ProjectPaths = PATHS,
) -> tuple[str, dict[str, str]]:
    hashes = {
        "rule": rules_hash(paths.rules),
        "config": manifest_hash(paths.tournament),
        "data": DataStore(paths).data_hash(),
        "source": source_version(paths),
    }
    snapshot_result = rule_snapshot_at(as_of, paths)
    if snapshot_result is None:
        hashes["rule_snapshot"] = "missing"
        hashes["rule_snapshot_id"] = "missing"
    else:
        snapshot, _ = snapshot_result
        hashes["rule_snapshot"] = snapshot.snapshot_sha256
        hashes["rule_snapshot_id"] = snapshot.snapshot_id
    material = {
        "kind": kind,
        "as_of": as_utc(as_of).isoformat(),
        "seed": seed,
        "profiles": [profile.value for profile in profiles],
        "parameters": parameters,
        "hashes": hashes,
    }
    return f"{kind}-{sha256_json(material)[:16]}", hashes


class ArtifactWriter:
    def __init__(self, run_id: str, paths: ProjectPaths = PATHS) -> None:
        self.paths = paths
        self.folder = paths.artifacts / run_id
        self.folder.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.folder / name
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing != content:
                raise RuntimeError(f"immutable artifact differs from existing file: {path}")
            return path
        path.write_text(content, encoding="utf-8")
        return path

    def write_text(self, name: str, content: str) -> Path:
        path = self.folder / name
        normalized = content if content.endswith("\n") else content + "\n"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing != normalized:
                raise RuntimeError(f"immutable artifact differs from existing file: {path}")
            return path
        path.write_text(normalized, encoding="utf-8")
        return path

    def write_run(self, run: ForecastRun) -> Path:
        return self.write_json("run.json", run.model_dump(mode="json"))

    def manifest(self) -> list[dict[str, Any]]:
        return file_manifest(self.folder)
