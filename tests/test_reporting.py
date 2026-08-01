from __future__ import annotations

from ti_predictor.reporting import filling_checklist


def test_group_checklist_uses_game_order() -> None:
    slots = {
        "four_zero": [{"team_id": 1, "team": "A"}],
        "four_one": [{"team_id": 2, "team": "B"}, {"team_id": 3, "team": "C"}],
        "elimination_winner": [{"team_id": i, "team": str(i)} for i in range(4, 9)],
        "elimination_loser": [{"team_id": i, "team": str(i)} for i in range(9, 14)],
        "one_four": [{"team_id": 14, "team": "14"}, {"team_id": 15, "team": "15"}],
        "zero_four": [{"team_id": 16, "team": "16"}],
    }
    rows = filling_checklist({"recommendation_type": "group", "selections": {"slots": slots}})
    assert len(rows) == 16
    assert rows[0]["section"] == "4-0"
    assert rows[-1]["section"] == "0-4"
