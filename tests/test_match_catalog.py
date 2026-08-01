from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from ti_predictor.match_catalog import build_patch_timeline, filter_match_catalog, patch_at


def test_patch_timeline_uses_patch_active_at_game_start() -> None:
    timeline = build_patch_timeline(
        [
            {"id": 59, "name": "7.40", "date": "2025-12-16T00:50:40Z"},
            {"id": 60, "name": "7.41", "date": "2026-03-24T00:50:59Z"},
        ]
    )

    selected = patch_at(datetime(2026, 5, 1, tzinfo=UTC), timeline)

    assert selected is not None
    assert selected.patch_id == 60
    assert selected.name == "7.41"


def test_match_catalog_filters_time_patch_and_league_tier() -> None:
    matches = pd.DataFrame(
        [
            {
                "match_id": 1,
                "start_time": "2026-02-01T00:00:00Z",
                "patch_name": "7.40",
                "league_tier": "professional",
                "league_id": 10,
                "is_pro_match": True,
            },
            {
                "match_id": 2,
                "start_time": "2026-05-01T00:00:00Z",
                "patch_name": "7.41",
                "league_tier": "premium",
                "league_id": 20,
                "is_pro_match": True,
            },
            {
                "match_id": 3,
                "start_time": "2026-05-02T00:00:00Z",
                "patch_name": "7.41",
                "league_tier": "premium",
                "league_id": 20,
                "is_pro_match": False,
            },
        ]
    )

    filtered = filter_match_catalog(
        matches,
        start_at=datetime(2026, 3, 1, tzinfo=UTC),
        end_before=datetime(2026, 6, 1, tzinfo=UTC),
        patch_names={"7.41"},
        league_tiers={"premium"},
    )

    assert filtered["match_id"].tolist() == [2]
