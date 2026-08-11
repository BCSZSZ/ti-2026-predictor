from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _project_root() -> Path:
    configured = os.getenv("TI_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path = _project_root()

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def rules(self) -> Path:
        return self.config / "rules" / "ti2026.json"

    @property
    def tournament(self) -> Path:
        return self.config / "ti2026.yaml"

    @property
    def swiss(self) -> Path:
        return self.config / "tournaments" / "ti2026-swiss-v1.json"

    @property
    def swiss_policy(self) -> Path:
        return self.config / "models" / "group-swiss-v1.json"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def cache(self) -> Path:
        return self.data / "cache"

    @property
    def database(self) -> Path:
        return self.data / "ti.duckdb"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    def ensure_runtime_dirs(self) -> None:
        for path in (self.raw, self.processed, self.cache, self.artifacts):
            path.mkdir(parents=True, exist_ok=True)


PATHS = ProjectPaths()
