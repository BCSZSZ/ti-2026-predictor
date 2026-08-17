"""Content-addressed runtime boundary for the independent Main solver stack."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import zstandard as zstd
from pydantic import Field

from ti_predictor.fantasy.current_advisor import CurrentAdvisorContext
from ti_predictor.fantasy.main_advice_strategy import (
    MainAdviceStrategyCatalog,
    load_main_advice_strategy_catalog,
)
from ti_predictor.fantasy.main_current_advisor import (
    MainCurrentAdvisorContext,
    MainTerminalEvaluator,
)
from ti_predictor.fantasy.main_scenarios import MainScenarioSet
from ti_predictor.fantasy.main_title_runtime import validate_main_title_runtime_evidence
from ti_predictor.fantasy.scenarios import ROLE_IDS, PoolBuildResult, ScenarioDraws
from ti_predictor.fantasy.solver_release import _load_pool_result, _pool_result_payload
from ti_predictor.hashing import canonical_json, sha256_bytes, sha256_file, sha256_json
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import source_tree_hash, source_version
from ti_predictor.schemas import StrictModel

MAIN_SOLVER_RELEASE_ID = "ti2026-main-current-screen-solver-v2"
MAIN_SOLVER_RELEASE_SCHEMA_VERSION = 3
MAIN_SOLVER_POINTER_SCHEMA_VERSION = 2
_MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024


class MainSolverReleaseError(ValueError):
    """A Main runtime release is unavailable or invalid."""


class MainSolverReleasePending(MainSolverReleaseError):
    """The code is installed, but verified Main eligibility evidence is not ready."""


class MainSolverPolicy(StrictModel):
    schema_version: Literal[2]
    policy_id: Literal["fantasy-main-current-screen-advisor-v1"]
    period: Literal["main"]
    entrant_team_count: Literal[8]
    projected_candidate_team_count: Literal[16]
    actual_candidate_team_count: Literal[8]
    scenario_count: int = Field(ge=1)
    seed: int
    bracket_scenario_sampling: Literal["model_weighted_with_replacement"]
    projected_advancement_source: Literal["frozen_group_scenarios"]
    projected_seeding: Literal["group_category_then_strength_proxy"]
    fantasy_series_sampling: Literal["historical_pool_weighted_with_replacement"]
    slot_count: Literal[5]
    max_rolls: Literal[30]
    future_offer_generation: Literal[False]


def load_main_solver_policy(
    path: Path = PATHS.config / "models" / "fantasy-main-current-screen-advisor-v1.json",
) -> MainSolverPolicy:
    return MainSolverPolicy.model_validate_json(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class MainSolverReadiness:
    status: str
    eligibility_mode: str
    candidate_team_count: int
    entrant_team_count: int
    lock_at: str
    reason: str


@dataclass(frozen=True)
class MainSolverReleaseWriteResult:
    path: Path
    pointer_path: Path
    file_sha256: str
    release_sha256: str
    bytes: int


def default_main_solver_pointer_path(paths: ProjectPaths = PATHS) -> Path:
    return paths.root / "deploy" / "runtime" / "main-current.json"


def _read_pointer(paths: ProjectPaths = PATHS) -> dict[str, Any]:
    path = default_main_solver_pointer_path(paths)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise MainSolverReleasePending("Main 发布清单尚未建立") from error
    except (OSError, json.JSONDecodeError) as error:
        raise MainSolverReleaseError("Main 发布清单不可读") from error
    if not isinstance(payload, dict):
        raise MainSolverReleaseError("Main 发布清单根节点必须是对象")
    if payload.get("schema_version") != MAIN_SOLVER_POINTER_SCHEMA_VERSION:
        raise MainSolverReleaseError("Main 发布清单版本不受支持")
    if payload.get("release_schema_version") != MAIN_SOLVER_RELEASE_SCHEMA_VERSION:
        raise MainSolverReleaseError("Main 发布清单指向的发布文件版本不受支持")
    if payload.get("release_id") != MAIN_SOLVER_RELEASE_ID or payload.get("period") != "main":
        raise MainSolverReleaseError("Main 发布清单身份不正确")
    status = payload.get("status")
    if status not in {"provisional", "ready"}:
        raise MainSolverReleaseError("Main 发布清单状态未知")
    expected = {
        "schema_version",
        "release_schema_version",
        "release_id",
        "period",
        "status",
        "eligibility_mode",
        "candidate_team_count",
        "entrant_team_count",
        "as_of",
        "lock_at",
        "file",
        "bytes",
        "file_sha256",
        "release_sha256",
        "reason",
    }
    if set(payload) != expected:
        raise MainSolverReleaseError("Main 发布清单字段发生漂移")
    expected_mode = "projected" if status == "provisional" else "actual"
    if payload.get("eligibility_mode") != expected_mode:
        raise MainSolverReleaseError("Main 发布清单状态与候选模式不一致")
    expected_candidates = 16 if expected_mode == "projected" else 8
    if payload.get("candidate_team_count") != expected_candidates or payload.get("entrant_team_count") != 8:
        raise MainSolverReleaseError("Main 发布清单候选队数量无效")
    return payload


def main_solver_readiness(paths: ProjectPaths = PATHS) -> MainSolverReadiness:
    pointer = _read_pointer(paths)
    return MainSolverReadiness(
        str(pointer["status"]),
        str(pointer["eligibility_mode"]),
        int(pointer["candidate_team_count"]),
        int(pointer["entrant_team_count"]),
        str(pointer["lock_at"]),
        str(pointer["reason"]),
    )


def _release_path(pointer: Mapping[str, Any], paths: ProjectPaths) -> Path:
    runtime_root = (paths.root / "deploy" / "runtime").resolve()
    selected = (runtime_root / str(pointer["file"])).resolve()
    if not selected.is_relative_to(runtime_root):
        raise MainSolverReleaseError("Main 发布清单指向运行时目录之外")
    return selected


def _manifest_path(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def _read_release(path: Path, *, pointer: Mapping[str, Any] | None) -> dict[str, Any]:
    try:
        compressed = path.read_bytes()
    except FileNotFoundError as error:
        raise MainSolverReleaseError("Main 冻结发布文件缺失") from error
    if pointer is not None:
        if int(pointer["bytes"]) != len(compressed):
            raise MainSolverReleaseError("Main 发布文件大小与清单不一致")
        if pointer["file_sha256"] != sha256_bytes(compressed):
            raise MainSolverReleaseError("Main 发布文件哈希与清单不一致")
    manifest_path = _manifest_path(path)
    if manifest_path.is_file():
        parts = manifest_path.read_text(encoding="utf-8").strip().split("  ", maxsplit=1)
        if len(parts) != 2 or parts[1] != path.name or parts[0] != sha256_bytes(compressed):
            raise MainSolverReleaseError("Main 发布文件 manifest 无效")
    try:
        payload = json.loads(
            zstd.ZstdDecompressor().decompress(
                compressed,
                max_output_size=_MAX_DECOMPRESSED_BYTES,
            )
        )
    except (zstd.ZstdError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MainSolverReleaseError("Main 发布文件不可读") from error
    if not isinstance(payload, dict):
        raise MainSolverReleaseError("Main 发布文件根节点必须是对象")
    claimed = payload.pop("release_sha256", None)
    if claimed != sha256_json(payload):
        raise MainSolverReleaseError("Main 发布内容哈希无效")
    if pointer is not None and claimed != pointer["release_sha256"]:
        raise MainSolverReleaseError("Main 发布内容与清单不一致")
    payload["release_sha256"] = claimed
    return payload


def _scenario_payload(scenarios: MainScenarioSet) -> dict[str, Any]:
    return {
        "policy_id": scenarios.policy_id,
        "data_snapshot_sha256": scenarios.data_snapshot_sha256,
        "model_sha256": scenarios.model_sha256,
        "as_of": scenarios.as_of,
        "seed": scenarios.seed,
        "eligibility_mode": scenarios.eligibility_mode,
        "seeding_method": scenarios.seeding_method,
        "team_ids": list(scenarios.team_ids),
        "scenario_ids": scenarios.scenario_ids.tolist(),
        "series_counts": scenarios.series_counts.tolist(),
        "draws": [
            {
                "target_team_id": draw.target_team_id,
                "role": draw.role,
                "pool_sha256": draw.pool_sha256,
                "block_indexes": draw.block_indexes.tolist(),
                "semantic_hash": draw.semantic_hash,
            }
            for draw in scenarios.draws
        ],
        "semantic_hash": scenarios.semantic_hash,
    }


def _load_scenarios(payload: Mapping[str, Any]) -> MainScenarioSet:
    draws = []
    for row in payload["draws"]:
        draw = ScenarioDraws(
            target_team_id=int(row["target_team_id"]),
            role=str(row["role"]),
            pool_sha256=str(row["pool_sha256"]),
            block_indexes=np.asarray(row["block_indexes"], dtype="<i4"),
        )
        if draw.semantic_hash != row.get("semantic_hash"):
            raise MainSolverReleaseError("Main Scenario draw 哈希无效")
        draws.append(draw)
    scenarios = MainScenarioSet(
        policy_id=str(payload["policy_id"]),
        data_snapshot_sha256=str(payload["data_snapshot_sha256"]),
        model_sha256=str(payload["model_sha256"]),
        as_of=str(payload["as_of"]),
        seed=int(payload["seed"]),
        team_ids=tuple(int(team_id) for team_id in payload["team_ids"]),
        scenario_ids=np.asarray(payload["scenario_ids"], dtype="<i8"),
        series_counts=np.asarray(payload["series_counts"], dtype="<i1"),
        draws=tuple(draws),
        eligibility_mode=str(payload["eligibility_mode"]),
        seeding_method=str(payload["seeding_method"]),
    )
    if scenarios.semantic_hash != payload.get("semantic_hash"):
        raise MainSolverReleaseError("Main Scenario set 哈希无效")
    return scenarios


def load_main_solver_release_context(
    group_context: CurrentAdvisorContext,
    path: Path | None = None,
    *,
    paths: ProjectPaths = PATHS,
    legacy_research_strategy_catalog: MainAdviceStrategyCatalog | None = None,
) -> MainCurrentAdvisorContext:
    pointer = None if path is not None else _read_pointer(paths)
    selected = path.resolve() if path is not None else _release_path(pointer, paths)
    payload = _read_release(selected, pointer=pointer)
    legacy_research_release = (
        payload.get("schema_version") == 2
        and pointer is None
        and legacy_research_strategy_catalog is not None
    )
    if legacy_research_strategy_catalog is not None and not legacy_research_release:
        raise MainSolverReleaseError("legacy Main compatibility is restricted to explicit research files")
    if payload.get("schema_version") != MAIN_SOLVER_RELEASE_SCHEMA_VERSION and not legacy_research_release:
        raise MainSolverReleaseError("Main 发布文件版本不受支持")
    if payload.get("release_id") != MAIN_SOLVER_RELEASE_ID or payload.get("period") != "main":
        raise MainSolverReleaseError("Main 发布文件身份不正确")
    expected_runtime = (
        {
            "accepted_input": "confirmed-main-roll-state-v1",
            "contains_raw_data": False,
            "contains_ocr": False,
            "contains_screen_capture": False,
            "contains_dota_client_control": False,
            "future_offer_generation": False,
        }
        if legacy_research_release
        else {
            "accepted_input": "confirmed-main-roll-state-v1",
            "contains_raw_data": False,
            "contains_ocr": False,
            "contains_screen_capture": False,
            "contains_dota_client_control": False,
            "future_offer_generation": "g-lite-only-bounded-primary-model-sampling-v1",
        }
    )
    if payload.get("runtime_contract") != expected_runtime:
        raise MainSolverReleaseError("Main 发布运行边界发生漂移")
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise MainSolverReleaseError("Main 发布来源信息缺失")
    policy_payload = payload.get("policy")
    if not isinstance(policy_payload, Mapping):
        raise MainSolverReleaseError("Main 发布缺少冻结策略")
    try:
        policy = MainSolverPolicy.model_validate(policy_payload)
    except ValueError as error:
        raise MainSolverReleaseError("Main 冻结策略无效") from error
    if provenance.get("policy_sha256") != sha256_json(policy.model_dump(mode="json")):
        raise MainSolverReleaseError("Main 冻结策略哈希无效")
    if legacy_research_release:
        strategy_catalog = legacy_research_strategy_catalog
    else:
        strategy_payload = payload.get("advice_strategy_catalog")
        if not isinstance(strategy_payload, Mapping):
            raise MainSolverReleaseError("Main 发布缺少 G / G-Lite 策略目录")
        try:
            strategy_catalog = MainAdviceStrategyCatalog.model_validate(strategy_payload)
        except ValueError as error:
            raise MainSolverReleaseError("Main G / G-Lite 策略目录无效") from error
        if provenance.get("advice_strategy_catalog_sha256") != strategy_catalog.semantic_hash:
            raise MainSolverReleaseError("Main G / G-Lite 策略目录哈希无效")
    if provenance.get("canonical_rules_sha256") != sha256_json(group_context.canonical_rules):
        raise MainSolverReleaseError("Main 发布与规则版本不一致")
    pool_payload = payload.get("pool_result")
    if not isinstance(pool_payload, Mapping):
        raise MainSolverReleaseError("Main 发布缺少自身的 Fantasy 样本池")
    try:
        pool_result = _load_pool_result(
            pool_payload,
            expected_sha256=str(provenance.get("pool_set_sha256")),
        )
    except ValueError as error:
        raise MainSolverReleaseError("Main Fantasy 样本池无效") from error
    scenarios = _load_scenarios(payload["scenarios"])
    if (
        scenarios.policy_id != policy.policy_id
        or len(scenarios.scenario_ids) != policy.scenario_count
        or scenarios.seed != policy.seed
    ):
        raise MainSolverReleaseError("Main Scenario 与冻结策略不一致")
    if provenance.get("scenario_sha256") != scenarios.semantic_hash:
        raise MainSolverReleaseError("Main Scenario 来源身份不一致")
    if provenance.get("model_sha256") != scenarios.model_sha256:
        raise MainSolverReleaseError("Main Team strength model 来源身份不一致")
    eligibility_evidence = payload.get("eligibility_evidence")
    if not isinstance(eligibility_evidence, Mapping):
        raise MainSolverReleaseError("Main 候选 Team 证据摘要缺失")
    expected_eligibility = {
        "mode": scenarios.eligibility_mode,
        "candidate_team_count": len(scenarios.team_ids),
        "entrant_team_count": policy.entrant_team_count,
        "seeding_method": scenarios.seeding_method,
    }
    if any(eligibility_evidence.get(key) != value for key, value in expected_eligibility.items()):
        raise MainSolverReleaseError("Main 候选 Team 证据摘要与 Scenario 不一致")
    if pointer is not None and (
        pointer["eligibility_mode"] != scenarios.eligibility_mode
        or int(pointer["candidate_team_count"]) != len(scenarios.team_ids)
    ):
        raise MainSolverReleaseError("Main 发布清单与候选 Team 模式不一致")
    names = [(int(row["team_id"]), str(row["name"])) for row in payload.get("team_names", [])]
    if tuple(team_id for team_id, _ in names) != scenarios.team_ids:
        raise MainSolverReleaseError("Main 发布队伍顺序与 Scenario 不一致")
    expected_names = [(team_id, group_context.team_names.get(team_id)) for team_id in scenarios.team_ids]
    if names != expected_names:
        raise MainSolverReleaseError("Main 发布队伍身份与稳定 ID 清单不一致")
    if group_context.roll_rules.main_rolls != 30:
        raise MainSolverReleaseError("Main 发布要求客户端规则为 30 次 Roll")
    title_evidence = None
    title_payload = payload.get("title_evidence")
    if title_payload is not None:
        if not isinstance(title_payload, Mapping):
            raise MainSolverReleaseError("Main Title 证据格式无效")
        try:
            title_evidence = validate_main_title_runtime_evidence(
                title_payload,
                as_of=str(payload["as_of"]),
                pool_result=pool_result,
                team_ids=scenarios.team_ids,
                scenario_sha256=scenarios.semantic_hash,
            )
        except ValueError as error:
            raise MainSolverReleaseError(str(error)) from error
        if provenance.get("title_evidence_sha256") != title_evidence["evidence_sha256"]:
            raise MainSolverReleaseError("Main Title 证据来源身份不一致")
    elif provenance.get("title_evidence_sha256") is not None:
        raise MainSolverReleaseError("Main Title 证据正文缺失")
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise MainSolverReleaseError("Main 发布警告字段无效")
    terminal = MainTerminalEvaluator(
        pool_result,
        scenarios,
        group_context.canonical_rules,
    )
    return MainCurrentAdvisorContext(
        as_of=str(payload["as_of"]),
        roll_rules=group_context.roll_rules,
        terminal=terminal,
        scenario_count=len(scenarios.scenario_ids),
        team_names=dict(names),
        strategy_catalog=strategy_catalog,
        title_evidence=title_evidence,
        eligibility_mode=scenarios.eligibility_mode,
        warnings=tuple(warnings),
    )


def write_main_solver_release_bundle(
    group_context: CurrentAdvisorContext,
    scenarios: MainScenarioSet,
    *,
    lock_at: str,
    pool_result: PoolBuildResult | None = None,
    additional_warnings: tuple[str, ...] = (),
    eligibility_evidence: Mapping[str, Any] | None = None,
    title_evidence: Mapping[str, Any] | None = None,
    output_path: Path | None = None,
    paths: ProjectPaths = PATHS,
) -> MainSolverReleaseWriteResult:
    """Publish a usable projected or actual-eight Main runtime bundle."""

    policy = load_main_solver_policy(paths.config / "models" / "fantasy-main-current-screen-advisor-v1.json")
    strategy_catalog = load_main_advice_strategy_catalog(
        paths.config / "models" / "fantasy-main-advice-strategies-v1.json"
    )
    if (
        scenarios.policy_id != policy.policy_id
        or len(scenarios.scenario_ids) != policy.scenario_count
        or scenarios.seed != policy.seed
    ):
        raise MainSolverReleaseError("Main Scenario 与当前冻结策略不一致")
    expected_candidates = (
        policy.projected_candidate_team_count
        if scenarios.eligibility_mode == "projected"
        else policy.actual_candidate_team_count
    )
    if len(scenarios.team_ids) != expected_candidates:
        raise MainSolverReleaseError("Main Scenario 候选 Team 数与当前策略不一致")
    effective_pool = pool_result or group_context.pool_result
    MainTerminalEvaluator(effective_pool, scenarios, group_context.canonical_rules)
    validated_title_evidence = None
    if title_evidence is not None:
        if scenarios.eligibility_mode != "actual":
            raise MainSolverReleaseError("Main Title runtime evidence is restricted to actual eligibility")
        try:
            validated_title_evidence = validate_main_title_runtime_evidence(
                title_evidence,
                as_of=scenarios.as_of,
                pool_result=effective_pool,
                team_ids=scenarios.team_ids,
                scenario_sha256=scenarios.semantic_hash,
            )
        except ValueError as error:
            raise MainSolverReleaseError(str(error)) from error
    names = [
        {"team_id": team_id, "name": group_context.team_names[team_id]} for team_id in scenarios.team_ids
    ]
    body = {
        "schema_version": MAIN_SOLVER_RELEASE_SCHEMA_VERSION,
        "release_id": MAIN_SOLVER_RELEASE_ID,
        "period": "main",
        "as_of": scenarios.as_of,
        "policy": policy.model_dump(mode="json"),
        "advice_strategy_catalog": strategy_catalog.model_dump(mode="json"),
        "provenance": {
            "source_version": source_version(paths),
            "source_tree_sha256": source_tree_hash(paths),
            "policy_sha256": sha256_json(policy.model_dump(mode="json")),
            "advice_strategy_catalog_sha256": strategy_catalog.semantic_hash,
            "pool_set_sha256": effective_pool.semantic_hash,
            "canonical_rules_sha256": sha256_json(group_context.canonical_rules),
            "tournament_manifest_sha256": sha256_file(paths.tournament),
            "scenario_sha256": scenarios.semantic_hash,
            "model_sha256": scenarios.model_sha256,
            **(
                {"title_evidence_sha256": validated_title_evidence["evidence_sha256"]}
                if validated_title_evidence is not None
                else {}
            ),
        },
        "runtime_contract": {
            "accepted_input": "confirmed-main-roll-state-v1",
            "contains_raw_data": False,
            "contains_ocr": False,
            "contains_screen_capture": False,
            "contains_dota_client_control": False,
            "future_offer_generation": "g-lite-only-bounded-primary-model-sampling-v1",
        },
        "team_names": names,
        "eligibility_evidence": {
            "mode": scenarios.eligibility_mode,
            "candidate_team_count": len(scenarios.team_ids),
            "entrant_team_count": policy.entrant_team_count,
            "seeding_method": scenarios.seeding_method,
            **dict(eligibility_evidence or {}),
        },
        "pool_result": _pool_result_payload(effective_pool),
        "scenarios": _scenario_payload(scenarios),
        "title_evidence": validated_title_evidence,
        "warnings": [
            "Main Operation #24 的目标概率采用显式假设：均匀选择两个不同槽提升、另一个不同槽降低；"
            "客户端仅公开了操作名与 All target，尚无逐次出率样本。",
            "Main 出场 Series 数来自完整双败 bracket 情景；单个 Series 的 Fantasy 表现仍以完整历史"
            " BO2/BO3 块为 proxy，不声称精确重建可能的 BO5 局数。",
            "Web 默认使用 G；G-Lite 仅在近似平手时按冻结 seed 与主出率模型生成 4 个"
            "下一轮样本，每局最多触发 4 次，且仍标记为未完成独立 confirmation。",
            *(
                validated_title_evidence["warnings"]
                if validated_title_evidence is not None
                else ["Main Title runtime evidence is unavailable in this release."]
            ),
            *(
                [
                    "当前为预测晋级模式：16 支候选队按 Group 联合情景缩成每个情景的 8 支 Main "
                    "参赛队；尚未晋级的队在该情景中记 0 分。",
                    "预测晋级模式中的 Main 种子按 Group 结果类别、Team-strength 顺序构造，属于"
                    "显式 proxy；实际八队与种子录入并刷新赛后数据后会被替换。",
                ]
                if scenarios.eligibility_mode == "projected"
                else ["当前为实际八队模式；候选 Team 已按正式 Main 种子缩减。"]
            ),
            *additional_warnings,
        ],
    }
    release_sha256 = sha256_json(body)
    envelope = {**body, "release_sha256": release_sha256}
    compressed = zstd.ZstdCompressor(level=19, write_checksum=True, write_content_size=True).compress(
        canonical_json(envelope)
    )
    if output_path is None:
        cutoff = scenarios.as_of.replace("-", "").replace(":", "")
        destination = (
            paths.root
            / "deploy"
            / "runtime"
            / "releases"
            / f"main-roll-{cutoff}-{release_sha256[:12]}.json.zst"
        ).resolve()
    else:
        destination = output_path.resolve()
    runtime_root = (paths.root / "deploy" / "runtime").resolve()
    if not destination.is_relative_to(runtime_root):
        raise MainSolverReleaseError("Main 发布文件必须位于 deploy/runtime 下")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.read_bytes() != compressed:
        raise MainSolverReleaseError("不可变 Main 发布文件已存在但内容不同")
    if not destination.is_file():
        destination.write_bytes(compressed)
    file_sha256 = sha256_bytes(compressed)
    _manifest_path(destination).write_text(
        f"{file_sha256}  {destination.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    pointer_path = default_main_solver_pointer_path(paths)
    pointer = {
        "schema_version": MAIN_SOLVER_POINTER_SCHEMA_VERSION,
        "release_schema_version": MAIN_SOLVER_RELEASE_SCHEMA_VERSION,
        "release_id": MAIN_SOLVER_RELEASE_ID,
        "period": "main",
        "status": "provisional" if scenarios.eligibility_mode == "projected" else "ready",
        "eligibility_mode": scenarios.eligibility_mode,
        "candidate_team_count": len(scenarios.team_ids),
        "entrant_team_count": policy.entrant_team_count,
        "as_of": scenarios.as_of,
        "lock_at": lock_at,
        "file": destination.relative_to(runtime_root).as_posix(),
        "bytes": len(compressed),
        "file_sha256": file_sha256,
        "release_sha256": release_sha256,
        "reason": (
            "Main 五槽计算已启用；当前 16 队通过预测晋级情景参与，正式名单形成后缩减为实际八队。"
            if scenarios.eligibility_mode == "projected"
            else "Main 五槽计算使用已确认并按种子排序的实际八队。"
        ),
    }
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return MainSolverReleaseWriteResult(
        path=destination,
        pointer_path=pointer_path,
        file_sha256=file_sha256,
        release_sha256=release_sha256,
        bytes=len(compressed),
    )


def main_solver_team_options(
    context: MainCurrentAdvisorContext,
    group_context: CurrentAdvisorContext | None = None,
) -> dict[str, tuple[tuple[int, str], ...]]:
    terminal_pool = getattr(context.terminal, "pool_result", None)
    if terminal_pool is None:
        if group_context is None:
            raise MainSolverReleaseError("Main Team options require an aligned Fantasy sample pool")
        terminal_pool = group_context.pool_result
    available = {(pool.target_team_id, pool.role) for pool in terminal_pool.pools}
    return {
        role: tuple(
            (team_id, name) for team_id, name in context.team_names.items() if (team_id, role) in available
        )
        for role in ROLE_IDS
    }


__all__ = [
    "MAIN_SOLVER_RELEASE_ID",
    "MainSolverReadiness",
    "MainSolverReleaseError",
    "MainSolverReleasePending",
    "default_main_solver_pointer_path",
    "load_main_solver_release_context",
    "load_main_solver_policy",
    "main_solver_readiness",
    "main_solver_team_options",
    "write_main_solver_release_bundle",
]
