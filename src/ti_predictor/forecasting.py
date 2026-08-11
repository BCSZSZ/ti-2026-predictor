from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from ti_predictor.backtesting import evaluate_bo3_probability_transform, evaluate_league_holdout
from ti_predictor.config import (
    load_rules,
    load_swiss_format,
    load_swiss_simulation_policy,
    load_team_strength_policy,
    load_tournament_manifest,
    swiss_hash,
    swiss_policy_hash,
    team_strength_policy_path,
)
from ti_predictor.fantasy.recommend import FantasyRecommender
from ti_predictor.fantasy.roll import BannerState, EmblemState
from ti_predictor.fantasy.scenarios import (
    build_common_scenario_set,
    build_series_block_pools,
    load_group_scenario_policy,
)
from ti_predictor.fantasy.stat_reporting import (
    TEAM_RANK_REPORT_FILENAME,
    TEAM_RANK_REPORT_VERSION,
    render_group_stat_team_top3_markdown,
)
from ti_predictor.fantasy.valuation import (
    RiskConfiguration,
    TerminalValueCache,
    build_stat_forecast_package,
    cluster_bootstrap_stat_intervals,
)
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.identity import canonicalize_match_team_ids
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.models.ratings import ModelReport, TeamStrengthModel, fit_team_strengths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import rule_snapshot_issues
from ti_predictor.runs import ArtifactWriter, make_run_id
from ti_predictor.schemas import AuditIssue, ForecastRun, Recommendation, StrategyProfile, as_utc
from ti_predictor.storage import read_parquet_if_exists
from ti_predictor.tournament.bracket import BracketEngine
from ti_predictor.tournament.group import (
    SwissGroupSimulator,
    scenario_probability_tables,
    scenario_sensitivity,
)


@dataclass
class GenerationResult:
    run: ForecastRun
    run_path: Path
    recommendations: list[Recommendation]


@dataclass
class FantasyEvidenceResult:
    run: ForecastRun
    run_path: Path
    evidence_path: Path
    evidence: dict[str, Any]
    runtime_seconds: dict[str, float]
    team_rank_report_path: Path | None = None


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


def _available_by_as_of(frame: pd.DataFrame, as_of) -> pd.DataFrame:
    """Exclude captures that were not locally available at the declared cutoff."""

    cutoff = pd.Timestamp(as_utc(as_of))
    result = frame.copy()
    available = pd.Series(True, index=result.index, dtype=bool)
    for column in ("as_of", "fetched_at"):
        if column not in result:
            continue
        values = pd.to_datetime(result[column], utc=True, errors="coerce")
        available &= values.notna() & values.le(cutoff)
    return result.loc[available].copy()


def _load_strength_model(paths: ProjectPaths, as_of) -> tuple[TeamStrengthModel, ModelReport]:
    manifest = load_tournament_manifest(paths.tournament)
    policy = load_team_strength_policy(manifest, config_root=paths.config)
    matches = read_parquet_if_exists(paths.processed / "matches.parquet")
    patches = read_parquet_if_exists(paths.processed / "patches.parquet")
    matches = _available_by_as_of(matches, as_of)
    patches = _available_by_as_of(patches, as_of)
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
    matches, identity_audit = canonicalize_match_team_ids(
        matches,
        manifest.team_identity_bridges,
        as_of=as_of,
        registration_identities={
            team.team_id: team.registration_identity
            for team in manifest.teams
            if team.registration_identity is not None
        },
    )
    holdout = matches.loc[
        matches.get("league_id", pd.Series(dtype=float)).eq(policy.ti2025_holdout.league_id)
    ].copy()
    calibration_as_of = None
    if not holdout.empty:
        holdout["start_time"] = pd.to_datetime(holdout["start_time"], utc=True, errors="coerce")
        holdout_start = holdout["start_time"].dropna().min()
        if pd.notna(holdout_start):
            calibration_as_of = holdout_start.to_pydatetime() - timedelta(microseconds=1)
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
    report.evidence_audit["team_identity_normalization"] = identity_audit
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
    sensitivity_samples: int | None = None,
    seed: int = 20260813,
    paths: ProjectPaths = PATHS,
) -> GenerationResult:
    cutoff = as_utc(as_of)
    sensitivity_sample_count = samples if sensitivity_samples is None else sensitivity_samples
    if samples < 1 or sensitivity_sample_count < 1:
        raise ValueError("Group simulation sample counts must be positive")
    selected_profiles = _profiles(profile)
    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    swiss_format = load_swiss_format(as_of=cutoff, manifest=manifest, path=paths.swiss)
    swiss_policy = load_swiss_simulation_policy(
        as_of=cutoff,
        manifest=manifest,
        path=paths.swiss_policy,
    )
    model, report = _load_strength_model(paths, cutoff)
    report.issues.extend(rule_snapshot_issues(cutoff, paths))
    holdout_details: dict[str, Any] = {}
    bo3_details: dict[str, Any] = {
        "selected_mode": swiss_policy.bo3_selection.fallback_mode,
        "status": "fallback",
    }
    try:
        matches = read_parquet_if_exists(paths.processed / "matches.parquet")
        patches = read_parquet_if_exists(paths.processed / "patches.parquet")
        policy = load_team_strength_policy(manifest, config_root=paths.config)
        holdout_model, holdout_model_report, holdout_details, holdout_issues = evaluate_league_holdout(
            matches,
            patches,
            policy=policy,
            league_id=policy.ti2025_holdout.league_id,
        )
        holdout_matches = matches.loc[matches["league_id"].eq(policy.ti2025_holdout.league_id)]
        bo3_details = evaluate_bo3_probability_transform(holdout_model, holdout_matches)
        bo3_details["status"] = "qualified"
        if bo3_details["evaluated_series"] < swiss_policy.bo3_selection.minimum_holdout_series:
            report.issues.append(
                AuditIssue(
                    code="bo3-transform-insufficient-series",
                    severity="blocking",
                    message="BO3 transform holdout contains fewer complete Series than required",
                    context={
                        "required": swiss_policy.bo3_selection.minimum_holdout_series,
                        "actual": bo3_details["evaluated_series"],
                    },
                )
            )
            bo3_details["selected_mode"] = swiss_policy.bo3_selection.fallback_mode
            bo3_details["status"] = "fallback"
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
    simulator = SwissGroupSimulator(
        model,
        manifest,
        swiss_format=swiss_format,
        policy=swiss_policy,
        as_of=cutoff,
        series_probability_mode=bo3_details["selected_mode"],
    )
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
    scenario_ids = [swiss_policy.primary_scenario] + [
        scenario.scenario_id
        for scenario in swiss_policy.scenarios
        if scenario.scenario_id != swiss_policy.primary_scenario
    ]
    scenarios = [
        simulator.simulate(
            samples=samples if offset == 0 else sensitivity_sample_count,
            seed=seed + offset * 1009,
            scenario=scenario_id,
        )
        for offset, scenario_id in enumerate(scenario_ids)
    ]
    primary = scenarios[0]
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
            "percentages": {
                category: round(float(primary.probabilities[team_index, category_index]) * 100.0, 2)
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
    first_round_forecasts = []
    for series in swiss_format.first_round:
        unadjusted_probability = model.predict(series.team_a_id, series.team_b_id)
        unadjusted_odds = unadjusted_probability / (1.0 - unadjusted_probability)
        multiplier_a = simulator.roster_strength_multiplier(
            series.team_a_id,
            scenario=primary.scenario,
        )
        multiplier_b = simulator.roster_strength_multiplier(
            series.team_b_id,
            scenario=primary.scenario,
        )
        adjusted_odds = unadjusted_odds * multiplier_a / multiplier_b
        model_probability = simulator.adjusted_game_probability(
            series.team_a_id,
            series.team_b_id,
            scenario=primary.scenario,
        )
        scoreline_game_probability = simulator.scoreline_game_probability(
            series.team_a_id,
            series.team_b_id,
            scenario=primary.scenario,
        )
        series_probability = simulator.series_win_probability(
            series.team_a_id,
            series.team_b_id,
            scenario=primary.scenario,
        )
        first_round_forecasts.append(
            {
                "node_id": series.node_id,
                "initial_group": series.initial_group,
                "start_at": series.start_at.isoformat().replace("+00:00", "Z"),
                "team_a_id": series.team_a_id,
                "team_a": simulator.team_names[series.team_a_id],
                "team_b_id": series.team_b_id,
                "team_b": simulator.team_names[series.team_b_id],
                "team_a_unadjusted_model_probability": round(unadjusted_probability, 6),
                "team_a_unadjusted_model_probability_percent": round(
                    unadjusted_probability * 100.0,
                    2,
                ),
                "team_b_unadjusted_model_probability": round(
                    1.0 - unadjusted_probability,
                    6,
                ),
                "team_b_unadjusted_model_probability_percent": round(
                    (1.0 - unadjusted_probability) * 100.0,
                    2,
                ),
                "team_a_unadjusted_odds": round(unadjusted_odds, 6),
                "team_b_unadjusted_odds": round(1.0 / unadjusted_odds, 6),
                "team_a_roster_strength_multiplier": multiplier_a,
                "team_b_roster_strength_multiplier": multiplier_b,
                "team_a_adjusted_odds": round(adjusted_odds, 6),
                "team_b_adjusted_odds": round(1.0 / adjusted_odds, 6),
                "team_a_model_probability": round(model_probability, 6),
                "team_a_model_probability_percent": round(model_probability * 100.0, 2),
                "team_a_scoreline_proxy_game_probability": round(
                    scoreline_game_probability,
                    6,
                ),
                "team_a_scoreline_proxy_game_probability_percent": round(
                    scoreline_game_probability * 100.0,
                    2,
                ),
                "team_a_series_probability": round(series_probability, 6),
                "team_a_series_probability_percent": round(series_probability * 100.0, 2),
                "team_b_series_probability": round(1.0 - series_probability, 6),
                "team_b_series_probability_percent": round(
                    (1.0 - series_probability) * 100.0,
                    2,
                ),
            }
        )
    return _finalize(
        kind="group",
        as_of=cutoff,
        seed=seed,
        selected_profiles=selected_profiles,
        parameters={
            "primary_samples": samples,
            "sensitivity_samples": sensitivity_sample_count,
            "scenario_sample_counts": {scenario.scenario: len(scenario.outcomes) for scenario in scenarios},
            "primary_scenario": primary.scenario,
            "scenarios": scenario_ids,
            "swiss_format_sha256": swiss_hash(paths.swiss),
            "swiss_policy_sha256": swiss_policy_hash(paths.swiss_policy),
            "bo3_probability_mode": bo3_details["selected_mode"],
        },
        recommendations=recommendations,
        model=model,
        report=report,
        extra={
            "probabilities": probabilities,
            "first_round_forecasts": first_round_forecasts,
            "swiss_simulation": primary.metadata,
            "bo3_probability_transform": bo3_details,
            "scenario_probabilities": scenario_probability_tables(
                scenarios,
                simulator.team_names,
            ),
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
            "current_exact_patch_weight": (
                None
                if policy.current_exact_patch_weight is None
                else policy.current_exact_patch_weight.model_dump(mode="json")
            ),
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


def generate_group_fantasy_evidence(
    *,
    as_of,
    seed: int = 20260813,
    include_bootstrap: bool = True,
    include_team_rank_bootstrap: bool = False,
    paths: ProjectPaths = PATHS,
) -> FantasyEvidenceResult:
    """Create the governed P3 Group Scenario and Stat-evidence package."""

    started = perf_counter()
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    if include_team_rank_bootstrap and not include_bootstrap:
        raise ValueError("team-rank bootstrap requires the complete Series bootstrap")
    manifest = load_tournament_manifest(paths.tournament)
    rules = load_rules(paths.rules)
    scenario_policy_path = paths.config / "models" / "fantasy-group-scenarios-v2.json"
    scenario_policy = load_group_scenario_policy(scenario_policy_path)
    swiss_format = load_swiss_format(as_of=cutoff, manifest=manifest, path=paths.swiss)
    swiss_policy = load_swiss_simulation_policy(
        as_of=cutoff,
        manifest=manifest,
        path=paths.swiss_policy,
    )
    matches_path = paths.processed / "matches.parquet"
    observations_path = paths.processed / "fantasy_performance_samples.parquet"
    patches_path = paths.processed / "patches.parquet"
    for required_path in (matches_path, observations_path, patches_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"P3 requires the processed snapshot file: {required_path}")
    matches = _available_by_as_of(read_parquet_if_exists(matches_path), cutoff)
    observations = _available_by_as_of(read_parquet_if_exists(observations_path), cutoff)
    patches = _available_by_as_of(read_parquet_if_exists(patches_path), cutoff)

    model, model_report = _load_strength_model(paths, cutoff)
    strength_policy = load_team_strength_policy(manifest, config_root=paths.config)
    holdout_model, holdout_model_report, _, holdout_issues = evaluate_league_holdout(
        matches,
        patches,
        policy=strength_policy,
        league_id=strength_policy.ti2025_holdout.league_id,
    )
    holdout_blocking = [
        issue for issue in [*holdout_issues, *holdout_model_report.issues] if issue.severity == "blocking"
    ]
    if holdout_blocking:
        raise ValueError(
            "P3 BO3 holdout is blocked: " + "; ".join(issue.message for issue in holdout_blocking)
        )
    bo3_details = evaluate_bo3_probability_transform(
        holdout_model,
        matches.loc[matches["league_id"].eq(strength_policy.ti2025_holdout.league_id)],
    )
    if bo3_details["evaluated_series"] < swiss_policy.bo3_selection.minimum_holdout_series:
        raise ValueError(
            "P3 BO3 transform has "
            f"{bo3_details['evaluated_series']} complete holdout Series; "
            f"policy requires {swiss_policy.bo3_selection.minimum_holdout_series}"
        )
    fantasy_evidence_policy = strength_policy.model_copy(
        update={
            "policy_id": f"{strength_policy.policy_id}-fantasy-player-history",
            "evidence_scope": EvidenceScopePolicy(mode="global"),
        }
    )
    evidence = build_evidence_set(
        matches,
        patches,
        as_of=cutoff,
        policy=fantasy_evidence_policy,
        target_patch_family=model.target_patch_family,
    )
    blocking_evidence = [issue for issue in evidence.issues if issue.severity == "blocking"]
    if blocking_evidence:
        raise ValueError(
            "P3 Fantasy evidence is blocked: " + "; ".join(issue.message for issue in blocking_evidence)
        )

    data_snapshot_sha256 = sha256_json(
        {
            "as_of": cutoff.isoformat().replace("+00:00", "Z"),
            "matches_sha256": sha256_file(matches_path),
            "observations_sha256": sha256_file(observations_path),
            "patches_sha256": sha256_file(patches_path),
            "rules_sha256": sha256_file(paths.rules),
            "manifest_sha256": sha256_file(paths.tournament),
            "scenario_policy_sha256": sha256_file(scenario_policy_path),
            "swiss_format_sha256": swiss_hash(paths.swiss),
            "swiss_policy_sha256": swiss_policy_hash(paths.swiss_policy),
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
    pools_finished = perf_counter()
    group_simulation = SwissGroupSimulator(
        model,
        manifest,
        swiss_format=swiss_format,
        policy=swiss_policy,
        as_of=cutoff,
        series_probability_mode=bo3_details["selected_mode"],
    ).simulate(
        samples=scenario_policy.scenario_count,
        seed=seed,
        scenario=swiss_policy.primary_scenario,
    )
    scenario_set = build_common_scenario_set(
        pool_result,
        group_team_ids=group_simulation.team_ids,
        group_outcomes=group_simulation.outcomes,
        policy=scenario_policy,
        data_snapshot_sha256=data_snapshot_sha256,
        as_of=cutoff,
        seed=seed,
    )
    scenarios_finished = perf_counter()
    stat_forecasts = build_stat_forecast_package(
        pool_result,
        scenario_set,
        rules,
        cvar_alpha=scenario_policy.risk.cvar_alpha,
    )
    stats_finished = perf_counter()
    stats_by_color = {
        color: [
            stat_id for stat_id, stat_rule in rules["fantasy"]["stats"].items() if stat_rule["color"] == color
        ]
        for color in ("red", "blue", "green")
    }
    reference_banners: dict[str, BannerState] = {}
    for role in ("core", "mid", "support"):
        colors = rules["fantasy"]["role_banners"][role][:3]
        reference_banners[role] = BannerState(
            role=role,
            emblems=tuple(
                EmblemState(
                    stat_id=stats_by_color[color][0],
                    quality_tier=slot + 1,
                    trait_id=("fractal", "benevolent", "vampiric")[slot],
                )
                for slot, color in enumerate(colors)
            ),
        )
    risk = RiskConfiguration(
        mean_retention_epsilon=scenario_policy.risk.verified_mean_retention_epsilons[0],
        cvar_alpha=scenario_policy.risk.cvar_alpha,
    )
    terminal_cache = TerminalValueCache()
    reference_matrices = {
        role: terminal_cache.banner(
            pool_result,
            scenario_set,
            reference_banners[role],
            rules,
        )
        for role in ("core", "mid", "support")
    }
    reference_banner_matches = {
        role: terminal_cache.matched_banner(reference_matrices[role], risk)
        for role in ("core", "mid", "support")
    }
    reference_group_match = terminal_cache.matched_group(reference_matrices, risk)
    terminal_smoke = {
        "purpose": "arithmetic_only_nonoptimized_reference_banners",
        "coach_status": scenario_policy.production_coach_status,
        "risk": {
            "mean_retention_epsilon": risk.mean_retention_epsilon,
            "cvar_alpha": risk.cvar_alpha,
        },
        "banners": {
            role: {
                "emblems": [
                    {
                        "stat_id": emblem.stat_id,
                        "quality_tier": emblem.quality_tier,
                        "trait_id": emblem.trait_id,
                    }
                    for emblem in reference_banners[role].emblems
                ],
                "matrix_sha256": reference_matrices[role].semantic_hash,
                "single_banner_team_id": reference_banner_matches[role].selected_team_ids[0],
                "single_banner_value_sha256": reference_banner_matches[role].semantic_hash,
            }
            for role in ("core", "mid", "support")
        },
        "joint_selected_team_ids": list(reference_group_match.selected_team_ids),
        "joint_summary": reference_group_match.summary,
        "joint_value_sha256": reference_group_match.semantic_hash,
    }
    terminal_smoke["terminal_smoke_sha256"] = sha256_json(terminal_smoke)
    terminal_finished = perf_counter()
    bootstrap = (
        cluster_bootstrap_stat_intervals(
            pool_result,
            scenario_set,
            stat_forecasts,
            rules,
            scenario_policy,
            seed=seed + 300_007,
            include_team_rankings=include_team_rank_bootstrap,
        )
        if include_bootstrap
        else None
    )
    finished = perf_counter()

    warnings = [
        "Group 机会数来自固定官方首轮与规则驱动 Swiss 模拟；非唯一配对和选对手仍是显式情景。",
        "Group v2 在给定 Team 结果后独立抽取三个角色的表现块，未建模跨角色历史相关性。",
        "没有完整且情景对齐的 Coach 前缀加后缀候选；P3 生产估值明确排除 Coach。",
    ]
    unavailable = [
        item for item in pool_result.audit["team_role_availability"] if item["status"] == "unavailable"
    ]
    if unavailable:
        warnings.append(
            "缺少正式 Series 证据的 Team/role 已标为 unavailable 并从该角色候选中排除："
            + ", ".join(f"{item['target_team_id']}/{item['role']}" for item in unavailable)
        )
    warnings.extend(issue.message for issue in evidence.issues if issue.severity == "warning")
    model_report.issues.extend(rule_snapshot_issues(cutoff, paths))
    warnings.extend(issue.message for issue in model_report.issues if issue.severity == "warning")
    if not include_bootstrap:
        warnings.append("完整 Series 分组重采样被关闭；该烟雾运行不能作为 P3/P4 正式证据。")
    status = (
        "blocked"
        if not include_bootstrap or any(issue.severity == "blocking" for issue in model_report.issues)
        else "warning"
    )
    runtime_seconds = {
        "series_block_build": pools_finished - started,
        "common_scenario_build": scenarios_finished - pools_finished,
        "stat_forecasts": stats_finished - scenarios_finished,
        "terminal_smoke": terminal_finished - stats_finished,
        "cluster_bootstrap": finished - terminal_finished,
        "total": finished - started,
    }
    evidence_payload = {
        "schema_version": 2 if include_team_rank_bootstrap else 1,
        "artifact_type": "group_fantasy_stat_evidence",
        "status": status,
        "as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "seed": seed,
        "data_snapshot_sha256": data_snapshot_sha256,
        "scenario_policy": scenario_policy.model_dump(mode="json"),
        "scenario_policy_sha256": sha256_file(scenario_policy_path),
        "swiss_simulation": group_simulation.metadata,
        "bo3_probability_transform": bo3_details,
        "fantasy_evidence_audit": evidence.audit,
        "series_block_audit": pool_result.audit,
        "scenario_set": {
            "scenario_count": len(scenario_set.scenario_ids),
            "team_ids": list(scenario_set.team_ids),
            "group_outcome_model": group_simulation.scenario,
            "unavailable_team_roles": unavailable,
            "pool_set_sha256": pool_result.semantic_hash,
            "scenario_sha256": scenario_set.semantic_hash,
        },
        "stat_forecasts": stat_forecasts,
        "terminal_smoke": terminal_smoke,
        "cluster_bootstrap": bootstrap,
        "coach": {
            "status": scenario_policy.production_coach_status,
            "reason": "no_complete_validated_prefix_plus_suffix_future_scenario",
        },
        "warnings": sorted(set(warnings)),
    }
    evidence_payload["evidence_package_sha256"] = sha256_json(evidence_payload)

    parameters = {
        "phase": "p3_group_fantasy_evidence",
        "scenario_policy_id": scenario_policy.policy_id,
        "scenario_policy_sha256": sha256_file(scenario_policy_path),
        "scenario_count": scenario_policy.scenario_count,
        "swiss_format_sha256": swiss_hash(paths.swiss),
        "swiss_policy_sha256": swiss_policy_hash(paths.swiss_policy),
        "bo3_probability_mode": bo3_details["selected_mode"],
        "bootstrap": include_bootstrap,
        "team_strength": {
            "policy_id": model_report.policy_id,
            "policy_sha256": model_report.evidence_audit.get("policy_sha256"),
            "target_patch_family": model_report.target_patch_family,
        },
    }
    if include_team_rank_bootstrap:
        parameters["team_rank_bootstrap"] = {
            "enabled": True,
            "top_k": 3,
            "point_order": "descending_mean_then_team_id",
            "report_version": TEAM_RANK_REPORT_VERSION,
        }
    run_id, hashes = make_run_id(
        kind="fantasy",
        as_of=cutoff,
        seed=seed,
        profiles=[],
        parameters=parameters,
        paths=paths,
    )
    writer = ArtifactWriter(run_id, paths)
    evidence_path = writer.write_json("group-fantasy-evidence.json", evidence_payload)
    writer.write_json("model.json", {"model": model.as_dict(), "report": model_report.as_dict()})
    team_rank_report_path = None
    outputs = [evidence_path.name, "model.json"]
    if include_team_rank_bootstrap:
        team_rank_report_path = writer.write_text(
            TEAM_RANK_REPORT_FILENAME,
            render_group_stat_team_top3_markdown(
                evidence_payload,
                team_names={team.team_id: team.name for team in manifest.teams},
            ),
        )
        outputs.append(team_rank_report_path.name)
    run = ForecastRun(
        run_id=run_id,
        kind="fantasy",
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
        model={"name": scenario_policy.policy_id, "parameters": parameters},
        profiles=[],
        outputs=outputs,
        warnings=sorted(set(warnings)),
    )
    run_path = writer.write_run(run)
    return FantasyEvidenceResult(
        run=run,
        run_path=run_path,
        evidence_path=evidence_path,
        evidence=evidence_payload,
        runtime_seconds=runtime_seconds,
        team_rank_report_path=team_rank_report_path,
    )
