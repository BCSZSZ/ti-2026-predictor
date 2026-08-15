from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from ti_predictor.config import load_rules, load_tournament_manifest, rules_hash
from ti_predictor.rules import (
    create_rule_snapshot,
    inspect_client_sources,
    latest_rule_snapshot,
    rule_snapshot_at,
    rule_snapshot_issues,
    validate_rules,
    validate_snapshot,
)
from ti_predictor.schemas import RuleSnapshot


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
    roll = rules["fantasy"]["roll"]
    assert roll["supported_periods"] == ["group", "main"]
    assert roll["offer"] == {
        "count": 3,
        "unique": True,
        "shared_across_banners": True,
        "apply_replaces_all": True,
        "refresh_replaces_all": True,
    }
    assert roll["token_cost"] == {"apply": 1, "refresh": 1}
    assert roll["application_scope"] == "selected_banner_only"
    assert roll["client_contract"]["positive_weight_sum"] == 168
    assert {item["id"]: item["exposed_weight_power"] for item in roll["transition_models"]} == {
        "client-weight-primary-v1": 1.0,
        "flattened-weights-v1": 0.5,
        "sharpened-weights-v1": 2.0,
    }
    assert [trait["shape_id"] for trait in rules["fantasy"]["traits"]] == [1, 2, 3, 4, 5]


def test_manifest_has_sixteen_unique_complete_teams(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    assert len(manifest.teams) == 16
    assert len({team.team_id for team in manifest.teams}) == 16
    assert all(sum(len(players) for players in team.players.values()) == 5 for team in manifest.teams)


def test_client_roster_keeps_inactive_entries_for_audit_but_compares_only_active(tmp_path: Path) -> None:
    crafting = tmp_path / "scripts/fantasy_crafting.vdata"
    crafting.parent.mkdir(parents=True)
    crafting.write_text(
        """
        m_eEvent = "EVENT_ID_INTERNATIONAL_2026"
        m_vecPlayers = [
            {
                m_unAccountID = 1026694469
                m_unTeamID = 10150538
                m_strPlayerName = "TaiLung"
                m_bIsValid = false
            },
            {
                m_unAccountID = 94054712
                m_unTeamID = 10150538
                m_strPlayerName = "Topson"
                m_bIsValid = true
            },
        ]
        """,
        encoding="utf-8",
    )

    observed = inspect_client_sources(tmp_path)

    assert observed["event_account_ids"] == [94054712]
    assert observed["event_roster_pairs"] == [[94054712, 10150538]]
    assert observed["event_inactive_account_ids"] == [1026694469]
    assert observed["event_roster_entries"] == [
        {
            "account_id": 94054712,
            "team_id": 10150538,
            "player_name": "Topson",
            "is_valid": True,
        },
        {
            "account_id": 1026694469,
            "team_id": 10150538,
            "player_name": "TaiLung",
            "is_valid": False,
        },
    ]


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
    crafting_fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    crafting_bytes = crafting_fixture.read_bytes()
    assert hashlib.sha256(crafting_bytes).hexdigest() == (
        "8208a82d2f8a15f947ba69ffb076df622a19c10803895a230394ad1d4c141b4b"
    )
    files = {
        "scripts/events/international_2026.eventdef": f"""
            \"predictions_road_to_ti\" {{ \"max_grants\" \"16\" {group_text} }}
            \"predictions_main_event\" {{ \"max_grants\" \"14\" {main_text} }}
            \"grant_fantasy_crafting_rolls\" {{ \"rolls\" \"40\" }}
            \"grant_fantasy_crafting_rolls\" {{ \"rolls\" \"30\" }}
            \"fantasy\" {{
              \"scoring\" {{ {scoring_text} }}
              \"period_definitions\" {{
                \"0\" {{ \"start\" \"1786586400\" \"LEAGUE_REGION_UNSET\" \"19719\" }}
                \"1\" {{ \"start\" \"1787191200\" \"LEAGUE_REGION_UNSET\" \"19719\" }}
              }}
            }}
        """,
        "scripts/fantasy_crafting.vdata": crafting_bytes.decode("utf-8") + "\nfirst_blood_after_6_minutes\n",
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
    assert snapshot.status == "warning", snapshot.issues
    assert len(snapshot.source_files) == 5
    assert any(issue.code == "late_first_blood_threshold" for issue in snapshot.issues)
    assert sum(issue.code == "late_first_blood_threshold" for issue in snapshot.issues) == 1
    client_roll = snapshot.observed["fantasy_roll"]
    operations = client_roll["operations"]
    positive = [item for item in operations if item["roll_weight"] > 0]
    assert client_roll["offer_size"] == 3
    assert len(operations) == 28
    assert [item["operation_id"] for item in positive] == [
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
    ]
    assert sum(item["roll_weight"] for item in positive) == 168
    assert [item["operation_id"] for item in operations if item["roll_weight"] == 0] == list(range(1, 9))
    assert next(item for item in operations if item["operation_id"] == 27)["roll_weight"] == 6
    status, issues = validate_snapshot(paths=project_paths)
    assert status == "warning"
    assert not [issue for issue in issues if issue.severity == "blocking"]


def test_historical_rule_resolution_uses_latest_snapshot_available_at_as_of(project_paths) -> None:
    def write_snapshot(snapshot_id: str, created_at: str, semantic_hash: str) -> None:
        snapshot = RuleSnapshot(
            snapshot_id=snapshot_id,
            event_id="international_2026",
            as_of=created_at,
            created_at=created_at,
            source="dota_client",
            source_files=[],
            canonical_rules_sha256=rules_hash(project_paths.rules),
            snapshot_sha256=semantic_hash,
            status="publishable",
            observed={},
        )
        path = project_paths.raw / "rules" / snapshot_id / "rule_snapshot.json"
        path.parent.mkdir(parents=True)
        path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")

    write_snapshot("20260810T134439Z-aaaaaaaaaaaa", "2026-08-10T13:44:39Z", "a" * 64)
    write_snapshot("20260811T025356Z-bbbbbbbbbbbb", "2026-08-11T02:53:56Z", "b" * 64)
    cutoff = datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC)

    assert latest_rule_snapshot(project_paths)[0].snapshot_sha256 == "b" * 64
    resolved = rule_snapshot_at(cutoff, project_paths)
    assert resolved is not None
    assert resolved[0].snapshot_sha256 == "a" * 64
    assert not [
        issue for issue in rule_snapshot_issues(cutoff, project_paths) if issue.severity == "blocking"
    ]
