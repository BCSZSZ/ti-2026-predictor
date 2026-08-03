from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.rules import create_rule_snapshot, validate_rules, validate_snapshot


def test_golden_rules_have_expected_shapes(project_paths) -> None:
    rules = load_rules(project_paths.rules)
    issues = validate_rules(rules)
    assert not [issue for issue in issues if issue.severity == "blocking"]
    assert [slot["count"] for slot in rules["prediction"]["group"]["slots"]] == [1, 2, 5, 5, 2, 1]
    assert len(rules["prediction"]["group"]["cumulative_points"]) == 17
    assert len(rules["prediction"]["main"]["cumulative_points"]) == 15
    assert rules["prediction"]["group"]["points_table_semantics"] == (
        "total_event_points_by_correct_prediction_count"
    )
    assert rules["prediction"]["main"]["points_table_semantics"] == (
        "total_event_points_by_correct_prediction_count"
    )
    rewards = rules["event"]["final_leaderboard_rewards"]
    assert [tier["tyrian_regalias"] for tier in rewards["tiers"]] == [5, 2, 1, 0, 0]
    assert rewards["dota_plus_shards"] == {"points_step": 1000, "shards_per_step": 300}
    assert len(rules["fantasy"]["stats"]) == 18
    assert rules["fantasy"]["score_unit"] == "client_fantasy_points"
    assert rules["fantasy"]["stats"]["kills"]["factor"] == 107.0
    assert rules["fantasy"]["bonus_stacking"]["emblem_quality_and_trait_effects"] == (
        "additive_percent_of_base_stat_score"
    )
    assert rules["fantasy"]["bonus_stacking"]["coach_prefix_and_suffix"] == "multiplicative"
    coach = rules["fantasy"]["coach"]
    assert coach["selection"] == {
        "prefix_count": 1,
        "suffix_count": 1,
        "scope": "all_fantasy_players",
        "bonus_target": "final_game_score",
        "change_cost_roll_tokens": 0,
    }
    suffixes = {item["id"]: item for item in coach["suffixes"]}
    assert suffixes["early_first_blood"]["condition"] == "first_blood_before_starting_horn"
    assert suffixes["late_first_blood"]["condition"] == "first_blood_after_10_minutes"
    assert suffixes["fountain"]["condition"] == "any_player_killed_in_own_fountain"
    assert rules["fantasy"]["period_rewards"]["between_anchor_mapping"] == ("unknown_do_not_interpolate")
    assert [period["banner_slots"] for period in rules["fantasy"]["periods"]] == [3, 5]


def test_manifest_has_sixteen_unique_complete_teams(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    assert len(manifest.teams) == 16
    assert len({team.team_id for team in manifest.teams}) == 16
    assert all(sum(len(players) for players in team.players.values()) == 5 for team in manifest.teams)


def test_client_snapshot_records_sources_and_conflict(tmp_path: Path, project_paths) -> None:
    source = tmp_path / "client"
    scoring = {
        "FANTASY_SCORING_KILLS": 107,
        "FANTASY_SCORING_DEATHS": 195,
        "FANTASY_SCORING_CS": 3,
        "FANTASY_SCORING_GPM": 2,
        "FANTASY_SCORING_MADSTONE": 13,
        "FANTASY_SCORING_TOWER_KILLS": 352,
        "FANTASY_SCORING_WARDS_PLANTED": 117,
        "FANTASY_SCORING_CAMPS_STACKED": 234,
        "FANTASY_SCORING_RUNES_GRABBED": 141,
        "FANTASY_SCORING_SMOKES_USED": 293,
        "FANTASY_SCORING_WATCHERS_TAKEN": 147,
        "FANTASY_SCORING_LOTUSES_GAINED": 176,
        "FANTASY_SCORING_ROSHAN_KILLS": 1172,
        "FANTASY_SCORING_TEAMFIGHT_PARTICIPATION": 2124,
        "FANTASY_SCORING_FIRST_BLOOD": 1934,
        "FANTASY_SCORING_STUNS": 10,
        "FANTASY_SCORING_TORMENTOR_KILLS": 879,
        "FANTASY_SCORING_COURIER_KILLS": 703,
    }
    group_grants = [30, 30, 60, 240, 360, 480, 600, 720, 840, 960, 1080, 1200, 1320, 1440, 1560, 1080]
    main_grants = [120 * index for index in range(1, 14)] + [1080]
    scoring_text = " ".join(f'"{key}" "{value}"' for key, value in scoring.items())
    group_text = " ".join(f'"points" "{value}"' for value in group_grants)
    main_text = " ".join(f'"points" "{value}"' for value in main_grants)
    files = {
        "scripts/events/international_2026.eventdef": f"""
            \"predictions_road_to_ti\" {{ \"max_grants\" \"16\" {group_text} }}
            \"predictions_main_event\" {{ \"max_grants\" \"14\" {main_text} }}
            \"grant_fantasy_crafting_rolls\" {{ \"rolls\" \"40\" }}
            \"grant_fantasy_crafting_rolls\" {{ \"rolls\" \"30\" }}
            \"fantasy\" {{
              \"scoring\" {{ {scoring_text} }}
              \"period_definitions\" {{
                \"0\" {{ \"start\" \"1786543200\" \"LEAGUE_REGION_UNSET\" \"19719\" }}
                \"1\" {{ \"start\" \"1787191200\" \"LEAGUE_REGION_UNSET\" \"19719\" }}
              }}
            }}
        """,
        "scripts/fantasy_crafting.vdata": """
            m_nBonus = 10 m_nBonus = 30 m_nBonus = 60 m_nBonus = 100 m_nBonus = 150
            m_nRollWeight = 10 m_nRollWeight = 20 m_nRollWeight = 10
            m_nRollWeight = 5 m_nRollWeight = 2
            first_blood_after_6_minutes
        """,
        "scripts/events/fantasy/dpc_fantasy_period_pointscore.eventactions": "fixture",
        "resource/localization/dota_english.txt": "after 10 minutes",
        "resource/localization/dota_schinese.txt": "10分钟之后",
    }
    for relative, content in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    snapshot, output = create_rule_snapshot(
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
        source_dir=source,
        paths=project_paths,
    )
    assert output.is_file()
    assert snapshot.status == "warning"
    assert len(snapshot.source_files) == 5
    assert any(issue.code == "late_first_blood_threshold" for issue in snapshot.issues)
    assert sum(issue.code == "late_first_blood_threshold" for issue in snapshot.issues) == 1
    status, issues = validate_snapshot(paths=project_paths)
    assert status == "warning"
    assert not [issue for issue in issues if issue.severity == "blocking"]
