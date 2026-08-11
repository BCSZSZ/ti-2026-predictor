"""Content-addressed Frozen Solver Release for both consumer applications.

The maintainer build path may read governed raw data and artifacts.  The
resulting release is the only solver context consumed by the public manual app
and the local OCR app; neither consumer may rebuild or download evidence.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import zstandard as zstd

from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.fantasy.current_advisor import (
    CurrentAdvisorContext,
    CurrentAdvisorError,
    _resolve_current_advisor_rule_snapshot,
    load_current_advisor_policy,
)
from ti_predictor.fantasy.roll import build_group_roll_rules
from ti_predictor.fantasy.scenarios import (
    ROLE_IDS,
    CommonScenarioSet,
    PoolBuildResult,
    ScenarioDraws,
    SeriesBlock,
    SeriesBlockPool,
)
from ti_predictor.fantasy.solver import TerminalGroupEvaluator
from ti_predictor.hashing import canonical_json, sha256_bytes, sha256_file, sha256_json
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import source_tree_hash

SOLVER_RELEASE_SCHEMA_VERSION = 2
SOLVER_RELEASE_POINTER_SCHEMA_VERSION = 1
SOLVER_RELEASE_ID = "ti2026-group-current-screen-solver-v2"
_MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class SolverReleaseWriteResult:
    path: Path
    pointer_path: Path | None
    file_sha256: str
    release_sha256: str
    bytes: int


def default_solver_release_pointer_path(paths: ProjectPaths = PATHS) -> Path:
    return paths.root / "deploy" / "runtime" / "current.json"


def _solver_release_pointer(paths: ProjectPaths = PATHS) -> dict[str, Any]:
    pointer_path = default_solver_release_pointer_path(paths)
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CurrentAdvisorError("冻结求解发布清单缺失；请更新仓库或重新安装当前版本") from error
    except (OSError, json.JSONDecodeError) as error:
        raise CurrentAdvisorError("冻结求解发布清单不可读") from error
    if not isinstance(payload, dict):
        raise CurrentAdvisorError("冻结求解发布清单根节点必须是对象")
    expected_keys = {
        "schema_version",
        "release_schema_version",
        "release_id",
        "as_of",
        "file",
        "bytes",
        "file_sha256",
        "release_sha256",
    }
    if set(payload) != expected_keys:
        raise CurrentAdvisorError("冻结求解发布清单字段发生漂移")
    if payload.get("schema_version") != SOLVER_RELEASE_POINTER_SCHEMA_VERSION:
        raise CurrentAdvisorError("不支持的冻结求解发布清单版本")
    if payload.get("release_schema_version") != SOLVER_RELEASE_SCHEMA_VERSION:
        raise CurrentAdvisorError("冻结求解发布清单与求解包版本不一致")
    if payload.get("release_id") != SOLVER_RELEASE_ID:
        raise CurrentAdvisorError("冻结求解发布清单身份不正确")
    return payload


def default_solver_release_path(paths: ProjectPaths = PATHS) -> Path:
    pointer = _solver_release_pointer(paths)
    runtime_root = (paths.root / "deploy" / "runtime").resolve()
    selected = (runtime_root / str(pointer["file"])).resolve()
    if not selected.is_relative_to(runtime_root):
        raise CurrentAdvisorError("冻结求解发布清单指向运行时目录之外")
    return selected


def default_manual_release_path(paths: ProjectPaths = PATHS) -> Path:
    """Backward-compatible alias for the shared Frozen Solver Release path."""

    return default_solver_release_path(paths)


def _block_payload(block: SeriesBlock) -> dict[str, Any]:
    return {
        "target_team_id": int(block.target_team_id),
        "role": block.role,
        "player_ids": list(block.player_ids),
        "historical_team_id": int(block.historical_team_id),
        "series_id": int(block.series_id),
        "match_ids": list(block.match_ids),
        "start_times": list(block.start_times),
        "evidence_weight": float(block.evidence_weight),
        "stat_ids": list(block.stat_ids),
        "game_stat_scores": block.game_stat_scores.tolist(),
        "semantic_hash": block.semantic_hash,
    }


def _pool_payload(pool: SeriesBlockPool) -> dict[str, Any]:
    return {
        "target_team_id": int(pool.target_team_id),
        "role": pool.role,
        "player_ids": list(pool.player_ids),
        "stat_ids": list(pool.stat_ids),
        "blocks": [_block_payload(block) for block in pool.blocks],
        "semantic_hash": pool.semantic_hash,
    }


def _pool_result_payload(pool_result: PoolBuildResult) -> dict[str, Any]:
    return {
        "pools": [_pool_payload(pool) for pool in pool_result.pools],
        "audit": pool_result.audit,
        "semantic_hash": pool_result.semantic_hash,
    }


def _scenario_payload(scenarios: CommonScenarioSet) -> dict[str, Any]:
    return {
        "policy_id": scenarios.policy_id,
        "data_snapshot_sha256": scenarios.data_snapshot_sha256,
        "as_of": scenarios.as_of,
        "seed": int(scenarios.seed),
        "team_ids": list(scenarios.team_ids),
        "scenario_ids": scenarios.scenario_ids.tolist(),
        "group_categories": scenarios.group_categories.tolist(),
        "series_counts": scenarios.series_counts.tolist(),
        "draws": [
            {
                "target_team_id": int(draw.target_team_id),
                "role": draw.role,
                "pool_sha256": draw.pool_sha256,
                "block_indexes": draw.block_indexes.tolist(),
                "semantic_hash": draw.semantic_hash,
            }
            for draw in scenarios.draws
        ],
        "semantic_hash": scenarios.semantic_hash,
    }


def _title_evidence_hash(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "evidence_sha256"}
    return sha256_json(body)


def _manifest_path(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def _release_filename(*, as_of: str, release_sha256: str) -> str:
    cutoff = as_of.replace("-", "").replace(":", "")
    return f"group-roll-{cutoff}-{release_sha256[:12]}.json.zst"


def _write_release_pointer(
    *,
    paths: ProjectPaths,
    destination: Path,
    as_of: str,
    file_sha256: str,
    release_sha256: str,
    size: int,
) -> Path:
    runtime_root = (paths.root / "deploy" / "runtime").resolve()
    resolved_destination = destination.resolve()
    if not resolved_destination.is_relative_to(runtime_root):
        raise CurrentAdvisorError("默认冻结求解发布文件必须位于 deploy/runtime 下")
    pointer_path = default_solver_release_pointer_path(paths)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer = {
        "schema_version": SOLVER_RELEASE_POINTER_SCHEMA_VERSION,
        "release_schema_version": SOLVER_RELEASE_SCHEMA_VERSION,
        "release_id": SOLVER_RELEASE_ID,
        "as_of": as_of,
        "file": resolved_destination.relative_to(runtime_root).as_posix(),
        "bytes": size,
        "file_sha256": file_sha256,
        "release_sha256": release_sha256,
    }
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return pointer_path


def write_solver_release_bundle(
    context: CurrentAdvisorContext,
    *,
    output_path: Path | None = None,
    paths: ProjectPaths = PATHS,
) -> SolverReleaseWriteResult:
    """Write a deterministic, compact deployment asset from a verified local context."""

    policy_path = paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    policy = load_current_advisor_policy(policy_path)
    if context.policy != policy:
        raise CurrentAdvisorError("solver release context and current advisor policy differ")
    snapshot, _ = _resolve_current_advisor_rule_snapshot(policy, paths=paths)
    client_roll = snapshot.observed.get("fantasy_roll")
    if not isinstance(client_roll, Mapping):
        raise CurrentAdvisorError("frozen Rule snapshot lacks normalized Fantasy Roll operations")
    if context.pool_result.semantic_hash != policy.source.pool_set_sha256:
        raise CurrentAdvisorError("solver release pool identity differs from the frozen policy")
    if _title_evidence_hash(context.title_evidence) != policy.source.title_evidence_sha256:
        raise CurrentAdvisorError("solver release Title evidence identity is invalid")

    body = {
        "schema_version": SOLVER_RELEASE_SCHEMA_VERSION,
        "release_id": SOLVER_RELEASE_ID,
        "as_of": policy.as_of,
        "seed": int(policy.seed),
        "provenance": {
            "source_tree_sha256": source_tree_hash(paths),
            "manual_entrypoint_sha256": sha256_file(paths.root / "streamlit_app.py"),
            "local_ocr_entrypoint_sha256": sha256_file(paths.root / "local_ocr_app.py"),
            "streamlit_config_sha256": sha256_file(paths.root / ".streamlit" / "config.toml"),
            "pyproject_sha256": sha256_file(paths.root / "pyproject.toml"),
            "uv_lock_sha256": sha256_file(paths.root / "uv.lock"),
            "policy_sha256": sha256_file(policy_path),
            "canonical_rules_sha256": sha256_file(paths.rules),
            "tournament_manifest_sha256": sha256_file(paths.tournament),
            "p3_evidence_sha256": policy.source.p3_evidence_sha256,
            "data_snapshot_sha256": policy.source.data_snapshot_sha256,
            "pool_set_sha256": policy.source.pool_set_sha256,
            "full_scenario_sha256": policy.source.full_scenario_sha256,
            "responsive_scenario_sha256": context.scenarios.semantic_hash,
            "title_evidence_sha256": policy.source.title_evidence_sha256,
            "rule_snapshot_sha256": policy.source.rule_snapshot_sha256,
            "client_roll_sha256": sha256_json(client_roll),
        },
        "runtime_contract": {
            "accepted_input": "confirmed-group-roll-state-v1",
            "contains_raw_data": False,
            "contains_processed_data": False,
            "contains_run_artifacts": False,
            "contains_ocr": False,
            "contains_screen_capture": False,
            "contains_data_sync": False,
            "contains_dota_client_control": False,
            "future_offer_generation": False,
        },
        "client_roll": client_roll,
        "team_names": [
            {"team_id": int(team_id), "name": name} for team_id, name in context.team_names.items()
        ],
        "pool_result": _pool_result_payload(context.pool_result),
        "scenarios": _scenario_payload(context.scenarios),
        "title_evidence": context.title_evidence,
        "warnings": list(context.warnings),
    }
    release_sha256 = sha256_json(body)
    envelope = {**body, "release_sha256": release_sha256}
    compressed = zstd.ZstdCompressor(
        level=19,
        write_checksum=True,
        write_content_size=True,
    ).compress(canonical_json(envelope))
    if output_path is None:
        destination = (
            paths.root
            / "deploy"
            / "runtime"
            / "releases"
            / _release_filename(as_of=policy.as_of, release_sha256=release_sha256)
        ).resolve()
    else:
        destination = output_path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.read_bytes() != compressed:
        raise CurrentAdvisorError(f"immutable solver release differs from existing file: {destination}")
    if not destination.is_file():
        destination.write_bytes(compressed)
    file_sha256 = sha256_bytes(compressed)
    _manifest_path(destination).write_text(
        f"{file_sha256}  {destination.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    pointer_path = None
    if output_path is None:
        pointer_path = _write_release_pointer(
            paths=paths,
            destination=destination,
            as_of=policy.as_of,
            file_sha256=file_sha256,
            release_sha256=release_sha256,
            size=len(compressed),
        )
    return SolverReleaseWriteResult(
        path=destination,
        pointer_path=pointer_path,
        file_sha256=file_sha256,
        release_sha256=release_sha256,
        bytes=len(compressed),
    )


def write_manual_release_bundle(
    context: CurrentAdvisorContext,
    *,
    output_path: Path | None = None,
    paths: ProjectPaths = PATHS,
) -> SolverReleaseWriteResult:
    """Backward-compatible alias for :func:`write_solver_release_bundle`."""

    return write_solver_release_bundle(context, output_path=output_path, paths=paths)


def _load_block(payload: Mapping[str, Any]) -> SeriesBlock:
    block = SeriesBlock(
        target_team_id=int(payload["target_team_id"]),
        role=str(payload["role"]),
        player_ids=tuple(int(value) for value in payload["player_ids"]),
        historical_team_id=int(payload["historical_team_id"]),
        series_id=int(payload["series_id"]),
        match_ids=tuple(int(value) for value in payload["match_ids"]),
        start_times=tuple(str(value) for value in payload["start_times"]),
        evidence_weight=float(payload["evidence_weight"]),
        stat_ids=tuple(str(value) for value in payload["stat_ids"]),
        game_stat_scores=np.asarray(payload["game_stat_scores"], dtype="<f8"),
    )
    if block.semantic_hash != payload.get("semantic_hash"):
        raise CurrentAdvisorError("solver release Series block hash is invalid")
    return block


def _load_pool_result(payload: Mapping[str, Any], *, expected_sha256: str) -> PoolBuildResult:
    pools = []
    for row in payload["pools"]:
        pool = SeriesBlockPool(
            target_team_id=int(row["target_team_id"]),
            role=str(row["role"]),
            player_ids=tuple(int(value) for value in row["player_ids"]),
            stat_ids=tuple(str(value) for value in row["stat_ids"]),
            blocks=tuple(_load_block(block) for block in row["blocks"]),
        )
        if pool.semantic_hash != row.get("semantic_hash"):
            raise CurrentAdvisorError("solver release Series pool hash is invalid")
        pools.append(pool)
    audit = dict(payload["audit"])
    calculated = sha256_json(
        {
            "pools": [pool.semantic_hash for pool in pools],
            "team_role_availability": audit.get("team_role_availability"),
        }
    )
    if calculated != payload.get("semantic_hash") or calculated != expected_sha256:
        raise CurrentAdvisorError("solver release pool-set hash is invalid")
    return PoolBuildResult(pools=tuple(pools), audit=audit, semantic_hash=calculated)


def _load_scenarios(payload: Mapping[str, Any], *, expected_sha256: str) -> CommonScenarioSet:
    draws = []
    for row in payload["draws"]:
        draw = ScenarioDraws(
            target_team_id=int(row["target_team_id"]),
            role=str(row["role"]),
            pool_sha256=str(row["pool_sha256"]),
            block_indexes=np.asarray(row["block_indexes"], dtype="<i4"),
        )
        if draw.semantic_hash != row.get("semantic_hash"):
            raise CurrentAdvisorError("solver release Scenario draw hash is invalid")
        draws.append(draw)
    scenarios = CommonScenarioSet(
        policy_id=str(payload["policy_id"]),
        data_snapshot_sha256=str(payload["data_snapshot_sha256"]),
        as_of=str(payload["as_of"]),
        seed=int(payload["seed"]),
        team_ids=tuple(int(value) for value in payload["team_ids"]),
        scenario_ids=np.asarray(payload["scenario_ids"], dtype="<i8"),
        group_categories=np.asarray(payload["group_categories"], dtype="<i1"),
        series_counts=np.asarray(payload["series_counts"], dtype="<i1"),
        draws=tuple(draws),
    )
    if scenarios.semantic_hash != payload.get("semantic_hash"):
        raise CurrentAdvisorError("solver release Scenario-set hash is invalid")
    if scenarios.semantic_hash != expected_sha256:
        raise CurrentAdvisorError("solver release Scenario identity differs from its provenance")
    return scenarios


def _read_release_payload(
    path: Path,
    *,
    pointer: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        compressed = path.read_bytes()
    except FileNotFoundError as error:
        raise CurrentAdvisorError("冻结求解发布文件缺失；请更新仓库或重新安装当前版本") from error
    if pointer is not None:
        if int(pointer["bytes"]) != len(compressed):
            raise CurrentAdvisorError("冻结求解发布文件大小与清单不一致")
        if pointer["file_sha256"] != sha256_bytes(compressed):
            raise CurrentAdvisorError("冻结求解发布文件哈希与清单不一致")
    manifest_path = _manifest_path(path)
    if manifest_path.is_file():
        parts = manifest_path.read_text(encoding="utf-8").strip().split("  ", maxsplit=1)
        if len(parts) != 2 or parts[1] != path.name or parts[0] != sha256_bytes(compressed):
            raise CurrentAdvisorError("solver release file manifest is invalid")
    try:
        content = zstd.ZstdDecompressor().decompress(
            compressed,
            max_output_size=_MAX_DECOMPRESSED_BYTES,
        )
        payload = json.loads(content)
    except (zstd.ZstdError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentAdvisorError("solver release bundle is unreadable") from error
    if not isinstance(payload, dict):
        raise CurrentAdvisorError("solver release bundle root must be an object")
    claimed = payload.pop("release_sha256", None)
    if claimed != sha256_json(payload):
        raise CurrentAdvisorError("solver release bundle hash is invalid")
    if pointer is not None and claimed != pointer["release_sha256"]:
        raise CurrentAdvisorError("solver release content hash differs from its pointer")
    payload["release_sha256"] = claimed
    return payload


def load_solver_release_context(
    path: Path | None = None,
    *,
    paths: ProjectPaths = PATHS,
) -> CurrentAdvisorContext:
    """Load the shared consumer context without raw data, downloads, or rebuilds."""

    started = perf_counter()
    pointer = None if path is not None else _solver_release_pointer(paths)
    selected_path = (path or default_solver_release_path(paths)).resolve()
    payload = _read_release_payload(selected_path, pointer=pointer)
    if payload.get("schema_version") != SOLVER_RELEASE_SCHEMA_VERSION:
        raise CurrentAdvisorError("unsupported solver release schema")
    if payload.get("release_id") != SOLVER_RELEASE_ID:
        raise CurrentAdvisorError("unexpected solver release identity")
    runtime_contract = payload.get("runtime_contract")
    expected_runtime_contract = {
        "accepted_input": "confirmed-group-roll-state-v1",
        "contains_raw_data": False,
        "contains_processed_data": False,
        "contains_run_artifacts": False,
        "contains_ocr": False,
        "contains_screen_capture": False,
        "contains_data_sync": False,
        "contains_dota_client_control": False,
        "future_offer_generation": False,
    }
    if runtime_contract != expected_runtime_contract:
        raise CurrentAdvisorError("solver release runtime contract drifted")
    if pointer is not None and payload.get("as_of") != pointer["as_of"]:
        raise CurrentAdvisorError("solver release cutoff differs from its pointer")

    policy_path = paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise CurrentAdvisorError("solver release provenance is missing")
    local_hashes = {
        "source_tree_sha256": source_tree_hash(paths),
        "manual_entrypoint_sha256": sha256_file(paths.root / "streamlit_app.py"),
        "local_ocr_entrypoint_sha256": sha256_file(paths.root / "local_ocr_app.py"),
        "streamlit_config_sha256": sha256_file(paths.root / ".streamlit" / "config.toml"),
        "pyproject_sha256": sha256_file(paths.root / "pyproject.toml"),
        "uv_lock_sha256": sha256_file(paths.root / "uv.lock"),
        "policy_sha256": sha256_file(policy_path),
        "canonical_rules_sha256": sha256_file(paths.rules),
        "tournament_manifest_sha256": sha256_file(paths.tournament),
    }
    if any(provenance.get(key) != value for key, value in local_hashes.items()):
        raise CurrentAdvisorError("solver release source or configuration drifted")

    policy = load_current_advisor_policy(policy_path)
    if payload.get("as_of") != policy.as_of or int(payload.get("seed", -1)) != policy.seed:
        raise CurrentAdvisorError("solver release cutoff or seed differs from the current policy")
    source_expectations = {
        "p3_evidence_sha256": policy.source.p3_evidence_sha256,
        "data_snapshot_sha256": policy.source.data_snapshot_sha256,
        "pool_set_sha256": policy.source.pool_set_sha256,
        "full_scenario_sha256": policy.source.full_scenario_sha256,
        "title_evidence_sha256": policy.source.title_evidence_sha256,
        "rule_snapshot_sha256": policy.source.rule_snapshot_sha256,
    }
    if any(provenance.get(key) != value for key, value in source_expectations.items()):
        raise CurrentAdvisorError("solver release frozen evidence identity drifted")

    canonical_rules = load_rules(paths.rules)
    client_roll = payload.get("client_roll")
    if not isinstance(client_roll, Mapping):
        raise CurrentAdvisorError("solver release client Roll rules are missing")
    if sha256_json(client_roll) != provenance.get("client_roll_sha256"):
        raise CurrentAdvisorError("solver release client Roll rules are invalid")
    roll_rules = build_group_roll_rules(canonical_rules, client_roll)

    pool_result = _load_pool_result(
        payload["pool_result"],
        expected_sha256=policy.source.pool_set_sha256,
    )
    scenarios = _load_scenarios(
        payload["scenarios"],
        expected_sha256=str(provenance["responsive_scenario_sha256"]),
    )
    if scenarios.data_snapshot_sha256 != policy.source.data_snapshot_sha256:
        raise CurrentAdvisorError("solver release Scenario data snapshot drifted")
    title_evidence = payload.get("title_evidence")
    if not isinstance(title_evidence, Mapping):
        raise CurrentAdvisorError("solver release Title evidence is missing")
    if _title_evidence_hash(title_evidence) != policy.source.title_evidence_sha256:
        raise CurrentAdvisorError("solver release Title evidence hash is invalid")

    manifest = load_tournament_manifest(paths.tournament)
    expected_names = [(int(team.team_id), team.name) for team in manifest.teams]
    supplied_names = [(int(row["team_id"]), str(row["name"])) for row in payload.get("team_names", [])]
    if supplied_names != expected_names:
        raise CurrentAdvisorError("solver release Team identities differ from the manifest")
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise CurrentAdvisorError("solver release warnings are invalid")

    terminal = TerminalGroupEvaluator(pool_result, scenarios, canonical_rules)
    return CurrentAdvisorContext(
        policy=policy,
        canonical_rules=canonical_rules,
        roll_rules=roll_rules,
        pool_result=pool_result,
        scenarios=scenarios,
        terminal=terminal,
        team_names=dict(supplied_names),
        title_evidence=dict(title_evidence),
        warnings=tuple(warnings),
        context_load_seconds=perf_counter() - started,
    )


def load_manual_release_context(
    path: Path | None = None,
    *,
    paths: ProjectPaths = PATHS,
) -> CurrentAdvisorContext:
    """Backward-compatible alias for :func:`load_solver_release_context`."""

    return load_solver_release_context(path, paths=paths)


def solver_release_team_options(
    context: CurrentAdvisorContext,
) -> dict[str, tuple[tuple[int, str], ...]]:
    available = {(pool.target_team_id, pool.role) for pool in context.pool_result.pools}
    return {
        role: tuple(
            (team_id, name) for team_id, name in context.team_names.items() if (team_id, role) in available
        )
        for role in ROLE_IDS
    }


def manual_release_team_options(
    context: CurrentAdvisorContext,
) -> dict[str, tuple[tuple[int, str], ...]]:
    """Backward-compatible alias for :func:`solver_release_team_options`."""

    return solver_release_team_options(context)
