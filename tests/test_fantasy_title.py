from __future__ import annotations

import numpy as np
import pytest

from ti_predictor.fantasy.scenarios import PoolBuildResult, SeriesBlock, SeriesBlockPool
from ti_predictor.fantasy.title import (
    MatchTitleFeatures,
    PlayerTitleFeatures,
    build_title_analysis,
    extract_match_title_features,
    parse_title_hero_categories,
)
from ti_predictor.fantasy.title_reporting import _archive_hero_source
from ti_predictor.paths import ProjectPaths


def _title_rules() -> dict:
    prefixes = [
        ("crimson", 6),
        ("cerulean", 11),
        ("emerald", 6),
        ("royal", 10),
        ("golden", 8),
        ("elemental", 8),
        ("otherworldly", 7),
        ("heroic", 9),
    ]
    suffixes = [
        ("tormented", 23),
        ("early_first_blood", 9),
        ("late_first_blood", 23),
        ("loser", 6),
        ("quick", 24),
        ("clutch", 16),
        ("lucky", 21),
        ("fountain", 13),
    ]
    return {
        "fantasy": {
            "coach": {
                "prefixes": [
                    {"id": item_id, "name": item_id, "label": item_id, "bonus_percent": bonus}
                    for item_id, bonus in prefixes
                ],
                "suffixes": [
                    {"id": item_id, "name": item_id, "label": item_id, "bonus_percent": bonus}
                    for item_id, bonus in suffixes
                ],
            }
        }
    }


def test_parse_title_categories_keeps_repeated_client_chunks_and_masked() -> None:
    text = r'''
    "DOTAHeroes"
    {
      "npc_dota_hero_alpha"
      {
        "HeroID" "1"
        "Adjectives"
        {
          "Red" "1" "Blue" "1" "Green" "1" "Purple" "1"
          "Yellow" "1" "Aquatic" "1" "Undead" "1" "Cape" "1"
        }
      }
    }
    "DOTAHeroes"
    {
      "npc_dota_hero_beta"
      {
        "HeroID" "2"
        "Adjectives" { "Brown" "1" "Fiery" "1" "Demon" "1" "Masked" "1" }
      }
    }
    '''

    result = parse_title_hero_categories(text)

    assert list(result) == [1, 2]
    assert result[1] == (
        "crimson",
        "cerulean",
        "emerald",
        "royal",
        "golden",
        "elemental",
        "otherworldly",
        "heroic",
    )
    assert result[2] == ("golden", "elemental", "otherworldly", "heroic")


def test_extract_match_title_features_uses_objective_time_and_stable_ids() -> None:
    payload = {
        "match_id": 100,
        "duration": 1808,
        "version": 22,
        "od_data": {"has_parsed": True},
        "objectives": [{"type": "CHAT_MESSAGE_FIRSTBLOOD", "time": -34}],
        "players": [
            {
                "account_id": 10,
                "hero_id": 1,
                "win": 1,
                "killed_by": {"npc_dota_miniboss": 1},
            },
            {"account_id": 20, "hero_id": 2, "win": 0, "killed_by": {}},
        ],
    }

    result = extract_match_title_features(payload, expected_match_id=100)

    assert result.duration_seconds == 1808
    assert result.first_blood_time_seconds == -34
    assert result.any_player_died_to_tormentor is True
    assert result.player(10) == PlayerTitleFeatures(account_id=10, hero_id=1, won=True)
    assert result.player(20) == PlayerTitleFeatures(account_id=20, hero_id=2, won=False)


def test_title_hero_source_archive_is_immutable(tmp_path) -> None:
    from datetime import UTC, datetime

    paths = ProjectPaths(root=tmp_path)
    cutoff = datetime(2026, 8, 8, 13, 12, tzinfo=UTC)
    content = b'"DOTAHeroes" {}\n'

    path, source_hash = _archive_hero_source(
        content,
        as_of=cutoff,
        client_build="1:2",
        paths=paths,
    )
    repeated, repeated_hash = _archive_hero_source(
        content,
        as_of=cutoff,
        client_build="1:2",
        paths=paths,
    )

    assert repeated == path
    assert repeated_hash == source_hash
    assert path.read_bytes() == content
    with pytest.raises(FileExistsError, match="immutable Title rule capture collision"):
        _archive_hero_source(
            content,
            as_of=cutoff,
            client_build="changed",
            paths=paths,
        )


def test_build_title_analysis_ranks_prefix_and_bo3_clutch() -> None:
    blocks = (
        SeriesBlock(
            target_team_id=1,
            role="mid",
            player_ids=(10,),
            historical_team_id=1,
            series_id=11,
            match_ids=(1, 2),
            start_times=("2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"),
            evidence_weight=1.0,
            stat_ids=("kills",),
            game_stat_scores=np.ones((2, 1)),
        ),
        SeriesBlock(
            target_team_id=1,
            role="mid",
            player_ids=(10,),
            historical_team_id=1,
            series_id=12,
            match_ids=(3, 4, 5),
            start_times=(
                "2026-01-02T00:00:00Z",
                "2026-01-02T01:00:00Z",
                "2026-01-02T02:00:00Z",
            ),
            evidence_weight=1.0,
            stat_ids=("kills",),
            game_stat_scores=np.ones((3, 1)),
        ),
    )
    pool = SeriesBlockPool(
        target_team_id=1,
        role="mid",
        player_ids=(10,),
        stat_ids=("kills",),
        blocks=blocks,
    )
    pool_result = PoolBuildResult(pools=(pool,), audit={}, semantic_hash="pool")
    features = {
        match_id: MatchTitleFeatures(
            match_id=match_id,
            duration_seconds=1800,
            first_blood_time_seconds=60,
            any_player_died_to_tormentor=False,
            players=(
                PlayerTitleFeatures(
                    account_id=10,
                    hero_id=1 if match_id in {1, 2, 5} else 2,
                    won=match_id != 1,
                ),
            ),
        )
        for match_id in range(1, 6)
    }

    result = build_title_analysis(
        pool_result,
        features,
        {match_id: 1 for match_id in range(1, 6)},
        {1: ("cerulean",), 2: ("crimson",)},
        _title_rules(),
        team_names={1: "Example"},
    )

    assert result["recommendation"]["default_prefix"] == "cerulean"
    assert result["recommendation"]["default_suffix"] == "clutch"
    cerulean = next(row for row in result["prefixes"] if row["id"] == "cerulean")
    assert cerulean["trigger_rate"] == pytest.approx(2 / 3)
    assert cerulean["paper_expected_bonus_percent"] == pytest.approx(22 / 3)
    clutch = next(row for row in result["suffixes"] if row["id"] == "clutch")
    assert clutch["trigger_rate"] == pytest.approx(0.2)
    assert clutch["paper_expected_bonus_percent"] == pytest.approx(3.2)
    early = next(row for row in result["suffixes"] if row["id"] == "early_first_blood")
    fountain = next(row for row in result["suffixes"] if row["id"] == "fountain")
    assert early["rank"] is None and early["status"] == "conflicted_excluded"
    assert fountain["rank"] is None and fountain["status"] == "unavailable"
