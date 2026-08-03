from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ti_predictor.hashing import sha256_file
from ti_predictor.models.policy import TeamStrengthPolicy
from ti_predictor.paths import PATHS
from ti_predictor.schemas import RosterInterval, TournamentManifest


def load_tournament_manifest(path: Path | None = None) -> TournamentManifest:
    manifest_path = path or PATHS.tournament
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return TournamentManifest.model_validate(payload)


def load_rules(path: Path | None = None) -> dict[str, Any]:
    rules_path = path or PATHS.rules
    return json.loads(rules_path.read_text(encoding="utf-8"))


def team_strength_policy_path(
    manifest: TournamentManifest,
    *,
    config_root: Path | None = None,
) -> Path:
    root = (config_root or PATHS.config).resolve()
    path = (root / manifest.team_strength_policy).resolve()
    if path != root and root not in path.parents:
        raise ValueError("team_strength_policy must stay within the config directory")
    return path


def load_team_strength_policy(
    manifest: TournamentManifest | None = None,
    *,
    config_root: Path | None = None,
) -> TeamStrengthPolicy:
    selected = manifest or load_tournament_manifest()
    path = team_strength_policy_path(selected, config_root=config_root)
    return TeamStrengthPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def manifest_hash(path: Path | None = None) -> str:
    return sha256_file(path or PATHS.tournament)


def rules_hash(path: Path | None = None) -> str:
    return sha256_file(path or PATHS.rules)


def roster_intervals(manifest: TournamentManifest, *, as_of=None) -> list[RosterInterval]:
    cutoff = as_of or manifest.roster_valid_from
    intervals: list[RosterInterval] = []
    for team in manifest.teams:
        for role, players in team.players.items():
            for player in players:
                intervals.append(
                    RosterInterval(
                        team_id=team.team_id,
                        account_id=player.account_id,
                        role=role,
                        valid_from=manifest.roster_valid_from,
                        source="config/ti2026.yaml:manual_review",
                        as_of=cutoff,
                    )
                )
    return intervals
