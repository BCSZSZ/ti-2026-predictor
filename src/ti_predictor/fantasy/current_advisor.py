"""Current-screen, one-step Group Roll advice backed by the current frozen evidence.

This module intentionally does not value or generate a future offer.  Every call
starts from the complete state the player can currently see in the Dota client.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ti_predictor.backtesting import evaluate_bo3_probability_transform, evaluate_league_holdout
from ti_predictor.config import (
    load_rules,
    load_swiss_format,
    load_swiss_simulation_policy,
    load_team_strength_policy,
    load_tournament_manifest,
    swiss_hash,
    swiss_policy_hash,
)
from ti_predictor.fantasy.advisor import action_identity, action_label
from ti_predictor.fantasy.roll import (
    BannerState,
    GroupRollState,
    RefreshRollAction,
    RollRuleSet,
    build_group_roll_rules,
    legal_actions,
    mutation_distribution,
    validate_group_state,
)
from ti_predictor.fantasy.scenarios import (
    ROLE_IDS,
    CommonScenarioSet,
    PoolBuildResult,
    build_common_scenario_set,
    build_series_block_pools,
    load_group_scenario_policy,
)
from ti_predictor.fantasy.solver import TerminalGroupEvaluator, WeightedOutcomeDistribution
from ti_predictor.fantasy.solver_validation import subset_solver_scenarios
from ti_predictor.fantasy.valuation import RiskConfiguration, distribution_summary
from ti_predictor.forecasting import _available_by_as_of, _load_strength_model
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import latest_rule_snapshot
from ti_predictor.schemas import RuleSnapshot, as_utc
from ti_predictor.storage import read_parquet_if_exists
from ti_predictor.tournament.group import SwissGroupSimulator


class CurrentAdvisorError(ValueError):
    """The current-screen advisor cannot safely publish a result."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CurrentAdvisorSourcePolicy(_StrictModel):
    p3_evidence_sha256: str
    data_snapshot_sha256: str
    pool_set_sha256: str
    full_scenario_sha256: str
    title_evidence_sha256: str
    rule_snapshot_sha256: str


class CurrentAdvisorScenarioPolicy(_StrictModel):
    count: int = Field(ge=32)
    seed: int


class CurrentAdvisorAnalysisPolicy(_StrictModel):
    primary_model: str
    models: tuple[str, ...]
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    risk_profiles: dict[str, float]

    @model_validator(mode="after")
    def _validate_models_and_risks(self) -> CurrentAdvisorAnalysisPolicy:
        if self.primary_model not in self.models:
            raise ValueError("primary_model must be included in models")
        if len(set(self.models)) != len(self.models):
            raise ValueError("analysis models must be unique")
        if set(self.risk_profiles) != {"mean-first", "balanced", "downside-first"}:
            raise ValueError("advisor requires the three published risk profiles")
        if any(value < 0.0 or value > 0.1 for value in self.risk_profiles.values()):
            raise ValueError("risk-profile mean retention must be between 0 and 10%")
        return self


class CurrentAdvisorTitlePolicy(_StrictModel):
    top_k: int = Field(ge=1, le=8)
    excluded_suffix_ids: tuple[str, ...]
    aggregation: Literal["current_banner_role_mean_weighted_pool_paper_bonus"]


class CurrentAdvisorBoundaryPolicy(_StrictModel):
    listen_address: Literal["127.0.0.1"]
    dota_client_control: Literal[False]
    automatic_filling: Literal[False]
    future_offer_generation: Literal[False]
    main_execution: Literal["fail_closed"]


class CurrentAdvisorPerformancePolicy(_StrictModel):
    context_load: float = Field(gt=0.0)
    analysis: float = Field(gt=0.0)
    cached_repeat: float = Field(gt=0.0)


class CurrentAdvisorPolicy(_StrictModel):
    schema_version: Literal[2]
    policy_id: Literal["fantasy-group-current-screen-advisor-v2"]
    period: Literal["group"]
    as_of: str
    seed: int
    source: CurrentAdvisorSourcePolicy
    responsive_scenarios: CurrentAdvisorScenarioPolicy
    analysis: CurrentAdvisorAnalysisPolicy
    title: CurrentAdvisorTitlePolicy
    boundaries: CurrentAdvisorBoundaryPolicy
    performance_targets_seconds: CurrentAdvisorPerformancePolicy


@dataclass(frozen=True)
class CurrentAdvisorContext:
    policy: CurrentAdvisorPolicy
    canonical_rules: dict[str, Any]
    roll_rules: RollRuleSet
    pool_result: PoolBuildResult
    scenarios: CommonScenarioSet
    terminal: TerminalGroupEvaluator
    team_names: Mapping[int, str]
    title_evidence: dict[str, Any]
    warnings: tuple[str, ...]
    context_load_seconds: float


@dataclass(frozen=True)
class CurrentGroupEvaluation:
    selected_team_ids: tuple[int, int, int]
    outcomes: np.ndarray
    mean: float
    cvar10: float
    maximum_mean: float
    role_base_means: Mapping[str, float]


def load_current_advisor_policy(path: Path) -> CurrentAdvisorPolicy:
    return CurrentAdvisorPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _resolve_current_advisor_rule_snapshot(
    policy: CurrentAdvisorPolicy,
    *,
    paths: ProjectPaths = PATHS,
) -> tuple[RuleSnapshot, Path]:
    """Resolve the exact freeze while allowing a metadata-only client refresh."""

    cutoff = as_utc(policy.as_of)
    if cutoff is None:
        raise CurrentAdvisorError("advisor policy requires an explicit Rule snapshot cutoff")

    frozen_matches: list[tuple[RuleSnapshot, Path]] = []
    for snapshot_path in sorted((paths.raw / "rules").glob("*/rule_snapshot.json")):
        try:
            if sha256_file(snapshot_path) != policy.source.rule_snapshot_sha256:
                continue
            snapshot = RuleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
        except OSError:
            continue
        except ValueError as exc:
            raise CurrentAdvisorError("the frozen local client Rule snapshot is invalid") from exc
        frozen_matches.append((snapshot, snapshot_path))

    if not frozen_matches:
        raise CurrentAdvisorError("the frozen local client Rule snapshot is unavailable")
    frozen_snapshot, frozen_path = frozen_matches[-1]
    if frozen_snapshot.as_of > cutoff or frozen_snapshot.created_at > cutoff:
        raise CurrentAdvisorError("the frozen local client Rule snapshot is later than the v2 cutoff")

    latest_result = latest_rule_snapshot(paths)
    if latest_result is None:
        raise FileNotFoundError("advisor requires the current local Dota Rule snapshot")
    latest_snapshot, _ = latest_result
    if latest_snapshot.status == "blocked":
        raise CurrentAdvisorError("the latest local client Rule snapshot is blocked")
    if latest_snapshot.snapshot_sha256 != frozen_snapshot.snapshot_sha256:
        raise CurrentAdvisorError("local client Rule semantics drifted from the v2 freeze")
    return frozen_snapshot, frozen_path


def _build_current_advisor_roll_rules(
    snapshot: RuleSnapshot,
    *,
    paths: ProjectPaths,
) -> RollRuleSet:
    client_roll = snapshot.observed.get("fantasy_roll")
    if not isinstance(client_roll, dict):
        raise CurrentAdvisorError("local Rule snapshot lacks normalized Fantasy Roll operations")
    return build_group_roll_rules(load_rules(paths.rules), client_roll)


def load_current_advisor_roll_rules(*, paths: ProjectPaths = PATHS) -> RollRuleSet:
    """Build current Group Roll rules without importing the historical v1 advisor."""

    policy = load_current_advisor_policy(
        paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )
    snapshot, _ = _resolve_current_advisor_rule_snapshot(policy, paths=paths)
    return _build_current_advisor_roll_rules(snapshot, paths=paths)


def load_current_advisor_team_options(
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, tuple[tuple[int, str], ...]]:
    policy = load_current_advisor_policy(
        paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )
    p3_evidence = _find_verified_artifact(
        paths,
        filename="group-fantasy-evidence.json",
        hash_field="evidence_package_sha256",
        expected_sha256=policy.source.p3_evidence_sha256,
    )
    unavailable = {
        (int(item["target_team_id"]), str(item["role"]))
        for item in p3_evidence.get("scenario_set", {}).get("unavailable_team_roles", [])
    }
    manifest = load_tournament_manifest(paths.tournament)
    options = {
        role: tuple(
            (int(team.team_id), team.name)
            for team in manifest.teams
            if (int(team.team_id), role) not in unavailable
        )
        for role in ROLE_IDS
    }
    if any(not values for values in options.values()):
        raise CurrentAdvisorError("current P3 evidence leaves a Fantasy role without Team options")
    return options


def _find_verified_artifact(
    paths: ProjectPaths,
    *,
    filename: str,
    hash_field: str,
    expected_sha256: str,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for path in sorted(paths.artifacts.glob(f"fantasy-*/{filename}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get(hash_field) != expected_sha256:
            continue
        body = {key: value for key, value in payload.items() if key != hash_field}
        if sha256_json(body) != expected_sha256:
            raise CurrentAdvisorError(f"{filename} carries an invalid {hash_field}")
        matches.append(payload)
    if not matches:
        raise FileNotFoundError(f"advisor requires {filename} with {hash_field}={expected_sha256}")
    reference = sha256_json(matches[0])
    if any(sha256_json(payload) != reference for payload in matches[1:]):
        raise CurrentAdvisorError(f"multiple {filename} artifacts claim one identity but differ")
    return matches[-1]


def prepare_current_advisor_context(
    *,
    as_of,
    paths: ProjectPaths = PATHS,
) -> CurrentAdvisorContext:
    """Rebuild the current P3 arithmetic and fail closed on frozen identity drift."""

    started = perf_counter()
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    policy = load_current_advisor_policy(
        paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    if cutoff_text != policy.as_of:
        raise CurrentAdvisorError("advisor as_of differs from the frozen v2 cutoff")

    p3_evidence = _find_verified_artifact(
        paths,
        filename="group-fantasy-evidence.json",
        hash_field="evidence_package_sha256",
        expected_sha256=policy.source.p3_evidence_sha256,
    )
    if p3_evidence.get("as_of") != cutoff_text:
        raise CurrentAdvisorError("P3 evidence as_of differs from the v2 cutoff")
    frozen_scenario = p3_evidence.get("scenario_set", {})
    p3_identities = {
        "data_snapshot_sha256": p3_evidence.get("data_snapshot_sha256"),
        "pool_set_sha256": frozen_scenario.get("pool_set_sha256"),
        "full_scenario_sha256": frozen_scenario.get("scenario_sha256"),
    }
    expected_p3_identities = {
        "data_snapshot_sha256": policy.source.data_snapshot_sha256,
        "pool_set_sha256": policy.source.pool_set_sha256,
        "full_scenario_sha256": policy.source.full_scenario_sha256,
    }
    if p3_identities != expected_p3_identities:
        raise CurrentAdvisorError("P3 artifact identities differ from the v2 policy")

    title_evidence = _find_verified_artifact(
        paths,
        filename="group-fantasy-title-evidence.json",
        hash_field="evidence_sha256",
        expected_sha256=policy.source.title_evidence_sha256,
    )
    if title_evidence.get("as_of") != cutoff_text:
        raise CurrentAdvisorError("Title evidence as_of differs from the Roll evidence cutoff")

    rule_snapshot, _ = _resolve_current_advisor_rule_snapshot(policy, paths=paths)

    manifest = load_tournament_manifest(paths.tournament)
    canonical_rules = load_rules(paths.rules)
    roll_rules = _build_current_advisor_roll_rules(rule_snapshot, paths=paths)
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
            raise FileNotFoundError(f"advisor requires the processed snapshot file: {required_path}")

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
        issue.message
        for issue in [*holdout_issues, *holdout_model_report.issues]
        if issue.severity == "blocking"
    ]
    if holdout_blocking:
        raise CurrentAdvisorError("current BO3 holdout is blocked: " + "; ".join(holdout_blocking))
    bo3_details = evaluate_bo3_probability_transform(
        holdout_model,
        matches.loc[matches["league_id"].eq(strength_policy.ti2025_holdout.league_id)],
    )
    if bo3_details["evaluated_series"] < swiss_policy.bo3_selection.minimum_holdout_series:
        raise CurrentAdvisorError(
            "current BO3 transform has fewer complete holdout Series than the Swiss policy requires"
        )
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
    blocking = [issue.message for issue in evidence.issues if issue.severity == "blocking"]
    if blocking:
        raise CurrentAdvisorError("current Fantasy evidence is blocked: " + "; ".join(blocking))

    data_snapshot_sha256 = sha256_json(
        {
            "as_of": cutoff_text,
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
    if data_snapshot_sha256 != policy.source.data_snapshot_sha256:
        raise CurrentAdvisorError("current data snapshot drifted from the v2 freeze")

    pool_result = build_series_block_pools(
        observations,
        matches,
        evidence.matches,
        manifest,
        canonical_rules,
        scenario_policy,
        as_of=cutoff,
    )
    if pool_result.semantic_hash != policy.source.pool_set_sha256:
        raise CurrentAdvisorError("current Series pool drifted from the v2 freeze")

    group_simulation = SwissGroupSimulator(
        model,
        manifest,
        swiss_format=swiss_format,
        policy=swiss_policy,
        as_of=cutoff,
        series_probability_mode=bo3_details["selected_mode"],
    ).simulate(
        samples=scenario_policy.scenario_count,
        seed=policy.seed,
        scenario=swiss_policy.primary_scenario,
    )
    full_scenarios = build_common_scenario_set(
        pool_result,
        group_team_ids=group_simulation.team_ids,
        group_outcomes=group_simulation.outcomes,
        policy=scenario_policy,
        data_snapshot_sha256=data_snapshot_sha256,
        as_of=cutoff,
        seed=policy.seed,
    )
    if full_scenarios.semantic_hash != policy.source.full_scenario_sha256:
        raise CurrentAdvisorError("current full Scenario set drifted from the v2 freeze")
    scenarios = subset_solver_scenarios(
        full_scenarios,
        count=policy.responsive_scenarios.count,
        seed=policy.responsive_scenarios.seed,
    )
    terminal = TerminalGroupEvaluator(pool_result, scenarios, canonical_rules)
    warnings = {
        "只评估当前三个选项的一步直接结果；不生成或估计下一轮未知选项。",
        "Title 是按当前队伍与位置历史触发率计算的纸面估算，未进入 Roll 分值。",
        "Group 机会数使用 Valve 官方首轮与规则驱动 Swiss 情景；非唯一后续决定仍是显式代理。",
        *(issue.message for issue in evidence.issues if issue.severity == "warning"),
        *(issue.message for issue in model_report.issues if issue.severity == "warning"),
    }
    return CurrentAdvisorContext(
        policy=policy,
        canonical_rules=canonical_rules,
        roll_rules=roll_rules,
        pool_result=pool_result,
        scenarios=scenarios,
        terminal=terminal,
        team_names={int(team.team_id): team.name for team in manifest.teams},
        title_evidence=title_evidence,
        warnings=tuple(sorted(warnings)),
        context_load_seconds=perf_counter() - started,
    )


def _replace_banner(
    banners: tuple[BannerState, ...], replacement: BannerState
) -> tuple[BannerState, ...]:
    return tuple(replacement if banner.role == replacement.role else banner for banner in banners)


def _evaluate_group(
    context: CurrentAdvisorContext,
    banners: tuple[BannerState, ...],
    risk: RiskConfiguration,
    selected_team_ids: tuple[int, int, int] | None,
) -> CurrentGroupEvaluation:
    banner_by_role = {banner.role: banner for banner in banners}
    matrices = {
        role: context.terminal.cache.banner(
            context.pool_result,
            context.scenarios,
            banner_by_role[role],
            context.canonical_rules,
        )
        for role in ROLE_IDS
    }
    if selected_team_ids is None:
        matched = context.terminal.cache.matched_group(matrices, risk)
        team_ids = tuple(int(value) for value in matched.selected_team_ids)
        outcomes = matched.outcomes
        maximum_mean = matched.maximum_mean
    else:
        if len(selected_team_ids) != len(ROLE_IDS):
            raise ValueError("manual lineup must select one Team for each of Core, Mid and Support")
        indexes = []
        for role, team_id in zip(ROLE_IDS, selected_team_ids, strict=True):
            try:
                indexes.append(matrices[role].team_ids.index(int(team_id)))
            except ValueError as error:
                raise ValueError(f"Team {team_id} is unavailable for {role}") from error
        team_ids = tuple(int(value) for value in selected_team_ids)
        outcomes = sum(
            (matrices[role].outcomes[index] for role, index in zip(ROLE_IDS, indexes, strict=True)),
            start=np.zeros(len(context.scenarios.scenario_ids), dtype=float),
        )
        maximum_mean = float(
            sum(float(matrices[role].outcomes.mean(axis=1).max()) for role in ROLE_IDS)
        )
    role_base_means = {}
    for role, team_id in zip(ROLE_IDS, team_ids, strict=True):
        matrix = matrices[role]
        role_base_means[role] = float(matrix.outcomes[matrix.team_ids.index(team_id)].mean())
    summary = distribution_summary(outcomes, cvar_alpha=risk.cvar_alpha)
    return CurrentGroupEvaluation(
        selected_team_ids=team_ids,  # type: ignore[arg-type]
        outcomes=outcomes,
        mean=float(summary["mean"]),
        cvar10=float(summary["cvar"]),
        maximum_mean=maximum_mean,
        role_base_means=role_base_means,
    )


def _preferred_action(
    rows: Sequence[Mapping[str, Any]], *, mean_retention_epsilon: float
) -> str:
    maximum_mean = max(float(row["mean"]) for row in rows)
    floor = maximum_mean - abs(maximum_mean) * mean_retention_epsilon - 1e-12
    eligible = [row for row in rows if float(row["mean"]) >= floor]
    chosen = min(
        eligible,
        key=lambda row: (
            -float(row["cvar10"]),
            -float(row["mean"]),
            0 if str(row["action_id"]) == "refresh" else 1,
            str(row["action_id"]),
        ),
    )
    refresh = next((row for row in rows if str(row["action_id"]) == "refresh"), None)
    if (
        refresh is not None
        and str(chosen["action_id"]) != "refresh"
        and float(chosen["mean"]) <= float(refresh["mean"]) + 1e-9
    ):
        return "refresh"
    return str(chosen["action_id"])


def _public_action_label(action: Any, rules: RollRuleSet) -> str:
    label = action_label(action, rules)
    if isinstance(action, RefreshRollAction):
        return label
    return (
        label.replace(f"#{action.operation_id} · ", "")
        .replace("Carry ·", "核心位 ·")
        .replace("Mid ·", "中单 ·")
        .replace("Support ·", "辅助位 ·")
        .replace(" / ", " · ")
    )


def classify_recommendation(
    *,
    selected_action_id: str,
    selected_row: Mapping[str, Any],
    preferred_action_ids: Sequence[str],
) -> dict[str, Any]:
    """Turn numerical evidence into one conservative, player-facing decision grade."""

    agreement = len(set(preferred_action_ids)) == 1
    if selected_action_id == "refresh":
        return {
            "grade": "refresh",
            "model_agreement": agreement,
            "reason": "当前三个选项没有可接受的直接改善；刷新只表示拒绝本轮，不估计未来选项。",
        }
    mean_delta = float(selected_row["mean_delta"])
    cvar_delta = float(selected_row["cvar10_delta"])
    support_lower = float(selected_row["support_lower"])
    if mean_delta > 0.0 and cvar_delta >= 0.0 and support_lower >= 0.0 and agreement:
        return {
            "grade": "clear",
            "model_agreement": True,
            "reason": "平均、低迷情景和所有合法结果都不低于当前战旗，三个出率模型也一致。",
        }
    return {
        "grade": "conditional",
        "model_agreement": agreement,
        "reason": "平均结果有改善，但低迷情景、最差合法结果或出率模型至少一项存在风险。",
    }


def rank_title_for_lineup(
    title_evidence: Mapping[str, Any],
    *,
    selected_team_ids: tuple[int, int, int],
    role_base_means: Mapping[str, float],
    excluded_suffix_ids: Sequence[str],
    top_k: int,
) -> dict[str, Any]:
    """Rank Title marginals for the selected Team×role pools.

    The available evidence contains marginal trigger rates, not Prefix/Suffix
    joint observations.  The displayed pair lift is therefore their simple sum.
    """

    analysis = title_evidence.get("analysis")
    if not isinstance(analysis, Mapping):
        raise CurrentAdvisorError("Title evidence has no analysis payload")
    pools = analysis.get("pools")
    if not isinstance(pools, Sequence):
        raise CurrentAdvisorError("Title evidence has no Team×role pools")
    pool_index = {
        (int(row["team_id"]), str(row["role"])): row
        for row in pools
        if isinstance(row, Mapping) and "team_id" in row and "role" in row
    }
    selected_pools = []
    for role, team_id in zip(ROLE_IDS, selected_team_ids, strict=True):
        try:
            selected_pools.append(pool_index[(int(team_id), role)])
        except KeyError as error:
            raise CurrentAdvisorError(f"Title evidence lacks Team {team_id} {role}") from error

    positive = {role: max(0.0, float(role_base_means.get(role, 0.0))) for role in ROLE_IDS}
    total = sum(positive.values())
    role_weights = (
        {role: positive[role] / total for role in ROLE_IDS}
        if total > 0.0
        else {role: 1.0 / len(ROLE_IDS) for role in ROLE_IDS}
    )

    def ranked(kind: str, *, excluded: set[str]) -> list[dict[str, Any]]:
        summary = analysis.get("prefixes" if kind == "prefix" else "suffixes")
        if not isinstance(summary, Sequence):
            raise CurrentAdvisorError(f"Title evidence has no {kind} summary")
        metadata = {
            str(row["id"]): row
            for row in summary
            if isinstance(row, Mapping) and "id" in row
        }
        bonus_key = f"{kind}_paper_bonus_percent"
        rate_key = f"{kind}_trigger_rates"
        rows = []
        for item_id, item in metadata.items():
            if item_id in excluded:
                continue
            values = []
            rates = []
            unavailable = False
            for role, pool in zip(ROLE_IDS, selected_pools, strict=True):
                bonus = pool.get(bonus_key, {}).get(item_id)
                rate = pool.get(rate_key, {}).get(item_id)
                if bonus is None or rate is None:
                    unavailable = True
                    break
                values.append(role_weights[role] * float(bonus))
                rates.append(role_weights[role] * float(rate))
            if unavailable:
                continue
            rows.append(
                {
                    "id": item_id,
                    "name": str(item.get("name", item_id)),
                    "label": str(item.get("label", "")),
                    "displayed_bonus_percent": float(item.get("bonus_percent", 0.0)),
                    "trigger_rate": sum(rates),
                    "paper_bonus_percent": sum(values),
                }
            )
        rows.sort(key=lambda row: (-float(row["paper_bonus_percent"]), str(row["id"])))
        return [{**row, "rank": index} for index, row in enumerate(rows[:top_k], start=1)]

    prefixes = ranked("prefix", excluded=set())
    suffixes = ranked("suffix", excluded=set(excluded_suffix_ids))
    if not prefixes or not suffixes:
        raise CurrentAdvisorError("Title evidence produced no recommendable Prefix or Suffix")
    pair_bonus = float(prefixes[0]["paper_bonus_percent"]) + float(
        suffixes[0]["paper_bonus_percent"]
    )
    return {
        "recommended_prefix": prefixes[0],
        "recommended_suffix": suffixes[0],
        "estimated_pair_bonus_percent": round(pair_bonus, 10),
        "prefixes": prefixes,
        "suffixes": suffixes,
        "selected_team_ids": list(selected_team_ids),
        "role_weights": {role: round(role_weights[role], 12) for role in ROLE_IDS},
        "method": "按当前三面战旗的预计基础贡献加权；组合加成是两项纸面均值的简单相加。",
        "limitation": "缺少 Prefix 与 Suffix 同局联合触发分布，不把该估算当成最终结算保证。",
    }


def analyze_current_screen(
    context: CurrentAdvisorContext,
    state: GroupRollState,
    *,
    risk_profile: str = "balanced",
    selected_team_ids: tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    """Recommend exactly one action from the complete currently observed screen."""

    validate_group_state(state, context.roll_rules)
    if state.period != "group":
        raise CurrentAdvisorError("Main five-slot execution is not implemented")
    try:
        epsilon = context.policy.analysis.risk_profiles[risk_profile]
    except KeyError as error:
        raise ValueError(f"unknown risk profile: {risk_profile}") from error
    risk = RiskConfiguration(
        mean_retention_epsilon=epsilon,
        cvar_alpha=context.policy.analysis.cvar_alpha,
    )
    current = _evaluate_group(context, state.banners, risk, selected_team_ids)
    actions = legal_actions(state, context.roll_rules)
    action_rows: list[dict[str, Any]] = []
    preferred_by_model: list[dict[str, str]] = []

    outcome_cache: dict[tuple[str, int, BannerState], CurrentGroupEvaluation] = {}
    support_bounds: dict[str, tuple[float, float]] = {"refresh": (0.0, 0.0)}
    for action in actions:
        if isinstance(action, RefreshRollAction):
            continue
        current_banner = next(banner for banner in state.banners if banner.role == action.banner_role)
        model = context.policy.analysis.primary_model
        outcomes = mutation_distribution(
            current_banner,
            action.operation_id,
            context.roll_rules,
            model,
        )
        deltas = []
        for outcome in outcomes:
            key = (action.banner_role, action.operation_id, outcome.banner)
            if key not in outcome_cache:
                outcome_cache[key] = _evaluate_group(
                    context,
                    _replace_banner(state.banners, outcome.banner),
                    risk,
                    selected_team_ids,
                )
            deltas.append(outcome_cache[key].mean - current.mean)
        support_bounds[action_identity(action)] = (min(deltas), max(deltas))

    for model_id in context.policy.analysis.models:
        model_rows = []
        for action in actions:
            identity = action_identity(action)
            if isinstance(action, RefreshRollAction):
                distribution = WeightedOutcomeDistribution(
                    current.outcomes,
                    np.full(len(current.outcomes), 1.0 / len(current.outcomes)),
                )
                support_count = 1
            else:
                current_banner = next(
                    banner for banner in state.banners if banner.role == action.banner_role
                )
                mutations = mutation_distribution(
                    current_banner,
                    action.operation_id,
                    context.roll_rules,
                    model_id,
                )
                values = np.concatenate(
                    [
                        outcome_cache[(action.banner_role, action.operation_id, item.banner)].outcomes
                        for item in mutations
                    ]
                )
                weights = np.concatenate(
                    [
                        np.full(len(context.scenarios.scenario_ids), item.probability)
                        / len(context.scenarios.scenario_ids)
                        for item in mutations
                    ]
                )
                distribution = WeightedOutcomeDistribution(values, weights)
                support_count = len(mutations)
            lower, upper = support_bounds[identity]
            row = {
                "model_id": model_id,
                "action_id": identity,
                "action_label": _public_action_label(action, context.roll_rules),
                "mean": distribution.mean,
                "cvar10": distribution.cvar(context.policy.analysis.cvar_alpha),
                "mean_delta": distribution.mean - current.mean,
                "cvar10_delta": distribution.cvar(context.policy.analysis.cvar_alpha)
                - current.cvar10,
                "support_lower": lower,
                "support_upper": upper,
                "support_count": support_count,
            }
            action_rows.append(row)
            model_rows.append(row)
        if model_rows:
            selected = _preferred_action(model_rows, mean_retention_epsilon=epsilon)
            preferred_by_model.append({"model_id": model_id, "action_id": selected})

    primary_rows = [
        row
        for row in action_rows
        if row["model_id"] == context.policy.analysis.primary_model
    ]
    if primary_rows:
        selected_action_id = next(
            row["action_id"]
            for row in preferred_by_model
            if row["model_id"] == context.policy.analysis.primary_model
        )
        selected_row = next(row for row in primary_rows if row["action_id"] == selected_action_id)
        classification = classify_recommendation(
            selected_action_id=selected_action_id,
            selected_row=selected_row,
            preferred_action_ids=tuple(row["action_id"] for row in preferred_by_model),
        )
        recommendation = {
            **classification,
            "action_id": selected_action_id,
            "action_label": selected_row["action_label"],
            "mean_delta": selected_row["mean_delta"],
            "cvar10_delta": selected_row["cvar10_delta"],
            "support_lower": selected_row["support_lower"],
            "support_upper": selected_row["support_upper"],
        }
    else:
        recommendation = {
            "grade": "complete",
            "model_agreement": True,
            "action_id": None,
            "action_label": "Roll 已用完",
            "mean_delta": 0.0,
            "cvar10_delta": 0.0,
            "support_lower": 0.0,
            "support_upper": 0.0,
            "reason": "没有剩余 Roll；请使用当前队伍和 Title 建议。",
        }

    title = rank_title_for_lineup(
        context.title_evidence,
        selected_team_ids=current.selected_team_ids,
        role_base_means=current.role_base_means,
        excluded_suffix_ids=context.policy.title.excluded_suffix_ids,
        top_k=context.policy.title.top_k,
    )
    primary_rows.sort(
        key=lambda row: (
            row["action_id"] != recommendation["action_id"],
            -float(row["mean"]),
            -float(row["cvar10"]),
            str(row["action_id"]),
        )
    )
    payload = {
        "schema_version": 2,
        "analysis_type": "current_screen_exact_one_step_no_future_offer_value",
        "as_of": context.policy.as_of,
        "risk_profile": risk_profile,
        "team_mode": "manual" if selected_team_ids is not None else "auto",
        "current": {
            "selected_team_ids": list(current.selected_team_ids),
            "selected_teams": [
                context.team_names.get(team_id, str(team_id)) for team_id in current.selected_team_ids
            ],
            "mean": current.mean,
            "cvar10": current.cvar10,
            "maximum_mean": current.maximum_mean,
            "role_base_means": dict(current.role_base_means),
        },
        "recommendation": recommendation,
        "primary_action_values": primary_rows,
        "preferred_by_model": preferred_by_model,
        "title": title,
        "limitations": [
            "不生成或估计下一轮未知 Roll 选项；玩家须按游戏实际画面更新输入。",
            "Title 目前独立展示，尚未加入 Roll 动作分值。",
        ],
    }
    payload["analysis_sha256"] = sha256_json(payload)
    return payload
