from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from ti_predictor.config import load_rules, load_tournament_manifest, roster_intervals
from ti_predictor.identity import RosterIndex
from ti_predictor.match_catalog import (
    PatchPoint,
    build_patch_timeline,
    normalize_league_tier,
    patch_at,
    utc_year_bounds,
)
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import (
    AuditIssue,
    FantasyPerformanceSample,
    MatchSnapshot,
    as_utc,
    utc_now,
)
from ti_predictor.storage import DataStore, read_parquet_if_exists

FANTASY_STAT_IDS = (
    "kills",
    "deaths",
    "creep_score",
    "gpm",
    "madstone_collected",
    "tower_kills",
    "wards_placed",
    "camps_stacked",
    "runes_grabbed",
    "smokes_used",
    "watchers_taken",
    "lotuses_gained",
    "roshan_kills",
    "teamfight_participation",
    "first_blood",
    "stuns",
    "tormentor_kills",
    "courier_kills",
)

FANTASY_SAMPLE_BASE_COLUMNS = (
    "match_id",
    "series_id",
    "account_id",
    "team_id",
    "role",
    "start_time",
    "source_sha256",
    "as_of",
    "duration",
)


@dataclass
class SyncResult:
    matches_path: Path
    fantasy_samples_path: Path
    roster_path: Path
    leagues_path: Path | None
    patches_path: Path | None
    requested_leagues: list[int]
    pro_year: int | None
    match_count: int
    pro_match_count: int
    fantasy_sample_count: int
    detailed_match_count: int
    data_sha256: str
    issues: list[AuditIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(issue.severity == "blocking" for issue in self.issues):
            return "blocked"
        if any(issue.severity == "warning" for issue in self.issues):
            return "warning"
        return "publishable"


@dataclass
class MatchCandidate:
    league_id: int
    summary: dict[str, Any]
    fetched_at: datetime
    source_hash: str
    detail_eligible: bool
    is_pro_match: bool = False


class OpenDotaClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.opendota.com/api",
        api_key: str | None = None,
        client: httpx.Client | None = None,
        min_interval_seconds: float = 1.05,
        rate_limit_pause_seconds: float = 61.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENDOTA_API_KEY")
        self.client = client or httpx.Client(timeout=45.0, headers={"User-Agent": "ti-predictor/0.1"})
        self._owns_client = client is None
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.rate_limit_pause_seconds = max(1.0, rate_limit_pause_seconds)
        self._sleep = sleeper
        self._last_request = 0.0
        self._next_request_delay = 0.0

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> OpenDotaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _throttle(self) -> None:
        interval_delay = self.min_interval_seconds - (time.monotonic() - self._last_request)
        delay = max(0.0, interval_delay, self._next_request_delay)
        self._next_request_delay = 0.0
        if delay > 0:
            self._sleep(delay)

    def _rate_limit_delay(self, response: httpx.Response) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(1.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after).astimezone(UTC)
                    return max(1.0, (retry_at - utc_now()).total_seconds())
                except (TypeError, ValueError):
                    pass
        return self.rate_limit_pause_seconds

    def get_json(self, resource: str, *, query: dict[str, int | str] | None = None) -> tuple[Any, datetime]:
        params: dict[str, int | str] = dict(query or {})
        if self.api_key:
            params["api_key"] = self.api_key
        url = f"{self.base_url}/{resource.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(4):
            self._throttle()
            try:
                response = self.client.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = error
                if attempt == 3:
                    raise
                self._sleep(min(0.5 * (2**attempt), 8.0))
                continue
            self._last_request = time.monotonic()
            if response.status_code == 429:
                if response.headers.get("X-Rate-Limit-Remaining-Day") == "0":
                    raise httpx.NetworkError("OpenDota daily rate limit reached; configure OPENDOTA_API_KEY")
                last_error = httpx.NetworkError("OpenDota minute rate limit reached")
                if attempt == 3:
                    raise last_error
                self._sleep(self._rate_limit_delay(response))
                continue
            response.raise_for_status()
            if response.headers.get("X-Rate-Limit-Remaining-Minute") == "0":
                self._next_request_delay = self.rate_limit_pause_seconds
            return response.json(), utc_now()
        raise RuntimeError("OpenDota request retry loop exhausted") from last_error

    def league_matches(self, league_id: int) -> tuple[list[dict[str, Any]], datetime]:
        payload, fetched_at = self.get_json(f"leagues/{league_id}/matches")
        if not isinstance(payload, list):
            raise TypeError(f"OpenDota league {league_id} response is not a list")
        return payload, fetched_at

    def match(self, match_id: int) -> tuple[dict[str, Any], datetime]:
        payload, fetched_at = self.get_json(f"matches/{match_id}")
        if not isinstance(payload, dict):
            raise TypeError(f"OpenDota match {match_id} response is not an object")
        return payload, fetched_at

    def team_matches(self, team_id: int) -> tuple[list[dict[str, Any]], datetime]:
        payload, fetched_at = self.get_json(f"teams/{team_id}/matches")
        if not isinstance(payload, list):
            raise TypeError(f"OpenDota team {team_id} response is not a list")
        return payload, fetched_at

    def pro_matches(self, less_than_match_id: int | None = None) -> tuple[list[dict[str, Any]], datetime]:
        query = {"less_than_match_id": less_than_match_id} if less_than_match_id is not None else None
        payload, fetched_at = self.get_json("proMatches", query=query)
        if not isinstance(payload, list):
            raise TypeError("OpenDota proMatches response is not a list")
        return payload, fetched_at

    def leagues(self) -> tuple[list[dict[str, Any]], datetime]:
        payload, fetched_at = self.get_json("leagues")
        if not isinstance(payload, list):
            raise TypeError("OpenDota leagues response is not a list")
        return payload, fetched_at

    def patches(self) -> tuple[list[dict[str, Any]], datetime]:
        payload, fetched_at = self.get_json("constants/patch")
        if not isinstance(payload, list):
            raise TypeError("OpenDota constants/patch response is not a list")
        return payload, fetched_at


def _unix_utc(value: int | float | str | None) -> datetime:
    if value is None:
        raise ValueError("missing Unix timestamp")
    return datetime.fromtimestamp(float(value), tz=UTC)


def _completed_by(payload: dict[str, Any], cutoff: datetime) -> bool:
    if payload.get("start_time") is None or payload.get("duration") is None:
        return False
    end_time = float(payload["start_time"]) + float(payload["duration"])
    return datetime.fromtimestamp(end_time, tz=UTC) <= cutoff and payload.get("radiant_win") is not None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mapping_value(player: dict[str, Any], mapping: str, key: str) -> float | None:
    values = player.get(mapping)
    if not isinstance(values, dict) or key not in values:
        return None
    return _number(values.get(key))


def _mapping_sum(player: dict[str, Any], mapping: str, keys: Iterable[str]) -> float | None:
    values = player.get(mapping)
    if not isinstance(values, dict):
        return None
    seen = False
    total = 0.0
    for key in keys:
        if key in values and _number(values[key]) is not None:
            seen = True
            total += float(values[key])
    return total if seen else None


def extract_fantasy_stats(player: dict[str, Any]) -> dict[str, float | None]:
    last_hits = _number(player.get("last_hits"))
    denies = _number(player.get("denies"))
    creep_score = last_hits + denies if last_hits is not None and denies is not None else None
    return {
        "kills": _number(player.get("kills")),
        "deaths": _number(player.get("deaths")),
        "creep_score": creep_score,
        "gpm": _number(player.get("gold_per_min")),
        "madstone_collected": _mapping_sum(player, "item_uses", ("madstone_bundle", "item_madstone_bundle")),
        "tower_kills": _number(player.get("towers_killed")),
        "wards_placed": _number(player.get("obs_placed")),
        "camps_stacked": _number(player.get("camps_stacked")),
        "runes_grabbed": _number(player.get("rune_pickups")),
        "smokes_used": _mapping_sum(player, "item_uses", ("smoke_of_deceit", "item_smoke_of_deceit")),
        "watchers_taken": _mapping_value(player, "ability_uses", "ability_lamp_use"),
        "lotuses_gained": _mapping_sum(
            player,
            "item_uses",
            (
                "famango",
                "great_famango",
                "greater_famango",
                "item_famango",
                "item_great_famango",
                "item_greater_famango",
            ),
        ),
        "roshan_kills": _number(player.get("roshans_killed")),
        "teamfight_participation": _number(player.get("teamfight_participation")),
        "first_blood": _number(player.get("firstblood_claimed")),
        "stuns": _number(player.get("stuns")),
        "tormentor_kills": _mapping_value(player, "killed", "npc_dota_miniboss"),
        "courier_kills": _number(player.get("courier_kills")),
    }


def _match_snapshot(
    payload: dict[str, Any],
    *,
    league_id: int,
    league_metadata: dict[str, Any] | None,
    patch_point: PatchPoint | None,
    is_pro_match: bool,
    fetched_at: datetime,
    source_hash: str,
    league_source_hash: str | None,
    patch_source_hash: str | None,
    as_of: datetime,
) -> MatchSnapshot:
    resolved_league_id = int(payload.get("leagueid") or payload.get("league_id") or league_id)
    league_metadata = league_metadata or {}
    patch_id = payload.get("patch")
    if patch_id is None and patch_point is not None:
        patch_id = patch_point.patch_id
    return MatchSnapshot(
        match_id=int(payload["match_id"]),
        league_id=resolved_league_id if resolved_league_id > 0 else None,
        league_name=payload.get("league_name") or league_metadata.get("name"),
        league_tier=normalize_league_tier(league_metadata.get("tier")),
        series_id=payload.get("series_id"),
        series_type=payload.get("series_type"),
        start_time=_unix_utc(payload.get("start_time")),
        radiant_team_id=payload.get("radiant_team_id"),
        radiant_team_name=payload.get("radiant_name") or payload.get("radiant_team_name"),
        dire_team_id=payload.get("dire_team_id"),
        dire_team_name=payload.get("dire_name") or payload.get("dire_team_name"),
        radiant_win=payload.get("radiant_win"),
        duration=payload.get("duration"),
        patch=patch_id,
        patch_name=patch_point.name if patch_point is not None else None,
        radiant_score=payload.get("radiant_score"),
        dire_score=payload.get("dire_score"),
        is_pro_match=is_pro_match,
        source_sha256=source_hash,
        league_source_sha256=league_source_hash,
        patch_source_sha256=patch_source_hash,
        fetched_at=fetched_at,
        as_of=as_of,
    )


def _fantasy_performance_rows(
    payload: dict[str, Any],
    *,
    source_hash: str,
    as_of: datetime,
    roster_index: RosterIndex,
    provenance: dict[str, str],
) -> list[dict[str, Any]]:
    start_time = _unix_utc(payload.get("start_time"))
    rows: list[dict[str, Any]] = []
    for player in payload.get("players") or []:
        account_id = player.get("account_id")
        if not account_id or int(account_id) <= 0:
            continue
        player_slot = int(player.get("player_slot", 0))
        team_id = payload.get("dire_team_id") if player_slot >= 128 else payload.get("radiant_team_id")
        roster = roster_index.resolve(int(account_id), start_time)
        stats = extract_fantasy_stats(player)
        observation = FantasyPerformanceSample(
            match_id=int(payload["match_id"]),
            series_id=payload.get("series_id"),
            account_id=int(account_id),
            team_id=int(team_id) if team_id else (roster.team_id if roster else None),
            role=roster.role if roster else None,
            start_time=start_time,
            stats=stats,
            provenance={key: provenance[key] for key in FANTASY_STAT_IDS},
            source_sha256=source_hash,
            as_of=as_of,
        )
        row = {
            "match_id": observation.match_id,
            "series_id": observation.series_id,
            "account_id": observation.account_id,
            "team_id": observation.team_id,
            "role": observation.role,
            "start_time": observation.start_time,
            "source_sha256": observation.source_sha256,
            "as_of": observation.as_of,
            "duration": payload.get("duration"),
        }
        for stat_id, value in observation.stats.items():
            row[stat_id] = value
            row[f"{stat_id}_provenance"] = observation.provenance[stat_id]
        rows.append(row)
    return rows


def _merge_rows(path: Path, rows: list[dict[str, Any]], keys: list[str]) -> pd.DataFrame:
    existing = read_parquet_if_exists(path)
    incoming = pd.DataFrame(rows)
    if existing.empty:
        combined = incoming
    elif incoming.empty:
        combined = existing
    else:
        combined = pd.concat([existing, incoming], ignore_index=True)
    if not combined.empty:
        combined = combined.drop_duplicates(subset=keys, keep="last").sort_values(keys).reset_index(drop=True)
    return combined


def _coverage_issues(samples: pd.DataFrame) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if samples.empty:
        return [
            AuditIssue(
                code="fantasy-no-detail-data",
                severity="warning",
                message="No detailed player matches were synchronized; Fantasy remains unavailable",
            )
        ]
    for stat_id in FANTASY_STAT_IDS:
        coverage = float(samples[stat_id].notna().mean()) if stat_id in samples else 0.0
        severity = "warning" if coverage < 0.95 else "info"
        issues.append(
            AuditIssue(
                code=f"coverage-{stat_id}",
                severity=severity,
                message=f"Fantasy field {stat_id} coverage is {coverage:.1%}",
                context={"coverage": coverage},
            )
        )
    return issues


def sync_opendota(
    *,
    as_of: datetime,
    league_ids: list[int] | None = None,
    pro_year: int | None = None,
    include_details: bool = True,
    include_team_history: bool = False,
    team_history_limit: int = 100,
    team_history_detail_limit: int = 20,
    max_matches: int | None = None,
    refresh_details: bool = False,
    client: OpenDotaClient | None = None,
    paths: ProjectPaths = PATHS,
) -> SyncResult:
    cutoff = as_utc(as_of)
    manifest = load_tournament_manifest(paths.tournament)
    requested = league_ids or [*manifest.history_league_ids, manifest.league_id]
    rules = load_rules(paths.rules)
    provenance = {stat_id: rules["fantasy"]["stats"][stat_id]["provenance"] for stat_id in FANTASY_STAT_IDS}
    roster_as_of = max(cutoff, manifest.roster_valid_from)
    intervals = roster_intervals(manifest, as_of=roster_as_of)
    roster_index = RosterIndex(intervals)
    store = DataStore(paths)
    matches_path = paths.processed / "matches.parquet"
    fantasy_samples_path = paths.processed / "fantasy_performance_samples.parquet"
    roster_path = paths.processed / "roster_intervals.parquet"
    leagues_path = paths.processed / "leagues.parquet"
    patches_path = paths.processed / "patches.parquet"
    existing_matches = read_parquet_if_exists(matches_path)
    existing_samples = read_parquet_if_exists(fantasy_samples_path)
    existing_leagues = read_parquet_if_exists(leagues_path)
    existing_patches = read_parquet_if_exists(patches_path)
    existing_match_ids = (
        {int(value) for value in existing_matches["match_id"].dropna()}
        if "match_id" in existing_matches
        else set()
    )
    existing_detail_ids = (
        {int(value) for value in existing_samples["match_id"].dropna()}
        if "match_id" in existing_samples
        else set()
    )
    own_client = client is None
    api = client or OpenDotaClient()
    match_rows: list[dict[str, Any]] = []
    fantasy_sample_rows: list[dict[str, Any]] = []
    detailed = 0
    issues: list[AuditIssue] = []

    league_rows = existing_leagues.to_dict(orient="records") if not existing_leagues.empty else []
    patch_rows = existing_patches.to_dict(orient="records") if not existing_patches.empty else []
    league_index = {int(row["leagueid"]): row for row in league_rows if row.get("leagueid") is not None}
    patch_timeline = build_patch_timeline(patch_rows)
    patch_source_hash = (
        str(patch_rows[0].get("source_sha256")) if patch_rows and patch_rows[0].get("source_sha256") else None
    )

    try:
        candidates: dict[int, MatchCandidate] = {}
        league_team_ids: set[int] = set()
        history_anchors: list[datetime] = []

        if pro_year is not None:
            year_start, year_end = utc_year_bounds(pro_year)
            if cutoff < year_start:
                raise ValueError(f"as_of {cutoff.isoformat()} is before requested pro year {pro_year}")

            league_payload, league_fetched_at = api.leagues()
            _, league_source_hash = store.write_raw_json(
                source="opendota",
                resource="leagues",
                payload=league_payload,
                request={
                    "method": "GET",
                    "url": f"{getattr(api, 'base_url', 'https://api.opendota.com/api')}/leagues",
                    "http_status": 200,
                },
                fetched_at=league_fetched_at,
            )
            league_rows = [
                {
                    **row,
                    "tier": normalize_league_tier(row.get("tier")),
                    "source_sha256": league_source_hash,
                    "fetched_at": league_fetched_at,
                    "as_of": cutoff,
                }
                for row in league_payload
                if row.get("leagueid") is not None
            ]
            league_index = {int(row["leagueid"]): row for row in league_rows}

            patch_payload, patch_fetched_at = api.patches()
            _, patch_source_hash = store.write_raw_json(
                source="opendota",
                resource="constants/patch",
                payload=patch_payload,
                request={
                    "method": "GET",
                    "url": f"{getattr(api, 'base_url', 'https://api.opendota.com/api')}/constants/patch",
                    "http_status": 200,
                },
                fetched_at=patch_fetched_at,
            )
            patch_rows = [
                {
                    **row,
                    "source_sha256": patch_source_hash,
                    "fetched_at": patch_fetched_at,
                    "as_of": cutoff,
                }
                for row in patch_payload
            ]
            patch_timeline = build_patch_timeline(patch_rows)

            cursor: int | None = None
            seen_cursors: set[int] = set()
            while True:
                payload, fetched_at = api.pro_matches(cursor)
                resource = f"proMatches/{cursor}" if cursor is not None else "proMatches/latest"
                _, source_hash = store.write_raw_json(
                    source="opendota",
                    resource=resource,
                    payload=payload,
                    request={
                        "method": "GET",
                        "url": f"{getattr(api, 'base_url', 'https://api.opendota.com/api')}/proMatches",
                        "http_status": 200,
                        "less_than_match_id": cursor,
                    },
                    fetched_at=fetched_at,
                )
                if not payload:
                    break

                page_times = [
                    _unix_utc(row["start_time"]) for row in payload if row.get("start_time") is not None
                ]
                for row in payload:
                    if not row.get("match_id") or row.get("start_time") is None:
                        continue
                    started_at = _unix_utc(row["start_time"])
                    if not (year_start <= started_at < year_end and started_at <= cutoff):
                        continue
                    if not _completed_by(row, cutoff):
                        continue
                    match_id = int(row["match_id"])
                    candidates[match_id] = MatchCandidate(
                        league_id=int(row.get("leagueid") or 0),
                        summary=row,
                        fetched_at=fetched_at,
                        source_hash=source_hash,
                        detail_eligible=False,
                        is_pro_match=True,
                    )

                if page_times and max(page_times) < year_start:
                    break
                page_ids = [int(row["match_id"]) for row in payload if row.get("match_id")]
                if not page_ids:
                    issues.append(
                        AuditIssue(
                            code="pro-catalog-pagination-missing-match-id",
                            severity="blocking",
                            message=(
                                "OpenDota proMatches page had no usable match ID; catalog may be incomplete"
                            ),
                        )
                    )
                    break
                next_cursor = min(page_ids)
                if next_cursor in seen_cursors or (cursor is not None and next_cursor >= cursor):
                    issues.append(
                        AuditIssue(
                            code="pro-catalog-pagination-stalled",
                            severity="blocking",
                            message="OpenDota proMatches pagination stopped making progress",
                            context={"cursor": cursor, "next_cursor": next_cursor},
                        )
                    )
                    break
                seen_cursors.add(next_cursor)
                cursor = next_cursor

        for league_id in requested:
            payload, fetched_at = api.league_matches(league_id)
            _, source_hash = store.write_raw_json(
                source="opendota",
                resource=f"leagues/{league_id}/matches",
                payload=payload,
                request={
                    "method": "GET",
                    "url": f"{getattr(api, 'base_url', 'https://api.opendota.com/api')}/leagues/{league_id}/matches",
                    "http_status": 200,
                    "league_id": league_id,
                },
                fetched_at=fetched_at,
            )
            valid_starts = [
                _unix_utc(match["start_time"]) for match in payload if match.get("start_time") is not None
            ]
            if league_id != manifest.league_id and valid_starts:
                history_anchors.append(min(valid_starts))
            for match in payload:
                for key in ("radiant_team_id", "dire_team_id"):
                    if match.get(key) and int(match[key]) > 0:
                        league_team_ids.add(int(match[key]))
                if not match.get("match_id") or not match.get("start_time"):
                    continue
                if not _completed_by(match, cutoff):
                    continue
                match_id = int(match["match_id"])
                existing = candidates.get(match_id)
                if existing is not None:
                    existing.detail_eligible = True
                else:
                    candidates[match_id] = MatchCandidate(
                        league_id=league_id,
                        summary=match,
                        fetched_at=fetched_at,
                        source_hash=source_hash,
                        detail_eligible=True,
                    )

        if include_team_history:
            manifest_team_ids = {team.team_id for team in manifest.teams}
            team_history_ids = league_team_ids | manifest_team_ids
            for team_id in sorted(team_history_ids):
                payload, fetched_at = api.team_matches(team_id)
                _, source_hash = store.write_raw_json(
                    source="opendota",
                    resource=f"teams/{team_id}/matches",
                    payload=payload,
                    request={
                        "method": "GET",
                        "url": f"{getattr(api, 'base_url', 'https://api.opendota.com/api')}/teams/{team_id}/matches",
                        "http_status": 200,
                        "team_id": team_id,
                    },
                    fetched_at=fetched_at,
                )
                completed = sorted(
                    (item for item in payload if _completed_by(item, cutoff)),
                    key=lambda item: int(item["start_time"]),
                    reverse=True,
                )
                recent_detail_ids = (
                    {
                        int(item["match_id"])
                        for item in completed[:team_history_detail_limit]
                        if item.get("match_id") is not None
                    }
                    if team_id in manifest_team_ids and team_history_detail_limit > 0
                    else set()
                )
                selected = completed[:team_history_limit]
                for anchor in history_anchors:
                    before_anchor = [item for item in completed if _completed_by(item, anchor)]
                    selected.extend(before_anchor[:team_history_limit])
                selected_by_id = {
                    int(item["match_id"]): item for item in selected if item.get("match_id") is not None
                }
                for item in selected_by_id.values():
                    if not item.get("match_id") or not item.get("start_time"):
                        continue
                    radiant = bool(item.get("radiant"))
                    opponent = item.get("opposing_team_id")
                    if not opponent or int(opponent) <= 0:
                        continue
                    normalized = {
                        **item,
                        "radiant_team_id": team_id if radiant else opponent,
                        "dire_team_id": opponent if radiant else team_id,
                    }
                    match_id = int(item["match_id"])
                    detail_eligible = match_id in recent_detail_ids
                    existing = candidates.get(match_id)
                    if existing is None:
                        candidates[match_id] = MatchCandidate(
                            league_id=int(item.get("leagueid") or 0),
                            summary=normalized,
                            fetched_at=fetched_at,
                            source_hash=source_hash,
                            detail_eligible=detail_eligible,
                        )
                    elif detail_eligible:
                        existing.detail_eligible = True

        ordered = sorted(
            candidates.values(),
            key=lambda item: (int(item.summary["start_time"]), int(item.summary["match_id"])),
        )
        detail_candidates = [
            int(item.summary["match_id"])
            for item in ordered
            if item.detail_eligible
            and (refresh_details or int(item.summary["match_id"]) not in existing_detail_ids)
        ]
        if max_matches is not None:
            detail_candidates = detail_candidates[-max_matches:]
        detail_ids = set(detail_candidates)

        for candidate in ordered:
            summary = candidate.summary
            detail = summary
            detail_hash = candidate.source_hash
            detail_fetched = candidate.fetched_at
            use_detail = (
                include_details and candidate.detail_eligible and int(summary["match_id"]) in detail_ids
            )
            if use_detail:
                detail, detail_fetched = api.match(int(summary["match_id"]))
                _, detail_hash = store.write_raw_json(
                    source="opendota",
                    resource=f"matches/{summary['match_id']}",
                    payload=detail,
                    request={
                        "method": "GET",
                        "url": f"{getattr(api, 'base_url', 'https://api.opendota.com/api')}/matches/{summary['match_id']}",
                        "http_status": 200,
                        "match_id": int(summary["match_id"]),
                    },
                    fetched_at=detail_fetched,
                )
                detailed += 1
            if (
                int(summary["match_id"]) in existing_match_ids
                and not use_detail
                and not candidate.is_pro_match
            ):
                continue
            normalized = {**summary, **detail}
            resolved_league_id = int(
                normalized.get("leagueid") or normalized.get("league_id") or candidate.league_id
            )
            league_metadata = league_index.get(resolved_league_id)
            started_at = _unix_utc(normalized.get("start_time"))
            patch_point = patch_at(started_at, patch_timeline)
            snapshot = _match_snapshot(
                normalized,
                league_id=candidate.league_id,
                league_metadata=league_metadata,
                patch_point=patch_point,
                is_pro_match=candidate.is_pro_match,
                fetched_at=detail_fetched,
                source_hash=detail_hash,
                league_source_hash=(
                    str(league_metadata.get("source_sha256"))
                    if league_metadata and league_metadata.get("source_sha256")
                    else None
                ),
                patch_source_hash=patch_source_hash,
                as_of=cutoff,
            )
            match_rows.append(snapshot.model_dump())
            if use_detail:
                fantasy_sample_rows.extend(
                    _fantasy_performance_rows(
                        detail,
                        source_hash=detail_hash,
                        as_of=cutoff,
                        roster_index=roster_index,
                        provenance=provenance,
                    )
                )
    finally:
        if own_client:
            api.close()

    matches = _merge_rows(matches_path, match_rows, ["match_id"])
    fantasy_samples = _merge_rows(fantasy_samples_path, fantasy_sample_rows, ["match_id", "account_id"])
    if matches.empty and not len(matches.columns):
        matches = pd.DataFrame(columns=list(MatchSnapshot.model_fields))
    if fantasy_samples.empty and not len(fantasy_samples.columns):
        fantasy_sample_columns = list(FANTASY_SAMPLE_BASE_COLUMNS)
        for stat_id in FANTASY_STAT_IDS:
            fantasy_sample_columns.extend((stat_id, f"{stat_id}_provenance"))
        fantasy_samples = pd.DataFrame(columns=fantasy_sample_columns)
    rosters = pd.DataFrame([interval.model_dump() for interval in intervals])
    matches.to_parquet(matches_path, index=False)
    fantasy_samples.to_parquet(fantasy_samples_path, index=False)
    rosters.to_parquet(roster_path, index=False)
    tables = {
        "matches": matches_path,
        "fantasy_performance_samples": fantasy_samples_path,
        "roster_intervals": roster_path,
    }
    if pro_year is not None:
        pd.DataFrame(league_rows).to_parquet(leagues_path, index=False)
        pd.DataFrame(patch_rows).to_parquet(patches_path, index=False)
    if leagues_path.is_file():
        tables["leagues"] = leagues_path
    if patches_path.is_file():
        tables["patches"] = patches_path
    store.refresh_duckdb(tables)
    issues.extend(_coverage_issues(fantasy_samples))
    if matches.empty:
        issues.append(
            AuditIssue(
                code="sync-no-matches",
                severity="warning",
                message="No matches at or before as_of were returned for the requested leagues",
            )
        )

    pro_match_count = 0
    if not matches.empty and "is_pro_match" in matches:
        pro_matches = matches.loc[matches["is_pro_match"].eq(True)].copy()
        if pro_year is not None and not pro_matches.empty:
            year_start, year_end = utc_year_bounds(pro_year)
            starts = pd.to_datetime(pro_matches["start_time"], utc=True, errors="coerce")
            pro_matches = pro_matches.loc[
                (starts >= pd.Timestamp(year_start)) & (starts < pd.Timestamp(year_end))
            ]
        pro_match_count = len(pro_matches)
    if pro_year is not None:
        issues.append(
            AuditIssue(
                code="pro-catalog-coverage",
                severity="info",
                message=(
                    f"OpenDota professional match catalog contains {pro_match_count} Games for {pro_year}"
                ),
                context={"year": pro_year, "games": pro_match_count},
            )
        )
    return SyncResult(
        matches_path=matches_path,
        fantasy_samples_path=fantasy_samples_path,
        roster_path=roster_path,
        leagues_path=leagues_path if leagues_path.is_file() else None,
        patches_path=patches_path if patches_path.is_file() else None,
        requested_leagues=requested,
        pro_year=pro_year,
        match_count=len(matches),
        pro_match_count=pro_match_count,
        fantasy_sample_count=len(fantasy_samples),
        detailed_match_count=detailed,
        data_sha256=store.data_hash(),
        issues=issues,
    )
