"""Offline materialization and freezing of the TI 2026 actual-Main evidence snapshot."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ti_predictor.config import (
    load_rules,
    load_team_strength_policy,
    load_tournament_manifest,
    roster_intervals,
)
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.identity import RosterIndex
from ti_predictor.ingest.opendota import (
    FANTASY_STAT_IDS,
    _detail_status_row,
    _fantasy_performance_rows,
    _latest_raw_match_capture,
    _match_snapshot,
    _merge_frames,
    _write_parquet_atomic,
)
from ti_predictor.ingest.replay import overlay_native_fantasy_stats
from ti_predictor.match_catalog import build_patch_timeline, patch_at
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import as_utc
from ti_predictor.storage import read_parquet_if_exists

MAIN_EVIDENCE_POINTER = "main-evidence-current.json"
MAIN_WORKSPACE_SCHEMA_VERSION = 1
MAIN_SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MainActualWorkspace:
    path: Path
    as_of: str
    stage_game_count: int
    replay_target_match_ids: tuple[int, ...]
    replay_target_match_ids_sha256: str
    entrant_team_ids: tuple[int, ...]
    manifest_path: Path


@dataclass(frozen=True)
class MainActualSnapshot:
    path: Path
    pointer_path: Path
    manifest_path: Path
    manifest_sha256: str
    semantic_hash: str
    replay_target_game_count: int


def _utc_text(value: Any) -> str:
    selected = as_utc(value)
    if selected is None:
        raise ValueError("an explicit UTC timestamp is required")
    return selected.isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _copy_processed_base(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source_path in sorted(source.glob("*.parquet")):
        shutil.copy2(source_path, target / source_path.name)


def _latest_capture_or_fail(paths: ProjectPaths, match_id: int) -> tuple[dict[str, Any], datetime, str]:
    capture = _latest_raw_match_capture(paths, match_id)
    if capture is None:
        raise ValueError(f"Main actual evidence is missing raw OpenDota detail {match_id}")
    payload, fetched_at, source_hash = capture
    if int(payload.get("match_id") or 0) != match_id:
        raise ValueError(f"raw OpenDota detail identity mismatch for {match_id}")
    return payload, fetched_at, source_hash


def _snapshot_file_hashes(directory: Path) -> dict[str, str]:
    return {path.name: sha256_file(path) for path in sorted(directory.glob("*.parquet")) if path.is_file()}


def prepare_main_actual_workspace(
    *,
    as_of,
    catalog_audit_path: Path,
    workspace_path: Path,
    paths: ProjectPaths = PATHS,
) -> MainActualWorkspace:
    """Materialize the frozen Main inputs from immutable local raw captures only."""

    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("Main actual materialization requires an explicit as_of")
    cutoff_text = _utc_text(cutoff)
    manifest = load_tournament_manifest(paths.tournament)
    if len(manifest.main_event_seeds) != 8:
        raise ValueError("Main actual materialization requires eight imported entrant Team IDs")
    policy = load_team_strength_policy(manifest, config_root=paths.config, period="main")
    stage_scope = policy.current_event_stage_scope
    if stage_scope is None:
        raise ValueError("Main policy has no frozen current-event stage scope")
    if cutoff < stage_scope.snapshot_available_at:
        raise ValueError("Main actual as_of predates the frozen stage snapshot")
    if stage_scope.event_id != manifest.event_id or stage_scope.league_id != manifest.league_id:
        raise ValueError("Main stage scope conflicts with the tournament manifest")

    catalog_audit = json.loads(catalog_audit_path.read_text(encoding="utf-8"))
    missing_catalog_ids = tuple(
        int(value)
        for value in catalog_audit.get("catalog", {}).get("processed_catalog_missing_match_ids", [])
    )
    if not missing_catalog_ids:
        raise ValueError("catalog audit does not declare the locally missing processed Games")
    stage_ids = set(stage_scope.match_ids)
    if not stage_ids <= set(missing_catalog_ids):
        absent = sorted(stage_ids - set(missing_catalog_ids))
        raise ValueError(f"catalog audit does not cover frozen stage Games: {absent}")

    resolved_workspace = workspace_path.resolve()
    processed_root = paths.processed.resolve()
    if resolved_workspace == processed_root or processed_root not in resolved_workspace.parents:
        raise ValueError("Main actual workspace must stay below data/processed without replacing it")
    _copy_processed_base(paths.processed, resolved_workspace)
    workspace_paths = ProjectPaths(root=paths.root, processed_override=resolved_workspace)

    leagues = read_parquet_if_exists(workspace_paths.processed / "leagues.parquet")
    patches = read_parquet_if_exists(workspace_paths.processed / "patches.parquet")
    if leagues.empty or patches.empty:
        raise ValueError("Main actual materialization requires the existing League and Patch tables")
    league_index = {
        int(row["leagueid"]): row
        for row in leagues.to_dict(orient="records")
        if row.get("leagueid") is not None
    }
    patch_records = patches.to_dict(orient="records")
    patch_timeline = build_patch_timeline(patch_records)
    patch_source_hash = str(patch_records[0].get("source_sha256") or "")

    match_rows: list[dict[str, Any]] = []
    stage_captures: dict[int, tuple[dict[str, Any], datetime, str]] = {}
    for match_id in missing_catalog_ids:
        payload, fetched_at, source_hash = _latest_capture_or_fail(paths, match_id)
        if fetched_at > cutoff:
            raise ValueError(f"raw OpenDota detail {match_id} was unavailable at Main as_of")
        league_id = int(payload.get("leagueid") or payload.get("league_id") or 0)
        league_metadata = league_index.get(league_id)
        if league_metadata is None:
            raise ValueError(f"Main actual Game {match_id} has unknown League ID {league_id}")
        started_at = datetime.fromtimestamp(float(payload["start_time"]), tz=UTC)
        snapshot = _match_snapshot(
            payload,
            league_id=league_id,
            league_metadata=league_metadata,
            patch_point=patch_at(started_at, patch_timeline),
            is_pro_match=True,
            fetched_at=fetched_at,
            source_hash=source_hash,
            league_source_hash=(
                str(league_metadata.get("source_sha256"))
                if league_metadata.get("source_sha256") is not None
                else None
            ),
            patch_source_hash=patch_source_hash or None,
            as_of=cutoff,
        )
        match_rows.append(snapshot.model_dump())
        if match_id in stage_ids:
            stage_captures[match_id] = (payload, fetched_at, source_hash)
    if set(stage_captures) != stage_ids:
        raise ValueError("not all frozen TI stage Games were materialized")

    matches_path = workspace_paths.processed / "matches.parquet"
    matches = _merge_frames(read_parquet_if_exists(matches_path), match_rows, ["match_id"])
    if matches["match_id"].duplicated().any():
        raise ValueError("Main materialized match catalog contains duplicate stable IDs")
    stage_matches = matches.loc[matches["match_id"].isin(stage_ids)]
    if len(stage_matches) != len(stage_ids):
        raise ValueError("Main materialized match catalog is missing frozen stage Games")
    _write_parquet_atomic(matches, matches_path)

    rules = load_rules(paths.rules)
    provenance = {stat_id: rules["fantasy"]["stats"][stat_id]["provenance"] for stat_id in FANTASY_STAT_IDS}
    roster_index = RosterIndex(roster_intervals(manifest, as_of=cutoff))
    fantasy_rows: list[dict[str, Any]] = []
    detail_status_rows: list[dict[str, Any]] = []
    entrant_ids = tuple(int(value) for value in manifest.main_event_seeds)
    entrant_set = set(entrant_ids)
    entrant_players = {
        int(player.account_id): {
            "team_id": int(team.team_id),
            "team_name": team.name,
            "player_name": player.name,
            "role": role,
        }
        for team in manifest.teams
        if team.team_id in entrant_set
        for role, players in team.players.items()
        for player in players
    }
    for match_id in sorted(stage_ids):
        payload, fetched_at, source_hash = stage_captures[match_id]
        fantasy_rows.extend(
            _fantasy_performance_rows(
                payload,
                source_hash=source_hash,
                as_of=cutoff,
                roster_index=roster_index,
                provenance=provenance,
            )
        )
        detail_status_rows.append(
            _detail_status_row(
                payload,
                match_id=match_id,
                fetched_at=fetched_at,
                source_hash=source_hash,
                target_player_ids=set(entrant_players),
                as_of=cutoff,
            )
        )
    if len(fantasy_rows) != len(stage_ids) * 10:
        raise ValueError("Main stage details do not contain ten identified player rows per Game")

    samples_path = workspace_paths.processed / "fantasy_performance_samples.parquet"
    samples = _merge_frames(
        read_parquet_if_exists(samples_path),
        fantasy_rows,
        ["match_id", "account_id"],
    )
    samples = overlay_native_fantasy_stats(samples, paths=workspace_paths)
    _write_parquet_atomic(samples, samples_path)

    match_lookup = stage_matches.set_index("match_id").to_dict(orient="index")
    scope_rows: list[dict[str, Any]] = []
    replay_target_ids: set[int] = set()
    for row in fantasy_rows:
        identity = entrant_players.get(int(row["account_id"]))
        if identity is None or int(row["team_id"] or 0) != identity["team_id"]:
            continue
        match_id = int(row["match_id"])
        match = match_lookup[match_id]
        replay_target_ids.add(match_id)
        _, fetched_at, source_hash = stage_captures[match_id]
        scope_rows.append(
            {
                "account_id": int(row["account_id"]),
                "player_name": identity["player_name"],
                "manifest_team_id": identity["team_id"],
                "manifest_team_name": identity["team_name"],
                "fantasy_role": identity["role"],
                "match_id": match_id,
                "start_time": row["start_time"],
                "league_id": match.get("league_id"),
                "league_name": match.get("league_name"),
                "league_tier": match.get("league_tier"),
                "patch_name": match.get("patch_name"),
                "player_history_source_sha256": None,
                "scope_source": "opendota_match_detail",
                "scope_source_sha256": source_hash,
                "fetched_at": fetched_at,
                "as_of": cutoff,
            }
        )
    if len(entrant_players) != 40:
        raise ValueError("Main actual entrant roster must contain exactly forty reviewed players")
    if len(replay_target_ids) != 80:
        raise ValueError(f"Main actual replay scope expected 80 Games, found {len(replay_target_ids)}")
    if len(scope_rows) != 560:
        raise ValueError(f"Main actual player-Game scope expected 560 rows, found {len(scope_rows)}")

    scope_path = workspace_paths.processed / "fantasy_player_history_scope.parquet"
    scopes = _merge_frames(
        read_parquet_if_exists(scope_path),
        scope_rows,
        ["account_id", "match_id"],
    )
    _write_parquet_atomic(scopes, scope_path)
    detail_status_path = workspace_paths.processed / "match_detail_status.parquet"
    detail_statuses = _merge_frames(
        read_parquet_if_exists(detail_status_path),
        detail_status_rows,
        ["match_id"],
    )
    _write_parquet_atomic(detail_statuses, detail_status_path)
    roster_path = workspace_paths.processed / "roster_intervals.parquet"
    _write_parquet_atomic(
        pd.DataFrame([item.model_dump() for item in roster_intervals(manifest, as_of=cutoff)]),
        roster_path,
    )

    replay_ids = tuple(sorted(replay_target_ids))
    replay_ids_hash = sha256_json(list(replay_ids))
    workspace_manifest = {
        "schema_version": MAIN_WORKSPACE_SCHEMA_VERSION,
        "kind": "ti2026-main-actual-processed-workspace",
        "status": "prepared-replay-pending",
        "as_of": cutoff_text,
        "event_id": manifest.event_id,
        "entrant_team_ids": list(entrant_ids),
        "stage_match_ids_sha256": stage_scope.match_ids_sha256,
        "stage_game_count": len(stage_ids),
        "replay_target_match_ids": list(replay_ids),
        "replay_target_match_ids_sha256": replay_ids_hash,
        "replay_target_game_count": len(replay_ids),
        "catalog_audit_path": str(catalog_audit_path.resolve()),
        "catalog_audit_sha256": sha256_file(catalog_audit_path),
        "processed_file_sha256": _snapshot_file_hashes(resolved_workspace),
    }
    workspace_manifest_path = resolved_workspace / "workspace-manifest.json"
    _atomic_json(workspace_manifest_path, workspace_manifest)
    return MainActualWorkspace(
        path=resolved_workspace,
        as_of=cutoff_text,
        stage_game_count=len(stage_ids),
        replay_target_match_ids=replay_ids,
        replay_target_match_ids_sha256=replay_ids_hash,
        entrant_team_ids=entrant_ids,
        manifest_path=workspace_manifest_path,
    )


def load_main_actual_workspace(path: Path) -> MainActualWorkspace:
    manifest_path = path.resolve() / "workspace-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return MainActualWorkspace(
        path=path.resolve(),
        as_of=str(payload["as_of"]),
        stage_game_count=int(payload["stage_game_count"]),
        replay_target_match_ids=tuple(int(value) for value in payload["replay_target_match_ids"]),
        replay_target_match_ids_sha256=str(payload["replay_target_match_ids_sha256"]),
        entrant_team_ids=tuple(int(value) for value in payload["entrant_team_ids"]),
        manifest_path=manifest_path,
    )


def freeze_main_actual_snapshot(
    workspace: MainActualWorkspace,
    *,
    paths: ProjectPaths = PATHS,
) -> MainActualSnapshot:
    """Validate exact replay coverage, content-address the snapshot, and update its pointer."""

    workspace_paths = ProjectPaths(root=paths.root, processed_override=workspace.path)
    cutoff = as_utc(workspace.as_of)
    if cutoff is None:
        raise ValueError("Main actual workspace has no explicit UTC as_of")
    replay_status = read_parquet_if_exists(workspace.path / "fantasy_replay_status.parquet")
    native = read_parquet_if_exists(workspace.path / "fantasy_native_stats.parquet")
    target_ids = set(workspace.replay_target_match_ids)
    target_status = replay_status.loc[replay_status["match_id"].isin(target_ids)].copy()
    status_by_id = {
        int(row.match_id): str(row.status)
        for row in target_status[["match_id", "status"]].itertuples(index=False)
    }
    non_exact = sorted(match_id for match_id in target_ids if status_by_id.get(match_id) != "exact")
    if non_exact:
        raise ValueError(f"Main actual replay scope is not exact for Games: {non_exact}")
    for label, frame in (("replay status", target_status), ("native Fantasy", native)):
        selected = frame.loc[frame["match_id"].isin(target_ids)]
        fetched_at = pd.to_datetime(selected["fetched_at"], utc=True, errors="coerce")
        row_as_of = pd.to_datetime(selected["as_of"], utc=True, errors="coerce")
        if fetched_at.isna().any() or fetched_at.gt(pd.Timestamp(cutoff)).any():
            raise ValueError(f"Main actual {label} evidence was captured after workspace as_of")
        if row_as_of.isna().any() or row_as_of.gt(pd.Timestamp(cutoff)).any():
            raise ValueError(f"Main actual {label} rows exceed workspace as_of")
    native_counts = (
        native.loc[native["match_id"].isin(target_ids)].groupby("match_id")["account_id"].nunique()
    )
    incomplete_native = sorted(
        match_id for match_id in target_ids if int(native_counts.get(match_id, 0)) != 10
    )
    if incomplete_native:
        raise ValueError(f"Main actual native Fantasy rows are incomplete for Games: {incomplete_native}")

    samples_path = workspace.path / "fantasy_performance_samples.parquet"
    samples = overlay_native_fantasy_stats(read_parquet_if_exists(samples_path), paths=workspace_paths)
    _write_parquet_atomic(samples, samples_path)
    target_samples = samples.loc[
        samples["match_id"].isin(target_ids) & samples["team_id"].isin(workspace.entrant_team_ids)
    ]
    native_stat_ids = (
        "madstone_collected",
        "smokes_used",
        "watchers_taken",
        "lotuses_gained",
        "tormentor_kills",
    )
    invalid_native = [
        stat_id
        for stat_id in native_stat_ids
        if target_samples[stat_id].isna().any()
        or not target_samples[f"{stat_id}_provenance"].eq("exact").all()
    ]
    if invalid_native:
        raise ValueError(f"Main actual Fantasy native counters are incomplete: {invalid_native}")

    file_hashes = _snapshot_file_hashes(workspace.path)
    semantic_hash = sha256_json(
        {
            "as_of": workspace.as_of,
            "entrant_team_ids": list(workspace.entrant_team_ids),
            "stage_game_count": workspace.stage_game_count,
            "replay_target_match_ids_sha256": workspace.replay_target_match_ids_sha256,
            "processed_file_sha256": file_hashes,
        }
    )
    snapshot_id = f"main-actual-{workspace.as_of.replace(':', '').replace('-', '')[:15]}-{semantic_hash[:12]}"
    snapshots_root = paths.data / "processed" / "snapshots"
    snapshot_path = (snapshots_root / snapshot_id).resolve()
    if snapshots_root.resolve() not in snapshot_path.parents:
        raise ValueError("Main actual snapshot escaped its governed directory")
    if snapshot_path.exists():
        existing = _snapshot_file_hashes(snapshot_path)
        if existing != file_hashes:
            raise ValueError("content-addressed Main snapshot path already exists with different files")
    else:
        snapshot_path.mkdir(parents=True)
        for source_path in sorted(workspace.path.glob("*.parquet")):
            shutil.copy2(source_path, snapshot_path / source_path.name)

    snapshot_manifest = {
        "schema_version": MAIN_SNAPSHOT_SCHEMA_VERSION,
        "kind": "ti2026-main-actual-processed-snapshot",
        "status": "ready",
        "as_of": workspace.as_of,
        "entrant_team_ids": list(workspace.entrant_team_ids),
        "stage_game_count": workspace.stage_game_count,
        "replay_target_game_count": len(target_ids),
        "replay_target_match_ids_sha256": workspace.replay_target_match_ids_sha256,
        "processed_file_sha256": file_hashes,
        "semantic_hash": semantic_hash,
    }
    snapshot_manifest_path = snapshot_path / "manifest.json"
    _atomic_json(snapshot_manifest_path, snapshot_manifest)
    manifest_sha256 = sha256_file(snapshot_manifest_path)
    pointer_path = paths.data / "processed" / MAIN_EVIDENCE_POINTER
    pointer = {
        "schema_version": 1,
        "kind": "ti2026-main-actual-evidence-pointer",
        "status": "ready",
        "as_of": workspace.as_of,
        "snapshot": str(snapshot_path.relative_to(paths.root)).replace("\\", "/"),
        "manifest": str(snapshot_manifest_path.relative_to(paths.root)).replace("\\", "/"),
        "manifest_sha256": manifest_sha256,
        "semantic_hash": semantic_hash,
    }
    _atomic_json(pointer_path, pointer)
    return MainActualSnapshot(
        path=snapshot_path,
        pointer_path=pointer_path,
        manifest_path=snapshot_manifest_path,
        manifest_sha256=manifest_sha256,
        semantic_hash=semantic_hash,
        replay_target_game_count=len(target_ids),
    )


def main_evidence_paths(
    paths: ProjectPaths = PATHS,
    *,
    require: bool = False,
) -> ProjectPaths:
    pointer_path = paths.data / "processed" / MAIN_EVIDENCE_POINTER
    if not pointer_path.is_file():
        if require:
            raise FileNotFoundError(f"Main evidence pointer is missing: {pointer_path}")
        return paths
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    snapshot_path = (paths.root / str(pointer["snapshot"])).resolve()
    snapshots_root = (paths.data / "processed" / "snapshots").resolve()
    if snapshots_root not in snapshot_path.parents:
        raise ValueError("Main evidence pointer escaped the snapshots directory")
    manifest_path = (paths.root / str(pointer["manifest"])).resolve()
    if manifest_path.parent != snapshot_path:
        raise ValueError("Main evidence manifest is not inside the selected snapshot")
    if sha256_file(manifest_path) != pointer["manifest_sha256"]:
        raise ValueError("Main evidence manifest integrity check failed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("semantic_hash") != pointer.get("semantic_hash"):
        raise ValueError("Main evidence pointer semantic hash differs from its manifest")
    for name, expected_hash in manifest.get("processed_file_sha256", {}).items():
        candidate = snapshot_path / name
        if not candidate.is_file() or sha256_file(candidate) != expected_hash:
            raise ValueError(f"Main evidence processed file integrity check failed: {name}")
    return ProjectPaths(root=paths.root, processed_override=snapshot_path)


__all__ = [
    "MainActualSnapshot",
    "MainActualWorkspace",
    "freeze_main_actual_snapshot",
    "load_main_actual_workspace",
    "main_evidence_paths",
    "prepare_main_actual_workspace",
]
