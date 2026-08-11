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
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source: str | None = None
    provenance: Literal["exact", "derived"] | None = None

    _utc_times = field_validator("valid_from", "valid_to", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_interval(self) -> PlayerEntry:
        if self.valid_to is not None and (self.valid_from is None or self.valid_to <= self.valid_from):
            raise ValueError("player valid_to requires an earlier valid_from")
        return self


class RosterHistoryEntry(StrictModel):
    team_id: int = Field(gt=0)
    account_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    role: Literal["core", "mid", "support"]
    valid_from: datetime
    valid_to: datetime
    source: str = Field(min_length=1)
    provenance: Literal["exact", "derived"]

    _utc_times = field_validator("valid_from", "valid_to", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_interval(self) -> RosterHistoryEntry:
        if self.valid_to <= self.valid_from:
            raise ValueError("roster history valid_to must be after valid_from")
        return self


class TeamRegistrationIdentity(StrictModel):
    valid_from: datetime
    valid_to: datetime | None = None
    evidence_as_of: datetime
    source: str = Field(min_length=1)
    provenance: Literal["exact", "derived"]

    _utc_times = field_validator("valid_from", "valid_to", "evidence_as_of", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_interval(self) -> TeamRegistrationIdentity:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("team registration identity valid_to must be after valid_from")
        return self


class TeamEntry(StrictModel):
    team_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    registration_identity: TeamRegistrationIdentity | None = None
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


class TeamIdentityBridge(StrictModel):
    bridge_id: str = Field(min_length=1)
    raw_team_id: int = Field(gt=0)
    canonical_team_id: int = Field(gt=0)
    valid_from: datetime
    valid_to: datetime | None = None
    evidence_as_of: datetime
    verified_account_ids: tuple[int, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)
    provenance: Literal["exact", "derived"]

    _utc_times = field_validator("valid_from", "valid_to", "evidence_as_of", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_bridge(self) -> TeamIdentityBridge:
        if self.raw_team_id == self.canonical_team_id:
            raise ValueError("team identity bridge must connect two distinct IDs")
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("team identity bridge valid_to must be after valid_from")
        if any(account_id <= 0 for account_id in self.verified_account_ids):
            raise ValueError("verified_account_ids must contain only positive stable IDs")
        if len(self.verified_account_ids) != len(set(self.verified_account_ids)):
            raise ValueError("verified_account_ids must not contain duplicates")
        return self


class TournamentManifest(StrictModel):
    schema_version: Literal[1, 2, 3] = 1
    event_id: str
    display_name: str
    league_id: int = Field(gt=0)
    team_strength_policy: str = Field(min_length=1)
    timezone: str
    history_league_ids: list[int] = Field(default_factory=list)
    group_lock_at: datetime
    main_lock_at: datetime
    roster_valid_from: datetime
    roster_snapshot_as_of: datetime | None = None
    teams: list[TeamEntry]
    roster_history: list[RosterHistoryEntry] = Field(default_factory=list)
    team_identity_bridges: list[TeamIdentityBridge] = Field(default_factory=list)
    main_event_seeds: list[int] = Field(default_factory=list)

    _utc_times = field_validator(
        "group_lock_at",
        "main_lock_at",
        "roster_valid_from",
        "roster_snapshot_as_of",
        mode="before",
    )(as_utc)

    @model_validator(mode="after")
    def validate_teams(self) -> TournamentManifest:
        if self.schema_version >= 2 and self.roster_snapshot_as_of is None:
            raise ValueError("schema v2+ requires roster_snapshot_as_of")
        if self.schema_version == 1 and self.roster_history:
            raise ValueError("roster_history requires schema version 2")
        if self.schema_version < 3 and self.team_identity_bridges:
            raise ValueError("team_identity_bridges require schema version 3")
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
        unknown_history_teams = {entry.team_id for entry in self.roster_history} - set(team_ids)
        if unknown_history_teams:
            raise ValueError(f"roster_history contains unknown team IDs: {sorted(unknown_history_teams)}")
        bridge_ids = [bridge.bridge_id for bridge in self.team_identity_bridges]
        if len(bridge_ids) != len(set(bridge_ids)):
            raise ValueError("team_identity_bridges contain duplicate bridge IDs")
        unknown_canonical_teams = {bridge.canonical_team_id for bridge in self.team_identity_bridges} - set(
            team_ids
        )
        if unknown_canonical_teams:
            raise ValueError(
                f"team_identity_bridges contain unknown canonical team IDs: {sorted(unknown_canonical_teams)}"
            )
        raw_target_collisions = {bridge.raw_team_id for bridge in self.team_identity_bridges} & set(team_ids)
        if raw_target_collisions:
            raise ValueError(
                "team_identity_bridges cannot merge a current tournament team: "
                f"{sorted(raw_target_collisions)}"
            )
        bridges_by_raw_id: dict[int, list[TeamIdentityBridge]] = {}
        for bridge in self.team_identity_bridges:
            bridges_by_raw_id.setdefault(bridge.raw_team_id, []).append(bridge)
        for raw_team_id, bridges in bridges_by_raw_id.items():
            ordered = sorted(bridges, key=lambda bridge: bridge.valid_from)
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if previous.valid_to is None or current.valid_from < previous.valid_to:
                    raise ValueError(f"team identity bridges overlap for raw team ID {raw_team_id}")
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
    provenance: Literal["exact", "derived"] = "exact"
    as_of: datetime

    _utc_times = field_validator("valid_from", "valid_to", "as_of", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_interval(self) -> RosterInterval:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if self.valid_from > self.as_of:
            raise ValueError("roster interval begins after as_of")
        return self


class SourceSnapshot(StrictModel):
    url: str = Field(min_length=1)
    fetched_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _utc_fetched_at = field_validator("fetched_at", mode="before")(as_utc)


class SwissFirstRoundSeries(StrictModel):
    node_id: str = Field(min_length=1)
    initial_group: Literal["A", "B"]
    start_at: datetime
    team_a_id: int = Field(gt=0)
    team_b_id: int = Field(gt=0)

    _utc_start_at = field_validator("start_at", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_teams(self) -> SwissFirstRoundSeries:
        if self.team_a_id == self.team_b_id:
            raise ValueError("Swiss Series requires two distinct teams")
        return self


class SwissFormat(StrictModel):
    schema_version: Literal[1]
    event_id: str = Field(min_length=1)
    league_id: int = Field(gt=0)
    format_version: str = Field(min_length=1)
    as_of: datetime
    league_source: SourceSnapshot
    rules_source: SourceSnapshot
    initial_group_provenance: Literal["exact", "derived"]
    rounds: Literal[5]
    win_loss_limit: Literal[4]
    series_best_of: Literal[3]
    first_round: list[SwissFirstRoundSeries]

    _utc_as_of = field_validator("as_of", mode="before")(as_utc)

    @model_validator(mode="after")
    def validate_format(self) -> SwissFormat:
        if self.league_source.fetched_at > self.as_of or self.rules_source.fetched_at > self.as_of:
            raise ValueError("Swiss source was fetched after format as_of")
        if len(self.first_round) != 8:
            raise ValueError("Swiss Round 1 requires exactly eight Series")
        node_ids = [series.node_id for series in self.first_round]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Swiss Round 1 contains duplicate node IDs")
        team_ids = [
            team_id for series in self.first_round for team_id in (series.team_a_id, series.team_b_id)
        ]
        if len(team_ids) != 16 or len(team_ids) != len(set(team_ids)):
            raise ValueError("Swiss Round 1 must contain sixteen unique teams")
        group_counts = {
            group: sum(series.initial_group == group for series in self.first_round) for group in ("A", "B")
        }
        if group_counts != {"A": 4, "B": 4}:
            raise ValueError("Swiss initial groups require four Round 1 Series each")
        return self


class MatchSnapshot(StrictModel):
    match_id: int = Field(gt=0)
    league_id: int | None = None
    league_name: str | None = None
    league_tier: str = "unknown"
    series_id: int | None = None
    series_type: int | None = None
    start_time: datetime
    radiant_team_id: int | None = None
    radiant_team_name: str | None = None
    dire_team_id: int | None = None
    dire_team_name: str | None = None
    radiant_win: bool | None = None
    duration: int | None = Field(default=None, ge=0)
    patch: int | None = None
    patch_name: str | None = None
    radiant_score: int | None = Field(default=None, ge=0)
    dire_score: int | None = Field(default=None, ge=0)
    data_source: str = "opendota"
    is_pro_match: bool = False
    source_sha256: str
    league_source_sha256: str | None = None
    patch_source_sha256: str | None = None
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


class FantasyPerformanceSample(StrictModel):
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
    def reject_future_observation(self) -> FantasyPerformanceSample:
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
