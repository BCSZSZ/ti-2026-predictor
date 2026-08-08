from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ti_predictor.models.evidence import (
    build_evidence_set,
    normalize_exact_patch,
    normalize_patch_family,
)
from ti_predictor.models.policy import TeamStrengthPolicy
from ti_predictor.models.ratings import fit_team_strengths, glicko_probability


def _policy() -> TeamStrengthPolicy:
    path = Path(__file__).resolve().parents[1] / "config/models/team-strength-v2.json"
    return TeamStrengthPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _patches() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"name": "7.39", "date": "2025-05-22T23:36:01Z"},
            {"name": "7.40", "date": "2025-12-16T00:50:40.281Z"},
            {"name": "7.41", "date": "2026-03-24T00:50:59.580Z"},
        ]
    )


def _game(**overrides) -> dict:
    result = {
        "match_id": 1,
        "start_time": "2026-05-31T00:00:00Z",
        "radiant_team_id": 1,
        "dire_team_id": 2,
        "radiant_win": True,
        "patch_name": "7.41",
        "league_tier": "professional",
    }
    result.update(overrides)
    return result


def test_patch_family_normalizes_letter_hotfixes() -> None:
    assert normalize_patch_family("7.41d") == "7.41"
    assert normalize_patch_family("7.41E") == "7.41"
    assert normalize_patch_family("unknown") is None
    assert normalize_exact_patch("7.41E") == "7.41e"
    assert normalize_exact_patch("7.41") == "7.41"


def test_evidence_weight_multiplies_patch_tier_and_time() -> None:
    frame = pd.DataFrame(
        [
            _game(match_id=1, start_time="2026-05-02T00:00:00Z"),
            _game(
                match_id=2,
                start_time="2026-05-02T00:00:00Z",
                patch_name="7.40e",
            ),
            _game(match_id=3, patch_name="7.39"),
            _game(match_id=4, patch_name=None),
            _game(match_id=5, league_tier="excluded"),
        ]
    )
    evidence = build_evidence_set(
        frame,
        _patches(),
        as_of="2026-06-01T00:00:00Z",
        policy=_policy(),
        target_team_ids={1, 2},
    )
    weights = dict(zip(evidence.matches["match_id"], evidence.matches["evidence_weight"], strict=True))
    assert weights[1] == pytest.approx(0.75 * 2 ** (-30 / 60))
    assert weights[2] == pytest.approx(0.15 * 0.75 * 2 ** (-30 / 60))
    assert set(weights) == {1, 2}
    assert evidence.audit["unknown_patch_games"] == 1
    assert evidence.audit["unsupported_tier_games"] == 1


def test_current_exact_patch_multiplier_uses_reviewed_utc_boundary() -> None:
    frame = pd.DataFrame(
        [
            _game(match_id=1, start_time="2026-07-30T23:58:14Z"),
            _game(match_id=2, start_time="2026-07-30T23:58:15Z"),
            _game(
                match_id=3,
                start_time="2026-07-31T00:00:00Z",
                patch_name="7.41e",
            ),
            _game(
                match_id=4,
                start_time="2026-07-31T00:00:00Z",
                patch_name="7.41d",
            ),
            _game(
                match_id=5,
                start_time="2026-07-31T00:00:00Z",
                patch_name="7.40",
            ),
        ]
    )
    evidence = build_evidence_set(
        frame,
        _patches(),
        as_of="2026-08-01T00:00:00Z",
        policy=_policy(),
        target_team_ids={1, 2},
    )
    weighted = evidence.matches.set_index("match_id")

    assert weighted.loc[1, "patch_weight"] == pytest.approx(1.0)
    assert weighted.loc[2, "patch_weight"] == pytest.approx(2.0)
    assert weighted.loc[3, "patch_weight"] == pytest.approx(2.0)
    assert weighted.loc[4, "patch_weight"] == pytest.approx(1.0)
    assert weighted.loc[5, "patch_weight"] == pytest.approx(0.15)
    assert weighted.loc[2, "current_exact_patch"]
    assert weighted.loc[3, "current_exact_patch"]
    assert not weighted.loc[4, "current_exact_patch"]
    assert evidence.audit["current_exact_patch_games"] == 2
    assert evidence.audit["current_exact_patch_weight_active"] is True
    assert evidence.audit["selected_by_exact_patch_multiplier"]["2.0"]["games"] == 2
    assert any(issue.code == "model-evidence-exact-patch-conflict" for issue in evidence.issues)


def test_weighted_elo_uses_game_weight_and_filters_future() -> None:
    frame = pd.DataFrame(
        [
            _game(match_id=1),
            _game(
                match_id=2,
                start_time="2027-01-01T00:00:00Z",
                radiant_team_id=2,
                dire_team_id=1,
            ),
        ]
    )
    model, report = fit_team_strengths(
        frame,
        _patches(),
        as_of="2026-06-02T00:00:00Z",
        policy=_policy(),
        target_team_ids={1, 2},
    )
    assert report.training_matches == 1
    assert report.evidence_audit["future_games"] == 1
    weight = 0.75 * 2 ** (-2 / 60)
    assert model.rating(1) == pytest.approx(1500 + 28 * weight * 0.5)
    assert model.rating(2) == pytest.approx(1500 - 28 * weight * 0.5)


def test_glicko_weights_score_and_information() -> None:
    professional, _ = fit_team_strengths(
        pd.DataFrame([_game(league_tier="professional")]),
        _patches(),
        as_of="2026-06-02T00:00:00Z",
        policy=_policy(),
        target_team_ids={1, 2},
    )
    premium, _ = fit_team_strengths(
        pd.DataFrame([_game(league_tier="premium")]),
        _patches(),
        as_of="2026-06-02T00:00:00Z",
        policy=_policy(),
        target_team_ids={1, 2},
    )
    assert premium.glicko_ratings[1] > professional.glicko_ratings[1]
    assert premium.glicko_deviations[1] < professional.glicko_deviations[1]


def test_glicko_probability_is_symmetric() -> None:
    forward = glicko_probability(1600, 80, 1450, 120)
    reverse = glicko_probability(1450, 120, 1600, 80)
    assert forward + reverse == pytest.approx(1.0)
    assert forward > 0.5


def test_target_connected_component_keeps_recursive_opponents_only() -> None:
    frame = pd.DataFrame(
        [
            _game(match_id=1, radiant_team_id=1, dire_team_id=2),
            _game(match_id=2, radiant_team_id=2, dire_team_id=3),
            _game(match_id=3, radiant_team_id=3, dire_team_id=4),
            _game(match_id=4, radiant_team_id=50, dire_team_id=51),
        ]
    )

    evidence = build_evidence_set(
        frame,
        _patches(),
        as_of="2026-06-02T00:00:00Z",
        policy=_policy(),
        target_team_ids={1},
    )

    assert set(evidence.matches["match_id"]) == {1, 2, 3}
    assert evidence.audit["evidence_scope_mode"] == "target_connected_component"
    assert evidence.audit["pre_scope_positive_weight_games"] == 4
    assert evidence.audit["positive_weight_games"] == 3
    assert evidence.audit["excluded_disconnected_games"] == 1
    assert evidence.audit["connected_team_count"] == 4
    assert len(evidence.audit["selected_match_ids_sha256"]) == 64


def test_target_connected_component_requires_explicit_target_ids() -> None:
    with pytest.raises(ValueError, match="target_team_ids"):
        build_evidence_set(
            pd.DataFrame([_game()]),
            _patches(),
            as_of="2026-06-02T00:00:00Z",
            policy=_policy(),
        )
