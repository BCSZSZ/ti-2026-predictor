from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ti_predictor.models.ratings import (
    ModelReport,
    TeamStrengthModel,
    fit_team_strengths,
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


def evaluate_league_holdout(
    matches: pd.DataFrame,
    *,
    league_id: int,
) -> tuple[TeamStrengthModel, ModelReport, dict[str, Any], list[AuditIssue]]:
    required = {
        "match_id",
        "league_id",
        "start_time",
        "radiant_team_id",
        "dire_team_id",
        "radiant_win",
    }
    missing = required - set(matches)
    if missing:
        raise ValueError(f"holdout data is missing columns: {sorted(missing)}")
    frame = matches.copy()
    frame["start_time"] = pd.to_datetime(frame["start_time"], utc=True)
    frame = frame.loc[
        frame["start_time"].notna()
        & frame["radiant_team_id"].notna()
        & frame["dire_team_id"].notna()
        & frame["radiant_win"].notna()
    ].copy()
    holdout = frame.loc[frame["league_id"] == league_id].sort_values("start_time")
    if holdout.empty:
        raise ValueError(f"league {league_id} has no completed matches")
    holdout_start = holdout["start_time"].min().to_pydatetime()
    training = frame.loc[
        (frame["start_time"] < pd.Timestamp(holdout_start)) & (frame["league_id"] != league_id)
    ]
    model, model_report = fit_team_strengths(
        training,
        as_of=holdout_start - timedelta(microseconds=1),
    )
    probabilities = np.asarray(
        [
            model.predict(int(row.radiant_team_id), int(row.dire_team_id))
            for row in holdout.itertuples(index=False)
        ]
    )
    outcomes = holdout["radiant_win"].astype(bool).to_numpy(dtype=float)
    holdout_teams = {
        int(value) for column in ("radiant_team_id", "dire_team_id") for value in holdout[column].dropna()
    }
    covered_teams = {team_id for team_id in holdout_teams if model.matches_played.get(team_id, 0) >= 5}
    coverage = len(covered_teams) / len(holdout_teams) if holdout_teams else 0.0
    issues: list[AuditIssue] = []
    if len(holdout) < 50:
        issues.append(
            AuditIssue(
                code="holdout-incomplete",
                severity="blocking",
                message="TI holdout contains fewer than 50 matches and is likely incomplete",
                context={"matches": len(holdout)},
            )
        )
    if coverage < 0.75:
        issues.append(
            AuditIssue(
                code="holdout-team-coverage",
                severity="blocking",
                message="Fewer than 75% of holdout teams have five earlier training matches",
                context={"coverage": coverage},
            )
        )
    report = {
        "league_id": league_id,
        "holdout_start": holdout_start.isoformat().replace("+00:00", "Z"),
        "training_matches": len(training),
        "holdout_matches": len(holdout),
        "holdout_team_coverage": coverage,
        "metrics": {
            "model": probability_metrics(outcomes, probabilities),
            "fifty_percent": probability_metrics(outcomes, np.full(len(outcomes), 0.5)),
        },
    }
    model_metrics = report["metrics"]["model"]
    baseline_metrics = report["metrics"]["fifty_percent"]
    if (
        model_metrics["log_loss"] >= baseline_metrics["log_loss"]
        or model_metrics["brier"] >= baseline_metrics["brier"]
    ):
        issues.append(
            AuditIssue(
                code="holdout-no-probability-skill",
                severity="blocking",
                message="Held-out model does not beat the 50% baseline on log loss and Brier score",
                context={
                    "model_log_loss": model_metrics["log_loss"],
                    "baseline_log_loss": baseline_metrics["log_loss"],
                    "model_brier": model_metrics["brier"],
                    "baseline_brier": baseline_metrics["brier"],
                },
            )
        )
    return model, model_report, report, issues


def run_ti2025_backtest(
    *,
    as_of,
    league_id: int = 18324,
    seed: int = 2025,
    paths: ProjectPaths = PATHS,
) -> BacktestResult:
    cutoff = as_utc(as_of)
    matches = read_parquet_if_exists(paths.processed / "matches.parquet")
    model, model_report, report, issues = evaluate_league_holdout(matches, league_id=league_id)
    issues.extend(model_report.issues)
    issues.extend(rule_snapshot_issues(cutoff, paths))
    status = (
        "blocked"
        if any(issue.severity == "blocking" for issue in issues)
        else ("warning" if issues else "publishable")
    )
    parameters = {"holdout_league_id": league_id, "fixed_model_during_holdout": True}
    run_id, hashes = make_run_id(
        kind="backtest",
        as_of=cutoff,
        seed=seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
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
