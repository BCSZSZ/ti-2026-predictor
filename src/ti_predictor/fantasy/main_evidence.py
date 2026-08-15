"""Time-bounded Fantasy evidence refresh for an actual-eight Main release."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ti_predictor.config import (
    load_rules,
    load_team_strength_policy,
    load_tournament_manifest,
)
from ti_predictor.fantasy.scenarios import (
    PoolBuildResult,
    build_series_block_pools,
    load_group_scenario_policy,
)
from ti_predictor.forecasting import _available_by_as_of, load_strength_model_as_of
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.models.ratings import ModelReport, TeamStrengthModel
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import as_utc
from ti_predictor.storage import read_parquet_if_exists


@dataclass(frozen=True)
class MainEvidenceSnapshot:
    as_of: str
    data_snapshot_sha256: str
    pool_result: PoolBuildResult
    model: TeamStrengthModel
    model_report: ModelReport
    current_event_fantasy_game_count: int
    current_event_fantasy_team_ids: tuple[int, ...]
    latest_current_event_fantasy_start_at: str | None
    warnings: tuple[str, ...]


def build_main_evidence_snapshot(
    *,
    as_of,
    paths: ProjectPaths = PATHS,
) -> MainEvidenceSnapshot:
    """Rebuild Main pools from locally refreshed data without changing the Group freeze."""

    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("Main evidence requires an explicit as_of")
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    scenario_policy_path = paths.config / "models" / "fantasy-group-scenarios-v2.json"
    scenario_policy = load_group_scenario_policy(scenario_policy_path)
    matches_path = paths.processed / "matches.parquet"
    observations_path = paths.processed / "fantasy_performance_samples.parquet"
    patches_path = paths.processed / "patches.parquet"
    for required_path in (matches_path, observations_path, patches_path):
        if not required_path.is_file():
            raise FileNotFoundError(
                f"Main evidence requires the refreshed processed snapshot: {required_path}"
            )

    matches = _available_by_as_of(read_parquet_if_exists(matches_path), cutoff)
    observations = _available_by_as_of(read_parquet_if_exists(observations_path), cutoff)
    patches = _available_by_as_of(read_parquet_if_exists(patches_path), cutoff)
    model, model_report = load_strength_model_as_of(as_of=cutoff, paths=paths)
    blocking_model = [issue.message for issue in model_report.issues if issue.severity == "blocking"]
    if blocking_model:
        raise ValueError("Main Team-strength model is blocked: " + "; ".join(blocking_model))

    strength_policy = load_team_strength_policy(manifest, config_root=paths.config)
    fantasy_policy = strength_policy.model_copy(
        update={
            "policy_id": f"{strength_policy.policy_id}-fantasy-player-history",
            "evidence_scope": EvidenceScopePolicy(mode="global"),
        }
    )
    evidence = build_evidence_set(
        matches,
        patches,
        as_of=cutoff,
        policy=fantasy_policy,
        target_patch_family=model.target_patch_family,
    )
    blocking_evidence = [issue.message for issue in evidence.issues if issue.severity == "blocking"]
    if blocking_evidence:
        raise ValueError("Main Fantasy evidence is blocked: " + "; ".join(blocking_evidence))

    data_snapshot_sha256 = sha256_json(
        {
            "period": "main",
            "as_of": cutoff_text,
            "matches_sha256": sha256_file(matches_path),
            "observations_sha256": sha256_file(observations_path),
            "patches_sha256": sha256_file(patches_path),
            "rules_sha256": sha256_file(paths.rules),
            "manifest_sha256": sha256_file(paths.tournament),
            "scenario_policy_sha256": sha256_file(scenario_policy_path),
            "selected_match_ids_sha256": evidence.audit["selected_match_ids_sha256"],
            "weight_policy_sha256": evidence.audit["weight_policy_sha256"],
            "target_patch_family": evidence.target_patch_family,
        }
    )
    pool_result = build_series_block_pools(
        observations,
        matches,
        evidence.matches,
        manifest,
        rules,
        scenario_policy,
        as_of=cutoff,
    )
    current_matches = matches.loc[
        pd.to_numeric(matches.get("league_id"), errors="coerce").eq(manifest.league_id)
    ].copy()
    current_match_ids = set(
        pd.to_numeric(current_matches.get("match_id"), errors="coerce").dropna().astype(int)
    )
    current_observations = observations.loc[
        pd.to_numeric(observations.get("match_id"), errors="coerce").isin(current_match_ids)
    ].copy()
    fantasy_match_ids = set(
        pd.to_numeric(current_observations.get("match_id"), errors="coerce").dropna().astype(int)
    )
    fantasy_matches = current_matches.loc[
        pd.to_numeric(current_matches.get("match_id"), errors="coerce").isin(fantasy_match_ids)
    ].copy()
    latest_start = pd.to_datetime(
        fantasy_matches.get("start_time"),
        utc=True,
        errors="coerce",
    ).dropna()
    latest_current_event_fantasy_start_at = (
        None if latest_start.empty else latest_start.max().isoformat().replace("+00:00", "Z")
    )
    current_event_fantasy_team_ids = tuple(
        sorted(set(pd.to_numeric(current_observations.get("team_id"), errors="coerce").dropna().astype(int)))
    )
    unavailable = [
        row
        for row in pool_result.audit.get("team_role_availability", [])
        if row.get("status") == "unavailable"
    ]
    warnings = [
        issue.message for issue in [*evidence.issues, *model_report.issues] if issue.severity == "warning"
    ]
    if unavailable:
        warnings.append(
            "Main refreshed evidence excludes unavailable Team/role candidates: "
            + ", ".join(f"{row['target_team_id']}/{row['role']}" for row in unavailable)
        )
    return MainEvidenceSnapshot(
        as_of=cutoff_text,
        data_snapshot_sha256=data_snapshot_sha256,
        pool_result=pool_result,
        model=model,
        model_report=model_report,
        current_event_fantasy_game_count=len(fantasy_match_ids),
        current_event_fantasy_team_ids=current_event_fantasy_team_ids,
        latest_current_event_fantasy_start_at=latest_current_event_fantasy_start_at,
        warnings=tuple(sorted(set(warnings))),
    )


def validate_actual_main_evidence_refresh(
    snapshot: MainEvidenceSnapshot,
    *,
    entrant_team_ids: tuple[int, ...],
    newer_than,
) -> None:
    """Require post-freeze current-event Fantasy evidence for every actual entrant."""

    boundary = as_utc(newer_than)
    if boundary is None:
        raise ValueError("actual Main evidence validation requires a UTC refresh boundary")
    latest = as_utc(snapshot.latest_current_event_fantasy_start_at)
    if latest is None or latest <= boundary:
        raise ValueError("actual Main evidence has no current-event Fantasy Game newer than the Group freeze")
    missing = sorted(
        set(int(team_id) for team_id in entrant_team_ids) - set(snapshot.current_event_fantasy_team_ids)
    )
    if missing:
        raise ValueError(
            "actual Main evidence has no current-event Fantasy rows for entrant Team IDs: "
            + ", ".join(str(team_id) for team_id in missing)
        )


__all__ = [
    "MainEvidenceSnapshot",
    "build_main_evidence_snapshot",
    "validate_actual_main_evidence_refresh",
]
