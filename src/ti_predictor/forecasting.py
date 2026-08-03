from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ti_predictor.backtesting import evaluate_league_holdout
from ti_predictor.config import (
    load_rules,
    load_team_strength_policy,
    load_tournament_manifest,
    team_strength_policy_path,
)
from ti_predictor.fantasy.recommend import FantasyRecommender
from ti_predictor.hashing import sha256_file
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
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
    manifest = load_tournament_manifest(paths.tournament)
    policy = load_team_strength_policy(manifest, config_root=paths.config)
    matches = read_parquet_if_exists(paths.processed / "matches.parquet")
    patches = read_parquet_if_exists(paths.processed / "patches.parquet")
    if matches.empty:
        matches = pd.DataFrame(
            columns=[
                "match_id",
                "league_id",
                "start_time",
                "radiant_team_id",
                "dire_team_id",
                "radiant_win",
                "patch_name",
                "league_tier",
            ]
        )
    holdout = matches.loc[
        matches.get("league_id", pd.Series(dtype=float)).eq(policy.ti2025_holdout.league_id)
    ].copy()
    calibration_as_of = None
    if not holdout.empty:
        holdout["start_time"] = pd.to_datetime(holdout["start_time"], utc=True, errors="coerce")
        holdout_start = holdout["start_time"].dropna().min()
        if pd.notna(holdout_start):
            calibration_as_of = holdout_start.to_pydatetime() - pd.Timedelta(microseconds=1)
    model, report = fit_team_strengths(
        matches,
        patches,
        as_of=as_of,
        policy=policy,
        target_team_ids={team.team_id for team in manifest.teams},
        calibration_as_of=calibration_as_of,
        calibration_target_patch_family=policy.ti2025_holdout.target_patch_family,
    )
    policy_path = team_strength_policy_path(manifest, config_root=paths.config)
    report.evidence_audit["policy_sha256"] = sha256_file(policy_path)
    return model, report


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
    model_parameters = {
        "policy_id": report.policy_id,
        "policy_sha256": report.evidence_audit.get("policy_sha256"),
        "target_patch_family": report.target_patch_family,
        "previous_patch_family": report.previous_patch_family,
    }
    run_parameters = {**parameters, "team_strength": model_parameters}
    run_id, hashes = make_run_id(
        kind=kind,
        as_of=as_of,
        seed=seed,
        profiles=selected_profiles,
        parameters=run_parameters,
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
        model={"name": report.model_name, "parameters": run_parameters},
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
        patches = read_parquet_if_exists(paths.processed / "patches.parquet")
        policy = load_team_strength_policy(manifest, config_root=paths.config)
        _, holdout_model_report, holdout_details, holdout_issues = evaluate_league_holdout(
            matches,
            patches,
            policy=policy,
            league_id=policy.ti2025_holdout.league_id,
        )
        holdout_blocking = [
            issue for issue in [*holdout_issues, *holdout_model_report.issues] if issue.severity == "blocking"
        ]
        report.issues.extend(holdout_blocking)
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
    observations = read_parquet_if_exists(paths.processed / "fantasy_performance_samples.parquet")
    matches = read_parquet_if_exists(paths.processed / "matches.parquet")
    patches = read_parquet_if_exists(paths.processed / "patches.parquet")
    if not observations.empty and not matches.empty:
        metadata_columns = [
            column
            for column in (
                "match_id",
                "series_type",
                "radiant_team_id",
                "dire_team_id",
                "radiant_win",
            )
            if column in matches
        ]
        if "duration" not in observations and "duration" in matches:
            metadata_columns.append("duration")
        match_metadata = matches[metadata_columns].drop_duplicates("match_id", keep="last")
        observations = observations.merge(match_metadata, on="match_id", how="left")
        if {"team_id", "radiant_team_id", "dire_team_id", "radiant_win"}.issubset(observations.columns):
            observations["team_win"] = pd.Series(
                pd.NA,
                index=observations.index,
                dtype="boolean",
            )
            radiant = observations["team_id"].eq(observations["radiant_team_id"])
            dire = observations["team_id"].eq(observations["dire_team_id"])
            radiant_win = observations["radiant_win"].astype("boolean")
            observations.loc[radiant, "team_win"] = radiant_win.loc[radiant]
            observations.loc[dire, "team_win"] = ~radiant_win.loc[dire]
    model, report = _load_strength_model(paths, cutoff)
    policy = load_team_strength_policy(manifest, config_root=paths.config)
    fantasy_evidence_audit: dict[str, Any] = {}
    if not observations.empty:
        # Production generation fails closed when the patch/tier evidence set cannot be built.
        # Direct recommender tests may still omit this column and exercise the legacy estimator.
        observations["evidence_weight"] = 0.0
    if not observations.empty and not matches.empty and not patches.empty:
        fantasy_evidence_policy = policy.model_copy(
            update={
                "policy_id": f"{policy.policy_id}-fantasy-player-history",
                "evidence_scope": EvidenceScopePolicy(mode="global"),
            }
        )
        fantasy_evidence = build_evidence_set(
            matches,
            patches,
            as_of=cutoff,
            policy=fantasy_evidence_policy,
            target_patch_family=model.target_patch_family,
        )
        evidence_columns = fantasy_evidence.matches[
            ["match_id", "evidence_weight", "patch_family", "normalized_league_tier"]
        ].drop_duplicates("match_id", keep="last")
        observations = observations.drop(columns=["evidence_weight"]).merge(
            evidence_columns,
            on="match_id",
            how="left",
        )
        observations["evidence_weight"] = pd.to_numeric(
            observations["evidence_weight"], errors="coerce"
        ).fillna(0.0)
        fantasy_evidence_audit = fantasy_evidence.audit
        target_player_ids = {
            player.account_id
            for team in manifest.teams
            for players in team.players.values()
            for player in players
        }
        weighted_target_rows = observations.loc[
            observations["evidence_weight"].gt(0.0) & observations["account_id"].isin(target_player_ids)
        ]
        fantasy_evidence_audit.update(
            {
                "target_player_game_rows": int(len(weighted_target_rows)),
                "target_players_present": int(weighted_target_rows["account_id"].nunique()),
                "games_with_target_player": int(weighted_target_rows["match_id"].nunique()),
                "effective_target_player_row_weight": float(weighted_target_rows["evidence_weight"].sum()),
            }
        )
    report.issues.extend(rule_snapshot_issues(cutoff, paths))
    recommender = FantasyRecommender(observations, manifest, rules, model, as_of=cutoff)
    stat_priority_guide = recommender.stat_priority_guide(period=period)
    recommendations = [recommender.recommend(period=period, profile=item) for item in selected_profiles]
    return _finalize(
        kind="fantasy",
        as_of=cutoff,
        seed=seed,
        selected_profiles=selected_profiles,
        parameters={
            "period": period,
            "fantasy_evidence_policy_id": (f"{policy.policy_id}-fantasy-player-history"),
            "fantasy_evidence_scope": "all_positive_weight_games_for_target_player_ids",
            "patch_weights": policy.patch_weights.model_dump(mode="json"),
            "tier_weights": policy.tier_weights,
            "time_half_life_days": policy.time_half_life_days,
            "shrinkage_prior_n": 8,
            "stat_priority_cohort": "top_25_percent_expected_role_banners",
            "stat_priority_profiles": {"stable_z": -0.85, "expected_z": 0.0, "upside_z": 1.65},
        },
        recommendations=recommendations,
        model=model,
        report=report,
        extra={
            "coverage": recommender.coverage(),
            "fantasy_evidence_audit": fantasy_evidence_audit,
            "stat_priority_guide": stat_priority_guide,
        },
        paths=paths,
    )
