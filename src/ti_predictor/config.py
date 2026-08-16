from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml

from ti_predictor.hashing import sha256_file
from ti_predictor.models.policy import SwissSimulationPolicy, TeamStrengthPolicy
from ti_predictor.paths import PATHS
from ti_predictor.schemas import RosterInterval, SwissFormat, TournamentManifest, as_utc


def load_tournament_manifest(path: Path | None = None) -> TournamentManifest:
    manifest_path = path or PATHS.tournament
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return TournamentManifest.model_validate(payload)


def load_rules(path: Path | None = None) -> dict[str, Any]:
    rules_path = path or PATHS.rules
    return json.loads(rules_path.read_text(encoding="utf-8"))


def load_swiss_format(
    *,
    as_of,
    manifest: TournamentManifest | None = None,
    path: Path | None = None,
) -> SwissFormat:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("Swiss format requires an explicit UTC as_of")
    selected = SwissFormat.model_validate_json((path or PATHS.swiss).read_text(encoding="utf-8"))
    if selected.as_of > cutoff:
        raise ValueError(f"Swiss format was not available at as_of: {selected.as_of.isoformat()}")
    tournament = manifest or load_tournament_manifest()
    if selected.event_id != tournament.event_id or selected.league_id != tournament.league_id:
        raise ValueError("Swiss format event identity differs from tournament manifest")
    scheduled = {
        team_id for series in selected.first_round for team_id in (series.team_a_id, series.team_b_id)
    }
    declared = {team.team_id for team in tournament.teams}
    if scheduled != declared:
        raise ValueError(
            "Swiss Round 1 team IDs differ from tournament manifest: "
            f"missing={sorted(declared - scheduled)}, unknown={sorted(scheduled - declared)}"
        )
    return selected


def team_strength_policy_path(
    manifest: TournamentManifest,
    *,
    config_root: Path | None = None,
    period: Literal["group", "main"] = "group",
) -> Path:
    root = (config_root or PATHS.config).resolve()
    relative = (
        manifest.main_team_strength_policy
        if period == "main" and manifest.main_team_strength_policy is not None
        else manifest.team_strength_policy
    )
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError("team_strength_policy must stay within the config directory")
    return path


def load_team_strength_policy(
    manifest: TournamentManifest | None = None,
    *,
    config_root: Path | None = None,
    period: Literal["group", "main"] = "group",
) -> TeamStrengthPolicy:
    selected = manifest or load_tournament_manifest()
    path = team_strength_policy_path(selected, config_root=config_root, period=period)
    return TeamStrengthPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def load_swiss_simulation_policy(
    *,
    as_of,
    manifest: TournamentManifest | None = None,
    path: Path | None = None,
) -> SwissSimulationPolicy:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("Swiss simulation policy requires an explicit UTC as_of")
    selected = SwissSimulationPolicy.model_validate_json(
        (path or PATHS.swiss_policy).read_text(encoding="utf-8")
    )
    if selected.as_of > cutoff:
        raise ValueError(f"Swiss simulation policy was not available at as_of: {selected.as_of.isoformat()}")
    tournament = manifest or load_tournament_manifest()
    declared_team_ids = {team.team_id for team in tournament.teams}
    if selected.roster_shock.target_team_id not in declared_team_ids:
        raise ValueError("Swiss roster-shock target is absent from tournament manifest")
    return selected


def manifest_hash(path: Path | None = None) -> str:
    return sha256_file(path or PATHS.tournament)


def rules_hash(path: Path | None = None) -> str:
    return sha256_file(path or PATHS.rules)


def swiss_hash(path: Path | None = None) -> str:
    return sha256_file(path or PATHS.swiss)


def swiss_policy_hash(path: Path | None = None) -> str:
    return sha256_file(path or PATHS.swiss_policy)


def roster_intervals(manifest: TournamentManifest, *, as_of) -> list[RosterInterval]:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("roster intervals require an explicit UTC as_of")
    if manifest.roster_snapshot_as_of is not None and cutoff < manifest.roster_snapshot_as_of:
        raise ValueError(
            f"roster snapshot was not available at as_of: {manifest.roster_snapshot_as_of.isoformat()}"
        )
    intervals: list[RosterInterval] = []
    for entry in manifest.roster_history:
        if entry.valid_from > cutoff:
            continue
        intervals.append(
            RosterInterval(
                team_id=entry.team_id,
                account_id=entry.account_id,
                role=entry.role,
                valid_from=entry.valid_from,
                valid_to=entry.valid_to if entry.valid_to <= cutoff else None,
                source=entry.source,
                provenance=entry.provenance,
                as_of=cutoff,
            )
        )
    for team in manifest.teams:
        for role, players in team.players.items():
            for player in players:
                valid_from = player.valid_from or manifest.roster_valid_from
                if valid_from > cutoff:
                    continue
                intervals.append(
                    RosterInterval(
                        team_id=team.team_id,
                        account_id=player.account_id,
                        role=role,
                        valid_from=valid_from,
                        valid_to=player.valid_to if player.valid_to and player.valid_to <= cutoff else None,
                        source=player.source or "config/ti2026.yaml:manual_review",
                        provenance=player.provenance or "exact",
                        as_of=cutoff,
                    )
                )
    return intervals
