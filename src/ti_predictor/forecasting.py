from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ti_predictor.backtesting import evaluate_league_holdout
from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.fantasy.recommend import FantasyRecommender
from ti_predictor.models.ratings import ModelReport, TeamStrengthModel, fit_team_strengths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import rule_snapshot_issues
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import AuditIssue, ForecastRun, Recommendation, StrategyProfile, as_utc
from ti_predictor.storage import read_parquet_if_exists
from ti_predictor.tournament.bracket import BracketEngine
from ti_predictor.tournament.group import GroupSimulator, scenario_sensitivity


@dataclass
class GenerationResult:
    run: ForecastRun
    run_path: Path
    recommendations: list[Recommendation]


def _profiles(profile: str | StrategyProfile) -> list[StrategyProfile]:
    if isinstance(profile, StrategyProfile):
        return [profile]
    aliases = {
        "expected": StrategyProfile.EXPECTED_POINTS,
        "expected_points": StrategyProfile.EXPECTED_POINTS,
        "top10": StrategyProfile.TOP_10,
        "top_10": StrategyProfile.TOP_10,
        "top100": StrategyProfile.TOP_100,
        "top_100": StrategyProfile.TOP_100,
    }
    if profile == "all":
        return StrategyProfile.all()
    if profile not in aliases:
        raise ValueError(f"unknown profile {profile!r}; use all, expected_points, top_10 or top_100")
    return [aliases[profile]]


def _load_strength_model(paths: ProjectPaths, as_of) -> tuple[TeamStrengthModel, ModelReport]:
    matches = read_parquet_if_exists(paths.processed / "matches.parquet")
    if matches.empty:
        matches = pd.DataFrame(
            columns=["match_id", "start_time", "radiant_team_id", "dire_team_id", "radiant_win"]
        )
    return fit_team_strengths(matches, as_of=as_of)


def _status(recommendations: list[Recommendation], model_report: ModelReport) -> str:
    if any(item.status == "blocked" for item in recommendations) or any(
        issue.severity == "blocking" for issue in model_report.issues
    ):
        return "blocked"
    if any(item.status == "warning" for item in recommendations) or model_report.issues:
        return "warning"
    return "publishable"


def _finalize(
    *,
    kind: str,
    as_of,
    seed: int,
    selected_profiles: list[StrategyProfile],
    parameters: dict[str, Any],
    recommendations: list[Recommendation],
    model: TeamStrengthModel,
    report: ModelReport,
    extra: dict[str, Any],
    paths: ProjectPaths,
) -> GenerationResult:
    run_id, hashes = make_run_id(
        kind=kind,
        as_of=as_of,
        seed=seed,
        profiles=selected_profiles,
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
    recommendations_path = writer.write_json(
        "recommendations.json", [item.model_dump(mode="json") for item in recommendations]
    )
    writer.write_json("model.json", {"model": model.as_dict(), "report": report.as_dict()})
    writer.write_json("details.json", extra)
    warnings = [issue.message for issue in report.issues]
    warnings.extend(warning for item in recommendations for warning in item.warnings)
    run = ForecastRun(
        run_id=run_id,
        kind=kind,
        as_of=as_utc(as_of),
        created_at=as_utc(as_of),
        status=_status(recommendations, report),
        seed=seed,
        rule_sha256=hashes["rule"],
        rule_snapshot_id=(None if hashes["rule_snapshot_id"] == "missing" else hashes["rule_snapshot_id"]),
        rule_snapshot_sha256=(None if hashes["rule_snapshot"] == "missing" else hashes["rule_snapshot"]),
        data_sha256=hashes["data"],
        config_sha256=hashes["config"],
        git_commit=hashes["source"],
        model={"name": report.model_name, "parameters": parameters},
        profiles=selected_profiles,
        outputs=[recommendations_path.name, "model.json", "details.json"],
        warnings=sorted(set(warnings)),
    )
    run_path = writer.write_run(run)
    return GenerationResult(run=run, run_path=run_path, recommendations=recommendations)


def generate_group(
    *,
    as_of,
    profile: str | StrategyProfile = "all",
    samples: int = 20000,
    seed: int = 20260813,
    paths: ProjectPaths = PATHS,
) -> GenerationResult:
    cutoff = as_utc(as_of)
    selected_profiles = _profiles(profile)
    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    model, report = _load_strength_model(paths, cutoff)
    report.issues.extend(rule_snapshot_issues(cutoff, paths))
    holdout_details: dict[str, Any] = {}
    try:
        matches = read_parquet_if_exists(paths.processed / "matches.parquet")
        _, _, holdout_details, holdout_issues = evaluate_league_holdout(matches, league_id=18324)
        report.issues.extend(issue for issue in holdout_issues if issue.severity == "blocking")
    except ValueError as error:
        report.issues.append(
            AuditIssue(
                code="holdout-unavailable",
                severity="blocking",
                message=f"TI 2025 holdout gate could not run: {error}",
            )
        )
    simulator = GroupSimulator(model, manifest)
    covered_teams = [
        team.team_id for team in manifest.teams if model.matches_played.get(team.team_id, 0) >= 5
    ]
    coverage = len(covered_teams) / len(manifest.teams)
    if coverage < 0.75:
        report.issues.append(
            AuditIssue(
                code="group-strength-coverage",
                severity="blocking",
                message="Fewer than 75% of TI teams have five as_of-prior matches in the strength model",
                context={
                    "covered_teams": len(covered_teams),
                    "total_teams": len(manifest.teams),
                    "coverage": coverage,
                },
            )
        )
    scenarios = [
        simulator.simulate(samples=samples, seed=seed + offset, scenario=scenario)
        for offset, scenario in enumerate(("strength_seeded", "balanced_pairing", "high_variance"))
    ]
    primary = scenarios[1]
    recommendations = [
        simulator.recommend(
            primary,
            profile=item,
            cumulative_points=rules["prediction"]["group"]["cumulative_points"],
            as_of=cutoff,
        )
        for item in selected_profiles
    ]
    blocking_codes = {issue.code for issue in report.issues if issue.severity == "blocking"}
    if blocking_codes:
        if "model-no-matches" in blocking_codes:
            blocking_message = "胜负模型没有可用的 as_of 前比赛，推荐不可发布。"
        elif "holdout-no-probability-skill" in blocking_codes:
            blocking_message = "TI 2025 留出回测未击败 50% 概率基准，推荐不可发布。"
        else:
            blocking_message = "胜负模型或规则发布门槛未通过，推荐不可发布。"
        for recommendation in recommendations:
            recommendation.status = "blocked"
            recommendation.warnings.append(blocking_message)
    probabilities = [
        {
            "team_id": int(team_id),
            "team": simulator.team_names[int(team_id)],
            **{
                category: round(float(primary.probabilities[team_index, category_index]), 6)
                for category_index, category in enumerate(
                    (
                        "four_zero",
                        "four_one",
                        "elimination_winner",
                        "elimination_loser",
                        "one_four",
                        "zero_four",
                    )
                )
            },
        }
        for team_index, team_id in enumerate(primary.team_ids)
    ]
    return _finalize(
        kind="group",
        as_of=cutoff,
        seed=seed,
        selected_profiles=selected_profiles,
        parameters={"samples_per_scenario": samples, "primary_scenario": primary.scenario},
        recommendations=recommendations,
        model=model,
        report=report,
        extra={
            "probabilities": probabilities,
            "scenario_sensitivity": scenario_sensitivity(scenarios, simulator.team_names),
            "team_strength_coverage": {
                "teams_with_at_least_five_matches": covered_teams,
                "coverage": coverage,
            },
            "ti2025_holdout": holdout_details,
        },
        paths=paths,
    )


def generate_bracket(
    *,
    as_of,
    profile: str | StrategyProfile = "all",
    team_ids: list[int] | None = None,
    seed: int = 20260820,
    paths: ProjectPaths = PATHS,
) -> GenerationResult:
    cutoff = as_utc(as_of)
    selected_profiles = _profiles(profile)
    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    model, report = _load_strength_model(paths, cutoff)
    report.issues.extend(rule_snapshot_issues(cutoff, paths))
    projected = not bool(team_ids or manifest.main_event_seeds)
    seeds = team_ids or manifest.main_event_seeds
    if not seeds:
        seeds = [team_id for team_id, _ in model.ranked([team.team_id for team in manifest.teams])[:8]]
    names = {team.team_id: team.name for team in manifest.teams}
    engine = BracketEngine(seeds, model)
    recommendations = [
        engine.recommend(
            profile=item,
            cumulative_points=rules["prediction"]["main"]["cumulative_points"],
            as_of=cutoff,
            team_names=names,
            projected_entrants=projected,
        )
        for item in selected_profiles
    ]
    return _finalize(
        kind="bracket",
        as_of=cutoff,
        seed=seed,
        selected_profiles=selected_profiles,
        parameters={"seeds": seeds, "projected_entrants": projected, "enumerated_grids": 16384},
        recommendations=recommendations,
        model=model,
        report=report,
        extra={
            "seeds": [{"team_id": team_id, "team": names.get(team_id, str(team_id))} for team_id in seeds]
        },
        paths=paths,
    )


def generate_fantasy(
    *,
    as_of,
    period: str,
    profile: str | StrategyProfile = "all",
    seed: int = 20260813,
    paths: ProjectPaths = PATHS,
) -> GenerationResult:
    cutoff = as_utc(as_of)
    selected_profiles = _profiles(profile)
    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    observations = read_parquet_if_exists(paths.processed / "fantasy_observations.parquet")
    matches = read_parquet_if_exists(paths.processed / "matches.parquet")
    if not observations.empty and not matches.empty and "duration" in matches:
        observations = observations.merge(matches[["match_id", "duration"]], on="match_id", how="left")
    model, report = _load_strength_model(paths, cutoff)
    report.issues.extend(rule_snapshot_issues(cutoff, paths))
    recommender = FantasyRecommender(observations, manifest, rules, model, as_of=cutoff)
    recommendations = [recommender.recommend(period=period, profile=item) for item in selected_profiles]
    return _finalize(
        kind="fantasy",
        as_of=cutoff,
        seed=seed,
        selected_profiles=selected_profiles,
        parameters={"period": period, "empirical_half_life_days": 150, "shrinkage_prior_n": 8},
        recommendations=recommendations,
        model=model,
        report=report,
        extra={"coverage": recommender.coverage()},
        paths=paths,
    )
