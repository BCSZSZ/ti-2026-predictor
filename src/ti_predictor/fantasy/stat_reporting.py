"""Human-readable reports for governed Group Fantasy Stat evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_ROLE_LABELS = {"core": "Core", "mid": "Mid", "support": "Support"}
_COLOR_LABELS = {"red": "Red", "blue": "Blue", "green": "Green"}
_ROLE_COLOR_ORDER = {
    ("core", "red"): 0,
    ("core", "green"): 1,
    ("mid", "red"): 2,
    ("mid", "blue"): 3,
    ("mid", "green"): 4,
    ("support", "blue"): 5,
    ("support", "green"): 6,
}


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _team_cell(row: Mapping[str, Any], team_names: Mapping[int, str]) -> str:
    team_id = int(row["team_id"])
    name = _escape_cell(team_names.get(team_id, str(team_id)))
    return (
        f"{name} (`{team_id}`)<br>"
        f"μ/C10={float(row['point_mean']):.1f} / {float(row['point_cvar10']):.1f}<br>"
        f"n={int(row['series_blocks'])} · Δ={100.0 * float(row['gap_to_point_best_fraction']):.2f}%<br>"
        f"P1={100.0 * float(row['rank1_probability']):.1f}% · "
        f"P3={100.0 * float(row['top3_probability']):.1f}%"
    )


def render_group_stat_team_top3_markdown(
    evidence: Mapping[str, Any],
    *,
    team_names: Mapping[int, str],
    run_id: str,
) -> str:
    """Render point-estimate Top 3 with team-rank bootstrap probabilities."""

    bootstrap = evidence.get("cluster_bootstrap")
    if not isinstance(bootstrap, Mapping):
        raise ValueError("Top 3 report requires cluster bootstrap evidence")
    rankings = bootstrap.get("team_rankings")
    if not isinstance(rankings, Mapping):
        raise ValueError("Top 3 report requires team-rank bootstrap evidence")
    top_k = int(rankings.get("top_k", 0))
    if top_k != 3:
        raise ValueError("Top 3 report requires a frozen top_k of three")

    ranking_rows = rankings.get("rows")
    forecasts = evidence.get("stat_forecasts")
    if not isinstance(ranking_rows, list) or not isinstance(forecasts, Mapping):
        raise ValueError("Top 3 report evidence rows are missing")
    forecast_rows = forecasts.get("rows")
    if not isinstance(forecast_rows, list):
        raise ValueError("Top 3 report Stat forecasts are missing")

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
            raise ValueError(f"Top 3 report has incomplete point ranks for {key}")

    boundary_by_key = {
        (str(row["role"]), str(row["color"]), str(row["stat_id"])): bool(row["boundary"])
        for row in bootstrap.get("rows", ())
    }
    boundary_count = sum(boundary_by_key.get(key, False) for key in forecast_by_key)
    point_seconds = [row for row in ranking_rows if int(row["point_rank"]) == 2]
    point_thirds = [row for row in ranking_rows if int(row["point_rank"]) == 3]
    tight_top2 = sum(float(row["gap_to_point_best_fraction"]) < 0.01 for row in point_seconds)
    tight_top3 = sum(float(row["gap_to_point_best_fraction"]) < 0.02 for row in point_thirds)

    lines = [
        "# Group Stat 队伍 Top 3 证据表",
        "",
        "状态：**点估计前三与队伍排名 bootstrap 的描述性扩展；不改变 v2 手册或发布标签**",
        "",
        f"- 显式 `as_of`：`{evidence['as_of']}`",
        f"- run：`{run_id}`",
        f"- evidence SHA-256：`{evidence['evidence_package_sha256']}`",
        f"- Series cluster bootstrap：{int(bootstrap['replicates'])} 次，"
        f"置信水平 {100.0 * float(bootstrap['confidence_level']):.0f}%",
        "- 排名：点估计与每次 bootstrap 均按 Expected mean 降序、稳定 `team_id` 升序打破平手",
        "",
        "`P1` 是该队在完整 Series 重采样中排名第一的比例；`P3` 是进入前三的比例。"
        "它们是诊断性重采样频率，不是经校准的未来真实排名概率或置信区间。"
        "`exact/derived` 只描述 Stat 来源，不表示队伍未来排名确定。队名仅用于显示，连接使用稳定 ID。",
        "",
        "## 可信度提示",
        "",
        f"- {len(forecast_by_key)} 个位置/颜色/Stat 行中，{boundary_count} 个 Stat 分档区间跨线；",
        f"- {tight_top2} 项的点估计第一与第二差距小于 1%；",
        f"- {tight_top3} 项的点估计第一与第三差距小于 2%；",
        "- 点估计前三是描述性候选，不是自动锁队规则；完整三格仍须重新执行同队 Team matching。",
        "",
        "单元格格式：`μ/C10` 为 Expected mean / CVaR10，`n` 为该队该位置的完整 Series blocks，"
        "`Δ` 为相对点估计第一的均值差距。",
        "",
    ]

    ordered_forecasts = sorted(
        forecast_rows,
        key=lambda row: (
            _ROLE_COLOR_ORDER[(str(row["role"]), str(row["color"]))],
            -float(row["best_team_mean"]),
            str(row["stat_id"]),
        ),
    )
    current_group: tuple[str, str] | None = None
    for forecast in ordered_forecasts:
        key = (str(forecast["role"]), str(forecast["color"]), str(forecast["stat_id"]))
        group = key[:2]
        if group != current_group:
            if current_group is not None:
                lines.append("")
            lines.extend(
                [
                    f"## {_ROLE_LABELS[group[0]]} · {_COLOR_LABELS[group[1]]}",
                    "",
                    "| Stat | 来源/分档稳定性 | #1 | #2 | #3 | #1–#3 差距 |",
                    "| --- | --- | --- | --- | --- | ---: |",
                ]
            )
            current_group = group
        top3 = sorted(grouped[key], key=lambda row: int(row["point_rank"]))[:3]
        stability = "边界" if boundary_by_key.get(key, False) else "稳定"
        gap13 = 100.0 * float(top3[2]["gap_to_point_best_fraction"])
        lines.append(
            f"| `{key[2]}` | `{forecast['provenance']}` / {stability} | "
            f"{_team_cell(top3[0], team_names)} | {_team_cell(top3[1], team_names)} | "
            f"{_team_cell(top3[2], team_names)} | {gap13:.2f}% |"
        )

    warnings = evidence.get("warnings", ())
    if warnings:
        lines.extend(["", "## 模型与数据限制", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(
        [
            "",
            "该附表只扩展队伍匹配透明度。Stat 指数、Quality、Trait、手册规则和 `draft` 标签均未修改。",
            "",
        ]
    )
    return "\n".join(lines)
