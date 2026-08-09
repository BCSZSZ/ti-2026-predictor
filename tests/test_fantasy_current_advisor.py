from __future__ import annotations

from ti_predictor.fantasy.current_advisor import (
    _preferred_action,
    classify_recommendation,
    load_current_advisor_policy,
    rank_title_for_lineup,
)


def test_v2_policy_freezes_current_screen_boundaries(project_paths) -> None:
    policy = load_current_advisor_policy(
        project_paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )

    assert policy.period == "group"
    assert policy.analysis.primary_model in policy.analysis.models
    assert policy.responsive_scenarios.count == 256
    assert policy.boundaries.future_offer_generation is False
    assert policy.boundaries.dota_client_control is False
    assert policy.boundaries.main_execution == "fail_closed"


def test_title_ranking_uses_selected_role_pools_and_excludes_unverified_suffixes() -> None:
    pools = []
    for role, team_id, cerulean, golden, clutch, loser in (
        ("core", 1, 1.0, 4.0, 2.0, 6.0),
        ("mid", 2, 5.0, 1.0, 4.0, 1.0),
        ("support", 3, 2.0, 3.0, 3.0, 2.0),
    ):
        pools.append(
            {
                "role": role,
                "team_id": team_id,
                "prefix_trigger_rates": {"cerulean": cerulean / 10, "golden": golden / 10},
                "prefix_paper_bonus_percent": {"cerulean": cerulean, "golden": golden},
                "suffix_trigger_rates": {
                    "clutch": clutch / 10,
                    "loser": loser / 10,
                    "early_first_blood": 1.0,
                },
                "suffix_paper_bonus_percent": {
                    "clutch": clutch,
                    "loser": loser,
                    "early_first_blood": 99.0,
                },
            }
        )
    evidence = {
        "analysis": {
            "pools": pools,
            "prefixes": [
                {"id": "cerulean", "name": "Cerulean", "label": "蓝色英雄", "bonus_percent": 11},
                {"id": "golden", "name": "Golden", "label": "黄色英雄", "bonus_percent": 8},
            ],
            "suffixes": [
                {"id": "clutch", "name": "the Clutch", "label": "决胜局", "bonus_percent": 16},
                {"id": "loser", "name": "the Underdog", "label": "本局落败", "bonus_percent": 6},
                {
                    "id": "early_first_blood",
                    "name": "the Flayed Twins Acolyte",
                    "label": "号角前一血",
                    "bonus_percent": 9,
                },
            ],
        }
    }

    result = rank_title_for_lineup(
        evidence,
        selected_team_ids=(1, 2, 3),
        role_base_means={"core": 6.0, "mid": 3.0, "support": 1.0},
        excluded_suffix_ids=("early_first_blood",),
        top_k=3,
    )

    assert result["recommended_prefix"]["id"] == "golden"
    assert result["recommended_suffix"]["id"] == "loser"
    assert all(row["id"] != "early_first_blood" for row in result["suffixes"])
    assert result["role_weights"] == {"core": 0.6, "mid": 0.3, "support": 0.1}
    assert result["estimated_pair_bonus_percent"] == 7.1


def test_recommendation_classification_has_clear_conditional_and_refresh_gates() -> None:
    clear = classify_recommendation(
        selected_action_id="core:23",
        selected_row={"mean_delta": 10.0, "cvar10_delta": 3.0, "support_lower": 0.0},
        preferred_action_ids=("core:23", "core:23", "core:23"),
    )
    conditional = classify_recommendation(
        selected_action_id="mid:24",
        selected_row={"mean_delta": 8.0, "cvar10_delta": -2.0, "support_lower": -5.0},
        preferred_action_ids=("mid:24", "refresh", "mid:24"),
    )
    refresh = classify_recommendation(
        selected_action_id="refresh",
        selected_row={"mean_delta": 0.0, "cvar10_delta": 0.0, "support_lower": 0.0},
        preferred_action_ids=("refresh", "refresh", "refresh"),
    )

    assert clear["grade"] == "clear"
    assert conditional["grade"] == "conditional"
    assert conditional["model_agreement"] is False
    assert refresh["grade"] == "refresh"
    assert "未来" in refresh["reason"]


def test_action_selection_rejects_a_downside_trade_that_has_no_average_gain() -> None:
    selected = _preferred_action(
        (
            {"action_id": "refresh", "mean": 100.0, "cvar10": 50.0},
            {"action_id": "core:23", "mean": 99.5, "cvar10": 80.0},
        ),
        mean_retention_epsilon=0.01,
    )

    assert selected == "refresh"
