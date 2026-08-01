from __future__ import annotations

import json
import os

from ti_predictor.reporting import discover_runs, filling_checklist


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


def test_discover_runs_uses_manifest_mtime_when_created_at_ties(tmp_path) -> None:
    created_at = "2026-08-12T23:00:00Z"
    for run_id, modified_at in (("fantasy-old", 100), ("fantasy-new", 200)):
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        manifest = run_dir / "run.json"
        manifest.write_text(
            json.dumps({"run_id": run_id, "kind": "fantasy", "created_at": created_at}),
            encoding="utf-8",
        )
        os.utime(manifest, (modified_at, modified_at))

    runs = discover_runs(tmp_path, kind="fantasy")

    assert [run["run_id"] for run in runs] == ["fantasy-new", "fantasy-old"]
