from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include an explicit timezone")
    return parsed.astimezone(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AuditIssue(StrictModel):
    code: str
    severity: Literal["info", "warning", "blocking"]
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class RuleSourceFile(StrictModel):
    path: str
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RuleSnapshot(StrictModel):
    snapshot_id: str
    event_id: str
    as_of: datetime
    created_at: datetime = Field(default_factory=utc_now)
    source: Literal["dota_client", "canonical_fixture"]
    steam_build: str | None = None
    source_files: list[RuleSourceFile]
    canonical_rules_sha256: str
    snapshot_sha256: str
    status: Literal["publishable", "warning", "blocked"]
    issues: list[AuditIssue] = Field(default_factory=list)
    observed: dict[str, Any] = Field(default_factory=dict)

    _utc_as_of = field_validator("as_of", "created_at", mode="before")(as_utc)


class PlayerEntry(StrictModel):
    account_id: int = Field(gt=0)
    name: str = Field(min_length=1)


class TeamEntry(StrictModel):
    team_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    players: dict[Literal["core", "mid", "support"], list[PlayerEntry]]

    @model_validator(mode="after")
    def validate_role_counts(self) -> TeamEntry:
        expected = {"core": 2, "mid": 1, "support": 2}
        counts = {role: len(players) for role, players in self.players.items()}
        if counts != expected:
            raise ValueError(f"team {self.team_id} role counts must be {expected}, got {counts}")
        account_ids = [player.account_id for players in self.players.values() for player in players]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError(f"team {self.team_id} has duplicate account IDs")
        return self


class TournamentManifest(StrictModel):
    schema_version: int = 1
    event_id: str
    display_name: str
    league_id: int = Field(gt=0)
    timezone: str
    history_league_ids: list[int] = Field(default_factory=list)
    group_lock_at: datetime
    main_lock_at: datetime
    roster_valid_from: datetime
    teams: list[TeamEntry]
    main_event_seeds: list[int] = Field(default_factory=list)

    _utc_times = field_validator("group_lock_at", "main_lock_at", "roster_valid_from", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_teams(self) -> TournamentManifest:
        team_ids = [team.team_id for team in self.teams]
        if len(team_ids) != len(set(team_ids)):
            raise ValueError("tournament manifest contains duplicate team IDs")
        player_ids = [
            player.account_id
            for team in self.teams
            for players in team.players.values()
            for player in players
        ]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("tournament manifest assigns a player to more than one team")
        if self.main_event_seeds:
            if len(self.main_event_seeds) != 8 or len(set(self.main_event_seeds)) != 8:
                raise ValueError("main_event_seeds must contain eight unique team IDs")
            unknown = set(self.main_event_seeds) - set(team_ids)
            if unknown:
                raise ValueError(f"main_event_seeds contains unknown team IDs: {sorted(unknown)}")
        return self


class RosterInterval(StrictModel):
    team_id: int = Field(gt=0)
    account_id: int = Field(gt=0)
    role: Literal["core", "mid", "support"]
    valid_from: datetime
    valid_to: datetime | None = None
    source: str
    as_of: datetime

    _utc_times = field_validator("valid_from", "valid_to", "as_of", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_interval(self) -> RosterInterval:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if self.valid_from > self.as_of:
            raise ValueError("roster interval begins after as_of")
        return self


class MatchSnapshot(StrictModel):
    match_id: int = Field(gt=0)
    league_id: int | None = None
    series_id: int | None = None
    series_type: int | None = None
    start_time: datetime
    radiant_team_id: int | None = None
    dire_team_id: int | None = None
    radiant_win: bool | None = None
    duration: int | None = Field(default=None, ge=0)
    patch: int | None = None
    radiant_score: int | None = Field(default=None, ge=0)
    dire_score: int | None = Field(default=None, ge=0)
    data_source: str = "opendota"
    source_sha256: str
    fetched_at: datetime
    as_of: datetime

    _utc_times = field_validator("start_time", "fetched_at", "as_of", mode="before")(as_utc)

    @model_validator(mode="after")
    def reject_future_match(self) -> MatchSnapshot:
        if self.start_time > self.as_of:
            raise ValueError("match starts after as_of")
        if (
            self.radiant_win is not None
            and self.duration is not None
            and self.start_time.timestamp() + self.duration > self.as_of.timestamp()
        ):
            raise ValueError("completed match was not public by as_of")
        return self


class FantasyObservation(StrictModel):
    match_id: int = Field(gt=0)
    series_id: int | None = None
    account_id: int = Field(gt=0)
    team_id: int | None = None
    role: Literal["core", "mid", "support"] | None = None
    start_time: datetime
    stats: dict[str, float | None]
    provenance: dict[str, Literal["exact", "derived", "proxy", "unavailable"]]
    source_sha256: str
    as_of: datetime

    _utc_times = field_validator("start_time", "as_of", mode="before")(as_utc)

    @model_validator(mode="after")
    def reject_future_observation(self) -> FantasyObservation:
        if self.start_time > self.as_of:
            raise ValueError("fantasy observation starts after as_of")
        missing_provenance = set(self.stats) - set(self.provenance)
        if missing_provenance:
            raise ValueError(f"missing provenance for: {sorted(missing_provenance)}")
        return self


class StrategyProfile(StrEnum):
    EXPECTED_POINTS = "expected_points"
    TOP_10 = "top_10"
    TOP_100 = "top_100"

    @classmethod
    def all(cls) -> list[StrategyProfile]:
        return list(cls)


class Recommendation(StrictModel):
    recommendation_type: Literal["group", "bracket", "fantasy"]
    profile: StrategyProfile
    as_of: datetime
    generated_at: datetime = Field(default_factory=utc_now)
    status: Literal["publishable", "warning", "blocked"]
    objective_value: float | None = None
    confidence: Literal["high", "medium", "low", "unavailable"] = "unavailable"
    selections: dict[str, Any]
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    _utc_times = field_validator("as_of", "generated_at", mode="before")(as_utc)


class ForecastRun(StrictModel):
    run_id: str
    kind: Literal["group", "bracket", "fantasy", "backtest", "rules", "data"]
    as_of: datetime
    created_at: datetime = Field(default_factory=utc_now)
    status: Literal["publishable", "warning", "blocked"]
    seed: int = Field(ge=0)
    rule_sha256: str
    rule_snapshot_id: str | None = None
    rule_snapshot_sha256: str | None = None
    data_sha256: str
    config_sha256: str
    git_commit: str | None = None
    model: dict[str, Any] = Field(default_factory=dict)
    profiles: list[StrategyProfile] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    _utc_times = field_validator("as_of", "created_at", mode="before")(as_utc)
