from __future__ import annotations

import pandas as pd

from ti_predictor.config import load_tournament_manifest
from ti_predictor.fantasy.recommend import (
    FantasyRecommender,
    _last_possible_game_flags,
    _matching_provenance_values,
    _suffix_activation_values,
    _weighted_estimate,
)
from ti_predictor.models.ratings import TeamStrengthModel


def test_stat_values_require_the_current_rule_provenance() -> None:
    rows = pd.DataFrame(
        {
            "teamfight_participation": [0.7, 0.8],
            "teamfight_participation_provenance": ["exact", "derived"],
        }
    )

    values = _matching_provenance_values(rows, "teamfight_participation", "derived")

    assert pd.isna(values.iloc[0])
    assert values.iloc[1] == 0.8


def test_stat_values_fail_closed_without_provenance_column() -> None:
    rows = pd.DataFrame({"teamfight_participation": [0.7]})

    values = _matching_provenance_values(rows, "teamfight_participation", "derived")

    assert values.isna().all()


def test_suffix_activation_values_use_available_exact_fields() -> None:
    rows = pd.DataFrame(
        {
            "team_win": pd.Series([True, False, pd.NA], dtype="boolean"),
            "duration": [1499, 1518, None],
            "last_possible_game": pd.Series([False, True, pd.NA], dtype="boolean"),
        }
    )

    assert _suffix_activation_values(rows, "player_team_loses_game").tolist()[:2] == [0.0, 1.0]
    assert _suffix_activation_values(rows, "duration_under_25_minutes").tolist()[:2] == [1.0, 0.0]
    assert _suffix_activation_values(rows, "displayed_match_time_ends_in_8").tolist()[:2] == [0.0, 1.0]
    assert _suffix_activation_values(rows, "last_possible_game_of_series").tolist()[:2] == [0.0, 1.0]
    assert _suffix_activation_values(rows, "first_blood_after_10_minutes").isna().all()


def test_last_possible_game_flags_follow_series_format() -> None:
    rows = pd.DataFrame(
        {
            "match_id": [1, 2, 3, 4, 5, 6],
            "series_id": [10, 10, 10, 20, 20, pd.NA],
            "series_type": [1, 1, 1, 3, 3, 0],
            "start_time": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T02:00:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-01-02T01:00:00Z",
                    "2026-01-03T00:00:00Z",
                ]
            ),
        }
    )

    assert _last_possible_game_flags(rows).tolist() == [False, False, True, False, True, True]


def test_weighted_estimate_uses_explicit_evidence_weights() -> None:
    values = pd.Series([10.0, 1000.0])
    times = pd.to_datetime(["2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"])

    estimate = _weighted_estimate(
        values,
        pd.Series(times),
        "2026-08-01T00:00:00Z",
        evidence_weights=pd.Series([1.0, 0.0]),
    )

    assert estimate.mean == 10.0
    assert estimate.observations == 1
    assert estimate.coverage == 1.0


def test_stat_priority_guide_separates_floor_and_upside_and_includes_exact_native(
    project_paths,
    rules_payload,
    monkeypatch,
) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    recommender = FantasyRecommender(
        pd.DataFrame(),
        manifest,
        rules_payload,
        TeamStrengthModel({}),
        as_of="2026-08-01T00:00:00Z",
    )

    def fake_role_rankings(role, profile, banner_slots):
        return [
            {
                "team_id": team.team_id,
                "team": team.name,
                "players": [
                    {"account_id": player.account_id, "player": player.name} for player in team.players[role]
                ],
            }
            for team in manifest.teams
        ]

    def fake_team_stat(team, role, stat_id):
        mean, std = {
            "kills": (100.0, 100.0),
            "deaths": (90.0, 1.0),
            "madstone_collected": (1000.0, 1.0),
        }.get(stat_id, (10.0, 1.0))
        return {
            "mean": mean,
            "std": std,
            "coverage": 1.0,
        }

    monkeypatch.setattr(recommender, "_role_rankings", fake_role_rankings)
    monkeypatch.setattr(recommender, "_team_stat", fake_team_stat)

    guide = recommender.stat_priority_guide(period="group")
    core_red = guide["roles"]["core"]["colors"]["red"]

    assert len(guide["roles"]["core"]["cohort"]) == 4
    assert core_red["profiles"]["stable"][0]["stat_id"] == "madstone_collected"
    assert core_red["profiles"]["upside"][0]["stat_id"] == "madstone_collected"
    assert core_red["profiles"]["expected"][0]["stat_id"] == "madstone_collected"
    assert not core_red["sensitivity_only"]
