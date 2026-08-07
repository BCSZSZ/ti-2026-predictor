from __future__ import annotations

from ti_predictor.fantasy.stat_reporting import render_group_stat_team_top3_markdown


def test_top3_markdown_reports_ids_risk_samples_and_rank_probabilities() -> None:
    rankings = [
        {
            "role": "core",
            "color": "red",
            "stat_id": "kills",
            "team_id": team_id,
            "point_rank": rank,
            "point_mean": mean,
            "point_cvar10": cvar10,
            "series_blocks": blocks,
            "gap_to_point_best_fraction": gap,
            "rank1_probability": rank1,
            "top3_probability": top3,
        }
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
                    "role": "core",
                    "color": "red",
                    "stat_id": "kills",
                    "provenance": "exact",
                    "best_team_mean": 100.0,
                }
            ]
        },
        "cluster_bootstrap": {
            "replicates": 400,
            "confidence_level": 0.95,
            "rows": [{"role": "core", "color": "red", "stat_id": "kills", "boundary": False}],
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
        run_id="fantasy-fixture",
    )

    assert "# Group Stat 队伍 Top 3 证据表" in report
    assert "Alpha (`11`)" in report
    assert "100.0 / 80.0" in report
    assert "n=10" in report
    assert "P1=55.0%" in report
    assert "P3=90.0%" in report
    assert "Delta" not in report
    assert "点估计前三" in report
    assert "不是经校准的未来真实排名概率" in report
    assert "fixture warning" in report
    assert report.endswith("\n")
