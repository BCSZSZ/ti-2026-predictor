"""Current-screen, one-step advice for the independent five-slot Main stack."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import numpy as np

from ti_predictor.fantasy.advisor import action_identity, action_label
from ti_predictor.fantasy.main_advice_policy import (
    MainImmediateActionValue,
    choose_greedy_main_action,
    choose_main_strategy_action,
    main_state_sha256,
    sample_g_lite_transition,
)
from ti_predictor.fantasy.main_advice_strategy import (
    G_LITE_MAIN_STRATEGY_ID,
    MainAdviceStrategyCatalog,
)
from ti_predictor.fantasy.main_roll import (
    MainRollState,
    legal_actions,
    mutation_distribution,
    validate_main_state,
)
from ti_predictor.fantasy.roll import BannerState, RefreshRollAction, RollRuleSet
from ti_predictor.fantasy.scenarios import ROLE_IDS, PoolBuildResult
from ti_predictor.fantasy.solver import WeightedOutcomeDistribution
from ti_predictor.fantasy.valuation import (
    RiskConfiguration,
    TeamOutcomeMatrix,
    TerminalValueCache,
    distribution_summary,
    match_group_roles,
)
from ti_predictor.hashing import sha256_json


class MainCurrentAdvisorError(ValueError):
    """The Main current-screen advisor cannot safely produce a result."""


class MainBannerTerminal(Protocol):
    def banner(self, banner: BannerState) -> TeamOutcomeMatrix: ...


class MainTerminalEvaluator:
    """Five-slot Banner valuation over a separately built Main Scenario set."""

    def __init__(
        self,
        pool_result: PoolBuildResult,
        scenario_set: Any,
        canonical_rules: dict[str, Any],
    ) -> None:
        eligibility_mode = getattr(scenario_set, "eligibility_mode", "actual")
        if eligibility_mode not in {"projected", "actual"}:
            raise MainCurrentAdvisorError("unknown Main Scenario eligibility mode")
        expected_candidates = 16 if eligibility_mode == "projected" else 8
        if len(tuple(scenario_set.team_ids)) != expected_candidates:
            raise MainCurrentAdvisorError(
                f"{eligibility_mode} Main terminal evaluation requires {expected_candidates} candidate Teams"
            )
        self.pool_result = pool_result
        self.scenario_set = scenario_set
        self.canonical_rules = canonical_rules
        self.eligibility_mode = eligibility_mode
        self.cache = TerminalValueCache()

    def banner(self, banner: BannerState) -> TeamOutcomeMatrix:
        return self.cache.banner(
            self.pool_result,
            self.scenario_set,
            banner,
            self.canonical_rules,
            slot_count=5,
            period_label="Main",
            empty_series_value=0.0 if self.eligibility_mode == "projected" else None,
        )


@dataclass(frozen=True)
class MainCurrentAdvisorContext:
    as_of: str
    roll_rules: RollRuleSet
    terminal: MainBannerTerminal
    scenario_count: int
    team_names: Mapping[int, str]
    strategy_catalog: MainAdviceStrategyCatalog
    eligibility_mode: Literal["projected", "actual"] = "actual"
    primary_model: str = "client-weight-primary-v1"
    models: tuple[str, ...] = (
        "client-weight-primary-v1",
        "flattened-weights-v1",
        "sharpened-weights-v1",
    )
    cvar_alpha: float = 0.1
    risk_profiles: tuple[tuple[str, float], ...] = (
        ("mean-first", 0.0),
        ("balanced", 0.01),
        ("downside-first", 0.02),
    )
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.eligibility_mode not in {"projected", "actual"}:
            raise MainCurrentAdvisorError("unknown Main eligibility mode")
        if self.scenario_count < 1:
            raise MainCurrentAdvisorError("Main advisor requires at least one coherent Scenario")
        expected_candidates = 16 if self.eligibility_mode == "projected" else 8
        if len(self.team_names) != expected_candidates:
            raise MainCurrentAdvisorError(
                f"{self.eligibility_mode} Main advisor requires {expected_candidates} candidate Teams"
            )
        if self.primary_model not in self.models or len(set(self.models)) != len(self.models):
            raise MainCurrentAdvisorError("Main transition models are inconsistent")
        if self.strategy_catalog.primary_transition_model != self.primary_model:
            raise MainCurrentAdvisorError("Main strategy catalog and transition model are inconsistent")
        if set(dict(self.risk_profiles)) != {"mean-first", "balanced", "downside-first"}:
            raise MainCurrentAdvisorError("Main advisor requires the three risk profiles")
        if not 0.0 < self.cvar_alpha <= 1.0:
            raise MainCurrentAdvisorError("Main CVaR alpha must be in (0, 1]")


@dataclass(frozen=True)
class CurrentMainEvaluation:
    selected_team_ids: tuple[int, int, int]
    outcomes: np.ndarray
    mean: float
    cvar10: float
    maximum_mean: float
    role_base_means: Mapping[str, float]


def _evaluate_main(
    context: MainCurrentAdvisorContext,
    banners: tuple[BannerState, ...],
    risk: RiskConfiguration,
    selected_team_ids: tuple[int, int, int] | None,
) -> CurrentMainEvaluation:
    banner_by_role = {banner.role: banner for banner in banners}
    matrices = {role: context.terminal.banner(banner_by_role[role]) for role in ROLE_IDS}
    if any(matrix.outcomes.shape[1] != context.scenario_count for matrix in matrices.values()):
        raise MainCurrentAdvisorError("Main terminal matrices do not align with the Scenario count")
    if selected_team_ids is None:
        matched = match_group_roles(matrices, risk)
        team_ids = tuple(int(value) for value in matched.selected_team_ids)
        outcomes = matched.outcomes
        maximum_mean = matched.maximum_mean
    else:
        if len(selected_team_ids) != len(ROLE_IDS):
            raise ValueError("manual Main lineup must select one Team for each Fantasy role")
        indexes = []
        for role, team_id in zip(ROLE_IDS, selected_team_ids, strict=True):
            try:
                indexes.append(matrices[role].team_ids.index(int(team_id)))
            except ValueError as error:
                raise ValueError(f"Team {team_id} is unavailable for Main {role}") from error
        team_ids = tuple(int(value) for value in selected_team_ids)
        outcomes = sum(
            (matrices[role].outcomes[index] for role, index in zip(ROLE_IDS, indexes, strict=True)),
            start=np.zeros(context.scenario_count, dtype=float),
        )
        maximum_mean = float(sum(float(matrices[role].outcomes.mean(axis=1).max()) for role in ROLE_IDS))
    role_base_means = {
        role: float(matrices[role].outcomes[matrices[role].team_ids.index(team_id)].mean())
        for role, team_id in zip(ROLE_IDS, team_ids, strict=True)
    }
    summary = distribution_summary(outcomes, cvar_alpha=risk.cvar_alpha)
    return CurrentMainEvaluation(
        selected_team_ids=team_ids,  # type: ignore[arg-type]
        outcomes=outcomes,
        mean=float(summary["mean"]),
        cvar10=float(summary["cvar"]),
        maximum_mean=maximum_mean,
        role_base_means=role_base_means,
    )


def _replace_banner(
    banners: tuple[BannerState, ...],
    replacement: BannerState,
) -> tuple[BannerState, ...]:
    return tuple(replacement if banner.role == replacement.role else banner for banner in banners)


def _preferred_action(rows: Sequence[Mapping[str, Any]], *, epsilon: float) -> str:
    maximum_mean = max(float(row["mean"]) for row in rows)
    floor = maximum_mean - abs(maximum_mean) * epsilon - 1e-12
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


def _classification(
    selected_action_id: str,
    selected_row: Mapping[str, Any],
    preferred_action_ids: Sequence[str],
) -> dict[str, Any]:
    agreement = len(set(preferred_action_ids)) == 1
    if selected_action_id == "refresh":
        return {
            "grade": "refresh",
            "model_agreement": agreement,
            "reason": "当前三个选项没有可接受的 Main 直接改善；不估计下一轮未知选项。",
        }
    mean_delta = float(selected_row["mean_delta"])
    cvar_delta = float(selected_row["cvar10_delta"])
    support_lower = float(selected_row["support_lower"])
    if mean_delta > 0.0 and cvar_delta >= 0.0 and support_lower >= 0.0 and agreement:
        return {
            "grade": "clear",
            "model_agreement": True,
            "reason": "Main 平均、低迷情景和所有合法结果都不低于当前战旗，三个出率模型一致。",
        }
    return {
        "grade": "conditional",
        "model_agreement": agreement,
        "reason": "平均结果有改善，但 Main 低迷情景、最差结果或出率模型至少一项存在风险。",
    }


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


@dataclass(frozen=True)
class _MainActionTable:
    current: CurrentMainEvaluation
    action_by_id: Mapping[str, Any]
    rows: tuple[dict[str, Any], ...]
    preferred_by_model: tuple[dict[str, str], ...]


def _build_main_action_table(
    context: MainCurrentAdvisorContext,
    state: MainRollState,
    risk: RiskConfiguration,
    selected_team_ids: tuple[int, int, int] | None,
    *,
    model_ids: Sequence[str],
    epsilon: float,
) -> _MainActionTable:
    current = _evaluate_main(context, state.banners, risk, selected_team_ids)
    actions = legal_actions(state, context.roll_rules)
    action_by_id = {action_identity(action): action for action in actions}
    evaluations: dict[BannerState, CurrentMainEvaluation] = {}

    def evaluate_outcome(role: str, banner: BannerState) -> CurrentMainEvaluation:
        if banner not in evaluations:
            evaluations[banner] = _evaluate_main(
                context,
                _replace_banner(state.banners, banner),
                risk,
                selected_team_ids,
            )
        return evaluations[banner]

    support_bounds: dict[str, tuple[float, float]] = {"refresh": (0.0, 0.0)}
    for action in actions:
        if isinstance(action, RefreshRollAction):
            continue
        banner = next(item for item in state.banners if item.role == action.banner_role)
        outcomes = mutation_distribution(
            banner,
            action.operation_id,
            context.roll_rules,
            context.primary_model,
        )
        deltas = [evaluate_outcome(action.banner_role, item.banner).mean - current.mean for item in outcomes]
        if not deltas or not all(math.isfinite(value) for value in deltas):
            raise MainCurrentAdvisorError("Main action support produced no finite valuation")
        support_bounds[action_identity(action)] = (min(deltas), max(deltas))

    action_rows: list[dict[str, Any]] = []
    preferred_by_model: list[dict[str, str]] = []
    for model_id in model_ids:
        model_rows: list[dict[str, Any]] = []
        for action in actions:
            identity = action_identity(action)
            if isinstance(action, RefreshRollAction):
                distribution = WeightedOutcomeDistribution(
                    current.outcomes,
                    np.full(context.scenario_count, 1.0 / context.scenario_count),
                )
                support_count = 1
            else:
                banner = next(item for item in state.banners if item.role == action.banner_role)
                mutations = mutation_distribution(
                    banner,
                    action.operation_id,
                    context.roll_rules,
                    model_id,
                )
                values = np.concatenate(
                    [evaluate_outcome(action.banner_role, item.banner).outcomes for item in mutations]
                )
                weights = np.concatenate(
                    [
                        np.full(context.scenario_count, item.probability) / context.scenario_count
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
                "cvar10": distribution.cvar(context.cvar_alpha),
                "mean_delta": distribution.mean - current.mean,
                "cvar10_delta": distribution.cvar(context.cvar_alpha) - current.cvar10,
                "support_lower": lower,
                "support_upper": upper,
                "support_count": support_count,
            }
            action_rows.append(row)
            model_rows.append(row)
        if model_rows:
            preferred_by_model.append(
                {"model_id": model_id, "action_id": _preferred_action(model_rows, epsilon=epsilon)}
            )
    return _MainActionTable(
        current=current,
        action_by_id=action_by_id,
        rows=tuple(action_rows),
        preferred_by_model=tuple(preferred_by_model),
    )


def _primary_strategy_values(
    table: _MainActionTable,
    model_id: str,
) -> tuple[MainImmediateActionValue, ...]:
    return tuple(
        MainImmediateActionValue(
            action=table.action_by_id[str(row["action_id"])],
            mean=float(row["mean"]),
            cvar10=float(row["cvar10"]),
            mean_delta=float(row["mean_delta"]),
            support_lower=float(row["support_lower"]),
        )
        for row in table.rows
        if row["model_id"] == model_id
    )


def analyze_main_current_screen(
    context: MainCurrentAdvisorContext,
    state: MainRollState,
    *,
    risk_profile: str = "mean-first",
    selected_team_ids: tuple[int, int, int] | None = None,
    strategy_id: str | None = None,
    g_lite_triggers_used: int = 0,
) -> dict[str, Any]:
    """Recommend one Main action from all fifteen currently visible Emblems."""

    validate_main_state(state, context.roll_rules)
    try:
        epsilon = dict(context.risk_profiles)[risk_profile]
    except KeyError as error:
        raise ValueError(f"unknown Main risk profile: {risk_profile}") from error
    resolved_strategy_id = strategy_id or context.strategy_catalog.default_strategy_id
    strategy_label = context.strategy_catalog.label(resolved_strategy_id)
    risk = RiskConfiguration(mean_retention_epsilon=epsilon, cvar_alpha=context.cvar_alpha)
    table = _build_main_action_table(
        context,
        state,
        risk,
        selected_team_ids,
        model_ids=context.models,
        epsilon=epsilon,
    )
    current = table.current
    primary_rows = [row for row in table.rows if row["model_id"] == context.primary_model]
    decision_diagnostics: dict[str, Any]
    g_lite_triggered = False
    if primary_rows:
        continuation_cache: dict[tuple[str, int], tuple[float, float]] = {}

        def continuation_value(action: Any, sample_index: int) -> tuple[float, float]:
            cache_key = (action_identity(action), sample_index)
            if cache_key in continuation_cache:
                return continuation_cache[cache_key]
            specification = context.strategy_catalog.strategies.g_lite
            next_state = sample_g_lite_transition(
                state,
                action,
                sample_index,
                rules=context.roll_rules,
                model_id=context.primary_model,
                decision_seed=specification.decision_seed,
            )
            next_table = _build_main_action_table(
                context,
                next_state,
                risk,
                selected_team_ids,
                model_ids=(context.primary_model,),
                epsilon=epsilon,
            )
            next_values = _primary_strategy_values(next_table, context.primary_model)
            if next_values:
                selected = choose_greedy_main_action(
                    next_state,
                    next_values,
                    mean_retention_epsilon=epsilon,
                    improvement_tolerance=(context.strategy_catalog.strategies.greedy.improvement_tolerance),
                )
                value = (selected.mean, selected.cvar10)
            else:
                value = (next_table.current.mean, next_table.current.cvar10)
            continuation_cache[cache_key] = value
            return value

        decision = choose_main_strategy_action(
            context.strategy_catalog,
            resolved_strategy_id,
            state,
            current.mean,
            _primary_strategy_values(table, context.primary_model),
            mean_retention_epsilon=epsilon,
            g_lite_triggers_used=g_lite_triggers_used,
            continuation_value=continuation_value,
        )
        selected_action_id = action_identity(decision.action)
        selected_row = next(row for row in primary_rows if row["action_id"] == selected_action_id)
        g_lite_triggered = decision.triggered
        decision_diagnostics = dict(decision.diagnostics)
        classification = _classification(
            selected_action_id,
            selected_row,
            tuple(row["action_id"] for row in table.preferred_by_model),
        )
        if resolved_strategy_id == G_LITE_MAIN_STRATEGY_ID:
            changed_from_g = selected_action_id != action_identity(decision.baseline_action)
            if decision.triggered and changed_from_g:
                classification["reason"] = (
                    "G-Lite 在两项一步价值足够接近时完成了固定 4 样本的有限二步比较，"
                    "并改选了相对 G 更高的二步估计。"
                )
            elif decision.triggered:
                classification["reason"] = "G-Lite 已触发有限二步比较；固定样本没有给出足够优势，因此保持 G。"
            else:
                classification["reason"] = "本次不满足 G-Lite 触发条件，直接保持 G 的一步建议。"
        recommendation = {
            **classification,
            "action_id": selected_action_id,
            "action_label": selected_row["action_label"],
            "mean_delta": selected_row["mean_delta"],
            "cvar10_delta": selected_row["cvar10_delta"],
            "support_lower": selected_row["support_lower"],
            "support_upper": selected_row["support_upper"],
            "strategy_id": resolved_strategy_id,
            "strategy_label": strategy_label,
            "g_lite_triggered": decision.triggered,
            "changed_from_g": selected_action_id != action_identity(decision.baseline_action),
        }
    else:
        decision_diagnostics = {"mode": "rolls-complete"}
        recommendation = {
            "grade": "complete",
            "model_agreement": True,
            "action_id": None,
            "action_label": "Main Roll 已用完",
            "mean_delta": 0.0,
            "cvar10_delta": 0.0,
            "support_lower": 0.0,
            "support_upper": 0.0,
            "reason": "没有剩余 Main Roll。",
            "strategy_id": resolved_strategy_id,
            "strategy_label": strategy_label,
            "g_lite_triggered": False,
            "changed_from_g": False,
        }
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
        "period": "main",
        "analysis_type": (
            "main_current_screen_selective_two_step_sampled_future_offer_value"
            if resolved_strategy_id == G_LITE_MAIN_STRATEGY_ID
            else "main_current_screen_exact_one_step_no_future_offer_value"
        ),
        "as_of": context.as_of,
        "eligibility_mode": context.eligibility_mode,
        "state_sha256": main_state_sha256(state),
        "risk_profile": risk_profile,
        "team_mode": "manual" if selected_team_ids is not None else "auto",
        "strategy": {
            "catalog_id": context.strategy_catalog.catalog_id,
            "catalog_sha256": context.strategy_catalog.semantic_hash,
            "strategy_id": resolved_strategy_id,
            "strategy_label": strategy_label,
            "is_default": resolved_strategy_id == context.strategy_catalog.default_strategy_id,
            "decision_mode": decision_diagnostics["mode"],
            "diagnostics": decision_diagnostics,
            "g_lite_triggers_used_before": g_lite_triggers_used,
            "g_lite_triggered": g_lite_triggered,
            "g_lite_triggers_used_after": g_lite_triggers_used + int(g_lite_triggered),
            "g_lite_max_triggers": (context.strategy_catalog.strategies.g_lite.max_triggers_per_episode),
            "evidence_status": (
                context.strategy_catalog.strategies.g_lite.research_evidence.evidence_status
                if resolved_strategy_id == G_LITE_MAIN_STRATEGY_ID
                else "production-default"
            ),
        },
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
        "preferred_by_model": list(table.preferred_by_model),
        "limitations": [
            *(
                [
                    "G-Lite 只在近似平手时，对两个候选各抽 4 个确定性下一轮样本；它不是完整 30 步搜索。",
                    "G-Lite 每局最多触发 4 次，当前只有 100 个合成开发状态的正向点估计，"
                    "未通过独立 confirmation；因此仅供用户主动选择。",
                    "执行建议后必须重新读取完整五槽画面。",
                ]
                if resolved_strategy_id == G_LITE_MAIN_STRATEGY_ID
                else ["G 不生成或估计下一轮未知 Main Roll 选项；操作后必须重新读取完整五槽画面。"]
            ),
            *context.warnings,
        ],
    }
    payload["analysis_sha256"] = sha256_json(payload)
    return payload


__all__ = [
    "MainCurrentAdvisorContext",
    "MainCurrentAdvisorError",
    "MainTerminalEvaluator",
    "analyze_main_current_screen",
]
