from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ti_predictor.config import (
    load_team_strength_policy,
    load_tournament_manifest,
    team_strength_policy_path,
)
from ti_predictor.hashing import sha256_file
from ti_predictor.models.evidence import normalize_patch_family
from ti_predictor.models.policy import TeamStrengthPolicy
from ti_predictor.models.ratings import (
    ModelReport,
    TeamStrengthModel,
    fit_team_strengths,
    fit_unweighted_baseline,
    probability_metrics,
)
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import rule_snapshot_issues
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import AuditIssue, ForecastRun, as_utc
from ti_predictor.storage import read_parquet_if_exists


@dataclass
class BacktestResult:
    run: ForecastRun
    run_path: Path
    report: dict[str, Any]


def _holdout_predictions(
    model: TeamStrengthModel,
    holdout: pd.DataFrame,
) -> dict[str, np.ndarray]:
    elo: list[float] = []
    glicko: list[float] = []
    raw: list[float] = []
    calibrated: list[float] = []
    deployed: list[float] = []
    for row in holdout.itertuples(index=False):
        team_a = int(row.radiant_team_id)
        team_b = int(row.dire_team_id)
        elo_value, glicko_value = model.component_probabilities(team_a, team_b)
        elo.append(elo_value)
        glicko.append(glicko_value)
        raw.append(model.raw_probability(team_a, team_b))
        calibrated.append(model.candidate_calibrated_probability(team_a, team_b))
        deployed.append(model.predict(team_a, team_b))
    return {
        "elo": np.asarray(elo),
        "glicko": np.asarray(glicko),
        "ensemble": np.asarray(raw),
        "calibrated_candidate": np.asarray(calibrated),
        "deployed": np.asarray(deployed),
    }


def evaluate_league_holdout(
    matches: pd.DataFrame,
    patches: pd.DataFrame,
    *,
    policy: TeamStrengthPolicy,
    league_id: int,
) -> tuple[TeamStrengthModel, ModelReport, dict[str, Any], list[AuditIssue]]:
    required = {
        "match_id",
        "league_id",
        "start_time",
        "radiant_team_id",
        "dire_team_id",
        "radiant_win",
        "patch_name",
        "league_tier",
    }
    missing = required - set(matches)
    if missing:
        raise ValueError(f"holdout data is missing columns: {sorted(missing)}")
    frame = matches.copy()
    frame["start_time"] = pd.to_datetime(frame["start_time"], utc=True, errors="coerce")
    frame = frame.loc[
        frame["start_time"].notna()
        & frame["radiant_team_id"].notna()
        & frame["dire_team_id"].notna()
        & frame["radiant_win"].notna()
    ].copy()
    holdout = frame.loc[frame["league_id"] == league_id].sort_values(
        ["start_time", "match_id"], kind="stable"
    )
    if holdout.empty:
        raise ValueError(f"league {league_id} has no completed matches")
    holdout_start = holdout["start_time"].min().to_pydatetime()
    training_cutoff = holdout_start - timedelta(microseconds=1)
    actual_holdout_teams = {
        int(value) for column in ("radiant_team_id", "dire_team_id") for value in holdout[column].dropna()
    }
    declared_target_teams = set(policy.ti2025_holdout.target_team_ids)
    target_teams = declared_target_teams or actual_holdout_teams
    training = frame.loc[
        (frame["start_time"] < pd.Timestamp(holdout_start)) & (frame["league_id"] != league_id)
    ].copy()
    target_patch_family = policy.ti2025_holdout.target_patch_family
    model, model_report = fit_team_strengths(
        training,
        patches,
        as_of=training_cutoff,
        policy=policy,
        target_patch_family=target_patch_family,
        target_team_ids=target_teams,
        calibration_as_of=training_cutoff,
        calibration_target_patch_family=target_patch_family,
    )
    baseline_model = fit_unweighted_baseline(training, as_of=training_cutoff, policy=policy)
    weighted = _holdout_predictions(model, holdout)
    unweighted = _holdout_predictions(baseline_model, holdout)
    outcomes = holdout["radiant_win"].astype(bool).to_numpy(dtype=float)

    training["patch_family"] = training["patch_name"].map(normalize_patch_family)
    training["normalized_league_tier"] = training["league_tier"].map(
        lambda value: None if value is None or pd.isna(value) else str(value).strip().lower()
    )
    same_patch = training.loc[
        training["patch_family"].eq(target_patch_family)
        & training["normalized_league_tier"].isin(policy.tier_weights)
    ]
    same_patch_team_evidence = same_patch.loc[
        same_patch["radiant_team_id"].isin(target_teams) | same_patch["dire_team_id"].isin(target_teams)
    ]
    same_patch_by_team = {
        team_id: int(
            (
                same_patch_team_evidence["radiant_team_id"].eq(team_id)
                | same_patch_team_evidence["dire_team_id"].eq(team_id)
            ).sum()
        )
        for team_id in sorted(target_teams)
    }
    minimum_team_games = min(same_patch_by_team.values(), default=0)
    holdout_patch_families = sorted(
        {family for family in holdout["patch_name"].map(normalize_patch_family) if family is not None}
    )
    holdout_tiers = sorted(
        {str(value).strip().lower() for value in holdout["league_tier"].dropna() if str(value).strip()}
    )

    metrics = {
        "fifty_percent": probability_metrics(outcomes, np.full(len(outcomes), 0.5)),
        "unweighted_elo": probability_metrics(outcomes, unweighted["elo"]),
        "unweighted_glicko": probability_metrics(outcomes, unweighted["glicko"]),
        "unweighted_ensemble": probability_metrics(outcomes, unweighted["ensemble"]),
        "weighted_elo": probability_metrics(outcomes, weighted["elo"]),
        "weighted_glicko": probability_metrics(outcomes, weighted["glicko"]),
        "weighted_ensemble": probability_metrics(outcomes, weighted["ensemble"]),
        "weighted_calibrated_candidate": probability_metrics(outcomes, weighted["calibrated_candidate"]),
        "weighted_deployed": probability_metrics(outcomes, weighted["deployed"]),
    }
    issues: list[AuditIssue] = []
    holdout_policy = policy.ti2025_holdout
    if declared_target_teams and actual_holdout_teams != declared_target_teams:
        issues.append(
            AuditIssue(
                code="holdout-target-team-mismatch",
                severity="blocking",
                message="TI 2025 holdout teams differ from the declared stable-ID cohort",
                context={
                    "declared": sorted(declared_target_teams),
                    "actual": sorted(actual_holdout_teams),
                },
            )
        )
    if len(holdout) != holdout_policy.expected_games:
        issues.append(
            AuditIssue(
                code="holdout-game-count-mismatch",
                severity="blocking",
                message="TI 2025 holdout Game count differs from the preregistered expectation",
                context={"expected": holdout_policy.expected_games, "actual": len(holdout)},
            )
        )
    if holdout_patch_families != [target_patch_family]:
        issues.append(
            AuditIssue(
                code="holdout-patch-mismatch",
                severity="blocking",
                message="TI 2025 holdout is not entirely on the preregistered target Patch",
                context={
                    "expected": target_patch_family,
                    "actual": holdout_patch_families,
                },
            )
        )
    actual_same_patch_games = len(same_patch_team_evidence)
    if minimum_team_games < holdout_policy.minimum_same_patch_games_per_team:
        issues.append(
            AuditIssue(
                code="holdout-team-same-patch-coverage",
                severity="blocking",
                message="At least one TI 2025 team lacks the preregistered same-patch coverage",
                context={
                    "minimum_required": holdout_policy.minimum_same_patch_games_per_team,
                    "minimum_actual": minimum_team_games,
                },
            )
        )

    deployed_metrics = metrics["weighted_deployed"]
    baseline_metrics = metrics["fifty_percent"]
    if (
        deployed_metrics["log_loss"] >= baseline_metrics["log_loss"]
        or deployed_metrics["brier"] >= baseline_metrics["brier"]
    ):
        issues.append(
            AuditIssue(
                code="holdout-no-probability-skill",
                severity="blocking",
                message="Weighted deployed model does not beat 50% on both log loss and Brier score",
                context={
                    "model_log_loss": deployed_metrics["log_loss"],
                    "baseline_log_loss": baseline_metrics["log_loss"],
                    "model_brier": deployed_metrics["brier"],
                    "baseline_brier": baseline_metrics["brier"],
                },
            )
        )

    report = {
        "policy_id": policy.policy_id,
        "league_id": league_id,
        "holdout_start": holdout_start.isoformat().replace("+00:00", "Z"),
        "target_patch_family": target_patch_family,
        "evidence_scope_mode": policy.evidence_scope.mode,
        "declared_target_team_ids": sorted(target_teams),
        "actual_holdout_team_ids": sorted(actual_holdout_teams),
        "holdout_patch_families": holdout_patch_families,
        "holdout_league_tiers": holdout_tiers,
        "training_games_before_weighting": len(training),
        "positive_weight_training_games": model_report.training_matches,
        "holdout_games": len(holdout),
        "same_patch_training_games_all_teams": len(same_patch),
        "same_patch_ti_team_games": actual_same_patch_games,
        "same_patch_games_by_team": {str(key): value for key, value in same_patch_by_team.items()},
        "minimum_same_patch_games_per_team": minimum_team_games,
        "metrics": metrics,
        "comparison": {
            "weighted_deployed_minus_unweighted_ensemble_log_loss": (
                metrics["weighted_deployed"]["log_loss"] - metrics["unweighted_ensemble"]["log_loss"]
            ),
            "weighted_deployed_minus_unweighted_ensemble_brier": (
                metrics["weighted_deployed"]["brier"] - metrics["unweighted_ensemble"]["brier"]
            ),
        },
    }
    return model, model_report, report, issues


def run_ti2025_backtest(
    *,
    as_of,
    league_id: int | None = None,
    seed: int = 2025,
    paths: ProjectPaths = PATHS,
) -> BacktestResult:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    manifest = load_tournament_manifest(paths.tournament)
    policy = load_team_strength_policy(manifest, config_root=paths.config)
    selected_league_id = league_id or policy.ti2025_holdout.league_id
    policy_path = team_strength_policy_path(manifest, config_root=paths.config)
    parameters = {
        "holdout_league_id": selected_league_id,
        "fixed_model_during_holdout": True,
        "policy_id": policy.policy_id,
        "policy_sha256": sha256_file(policy_path),
        "target_patch_family": policy.ti2025_holdout.target_patch_family,
        "evidence_scope_mode": policy.evidence_scope.mode,
    }
    run_id, hashes = make_run_id(
        kind="backtest",
        as_of=cutoff,
        seed=seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    matches = read_parquet_if_exists(paths.processed / "matches.parquet")
    patches = read_parquet_if_exists(paths.processed / "patches.parquet")
    model, model_report, report, issues = evaluate_league_holdout(
        matches,
        patches,
        policy=policy,
        league_id=selected_league_id,
    )
    issues.extend(model_report.issues)
    issues.extend(rule_snapshot_issues(cutoff, paths))
    blocking = any(issue.severity == "blocking" for issue in issues)
    status = "blocked" if blocking else ("warning" if issues else "publishable")
    writer = ArtifactWriter(run_id, paths)
    report["data_snapshot_sha256"] = hashes["data"]
    report["policy_sha256"] = parameters["policy_sha256"]
    report["qualified"] = not blocking
    report["issues"] = [issue.model_dump(mode="json") for issue in issues]
    report_path = writer.write_json("backtest.json", report)
    writer.write_json("model.json", {"model": model.as_dict(), "report": model_report.as_dict()})
    run = ForecastRun(
        run_id=run_id,
        kind="backtest",
        as_of=cutoff,
        created_at=cutoff,
        status=status,
        seed=seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=(None if hashes["rule_snapshot_id"] == "missing" else hashes["rule_snapshot_id"]),
        rule_snapshot_sha256=(None if hashes["rule_snapshot"] == "missing" else hashes["rule_snapshot"]),
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={"name": model_report.model_name, "parameters": parameters},
        outputs=[report_path.name, "model.json"],
        warnings=[issue.message for issue in issues],
    )
    run_path = writer.write_run(run)
    return BacktestResult(run=run, run_path=run_path, report=report)
