"""Reproducible actual-eight Main Fantasy player publications."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from ti_predictor.config import load_team_strength_policy, load_tournament_manifest
from ti_predictor.fantasy.main_solver_release import load_main_solver_release_context
from ti_predictor.fantasy.scenarios import (
    ROLE_IDS,
    BootstrapScenarioPolicy,
    PoolBuildResult,
)
from ti_predictor.fantasy.solver_release import load_solver_release_context
from ti_predictor.fantasy.title import build_title_analysis, parse_title_hero_categories
from ti_predictor.fantasy.title_reporting import _load_match_features, _raw_capture_index
from ti_predictor.fantasy.valuation import (
    build_stat_forecast_package,
    cluster_bootstrap_stat_intervals,
)
from ti_predictor.forecasting import _available_by_as_of
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import rule_snapshot_at
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import ForecastRun, StrictModel, as_utc
from ti_predictor.storage import read_parquet_if_exists

MAIN_PUBLICATION_POLICY_FILENAME = "fantasy-main-publication-v1.json"
MAIN_STAT_REPORT_FILENAME = "main-stat-team-top3-publication.md"
MAIN_TITLE_REPORT_FILENAME = "main-fantasy-title-report.md"

_ROLE_LABELS = {"core": "核心位", "mid": "中单", "support": "辅助位"}
_COLOR_LABELS = {"red": "红色", "blue": "蓝色", "green": "绿色"}
_ROLE_COLOR_ORDER = {
    ("core", "red"): 0,
    ("core", "green"): 1,
    ("mid", "red"): 2,
    ("mid", "blue"): 3,
    ("mid", "green"): 4,
    ("support", "blue"): 5,
    ("support", "green"): 6,
}
_GRADE_LABELS = {
    "hard-protect": "一定保留",
    "keep": "可以保留",
    "conditional-reroll": "可以改善",
    "priority-repair": "优先改善",
}


class MainPublicationPolicy(StrictModel):
    schema_version: Literal[1]
    policy_id: str = Field(min_length=1)
    period: Literal["main"]
    eligibility_mode: Literal["actual"]
    team_count: Literal[8]
    scenario_count: int = Field(gt=0)
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    bootstrap_seed: int = Field(ge=0)
    bootstrap: BootstrapScenarioPolicy


@dataclass(frozen=True)
class MainPublicationResult:
    run: ForecastRun
    run_path: Path
    evidence_path: Path
    stat_report_path: Path
    title_report_path: Path
    evidence: dict[str, Any]


def load_main_publication_policy(path: Path) -> MainPublicationPolicy:
    return MainPublicationPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def subset_actual_main_pools(
    pool_result: PoolBuildResult,
    *,
    team_ids: tuple[int, ...],
) -> PoolBuildResult:
    expected = [(team_id, role) for team_id in team_ids for role in ROLE_IDS]
    pool_by_key = pool_result.by_key()
    if any(key not in pool_by_key for key in expected):
        raise ValueError("Main publication requires every actual Team/role pool in seed order")
    selected = tuple(pool_by_key[key] for key in expected)
    semantic_hash = sha256_json(
        {
            "period": "main",
            "eligibility_mode": "actual",
            "parent_pool_set_sha256": pool_result.semantic_hash,
            "team_ids": team_ids,
            "pools": [pool.semantic_hash for pool in selected],
        }
    )
    audit = {
        **pool_result.audit,
        "period": "main",
        "eligibility_mode": "actual",
        "team_ids": list(team_ids),
        "team_count": len(team_ids),
        "pool_count": len(selected),
        "parent_pool_set_sha256": pool_result.semantic_hash,
        "pool_set_sha256": semantic_hash,
        "pools": [
            row
            for row in pool_result.audit.get("pools", [])
            if int(row.get("target_team_id", -1)) in set(team_ids)
        ],
        "team_role_availability": [
            row
            for row in pool_result.audit.get("team_role_availability", [])
            if int(row.get("target_team_id", -1)) in set(team_ids)
        ],
        "unavailable_team_role_count": 0,
    }
    return PoolBuildResult(pools=selected, audit=audit, semantic_hash=semantic_hash)


def _team_cell(row: Mapping[str, Any], team_names: Mapping[int, str]) -> str:
    team_id = int(row["team_id"])
    name = _escape_cell(team_names.get(team_id, str(team_id)))
    return (
        f"{name}<br>"
        f"平均分 {float(row['point_mean']):.1f} · 低迷分 {float(row['point_cvar10']):.1f}<br>"
        f"样本 {int(row['series_blocks'])} 个完整系列赛 · "
        f"落后第一 {100.0 * float(row['gap_to_point_best_fraction']):.2f}%<br>"
        f"第一稳定率 {100.0 * float(row['rank1_probability']):.1f}% · "
        f"前三稳定率 {100.0 * float(row['top3_probability']):.1f}%"
    )


def render_main_stat_team_top3_markdown(
    evidence: Mapping[str, Any],
    *,
    team_names: Mapping[int, str],
) -> str:
    """Render the complete actual-eight Main Stat and Team Top-3 table."""

    bootstrap = evidence.get("cluster_bootstrap")
    forecasts = evidence.get("stat_forecasts")
    if not isinstance(bootstrap, Mapping) or not isinstance(forecasts, Mapping):
        raise ValueError("Main Stat report requires forecasts and cluster bootstrap evidence")
    rankings = bootstrap.get("team_rankings")
    if not isinstance(rankings, Mapping) or int(rankings.get("top_k", 0)) != 3:
        raise ValueError("Main Stat report requires a frozen Team Top 3")
    ranking_rows = rankings.get("rows")
    forecast_rows = forecasts.get("rows")
    if not isinstance(ranking_rows, list) or not isinstance(forecast_rows, list):
        raise ValueError("Main Stat report evidence rows are missing")

    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in ranking_rows:
        key = (str(row["role"]), str(row["color"]), str(row["stat_id"]))
        grouped.setdefault(key, []).append(row)
    forecast_by_key = {
        (str(row["role"]), str(row["color"]), str(row["stat_id"])): row for row in forecast_rows
    }
    for key in forecast_by_key:
        point_top3 = sorted(grouped.get(key, ()), key=lambda row: int(row["point_rank"]))[:3]
        if [int(row["point_rank"]) for row in point_top3] != [1, 2, 3]:
            raise ValueError(f"Main Stat Top 3 is incomplete for {key}")
    boundary_by_key = {
        (str(row["role"]), str(row["color"]), str(row["stat_id"])): bool(row["boundary"])
        for row in bootstrap.get("rows", ())
    }
    priority_by_key: dict[tuple[str, str, str], tuple[str, float]] = {}
    forecast_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in forecast_rows:
        forecast_groups.setdefault((str(row["role"]), str(row["color"])), []).append(row)
    for group_rows in forecast_groups.values():
        best = max(group_rows, key=lambda row: float(row["relative_to_best"]))
        best_is_hard = float(best["runner_up_mean"]) < 0.44 * float(best["best_team_mean"])
        for row in group_rows:
            relative = float(row["relative_to_best"])
            if row is best and best_is_hard:
                grade = "hard-protect"
            elif relative >= 0.846:
                grade = "keep"
            elif relative >= 0.44:
                grade = "conditional-reroll"
            else:
                grade = "priority-repair"
            priority_by_key[(str(row["role"]), str(row["color"]), str(row["stat_id"]))] = (
                grade,
                relative,
            )
    boundary_count = sum(boundary_by_key.get(key, False) for key in forecast_by_key)
    tight_top2 = sum(
        float(row["gap_to_point_best_fraction"]) < 0.01 for row in ranking_rows if int(row["point_rank"]) == 2
    )
    tight_top3 = sum(
        float(row["gap_to_point_best_fraction"]) < 0.02 for row in ranking_rows if int(row["point_rank"]) == 3
    )
    weighting = evidence["weighting"]
    team_list = "、".join(team_names[team_id] for team_id in evidence["team_ids"])
    lines = [
        "# Main Fantasy 各 Stat 推荐队伍 Top 3",
        "",
        f"数据截止：`{evidence['as_of']}` · 实际 Main 八队 · "
        f"排名稳定性检查：{int(bootstrap['replicates'])} 次完整系列赛分组重采样",
        "",
        f"参赛池：{team_list}。每队核心位、中单、辅助位均可用，共 24 个队伍×位置池。",
        "",
        f"权重：精确版本 `{weighting['exact_patch_name']}` 为同条件当前大版本其他小版本的 "
        f"{float(weighting['exact_patch_multiplier']):g} 倍；本届 TI 已结束的小组赛与突围赛再按 "
        f"{float(weighting['current_event_stage_multiplier']):g} 倍计入 Elo 与 Fantasy 各自的证据通道。"
        "赛事级别和 60 天半衰期继续生效，各乘数相乘而非互相替代。",
        "",
        "每项 Stat 按 Main 256 条完整双败路径中的预测平均分列出前三队。低迷分是最差 10% "
        "情形的平均分；稳定率来自 400 次完整 Series 分组重采样，不是未来真实排名概率。",
        "",
        "## 队名和五格该怎样理解",
        "",
        "队名只代表当前小标题对应的位置组合：核心和辅助各取两名稳定选手的单局均值，中单取一名。"
        "历史按稳定选手 ID 连接，并只保留该位置组合共同打完整个系列赛的记录。",
        "",
        "Main 每面战旗有五格；同一面五格最终必须匹配同一支队伍。这里每项 Stat 的 Top 3 只是"
        "单格候选，不能把五行第一名拼成一面战旗。正式选择应让 G/G-Lite 对完整五格重新做同队匹配。",
        "",
        "## 基础建议",
        "",
        "- **一定保留**：Stat 排名第 1，且该 Stat 的队伍第 2 名预测平均贡献低于第 1 名的 44%；",
        "- **可以保留**：未触发“一定保留”，且相对强度不低于 84.6；",
        "- **可以改善**：相对强度从 44（含）到 84.6（不含）；",
        "- **优先改善**：相对强度低于 44。",
        "",
        "这些标签是查表优先级，不是固定 Roll 指令。五格联动、剩余次数、Quality、Trait、"
        "当前三个选项和同队匹配都可能改变本次动作。",
        "",
        "## 稳定性摘要",
        "",
        f"- {len(forecast_by_key)} 个位置/颜色/Stat 行中，{boundary_count} 行的 95% 区间跨分档线；",
        f"- {tight_top2} 行前两名差距小于 1%，{tight_top3} 行第一与第三差距小于 2%；",
        "- 差距很小时把前三都当候选；“分档边界”表示样本扰动可能改变基础标签，不是数据错误。",
        "",
    ]
    ordered = sorted(
        forecast_rows,
        key=lambda row: (
            _ROLE_COLOR_ORDER[(str(row["role"]), str(row["color"]))],
            -float(row["relative_to_best"]),
            str(row["stat_id"]),
        ),
    )
    current_group: tuple[str, str] | None = None
    stat_rank = 0
    for forecast in ordered:
        key = (str(forecast["role"]), str(forecast["color"]), str(forecast["stat_id"]))
        group = key[:2]
        if group != current_group:
            if current_group is not None:
                lines.append("")
            lines.extend(
                [
                    f"## {_ROLE_LABELS[group[0]]} · {_COLOR_LABELS[group[1]]}",
                    "",
                    "| Stat 排名 | Stat | 基础建议 | 分档状态 | 第 1 | 第 2 | 第 3 |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            current_group = group
            stat_rank = 0
        stat_rank += 1
        top3 = sorted(grouped[key], key=lambda row: int(row["point_rank"]))[:3]
        grade, relative = priority_by_key[key]
        stability = "分档边界" if boundary_by_key.get(key, False) else "分档稳定"
        lines.append(
            f"| {stat_rank} | `{key[2]}` | {_GRADE_LABELS[grade]}<br>"
            f"相对强度 {100.0 * relative:.1f} | {stability} | "
            f"{_team_cell(top3[0], team_names)} | {_team_cell(top3[1], team_names)} | "
            f"{_team_cell(top3[2], team_names)} |"
        )
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "本表绑定当前 actual 八队、Main 求解发布包、256 条双败情景和数据截止时间。阵容、"
            "规则或样本变化后必须重新生成；projected 16 队结果不得与本表混用。Title 另表计算，"
            "不会被这些 Stat 排名自动决定。",
            "",
        ]
    )
    return "\n".join(lines)


def render_main_title_markdown(payload: Mapping[str, Any]) -> str:
    analysis = payload["title_analysis"]
    prefix_rows = analysis["prefixes"]
    suffix_rows = analysis["suffixes"]
    prefix_default = next(
        row for row in prefix_rows if row["id"] == analysis["recommendation"]["default_prefix"]
    )
    suffix_default = next(
        row for row in suffix_rows if row["id"] == analysis["recommendation"]["default_suffix"]
    )
    role_lines = []
    for role in ROLE_IDS:
        row = analysis["prefixes_by_role"][role][0]
        role_lines.append(
            f"- {_ROLE_LABELS[role]}：**{row['name']}**（纸面 +{row['paper_expected_bonus_percent']:.2f}%）"
        )
    lines = [
        "# TI 2026 Main Fantasy Title 分析与推荐",
        "",
        f"数据截止：`{payload['as_of']}`。范围：实际八队的 24 个队伍×位置池。",
        "",
        "## 直接结论",
        "",
        f"不知道三面最终战旗时，默认选 **{prefix_default['name']} + {suffix_default['name']}**。"
        "Title 免费更换，因此应先完成三面五格战旗和队伍选择，再按实际三个队伍复查。",
        "",
        "## Prefix 完整排名",
        "",
        "| 排名 | Prefix | 触发条件 | 触发率 | 纸面平均加成 | 适配池数 | 判断 |",
        "| ---: | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in prefix_rows:
        judgment = (
            "默认首选" if row["rank"] == 1 else ("接近，可按阵容反超" if row["rank"] <= 5 else "通常不优先")
        )
        lines.append(
            f"| {row['rank']} | **{row['name']}** | {row['label']} | {row['trigger_rate']:.1%} | "
            f"+{row['paper_expected_bonus_percent']:.2f}% | {row['best_pool_count']}/{row['pool_count']} | "
            f"{judgment} |"
        )
    lines.extend(
        [
            "",
            "纸面平均加成只是触发率×客户端标示加成，尚未与具体五格、Quality、Trait、"
            "最佳 Series 筛选做联合优化。按位置单独看：",
            "",
            *role_lines,
            "",
            "最终只能选择一个 Prefix；分位置结果只用来解释为何实际队伍组合可能改变默认答案。",
            "",
            "## Suffix 完整排名",
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
            judgment = (
                "默认首选" if row["rank"] == 1 else ("弱队时可反超" if row["id"] == "loser" else "备选")
            )
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
            rank, trigger, lift, judgment = "—", "不可可靠观测", "—", "暂不排名"
        lines.append(
            f"| {rank} | **{row['name']}** | {row['label']} | {trigger} | {lift} | "
            f"{row['best_pool_count']}/{row['pool_count']} | {judgment} |"
        )
    weighting = payload["weighting"]
    break_even = analysis["recommendation"]["underdog_break_even_loss_rate"]
    lines.extend(
        [
            "",
            "## Main 特有边界",
            "",
            "Clutch 当前仍用历史完整 BO3 中打到第三局的加权比例"
            f"（{payload['diagnostics']['mean_bo3_reaches_game3']:.1%}）"
            f"折算，得到约 {suffix_default['trigger_rate']:.1%} 的地图触发率。双败总决赛可能为 BO5，"
            "现有 Main Fantasy 路径尚未按 BO5 单独建模，所以这是明确的 BO3 proxy，不冒充完整赛制精算。",
            "",
            f"Underdog 只有在所选队伍预期输图率高于约 {break_even:.1%} 时，纸面值才可能超过 Clutch。"
            "本表对 24 个池等权汇总；最终若选择明显弱队，应单独复查。",
            "",
            "号角前/10 分钟后一血两个客户端条件仍存在可见文案与内部字段冲突，继续排除；"
            "泉水内死亡缺少可靠逐事件位置证据，继续保持 unavailable。",
            "",
            "## 数据与可信度",
            "",
            f"- 英雄映射：{payload['hero_source']['mapped_heroes']} 名英雄、8 类 Prefix；",
            f"- 历史输入：{payload['raw_detail_audit']['raw_match_count']} 场不可变原始详情、"
            f"{analysis['complete_series_blocks_across_pools']} 个队伍×位置完整 Series blocks；",
            f"- 权重：`{weighting['exact_patch_name']}` 精确版本 ×{weighting['exact_patch_multiplier']:g}；"
            f"本届 TI 已结束阶段 ×{weighting['current_event_stage_multiplier']:g}；"
            "赛事级别与 60 天半衰期继续生效；",
            "- Prefix 为中等偏低确定度且阵容相关；Suffix 为中等确定度；两者都不是最终结算增幅保证；",
            "- 当前 G/G-Lite 求解器仍只优化战旗和队伍，不把 Title 联合塞入终局价值；"
            "本表是免费改 Title 的独立依据。",
            "",
        ]
    )
    return "\n".join(lines)


def generate_main_publication_evidence(
    *,
    as_of,
    hero_source_path: Path,
    paths: ProjectPaths = PATHS,
) -> MainPublicationResult:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("Main publication requires an explicit UTC as_of")
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    policy_path = paths.config / "models" / MAIN_PUBLICATION_POLICY_FILENAME
    policy = load_main_publication_policy(policy_path)
    group_context = load_solver_release_context(paths=paths)
    main_context = load_main_solver_release_context(group_context, paths=paths)
    scenarios = main_context.terminal.scenario_set
    if main_context.as_of != cutoff_text:
        raise ValueError("Main publication as_of must equal the frozen Main solver release cutoff")
    if main_context.eligibility_mode != policy.eligibility_mode:
        raise ValueError("Main publication requires the actual-eight solver release")
    if len(main_context.team_names) != policy.team_count:
        raise ValueError("Main publication Team count differs from its frozen policy")
    if len(scenarios.scenario_ids) != policy.scenario_count:
        raise ValueError("Main publication Scenario count differs from its frozen policy")

    team_ids = tuple(main_context.team_names)
    pool_result = subset_actual_main_pools(main_context.terminal.pool_result, team_ids=team_ids)
    stat_forecasts = build_stat_forecast_package(
        pool_result,
        scenarios,
        main_context.terminal.canonical_rules,
        cvar_alpha=policy.cvar_alpha,
    )
    bootstrap = cluster_bootstrap_stat_intervals(
        pool_result,
        scenarios,
        stat_forecasts,
        main_context.terminal.canonical_rules,
        policy,
        seed=policy.bootstrap_seed,
        include_team_rankings=True,
    )

    hero_source = hero_source_path.resolve()
    if not hero_source.is_file():
        raise FileNotFoundError(f"Valve npc_heroes.txt is unavailable: {hero_source}")
    hero_content = hero_source.read_bytes()
    hero_categories = parse_title_hero_categories(hero_content.decode("utf-8", errors="replace"))
    evidence_paths = main_evidence_paths(paths, require=True)
    observations = _available_by_as_of(
        read_parquet_if_exists(evidence_paths.processed / "fantasy_performance_samples.parquet"), cutoff
    )
    matches = _available_by_as_of(
        read_parquet_if_exists(evidence_paths.processed / "matches.parquet"), cutoff
    )
    needed_match_ids = {
        match_id for pool in pool_result.pools for block in pool.blocks for match_id in block.match_ids
    }
    source_rows = observations.loc[
        observations["match_id"].isin(needed_match_ids), ["match_id", "source_sha256"]
    ].dropna()
    source_counts = source_rows.groupby("match_id")["source_sha256"].nunique()
    if source_counts.empty or source_counts.ne(1).any():
        raise ValueError("each Main Title match must map to one immutable raw source SHA-256")
    source_by_match = {
        int(row.match_id): str(row.source_sha256)
        for row in source_rows.drop_duplicates("match_id").itertuples(index=False)
    }
    if set(source_by_match) != needed_match_ids:
        missing = sorted(needed_match_ids - set(source_by_match))
        raise ValueError(f"Main Title matches lack raw source identities: {missing[:10]}")
    captures = _raw_capture_index(paths, set(source_by_match.values()), as_of=cutoff)
    match_features, raw_audit = _load_match_features(source_by_match, captures)
    series_types = {
        int(row.match_id): int(row.series_type)
        for row in matches.loc[matches["match_id"].isin(needed_match_ids), ["match_id", "series_type"]]
        .dropna()
        .itertuples(index=False)
    }
    title_analysis = build_title_analysis(
        pool_result,
        match_features,
        series_types,
        hero_categories,
        main_context.terminal.canonical_rules,
        team_names=dict(main_context.team_names),
    )
    bo3_values = [
        float(row["bo3_reaches_game3"])
        for row in title_analysis["pools"]
        if row["bo3_reaches_game3"] is not None
    ]
    if not bo3_values:
        raise ValueError("Main Title Clutch proxy has no complete historical BO3 evidence")

    manifest = load_tournament_manifest(paths.tournament)
    strength_policy = load_team_strength_policy(manifest, config_root=paths.config, period="main")
    exact_patch = strength_policy.current_exact_patch_weight
    stage_multiplier = strength_policy.fantasy_current_event_stage_multiplier
    if exact_patch is None or stage_multiplier is None:
        raise ValueError("Main publication requires frozen exact-patch and TI stage weights")
    weighting = {
        "exact_patch_name": exact_patch.patch_name,
        "exact_patch_multiplier": exact_patch.multiplier,
        "current_event_stage_multiplier": stage_multiplier,
        "time_half_life_days": strength_policy.time_half_life_days,
    }
    hero_counts = {
        item["id"]: sum(item["id"] in categories for categories in hero_categories.values())
        for item in main_context.terminal.canonical_rules["fantasy"]["coach"]["prefixes"]
    }
    pointer_path = paths.root / "deploy" / "runtime" / "main-current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    hero_metadata_path = hero_source.parents[2] / "metadata.json"
    hero_metadata = (
        json.loads(hero_metadata_path.read_text(encoding="utf-8")) if hero_metadata_path.is_file() else {}
    )
    evidence: dict[str, Any] = {
        "artifact_type": "ti2026_main_fantasy_player_publication_evidence",
        "schema_version": 1,
        "as_of": cutoff_text,
        "eligibility_mode": "actual",
        "team_ids": list(team_ids),
        "team_names": [
            {"team_id": team_id, "name": main_context.team_names[team_id]} for team_id in team_ids
        ],
        "policy": policy.model_dump(mode="json"),
        "weighting": weighting,
        "solver_release": {
            "release_sha256": pointer["release_sha256"],
            "file_sha256": pointer["file_sha256"],
            "scenario_sha256": scenarios.semantic_hash,
            "parent_pool_set_sha256": main_context.terminal.pool_result.semantic_hash,
            "actual_pool_set_sha256": pool_result.semantic_hash,
        },
        "pool_audit": pool_result.audit,
        "stat_forecasts": stat_forecasts,
        "cluster_bootstrap": bootstrap,
        "hero_source": {
            "resource": "scripts/npc/npc_heroes.txt",
            "path": hero_source.relative_to(paths.root).as_posix(),
            "sha256": sha256_file(hero_source),
            "bytes": len(hero_content),
            "client_build": hero_metadata.get("client_build"),
            "mapped_heroes": len(hero_categories),
            "category_hero_counts": hero_counts,
        },
        "raw_detail_audit": raw_audit,
        "diagnostics": {"mean_bo3_reaches_game3": sum(bo3_values) / len(bo3_values)},
        "title_analysis": title_analysis,
        "warnings": [
            "Main Title Clutch uses a historical BO3 proxy and does not separately model "
            "the possible BO5 grand final.",
            "Title paper bonuses are not jointly optimized with the five-slot terminal solver.",
            "G-Lite remains user-selected development-positive evidence and is not the default strategy.",
        ],
    }
    evidence["evidence_sha256"] = sha256_json(evidence)
    parameters = {
        "phase": "actual_eight_main_fantasy_player_publication_v1",
        "policy_sha256": sha256_file(policy_path),
        "solver_release_sha256": pointer["release_sha256"],
        "actual_pool_set_sha256": pool_result.semantic_hash,
        "scenario_sha256": scenarios.semantic_hash,
        "hero_source_sha256": sha256_file(hero_source),
    }
    run_id, hashes = make_run_id(
        kind="fantasy",
        as_of=cutoff,
        seed=policy.bootstrap_seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
    evidence_path = writer.write_json("main-fantasy-publication-evidence.json", evidence)
    stat_report_path = writer.write_text(
        MAIN_STAT_REPORT_FILENAME,
        render_main_stat_team_top3_markdown(evidence, team_names=main_context.team_names),
    )
    title_report_path = writer.write_text(MAIN_TITLE_REPORT_FILENAME, render_main_title_markdown(evidence))
    snapshot_result = rule_snapshot_at(cutoff, paths)
    snapshot = snapshot_result[0] if snapshot_result is not None else None
    run = ForecastRun(
        run_id=run_id,
        kind="fantasy",
        as_of=cutoff,
        created_at=cutoff,
        status="warning",
        seed=policy.bootstrap_seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=None if snapshot is None else snapshot.snapshot_id,
        rule_snapshot_sha256=None if snapshot is None else snapshot.snapshot_sha256,
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={"name": "actual_eight_main_fantasy_player_publication_v1", "parameters": parameters},
        profiles=[],
        outputs=[evidence_path.name, stat_report_path.name, title_report_path.name],
        warnings=list(evidence["warnings"]),
    )
    run_path = writer.write_run(run)
    return MainPublicationResult(
        run=run,
        run_path=run_path,
        evidence_path=evidence_path,
        stat_report_path=stat_report_path,
        title_report_path=title_report_path,
        evidence=evidence,
    )


__all__ = [
    "MAIN_STAT_REPORT_FILENAME",
    "MAIN_TITLE_REPORT_FILENAME",
    "MainPublicationPolicy",
    "MainPublicationResult",
    "generate_main_publication_evidence",
    "load_main_publication_policy",
    "render_main_stat_team_top3_markdown",
    "render_main_title_markdown",
    "subset_actual_main_pools",
]
