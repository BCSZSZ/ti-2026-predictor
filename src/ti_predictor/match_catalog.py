from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ti_predictor.schemas import as_utc


@dataclass(frozen=True)
class PatchPoint:
    patch_id: int
    name: str
    effective_at: datetime


def normalize_league_tier(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized else "unknown"


def build_patch_timeline(rows: list[dict[str, Any]]) -> list[PatchPoint]:
    timeline = [
        PatchPoint(
            patch_id=int(row["id"]),
            name=str(row["name"]),
            effective_at=as_utc(row["date"]),
        )
        for row in rows
        if row.get("id") is not None and row.get("name") and row.get("date")
    ]
    return sorted(timeline, key=lambda item: item.effective_at)


def patch_at(start_time: datetime, timeline: list[PatchPoint]) -> PatchPoint | None:
    if not timeline:
        return None
    cutoff = as_utc(start_time)
    offsets = [item.effective_at for item in timeline]
    index = bisect_right(offsets, cutoff) - 1
    return timeline[index] if index >= 0 else None


def filter_match_catalog(
    matches: pd.DataFrame,
    *,
    start_at: datetime | None = None,
    end_before: datetime | None = None,
    patch_names: set[str] | None = None,
    league_tiers: set[str] | None = None,
    league_ids: set[int] | None = None,
    pro_only: bool = True,
) -> pd.DataFrame:
    if matches.empty:
        return matches.copy()
    filtered = matches.copy()
    filtered["start_time"] = pd.to_datetime(filtered["start_time"], utc=True, errors="coerce")
    filtered = filtered.loc[filtered["start_time"].notna()]
    if pro_only:
        if "is_pro_match" not in filtered:
            return filtered.iloc[0:0].copy()
        filtered = filtered.loc[filtered["is_pro_match"].eq(True)]
    if start_at is not None:
        filtered = filtered.loc[filtered["start_time"] >= pd.Timestamp(as_utc(start_at))]
    if end_before is not None:
        filtered = filtered.loc[filtered["start_time"] < pd.Timestamp(as_utc(end_before))]
    if patch_names:
        if "patch_name" not in filtered:
            return filtered.iloc[0:0].copy()
        filtered = filtered.loc[filtered["patch_name"].astype("string").isin(patch_names)]
    if league_tiers:
        if "league_tier" not in filtered:
            return filtered.iloc[0:0].copy()
        normalized_tiers = {normalize_league_tier(value) for value in league_tiers}
        row_tiers = filtered["league_tier"].map(normalize_league_tier)
        filtered = filtered.loc[row_tiers.isin(normalized_tiers)]
    if league_ids:
        if "league_id" not in filtered:
            return filtered.iloc[0:0].copy()
        filtered = filtered.loc[filtered["league_id"].isin(league_ids)]
    return filtered.sort_values(["start_time", "match_id"], ascending=[False, False]).reset_index(drop=True)


def utc_year_bounds(year: int) -> tuple[datetime, datetime]:
    if year < 2013:
        raise ValueError("professional match catalog year must be 2013 or later")
    return datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)
