from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ti_predictor.schemas import MatchSnapshot, as_utc


def test_as_utc_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="explicit timezone"):
        as_utc("2026-08-01T00:00:00")


def test_match_snapshot_rejects_future_data() -> None:
    with pytest.raises(ValidationError, match="starts after as_of"):
        MatchSnapshot(
            match_id=1,
            start_time=datetime(2026, 8, 2, tzinfo=UTC),
            source_sha256="0" * 64,
            fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
            as_of=datetime(2026, 8, 1, tzinfo=UTC),
        )
