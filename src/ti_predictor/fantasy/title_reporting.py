"""Reproducible standalone evidence entry point for TI 2026 Fantasy Titles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ti_predictor.config import load_rules, load_team_strength_policy, load_tournament_manifest
from ti_predictor.fantasy.scenarios import build_series_block_pools, load_group_scenario_policy
from ti_predictor.fantasy.title import (
    MatchTitleFeatures,
    build_title_analysis,
    extract_match_title_features,
    parse_title_hero_categories,
)
from ti_predictor.forecasting import _available_by_as_of
from ti_predictor.hashing import sha256_bytes, sha256_file, sha256_json
from ti_predictor.models.evidence import build_evidence_set, ordered_patch_families
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import latest_rule_snapshot
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import ForecastRun, as_utc
from ti_predictor.storage import read_parquet_if_exists, timestamp_slug


@dataclass
class TitleEvidenceResult:
    run: ForecastRun
    run_path: Path
    evidence_path: Path
    report_path: Path
    evidence: dict[str, Any]


def _archive_hero_source(
    content: bytes,
    *,
    as_of: datetime,
    client_build: str | None,
    paths: ProjectPaths,
) -> tuple[Path, str]:
    source_hash = sha256_bytes(content)
    folder = paths.raw / "rules-title" / f"{timestamp_slug(as_of)}-{source_hash[:12]}"
    body_path = folder / "scripts" / "npc" / "npc_heroes.txt"
    metadata_path = folder / "metadata.json"
    metadata = {
        "source": "dota_client",
        "resource": "scripts/npc/npc_heroes.txt",
        "observed_at": as_of.isoformat().replace("+00:00", "Z"),
        "client_build": client_build,
        "content_sha256": source_hash,
        "bytes": len(content),
    }
    serialized = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if folder.exists():
        if (
            not body_path.is_file()
            or body_path.read_bytes() != content
            or not metadata_path.is_file()
            or metadata_path.read_text(encoding="utf-8") != serialized
        ):
            raise FileExistsError(f"immutable Title rule capture collision: {folder}")
    else:
        body_path.parent.mkdir(parents=True, exist_ok=False)
        body_path.write_bytes(content)
        metadata_path.write_text(serialized, encoding="utf-8")
    return body_path, source_hash


def _raw_capture_index(
    paths: ProjectPaths,
    source_hashes: set[str],
    *,
    as_of: datetime,
) -> dict[str, Path]:
    captures: dict[str, list[Path]] = {}
    root = paths.raw / "opendota" / "matches"
    for metadata_path in root.glob("*/*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            source_hash = str(metadata["content_sha256"])
            fetched_at = as_utc(metadata["fetched_at"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if source_hash not in source_hashes or fetched_at is None or fetched_at > as_of:
            continue
        body_path = metadata_path.with_name("response.json")
        if body_path.is_file():
            captures.setdefault(source_hash, []).append(body_path)
    return {source_hash: sorted(paths_for_hash)[0] for source_hash, paths_for_hash in captures.items()}


def _load_match_features(
    source_by_match: dict[int, str],
    capture_by_hash: dict[str, Path],
) -> tuple[dict[int, MatchTitleFeatures], dict[str, Any]]:
    features: dict[int, MatchTitleFeatures] = {}
    first_blood_observed = 0
    tormentor_observed = 0
    for match_id in sorted(source_by_match):
        source_hash = source_by_match[match_id]
        body_path = capture_by_hash.get(source_hash)
        if body_path is None:
            raise ValueError(f"raw capture {source_hash} for match {match_id} was unavailable at as_of")
        content = body_path.read_bytes().rstrip(b"\n")
        if sha256_bytes(content) != source_hash:
            raise ValueError(f"raw match {match_id} content differs from metadata SHA-256")
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError(f"raw match {match_id} is not a JSON object")
        feature = extract_match_title_features(payload, expected_match_id=match_id)
        features[match_id] = feature
        first_blood_observed += feature.first_blood_time_seconds is not None
        tormentor_observed += feature.any_player_died_to_tormentor is not None
    count = len(features)
    return features, {
        "raw_match_count": count,
        "first_blood_objective_matches": first_blood_observed,
        "first_blood_objective_coverage": first_blood_observed / count if count else 0.0,
        "parsed_tormentor_matches": tormentor_observed,
        "parsed_tormentor_coverage": tormentor_observed / count if count else 0.0,
        "source_hash_set_sha256": sha256_json(sorted(source_by_match.values())),
    }


def render_title_evidence_markdown(payload: dict[str, Any]) -> str:
    analysis = payload["analysis"]
    exact_patch_weight = payload["evidence_weight_audit"]["current_exact_patch_weight"]
    prefix_rows = analysis["prefixes"]
    suffix_rows = analysis["suffixes"]
    prefix_default = next(
        row for row in prefix_rows if row["id"] == analysis["recommendation"]["default_prefix"]
    )
    suffix_default = next(
        row for row in suffix_rows if row["id"] == analysis["recommendation"]["default_suffix"]
    )
    screenshot_prefix = next(row for row in prefix_rows if row["id"] == "otherworldly")
    screenshot_suffix = next(row for row in suffix_rows if row["id"] == "early_first_blood")
    screenshot_paper = float(screenshot_prefix["paper_expected_bonus_percent"]) + float(
        screenshot_suffix["paper_expected_bonus_percent"]
    )
    default_paper = float(prefix_default["paper_expected_bonus_percent"]) + float(
        suffix_default["paper_expected_bonus_percent"]
    )
    lines = [
        "# TI 2026 梦幻挑战 Title 分析与推荐",
        "",
        f"数据截止：`{payload['as_of']}`。状态：**可发布的中等确定度建议；不是完整 P3 终局优化**。",
        "",
        "## 直接结论",
        "",
        f"不知道三面最终战旗时，默认选 **{prefix_default['name']} + {suffix_default['name']}**。",
        "Prefix 会明显依赖最后选了哪些队伍和位置；Suffix 的默认首选更稳定。Title 免费更换，",
        "所以应在三面战旗和队伍确定后再复查一次，而不是把默认答案当成永久固定答案。",
        "",
        "## Prefix 排名",
        "",
        "| 排名 | Prefix | 触发条件 | 触发率 | 纸面平均加成 | 适配池数 | 判断 |",
        "| ---: | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in prefix_rows:
        judgment = (
            "默认首选" if row["rank"] == 1 else ("接近，可按阵容反超" if row["rank"] <= 5 else "通常不优先")
        )
        lines.append(
            f"| {row['rank']} | **{row['name']}** | {row['label']} | "
            f"{row['trigger_rate']:.1%} | +{row['paper_expected_bonus_percent']:.2f}% | "
            f"{row['best_pool_count']}/{row['pool_count']} | {judgment} |"
        )
    lines.extend(
        [
            "",
            "这里的“纸面平均加成”是触发率乘以标题标出的加成。它还没有代入你实际三格 Stat、品质、",
            "Trait，也没有执行“每个 Series 只取最高两局、整期只取最佳 Series”的最终筛选。",
            "",
            "按位置单独看，当前中性第一分别是：",
            "",
        ]
    )
    role_labels = {"core": "核心位", "mid": "中单", "support": "辅助位"}
    for role, label in role_labels.items():
        row = analysis["prefixes_by_role"][role][0]
        lines.append(f"- {label}：**{row['name']}**（纸面 +{row['paper_expected_bonus_percent']:.2f}%）")
    lines.extend(
        [
            "",
            "由于最终只能选一个 Prefix，而不是三个位置各选一个，上述分位置结果只用来解释阵容依赖。",
            "48 个“队伍×位置”池中，默认第一并没有覆盖过半，因此 Prefix 只能给中等偏低确定度。",
            "",
            "## 你截图里的当前组合",
            "",
            "截图中当前是 **Otherworldly + the Flayed Twins Acolyte**。Otherworldly 综合第 3，",
            "属于可以继续用、但不是中性默认第一的 Prefix；Flayed Twins Acolyte 不仅纸面值低于",
            "Clutch，规则条件本身也有冲突，所以更应优先替换。",
            "",
            "只把两列纸面平均加成相加作量级参照、暂不算同时触发的交叉项时，截图组合约为",
            f"`+{screenshot_paper:.2f}%`，默认组合约为 `+{default_paper:.2f}%`，相差约 "
            f"`{default_paper - screenshot_paper:.2f}` 个百分点。这个差值不是最终结算",
            "保证，只用于说明为什么值得换。",
            "",
            "## Suffix 排名",
            "",
            "| 排名 | Suffix | 触发条件 | 触发率 | 纸面平均加成 | 适配池数 | 判断 |",
            "| ---: | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in suffix_rows:
        if row["status"] == "estimated":
            rank = str(row["rank"])
            trigger = f"{row['trigger_rate']:.1%}"
            lift = f"+{row['paper_expected_bonus_percent']:.2f}%"
            if row["rank"] == 1:
                judgment = "默认首选"
            elif row["id"] == "loser":
                judgment = "弱队/高输图率时可反超"
            else:
                judgment = "备选"
        elif row["status"] == "conflicted_excluded":
            rank = "—"
            trigger = "—" if row["trigger_rate"] is None else f"{row['trigger_rate']:.1%}"
            lift = (
                "—"
                if row["paper_expected_bonus_percent"] is None
                else f"+{row['paper_expected_bonus_percent']:.2f}%"
            )
            judgment = "客户端条件冲突，不用于推荐"
        else:
            rank = "—"
            trigger = "不可可靠观测"
            lift = "—"
            judgment = "暂不排名"
        lines.append(
            f"| {rank} | **{row['name']}** | {row['label']} | {trigger} | {lift} | "
            f"{row['best_pool_count']}/{row['pool_count']} | {judgment} |"
        )
    break_even = analysis["recommendation"]["underdog_break_even_loss_rate"]
    lines.extend(
        [
            "",
            "Group 按 BO3 估计；历史完整 BO3 约有 "
            f"{payload['diagnostics']['mean_bo3_reaches_game3']:.1%} 打到第三局，因此 Clutch 折算为约 "
            f"{suffix_default['trigger_rate']:.1%} 的地图触发率。Underdog 只有在所选队伍预期输图率高于约 "
            f"{break_even:.1%} 时，纸面值才可能超过 Clutch；本手册本来就优先选择强队，所以默认仍是 Clutch。",
            "",
            "一血早/晚两个选项保留了可见规则下的历史观察值，但客户端内部条件与玩家可见文案冲突，",
            "因此不能把这些数字当成发布级最优依据。所谓内部字段，是客户端 vdata 交给结算系统的",
            "统计项 ID 和阈值配置，不是可见的服务器计算函数。准备阶段为负数倒计时，所以号角前是",
            "一血时刻 < 0；号角后从 0:00 正计时，0:00–0:59 不属于号角前。当前没有代码证据能确认",
            "`before_1_minute` 是否把后一段也算入，也不能仅凭 `after_6_minutes` 这个名字推翻界面的",
            "10 分钟文字。泉水击杀缺少可靠的逐事件位置证据，保持不可用。",
            "",
            "## 可信度与使用方法",
            "",
            f"- 客户端英雄分类：{payload['hero_source']['mapped_heroes']} 名英雄，8 类 Prefix；"
            "这是当前客户端直接证据。",
            f"- 历史样本：{payload['raw_detail_audit']['raw_match_count']} 场原始比赛详情、"
            f"{analysis['complete_series_blocks_across_pools']} 个队伍×位置完整 Series blocks。",
            f"- 版本权重：当前精确版本 {exact_patch_weight['patch_name']} 的单局权重为同条件其他"
            f"当前大版本小版本的 {exact_patch_weight['multiplier']:g} 倍；上一大版本、赛事级别和"
            "60 天时间半衰期保持原值。",
            "- Prefix 默认答案：中等偏低确定度，最终队伍和位置会改变排名。",
            "- Suffix 默认答案：中等确定度；Clutch 的方向较稳，但纸面加成不是客户端最终结算增幅。",
            "- 最佳实践：先完成三面战旗与队伍选择，再免费调整 Title；若没有重新计算条件，就使用默认组合。",
            "",
            "## 与既有 P3 的关系",
            "",
            "这份报告补上的是可复现的 Title 速查与默认选择。既有 P3 仍没有把 Title 与每一面实际战旗、",
            "每个未来 Series 和最终取最高分规则做完整联合优化，所以其 `Coach/Title unavailable_excluded`",
            "状态没有被偷偷改写。",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_group_title_evidence(
    *,
    as_of,
    hero_source_path: Path,
    client_build: str | None = None,
    seed: int = 20260808,
    paths: ProjectPaths = PATHS,
) -> TitleEvidenceResult:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    hero_source = hero_source_path.resolve()
    if not hero_source.is_file():
        raise FileNotFoundError(f"Valve npc_heroes.txt is unavailable: {hero_source}")
    hero_content = hero_source.read_bytes()
    archived_hero_source, hero_source_hash = _archive_hero_source(
        hero_content,
        as_of=cutoff,
        client_build=client_build,
        paths=paths,
    )
    hero_text = hero_content.decode("utf-8", errors="replace")
    hero_categories = parse_title_hero_categories(hero_text)

    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    scenario_policy_path = paths.config / "models" / "fantasy-group-scenarios-v1.json"
    scenario_policy = load_group_scenario_policy(scenario_policy_path)
    matches_path = paths.processed / "matches.parquet"
    observations_path = paths.processed / "fantasy_performance_samples.parquet"
    patches_path = paths.processed / "patches.parquet"
    for required_path in (matches_path, observations_path, patches_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"Title evidence requires {required_path}")
    matches = _available_by_as_of(read_parquet_if_exists(matches_path), cutoff)
    observations = _available_by_as_of(read_parquet_if_exists(observations_path), cutoff)
    patches = _available_by_as_of(read_parquet_if_exists(patches_path), cutoff)
    patch_families = ordered_patch_families(patches, as_of=cutoff)
    if not patch_families:
        raise ValueError("no Dota patch family is available at as_of")
    target_patch_family = patch_families[-1]

    strength_policy = load_team_strength_policy(manifest, config_root=paths.config)
    fantasy_policy = strength_policy.model_copy(
        update={
            "policy_id": f"{strength_policy.policy_id}-fantasy-title-history",
            "evidence_scope": EvidenceScopePolicy(mode="global"),
        }
    )
    evidence = build_evidence_set(
        matches,
        patches,
        as_of=cutoff,
        policy=fantasy_policy,
        target_patch_family=target_patch_family,
    )
    blocking = [issue for issue in evidence.issues if issue.severity == "blocking"]
    if blocking:
        raise ValueError("Fantasy Title evidence is blocked: " + "; ".join(x.message for x in blocking))
    pool_result = build_series_block_pools(
        observations,
        matches,
        evidence.matches,
        manifest,
        rules,
        scenario_policy,
        as_of=cutoff,
    )

    needed_match_ids = {
        match_id for pool in pool_result.pools for block in pool.blocks for match_id in block.match_ids
    }
    source_rows = observations.loc[
        observations["match_id"].isin(needed_match_ids), ["match_id", "source_sha256"]
    ].dropna()
    source_counts = source_rows.groupby("match_id")["source_sha256"].nunique()
    if source_counts.empty or source_counts.ne(1).any():
        raise ValueError("each Title evidence match must map to one immutable raw source SHA-256")
    source_by_match = {
        int(row.match_id): str(row.source_sha256)
        for row in source_rows.drop_duplicates("match_id").itertuples(index=False)
    }
    if set(source_by_match) != needed_match_ids:
        missing = sorted(needed_match_ids - set(source_by_match))
        raise ValueError(f"Title evidence matches lack raw source identities: {missing[:10]}")
    captures = _raw_capture_index(paths, set(source_by_match.values()), as_of=cutoff)
    match_features, raw_audit = _load_match_features(source_by_match, captures)
    series_types = {
        int(row.match_id): int(row.series_type)
        for row in matches.loc[matches["match_id"].isin(needed_match_ids), ["match_id", "series_type"]]
        .dropna()
        .itertuples(index=False)
    }
    team_names = {int(team.team_id): team.name for team in manifest.teams}
    analysis = build_title_analysis(
        pool_result,
        match_features,
        series_types,
        hero_categories,
        rules,
        team_names=team_names,
    )
    mean_bo3_reaches_game3 = sum(
        float(row["bo3_reaches_game3"]) for row in analysis["pools"] if row["bo3_reaches_game3"] is not None
    ) / len(analysis["pools"])
    data_snapshot_sha256 = sha256_json(
        {
            "as_of": cutoff.isoformat().replace("+00:00", "Z"),
            "matches_sha256": sha256_file(matches_path),
            "observations_sha256": sha256_file(observations_path),
            "patches_sha256": sha256_file(patches_path),
            "rules_sha256": sha256_file(paths.rules),
            "manifest_sha256": sha256_file(paths.tournament),
            "scenario_policy_sha256": sha256_file(scenario_policy_path),
            "selected_match_ids_sha256": evidence.audit["selected_match_ids_sha256"],
            "weight_policy_sha256": evidence.audit["weight_policy_sha256"],
            "raw_source_hash_set_sha256": raw_audit["source_hash_set_sha256"],
            "hero_source_sha256": hero_source_hash,
            "target_patch_family": target_patch_family,
        }
    )
    hero_counts = {
        item["id"]: sum(item["id"] in categories for categories in hero_categories.values())
        for item in rules["fantasy"]["coach"]["prefixes"]
    }
    payload: dict[str, Any] = {
        "artifact_type": "ti2026_group_fantasy_title_evidence",
        "schema_version": 2,
        "as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "target_patch_family": target_patch_family,
        "evidence_weight_audit": evidence.audit,
        "data_snapshot_sha256": data_snapshot_sha256,
        "hero_source": {
            "resource": "scripts/npc/npc_heroes.txt",
            "sha256": hero_source_hash,
            "bytes": len(hero_content),
            "client_build": client_build,
            "archive_path": archived_hero_source.relative_to(paths.root).as_posix(),
            "mapped_heroes": len(hero_categories),
            "category_hero_counts": hero_counts,
        },
        "raw_detail_audit": raw_audit,
        "pool_audit": pool_result.audit,
        "diagnostics": {"mean_bo3_reaches_game3": mean_bo3_reaches_game3},
        "analysis": analysis,
        "warnings": [
            "Prefix default is pool-balanced and must be revisited after the final three banners are known.",
            "Paper expected bonus is map-level trigger rate times displayed bonus, not final "
            "period score lift.",
            "Client-visible and internal first-blood Title conditions conflict; both are "
            "excluded from ranking.",
            "Own-fountain deaths are unavailable from the governed match feature set.",
            "P3 production Coach status remains unavailable_excluded until full scenario-aligned "
            "candidates exist.",
        ],
    }
    payload["evidence_sha256"] = sha256_json(payload)
    parameters = {
        "phase": "standalone_group_fantasy_title_evidence_v2",
        "target_patch_family": target_patch_family,
        "weight_policy_sha256": evidence.audit["weight_policy_sha256"],
        "hero_source_sha256": hero_source_hash,
        "data_snapshot_sha256": data_snapshot_sha256,
        "paper_bonus_only": True,
    }
    run_id, hashes = make_run_id(
        kind="fantasy",
        as_of=cutoff,
        seed=seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
    evidence_path = writer.write_json("group-fantasy-title-evidence.json", payload)
    report_path = writer.write_text("group-fantasy-title-report.md", render_title_evidence_markdown(payload))
    snapshot_result = latest_rule_snapshot(paths)
    snapshot = snapshot_result[0] if snapshot_result is not None else None
    run = ForecastRun(
        run_id=run_id,
        kind="fantasy",
        as_of=cutoff,
        created_at=cutoff,
        status="warning",
        seed=seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=None if snapshot is None else snapshot.snapshot_id,
        rule_snapshot_sha256=None if snapshot is None else snapshot.snapshot_sha256,
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={"name": "standalone_group_fantasy_title_evidence_v2", "parameters": parameters},
        profiles=[],
        outputs=[evidence_path.name, report_path.name],
        warnings=list(payload["warnings"]),
    )
    run_path = writer.write_run(run)
    return TitleEvidenceResult(
        run=run,
        run_path=run_path,
        evidence_path=evidence_path,
        report_path=report_path,
        evidence=payload,
    )
