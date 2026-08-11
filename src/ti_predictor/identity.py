from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd

from ti_predictor.hashing import sha256_json
from ti_predictor.schemas import (
    RosterInterval,
    TeamIdentityBridge,
    TeamRegistrationIdentity,
    TournamentManifest,
    as_utc,
)


class RosterIndex:
    def __init__(self, intervals: list[RosterInterval]) -> None:
        self._by_player: dict[int, list[RosterInterval]] = {}
        for interval in intervals:
            self._by_player.setdefault(interval.account_id, []).append(interval)
        for entries in self._by_player.values():
            entries.sort(key=lambda value: value.valid_from)

    def resolve(self, account_id: int, at: datetime) -> RosterInterval | None:
        matches = [
            interval
            for interval in self._by_player.get(account_id, [])
            if interval.valid_from <= at and (interval.valid_to is None or at < interval.valid_to)
        ]
        if len(matches) > 1:
            raise ValueError(f"ambiguous roster identity for account {account_id} at {at.isoformat()}")
        return matches[0] if matches else None


def canonicalize_match_team_ids(
    matches: pd.DataFrame,
    bridges: list[TeamIdentityBridge],
    *,
    as_of: datetime,
    registration_identities: Mapping[int, TeamRegistrationIdentity] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Map source registration IDs to canonical Team identities without mutating raw evidence."""

    required = {"match_id", "start_time", "radiant_team_id", "dire_team_id"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"match identity data is missing required columns: {sorted(missing)}")
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("team identity normalization requires an explicit UTC as_of")

    frame = matches.copy()
    frame["radiant_raw_team_id"] = frame["radiant_team_id"]
    frame["dire_raw_team_id"] = frame["dire_team_id"]
    frame["radiant_team_identity_bridge_id"] = pd.Series(pd.NA, index=frame.index, dtype="string")
    frame["dire_team_identity_bridge_id"] = pd.Series(pd.NA, index=frame.index, dtype="string")
    frame["radiant_registration_identity_excluded"] = False
    frame["dire_registration_identity_excluded"] = False
    starts = pd.to_datetime(frame["start_time"], utc=True, errors="coerce")
    match_ids = pd.to_numeric(frame["match_id"], errors="coerce")

    identity_items = sorted((registration_identities or {}).items())
    registration_payloads = [
        {"team_id": team_id, **identity.model_dump(mode="json")}
        for team_id, identity in identity_items
    ]
    registration_audit: list[dict[str, Any]] = []
    all_excluded_match_ids: set[int] = set()
    for team_id, identity in identity_items:
        available = identity.evidence_as_of <= cutoff
        eligible_time = starts.notna() & starts.lt(pd.Timestamp(cutoff))
        inside_identity = starts.ge(pd.Timestamp(identity.valid_from))
        if identity.valid_to is not None:
            inside_identity &= starts.lt(pd.Timestamp(identity.valid_to))
        outside_identity = eligible_time & ~inside_identity if available else eligible_time & False

        excluded_by_side: dict[str, int] = {}
        excluded_match_ids: set[int] = set()
        for side in ("radiant", "dire"):
            team_column = f"{side}_team_id"
            exclusion_column = f"{side}_registration_identity_excluded"
            team_ids = pd.to_numeric(frame[team_column], errors="coerce")
            mask = outside_identity & team_ids.eq(team_id)
            frame.loc[mask, team_column] = pd.NA
            frame.loc[mask, exclusion_column] = True
            excluded_by_side[side] = int(mask.sum())
            excluded_match_ids.update(int(value) for value in match_ids.loc[mask].dropna())

        all_excluded_match_ids.update(excluded_match_ids)
        registration_audit.append(
            {
                "team_id": team_id,
                **identity.model_dump(mode="json"),
                "available_at_as_of": available,
                "excluded_games": len(excluded_match_ids),
                "excluded_radiant_games": excluded_by_side["radiant"],
                "excluded_dire_games": excluded_by_side["dire"],
                "excluded_match_ids_sha256": sha256_json(sorted(excluded_match_ids)),
            }
        )

    bridge_payloads = [
        bridge.model_dump(mode="json") for bridge in sorted(bridges, key=lambda item: item.bridge_id)
    ]
    audit_bridges: list[dict[str, Any]] = []
    all_mapped_match_ids: set[int] = set()
    for bridge in sorted(bridges, key=lambda item: item.bridge_id):
        available = bridge.evidence_as_of <= cutoff
        time_mask = starts.notna() & starts.lt(pd.Timestamp(cutoff))
        if available:
            time_mask &= starts.ge(pd.Timestamp(bridge.valid_from))
            if bridge.valid_to is not None:
                time_mask &= starts.lt(pd.Timestamp(bridge.valid_to))
        else:
            time_mask &= False

        mapped_by_side: dict[str, int] = {}
        bridge_match_ids: set[int] = set()
        for side in ("radiant", "dire"):
            team_column = f"{side}_team_id"
            bridge_column = f"{side}_team_identity_bridge_id"
            team_ids = pd.to_numeric(frame[team_column], errors="coerce")
            mask = time_mask & team_ids.eq(bridge.raw_team_id)
            conflict = mask & frame[bridge_column].notna()
            if conflict.any():
                raise ValueError(
                    f"multiple team identity bridges apply to {bridge.raw_team_id} at the same Game"
                )
            frame.loc[mask, team_column] = bridge.canonical_team_id
            frame.loc[mask, bridge_column] = bridge.bridge_id
            mapped_by_side[side] = int(mask.sum())
            bridge_match_ids.update(int(value) for value in match_ids.loc[mask].dropna())

        all_mapped_match_ids.update(bridge_match_ids)
        audit_bridges.append(
            {
                **bridge.model_dump(mode="json"),
                "available_at_as_of": available,
                "mapped_games": len(bridge_match_ids),
                "mapped_radiant_games": mapped_by_side["radiant"],
                "mapped_dire_games": mapped_by_side["dire"],
                "mapped_match_ids_sha256": sha256_json(sorted(bridge_match_ids)),
            }
        )

    mapped_rows = frame["radiant_team_identity_bridge_id"].notna() | frame[
        "dire_team_identity_bridge_id"
    ].notna()
    collapsed_self_matches = (
        mapped_rows
        & frame["radiant_team_id"].notna()
        & frame["dire_team_id"].notna()
        & frame["radiant_team_id"].eq(frame["dire_team_id"])
    )
    if collapsed_self_matches.any():
        affected = sorted(int(value) for value in match_ids.loc[collapsed_self_matches].dropna())
        raise ValueError(f"team identity normalization collapsed opponents in Games: {affected}")

    audit = {
        "as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "configured_registration_identity_count": len(identity_items),
        "available_registration_identity_count": sum(
            identity.evidence_as_of <= cutoff for _, identity in identity_items
        ),
        "registration_identity_excluded_games": len(all_excluded_match_ids),
        "registration_identity_excluded_match_ids_sha256": sha256_json(
            sorted(all_excluded_match_ids)
        ),
        "registration_identity_config_sha256": sha256_json(registration_payloads),
        "registration_identities": registration_audit,
        "configured_bridge_count": len(bridges),
        "available_bridge_count": sum(item.evidence_as_of <= cutoff for item in bridges),
        "mapped_games": len(all_mapped_match_ids),
        "mapped_match_ids_sha256": sha256_json(sorted(all_mapped_match_ids)),
        "bridge_config_sha256": sha256_json(bridge_payloads),
        "bridges": audit_bridges,
    }
    return frame, audit


def manifest_lookup(manifest: TournamentManifest) -> tuple[dict[int, str], dict[int, str]]:
    teams = {team.team_id: team.name for team in manifest.teams}
    players = {
        player.account_id: player.name
        for team in manifest.teams
        for role_players in team.players.values()
        for player in role_players
    }
    players.update({entry.account_id: entry.name for entry in manifest.roster_history})
    return teams, players
