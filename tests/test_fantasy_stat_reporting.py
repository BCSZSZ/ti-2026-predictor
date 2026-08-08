from __future__ import annotations

from ti_predictor.fantasy.stat_reporting import render_group_stat_team_top3_markdown


def test_top3_markdown_reports_plain_language_risk_samples_and_rank_stability() -> None:
    stat_scales = (
        ("kills", 1.0),
        ("gpm", 0.9),
        ("deaths", 0.8),
        ("tower_kills", 0.6),
        ("stuns", 0.4),
        ("madstone_collected", 0.2),
    )
    groups = (
        ("core", "red"),
        ("core", "green"),
        ("mid", "red"),
        ("mid", "blue"),
        ("mid", "green"),
        ("support", "blue"),
        ("support", "green"),
    )
    group_stats = {
        group: (
            stat_scales
            if group == ("core", "red")
            else tuple((f"stat_{index}", scale) for index, (_, scale) in enumerate(stat_scales, 1))
        )
        for group in groups
    }
    rankings = [
        {
            "role": role,
            "color": color,
            "stat_id": stat_id,
            "team_id": team_id,
            "point_rank": rank,
            "point_mean": scale * mean,
            "point_cvar10": scale * cvar10,
            "series_blocks": blocks,
            "gap_to_point_best_fraction": gap,
            "rank1_probability": rank1,
            "top3_probability": top3,
        }
        for (role, color), stats in group_stats.items()
        for stat_id, scale in stats
        for team_id, rank, mean, cvar10, blocks, gap, rank1, top3 in (
            (11, 1, 100.0, 80.0, 10, 0.0, 0.55, 0.90),
            (22, 2, 99.0, 82.0, 20, 0.01, 0.35, 0.80),
            (33, 3, 95.0, 70.0, 30, 0.05, 0.10, 0.70),
            (44, 4, 90.0, 68.0, 40, 0.10, 0.00, 0.60),
        )
    ]
    evidence = {
        "as_of": "2026-08-06T17:27:00Z",
        "evidence_package_sha256": "a" * 64,
        "stat_forecasts": {
            "rows": [
                {
                    "role": role,
                    "color": color,
                    "stat_id": stat_id,
                    "provenance": "exact",
                    "best_team_mean": 100.0 * scale,
                    "runner_up_mean": (
                        40.0 if (role, color, stat_id) == ("core", "red", "kills") else 99.0 * scale
                    ),
                    "all_team_mean": 50.0 * scale,
                    "relative_to_best": scale,
                    "eligible_row_provenance_coverage": 1.0,
                    "complete_block_provenance_coverage": 1.0,
                }
                for (role, color), stats in group_stats.items()
                for stat_id, scale in stats
            ]
        },
        "cluster_bootstrap": {
            "replicates": 400,
            "confidence_level": 0.95,
            "rows": [
                {
                    "role": role,
                    "color": color,
                    "stat_id": stat_id,
                    "boundary": (role, color, stat_id) == ("core", "red", "deaths"),
                }
                for (role, color), stats in group_stats.items()
                for stat_id, _ in stats
            ],
            "team_rankings": {
                "top_k": 3,
                "point_order": "descending_mean_then_team_id",
                "bootstrap_order": "descending_mean_then_team_id",
                "rows": rankings,
            },
        },
        "warnings": ["fixture warning"],
    }

    report = render_group_stat_team_top3_markdown(
        evidence,
        team_names={11: "Alpha", 22: "Beta", 33: "Gamma", 44: "Delta"},
    )

    assert "# Group Fantasy 各 Stat 推荐队伍 Top 3" in report
    assert "## 核心位 · 红色" in report
    assert "Alpha<br>平均分 100.0" in report
    assert "平均分 100.0 · 低迷分 80.0" in report
    assert "样本 10 个完整系列赛 · 落后第一 0.00%" in report
    assert "第一稳定率 55.0% · 前三稳定率 90.0%" in report
    assert "| Stat 排名 | Stat | 基础建议 | 分档状态 | 第 1 | 第 2 | 第 3 |" in report
    assert "| 1 | `kills` | 一定保留<br>相对强度 100.0 | 分档稳定 |" in report
    assert "| 2 | `gpm` | 可以保留<br>相对强度 90.0 | 分档稳定 |" in report
    assert "| 3 | `deaths` | 可以改善<br>相对强度 80.0 | 分档边界 |" in report
    assert "| 5 | `stuns` | 优先改善<br>相对强度 40.0 | 分档稳定 |" in report
    assert "| 6 | `madstone_collected` | 优先改善<br>相对强度 20.0 | 分档稳定 |" in report
    assert "同一位置和颜色内从强到弱排列" in report
    assert "一定保留" in report
    assert "可以保留" in report
    assert "可以改善" in report
    assert "优先改善" in report
    assert "不等于无条件重随" in report
    assert "Delta" not in report
    assert "稳定率不是未来比赛的真实概率" in report
    assert "μ/C10" not in report
    assert "n=" not in report
    assert "Δ=" not in report
    assert "P1=" not in report
    assert "P3=" not in report
    assert "队伍 ID" not in report
    assert "`11`" not in report
    assert "数据来源" not in report
    assert "精确数据" not in report
    assert "推导数据" not in report
    assert "exact" not in report
    assert "fixture warning" not in report
    assert "evidence SHA-256" not in report
    assert report.endswith("\n")
