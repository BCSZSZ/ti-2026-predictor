from __future__ import annotations

from pathlib import Path

from ti_predictor.fantasy.main_publication import (
    load_main_publication_policy,
    render_main_stat_team_top3_markdown,
    subset_actual_main_pools,
)
from ti_predictor.fantasy.main_solver_release import load_main_solver_release_context
from ti_predictor.fantasy.solver_release import load_solver_release_context


def test_main_publication_policy_freezes_actual_eight_and_400_series_bootstraps() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_main_publication_policy(root / "config/models/fantasy-main-publication-v1.json")

    assert policy.period == "main"
    assert policy.eligibility_mode == "actual"
    assert policy.team_count == 8
    assert policy.scenario_count == 256
    assert policy.bootstrap.replicates == 400
    assert policy.bootstrap.scenarios_per_replicate == 256
    assert policy.bootstrap.unit == "full_series_block"


def test_current_main_publication_subset_contains_only_the_24_actual_team_role_pools() -> None:
    context = load_main_solver_release_context(load_solver_release_context())
    team_ids = tuple(context.team_names)

    selected = subset_actual_main_pools(context.terminal.pool_result, team_ids=team_ids)

    assert len(team_ids) == 8
    assert len(selected.pools) == 24
    assert [(pool.target_team_id, pool.role) for pool in selected.pools] == [
        (team_id, role) for team_id in team_ids for role in ("core", "mid", "support")
    ]
    assert selected.audit["eligibility_mode"] == "actual"
    assert selected.audit["parent_pool_set_sha256"] == context.terminal.pool_result.semantic_hash
    assert context.title_evidence is not None
    assert context.title_evidence["eligibility_mode"] == "actual"
    assert context.title_evidence["team_ids"] == list(team_ids)
    assert len(context.title_evidence["analysis"]["pools"]) == 24
    assert (
        context.title_evidence["evidence_sha256"]
        == "fbb3a6ae18ea3bd8e86ce20ac203db154ed09ebadebfe2c21f4767b5e7b85e5e"
    )


def test_main_stat_report_uses_five_slot_actual_scope_without_group_rule_claims() -> None:
    stats = (
        ("kills", 1.0),
        ("gpm", 0.9),
        ("deaths", 0.8),
        ("tower_kills", 0.6),
        ("stuns", 0.4),
        ("madstone_collected", 0.2),
    )
    rankings = [
        {
            "role": "core",
            "color": "red",
            "stat_id": stat_id,
            "team_id": team_id,
            "point_rank": rank,
            "point_mean": scale * mean,
            "point_cvar10": scale * cvar,
            "series_blocks": blocks,
            "gap_to_point_best_fraction": gap,
            "rank1_probability": rank1,
            "top3_probability": top3,
        }
        for stat_id, scale in stats
        for team_id, rank, mean, cvar, blocks, gap, rank1, top3 in (
            (11, 1, 100.0, 80.0, 10, 0.0, 0.6, 0.9),
            (22, 2, 90.0, 70.0, 20, 0.1, 0.3, 0.8),
            (33, 3, 80.0, 60.0, 30, 0.2, 0.1, 0.7),
        )
    ]
    evidence = {
        "as_of": "2026-08-16T15:31:30Z",
        "team_ids": [11, 22, 33],
        "weighting": {
            "exact_patch_name": "7.41e",
            "exact_patch_multiplier": 1.5,
            "current_event_stage_multiplier": 1.5,
        },
        "stat_forecasts": {
            "rows": [
                {
                    "role": "core",
                    "color": "red",
                    "stat_id": stat_id,
                    "relative_to_best": scale,
                    "best_team_mean": 100.0 * scale,
                    "runner_up_mean": 90.0 * scale,
                }
                for stat_id, scale in stats
            ]
        },
        "cluster_bootstrap": {
            "replicates": 400,
            "rows": [
                {
                    "role": "core",
                    "color": "red",
                    "stat_id": stat_id,
                    "boundary": stat_id == "deaths",
                }
                for stat_id, _ in stats
            ],
            "team_rankings": {"top_k": 3, "rows": rankings},
        },
    }

    report = render_main_stat_team_top3_markdown(
        evidence,
        team_names={11: "Alpha", 22: "Beta", 33: "Gamma"},
    )

    assert report.startswith("# Main Fantasy 各 Stat 推荐队伍 Top 3")
    assert "同一面五格最终必须匹配同一支队伍" in report
    assert "实际 Main 八队" in report
    assert "G/G-Lite" in report
    assert "Group 三格" not in report
    assert "B/C/D" not in report
