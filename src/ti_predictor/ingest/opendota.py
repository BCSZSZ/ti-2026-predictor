from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ti_predictor.config import load_rules, load_tournament_manifest, roster_intervals
from ti_predictor.identity import RosterIndex
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import AuditIssue, FantasyObservation, MatchSnapshot, as_utc, utc_now
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


@dataclass
class SyncResult:
    matches_path: Path
    players_path: Path
    roster_path: Path
    requested_leagues: list[int]
    match_count: int
    player_count: int
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


class OpenDotaClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.opendota.com/api",
        api_key: str | None = None,
        client: httpx.Client | None = None,
        min_interval_seconds: float = 1.05,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENDOTA_API_KEY")
        self.client = client or httpx.Client(timeout=45.0, headers={"User-Agent": "ti-predictor/0.1"})
        self._owns_client = client is None
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._last_request = 0.0

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> OpenDotaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _throttle(self) -> None:
        remaining = self.min_interval_seconds - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    def get_json(self, resource: str) -> tuple[Any, datetime]:
        self._throttle()
        params = {"api_key": self.api_key} if self.api_key else None
        response = self.client.get(f"{self.base_url}/{resource.lstrip('/')}", params=params)
        self._last_request = time.monotonic()
        if response.status_code == 429:
            raise httpx.NetworkError("OpenDota rate limit reached")
        response.raise_for_status()
        return response.json(), utc_now()

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
    fetched_at: datetime,
    source_hash: str,
    as_of: datetime,
) -> MatchSnapshot:
    return MatchSnapshot(
        match_id=int(payload["match_id"]),
        league_id=int(payload.get("leagueid") or payload.get("league_id") or league_id),
        series_id=payload.get("series_id"),
        series_type=payload.get("series_type"),
        start_time=_unix_utc(payload.get("start_time")),
        radiant_team_id=payload.get("radiant_team_id"),
        dire_team_id=payload.get("dire_team_id"),
        radiant_win=payload.get("radiant_win"),
        duration=payload.get("duration"),
        patch=payload.get("patch"),
        radiant_score=payload.get("radiant_score"),
        dire_score=payload.get("dire_score"),
        source_sha256=source_hash,
        fetched_at=fetched_at,
        as_of=as_of,
    )


def _fantasy_rows(
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
        observation = FantasyObservation(
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


def _coverage_issues(players: pd.DataFrame) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if players.empty:
        return [
            AuditIssue(
                code="fantasy-no-detail-data",
                severity="warning",
                message="No detailed player matches were synchronized; Fantasy remains unavailable",
            )
        ]
    for stat_id in FANTASY_STAT_IDS:
        coverage = float(players[stat_id].notna().mean()) if stat_id in players else 0.0
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
    players_path = paths.processed / "fantasy_observations.parquet"
    roster_path = paths.processed / "roster_intervals.parquet"
    existing_matches = read_parquet_if_exists(matches_path)
    existing_players = read_parquet_if_exists(players_path)
    existing_match_ids = (
        {int(value) for value in existing_matches["match_id"].dropna()}
        if "match_id" in existing_matches
        else set()
    )
    existing_detail_ids = (
        {int(value) for value in existing_players["match_id"].dropna()}
        if "match_id" in existing_players
        else set()
    )
    own_client = client is None
    api = client or OpenDotaClient()
    match_rows: list[dict[str, Any]] = []
    player_rows: list[dict[str, Any]] = []
    detailed = 0
    issues: list[AuditIssue] = []

    try:
        candidates: dict[int, tuple[int, dict[str, Any], datetime, str, bool]] = {}
        league_team_ids: set[int] = set()
        history_anchors: list[datetime] = []
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
                candidates[match_id] = (league_id, match, fetched_at, source_hash, True)

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
                        candidates[match_id] = (
                            int(item.get("leagueid") or 0),
                            normalized,
                            fetched_at,
                            source_hash,
                            detail_eligible,
                        )
                    elif detail_eligible and not existing[4]:
                        candidates[match_id] = (*existing[:4], True)

        ordered = sorted(
            candidates.values(), key=lambda item: (int(item[1]["start_time"]), int(item[1]["match_id"]))
        )
        detail_candidates = [
            int(item[1]["match_id"])
            for item in ordered
            if item[4] and (refresh_details or int(item[1]["match_id"]) not in existing_detail_ids)
        ]
        if max_matches is not None:
            detail_candidates = detail_candidates[-max_matches:]
        detail_ids = set(detail_candidates)

        for league_id, summary, fetched_at, summary_hash, detail_eligible in ordered:
            detail = summary
            detail_hash = summary_hash
            detail_fetched = fetched_at
            use_detail = include_details and detail_eligible and int(summary["match_id"]) in detail_ids
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
            if int(summary["match_id"]) in existing_match_ids and not use_detail:
                continue
            snapshot = _match_snapshot(
                detail,
                league_id=league_id,
                fetched_at=detail_fetched,
                source_hash=detail_hash,
                as_of=cutoff,
            )
            match_rows.append(snapshot.model_dump())
            if use_detail:
                player_rows.extend(
                    _fantasy_rows(
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
    players = _merge_rows(players_path, player_rows, ["match_id", "account_id"])
    rosters = pd.DataFrame([interval.model_dump() for interval in intervals])
    matches.to_parquet(matches_path, index=False)
    players.to_parquet(players_path, index=False)
    rosters.to_parquet(roster_path, index=False)
    store.refresh_duckdb(
        {"matches": matches_path, "fantasy_observations": players_path, "roster_intervals": roster_path}
    )
    issues.extend(_coverage_issues(players))
    if not match_rows:
        issues.append(
            AuditIssue(
                code="sync-no-matches",
                severity="warning",
                message="No matches at or before as_of were returned for the requested leagues",
            )
        )
    return SyncResult(
        matches_path=matches_path,
        players_path=players_path,
        roster_path=roster_path,
        requested_leagues=requested,
        match_count=len(matches),
        player_count=len(players),
        detailed_match_count=detailed,
        data_sha256=store.data_hash(),
        issues=issues,
    )
