from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ti_predictor.hashing import canonical_json, sha256_bytes, sha256_file
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import as_utc, utc_now


def timestamp_slug(value: datetime) -> str:
    return as_utc(value).strftime("%Y%m%dT%H%M%SZ")


class DataStore:
    def __init__(self, paths: ProjectPaths = PATHS) -> None:
        self.paths = paths
        self.paths.ensure_runtime_dirs()

    def write_raw_json(
        self,
        *,
        source: str,
        resource: str,
        payload: Any,
        request: dict[str, Any],
        fetched_at: datetime | None = None,
    ) -> tuple[Path, str]:
        fetched = fetched_at or utc_now()
        content = canonical_json(payload)
        content_hash = sha256_bytes(content)
        folder = self.paths.raw / source / resource / f"{timestamp_slug(fetched)}-{content_hash[:12]}"
        body_path = folder / "response.json"
        metadata_path = folder / "metadata.json"
        if folder.exists():
            if body_path.is_file() and sha256_bytes(body_path.read_bytes().rstrip(b"\n")) == content_hash:
                return body_path, content_hash
            raise FileExistsError(f"immutable raw capture collision: {folder}")
        folder.mkdir(parents=True, exist_ok=False)
        body_path.write_bytes(content + b"\n")
        metadata = {
            "source": source,
            "resource": resource,
            "request": request,
            "fetched_at": fetched.isoformat().replace("+00:00", "Z"),
            "content_sha256": content_hash,
            "bytes": len(content),
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return body_path, content_hash

    def write_parquet(self, name: str, rows: list[dict[str, Any]]) -> Path:
        path = self.paths.processed / f"{name}.parquet"
        frame = pd.DataFrame(rows)
        frame.to_parquet(path, index=False)
        return path

    def refresh_duckdb(self, tables: dict[str, Path]) -> None:
        self.paths.database.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.paths.database)) as connection:
            for table_name, parquet_path in tables.items():
                safe_name = "".join(char for char in table_name if char.isalnum() or char == "_")
                if safe_name != table_name:
                    raise ValueError(f"unsafe table name: {table_name}")
                connection.execute(
                    f"CREATE OR REPLACE TABLE {safe_name} AS SELECT * FROM read_parquet(?)",
                    [str(parquet_path)],
                )

    def data_hash(self) -> str:
        files = sorted(self.paths.processed.glob("*.parquet"))
        material = [{"name": path.name, "sha256": sha256_file(path)} for path in files]
        return sha256_bytes(canonical_json(material))


def read_parquet_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)
