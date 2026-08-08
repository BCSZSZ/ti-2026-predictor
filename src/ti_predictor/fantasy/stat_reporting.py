"""Human-readable reports for governed Group Fantasy Stat evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TEAM_RANK_REPORT_VERSION = "publication-v3"
TEAM_RANK_REPORT_FILENAME = "group-stat-team-top3-publication.md"

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


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


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


def render_group_stat_team_top3_markdown(
    evidence: Mapping[str, Any],
    *,
    team_names: Mapping[int, str],
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
        "# Group Fantasy 各 Stat 推荐队伍 Top 3",
        "",
        f"数据截止：`{evidence['as_of']}` · "
        f"排名稳定性检查：{int(bootstrap['replicates'])} 次完整系列赛重采样",
        "",
        "每项 Stat 按预测平均分列出前三队伍。平均分表示常规预期；低迷分表示最差 10% 情形的平均分，"
        "越高越抗风险；样本表示该队该位置可用的完整系列赛数量；落后第一表示与本行第一名的平均分差距。",
        "",
        "第一稳定率表示重采样后仍排第一的比例，前三稳定率表示仍在前三的比例。稳定率不是未来比赛的真实概率。",
        "",
        "## 使用提示",
        "",
        f"- {len(forecast_by_key)} 个位置/颜色/Stat 行中，{boundary_count} 个 Stat 分档区间跨线；",
        f"- {tight_top2} 项前两名差距小于 1%，{tight_top3} 项第一与第三差距小于 2%。"
        "差距较小时，应把前三都视为候选。",
        "- “分档边界”表示该 Stat 的优先级可能随样本变化跨档，不等于数据错误。",
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
                    "| Stat | 分档状态 | 第 1 | 第 2 | 第 3 |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            current_group = group
        top3 = sorted(grouped[key], key=lambda row: int(row["point_rank"]))[:3]
        stability = "分档边界" if boundary_by_key.get(key, False) else "分档稳定"
        lines.append(
            f"| `{key[2]}` | {stability} | "
            f"{_team_cell(top3[0], team_names)} | {_team_cell(top3[1], team_names)} | "
            f"{_team_cell(top3[2], team_names)} |"
        )

    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "本表基于数据截止日前的历史比赛和当前赛制近似；阵容、版本与赛程变化都可能改变排名。",
            "完整三格仍须重新进行同队匹配，不能把三行的第一名直接拼成一个选择。",
            "本表不改变 Stat 指数、Quality、Trait、v2 手册规则或 `draft` 状态。",
            "",
        ]
    )
    return "\n".join(lines)
