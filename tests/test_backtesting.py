from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ti_predictor.backtesting import evaluate_league_holdout
from ti_predictor.models.policy import TeamStrengthPolicy


def _policy(*, target_team_ids: list[int]) -> TeamStrengthPolicy:
    path = Path(__file__).resolve().parents[1] / "config/models/team-strength-v2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["ti2025_holdout"].update(
        {
            "league_id": 999,
            "target_team_ids": target_team_ids,
            "expected_games": 1,
            "minimum_same_patch_games_per_team": 1,
        }
    )
    return TeamStrengthPolicy.model_validate(payload)


def _matches(*, holdout_opponent: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "match_id": 1,
                "league_id": 100,
                "start_time": "2025-06-01T00:00:00Z",
                "radiant_team_id": 1,
                "dire_team_id": 3,
                "radiant_win": True,
                "patch_name": "7.39",
                "league_tier": "premium",
            },
            {
                "match_id": 2,
                "league_id": 100,
                "start_time": "2025-06-02T00:00:00Z",
                "radiant_team_id": 2,
                "dire_team_id": 3,
                "radiant_win": False,
                "patch_name": "7.39",
                "league_tier": "premium",
            },
            {
                "match_id": 3,
                "league_id": 999,
                "start_time": "2025-09-01T00:00:00Z",
                "radiant_team_id": 1,
                "dire_team_id": holdout_opponent,
                "radiant_win": True,
                "patch_name": "7.39",
                "league_tier": "premium",
            },
        ]
    )


def _patches() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"name": "7.38", "date": "2025-02-19T00:00:00Z"},
            {"name": "7.39", "date": "2025-05-22T00:00:00Z"},
        ]
    )


def test_holdout_reports_observed_count_without_using_it_as_a_gate() -> None:
    _, _, report, issues = evaluate_league_holdout(
        _matches(),
        _patches(),
        policy=_policy(target_team_ids=[1, 2]),
        league_id=999,
    )

    assert report["same_patch_ti_team_games"] == 2
    assert report["declared_target_team_ids"] == [1, 2]
    assert "holdout-same-patch-count-mismatch" not in {issue.code for issue in issues}


def test_holdout_blocks_when_actual_team_ids_differ_from_declared_cohort() -> None:
    _, _, _, issues = evaluate_league_holdout(
        _matches(holdout_opponent=4),
        _patches(),
        policy=_policy(target_team_ids=[1, 2]),
        league_id=999,
    )

    assert "holdout-target-team-mismatch" in {issue.code for issue in issues}
