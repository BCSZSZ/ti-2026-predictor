from __future__ import annotations

from datetime import datetime

from ti_predictor.schemas import RosterInterval, TournamentManifest


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


def manifest_lookup(manifest: TournamentManifest) -> tuple[dict[int, str], dict[int, str]]:
    teams = {team.team_id: team.name for team in manifest.teams}
    players = {
        player.account_id: player.name
        for team in manifest.teams
        for role_players in team.players.values()
        for player in role_players
    }
    return teams, players
