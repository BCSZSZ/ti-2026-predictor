from __future__ import annotations

import pandas as pd
import pytest

from ti_predictor.models.ratings import fit_team_strengths, glicko_probability


def test_rating_model_uses_time_order_and_as_of_filter() -> None:
    frame = pd.DataFrame(
        [
            {
                "match_id": 1,
                "start_time": "2026-01-01T00:00:00Z",
                "radiant_team_id": 1,
                "dire_team_id": 2,
                "radiant_win": True,
            },
            {
                "match_id": 2,
                "start_time": "2027-01-01T00:00:00Z",
                "radiant_team_id": 2,
                "dire_team_id": 1,
                "radiant_win": True,
            },
        ]
    )
    model, report = fit_team_strengths(frame, as_of="2026-08-01T00:00:00Z")
    assert report.training_matches == 1
    assert model.rating(1) > model.rating(2)


def test_glicko_probability_is_symmetric() -> None:
    forward = glicko_probability(1600, 80, 1450, 120)
    reverse = glicko_probability(1450, 120, 1600, 80)
    assert forward + reverse == pytest.approx(1.0)
    assert forward > 0.5
