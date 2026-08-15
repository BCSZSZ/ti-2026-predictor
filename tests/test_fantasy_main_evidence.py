from __future__ import annotations

from types import SimpleNamespace

import pytest

from ti_predictor.fantasy.main_evidence import validate_actual_main_evidence_refresh


def test_actual_main_evidence_requires_post_group_rows_for_every_entrant() -> None:
    snapshot = SimpleNamespace(
        latest_current_event_fantasy_start_at="2026-08-16T12:00:00Z",
        current_event_fantasy_team_ids=tuple(range(1, 17)),
    )

    validate_actual_main_evidence_refresh(
        snapshot,
        entrant_team_ids=tuple(range(1, 9)),
        newer_than="2026-08-10T13:45:12Z",
    )


def test_actual_main_evidence_rejects_a_stale_or_missing_entrant_refresh() -> None:
    stale = SimpleNamespace(
        latest_current_event_fantasy_start_at="2026-08-10T13:45:12Z",
        current_event_fantasy_team_ids=tuple(range(1, 17)),
    )
    with pytest.raises(ValueError, match="newer than the Group freeze"):
        validate_actual_main_evidence_refresh(
            stale,
            entrant_team_ids=tuple(range(1, 9)),
            newer_than="2026-08-10T13:45:12Z",
        )

    missing = SimpleNamespace(
        latest_current_event_fantasy_start_at="2026-08-16T12:00:00Z",
        current_event_fantasy_team_ids=tuple(range(1, 8)),
    )
    with pytest.raises(ValueError, match="Team IDs: 8"):
        validate_actual_main_evidence_refresh(
            missing,
            entrant_team_ids=tuple(range(1, 9)),
            newer_than="2026-08-10T13:45:12Z",
        )
