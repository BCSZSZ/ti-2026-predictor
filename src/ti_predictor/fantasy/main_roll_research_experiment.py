"""Offline paired experiments for the isolated TI 2026 Main Roll simulator.

Run this module directly; it is intentionally not registered in the shared ``ti`` CLI
and is not imported by the Web application::

    uv run python -m ti_predictor.fantasy.main_roll_research_experiment --state state.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
from scipy import stats

from ti_predictor.fantasy.main_advice_strategy import load_main_advice_strategy_catalog
from ti_predictor.fantasy.main_roll import MainRollState
from ti_predictor.fantasy.main_roll_research_contract import (
    MainRollResearchManifest,
    load_main_roll_research_manifest,
)
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_rosters import (
    ProjectedRosterConditionalTerminal,
    ProjectedRosterPanel,
    build_projected_roster_panel,
)
from ti_predictor.fantasy.main_roll_research_simulator import (
    EpisodeResult,
    MainResearchTerminal,
    MainRollResearchSimulator,
    state_from_payload,
    state_sha256,
)
from ti_predictor.fantasy.main_roll_research_strategies import (
    GreedyImmediatePolicy,
    HorizonHybridPolicy,
    TargetSeekingPolicy,
)
from ti_predictor.fantasy.main_roll_research_terminal import VectorizedMainResearchTerminal
from ti_predictor.fantasy.main_solver_release import load_main_solver_release_context
from ti_predictor.fantasy.roll import RollRuleSet
from ti_predictor.fantasy.solver_release import load_solver_release_context
from ti_predictor.fantasy.valuation import lower_tail_cvar
from ti_predictor.forecasting import load_strength_model_as_of
from ti_predictor.hashing import canonical_json, sha256_bytes, sha256_file, sha256_json
from ti_predictor.paths import PATHS
from ti_predictor.rules import rules_hash
from ti_predictor.runs import source_version

RunMode = Literal["smoke", "tuning", "confirmation"]


class MainResearchExperimentError(ValueError):
    """An offline experiment violates its frozen comparison or output boundary."""


@dataclass(frozen=True)
class ResearchExperimentResult:
    report: dict[str, Any]
    episodes: tuple[EpisodeResult, ...]
    roster_panel: dict[str, Any] | None = None


_WORKER_CONTEXT: (
    tuple[
        MainRollResearchManifest,
        RollRuleSet,
        MainResearchTerminal,
        MainRollState,
        str,
    ]
    | None
) = None


type ParallelWorkerContext = tuple[str, str, tuple[int, ...], int, int]


def _initialize_episode_worker_from_files(
    manifest_path: str,
    state_path: str,
    selected_folds: tuple[int, ...],
    inner_count: int,
    remaining_rolls: int,
    source_version_id: str,
) -> None:
    global _WORKER_CONTEXT
    manifest = load_main_roll_research_manifest(Path(manifest_path))
    group_context = load_solver_release_context()
    main_context = load_frozen_main_research_context(group_context, manifest)
    model, model_report = load_strength_model_as_of(as_of=manifest.as_of)
    blocking = [issue.message for issue in model_report.issues if issue.severity == "blocking"]
    if blocking or sha256_json(model.as_dict()) != manifest.source.team_strength_model_sha256:
        raise MainResearchExperimentError("episode worker could not reproduce the frozen model")
    roster_panel = build_projected_roster_panel(
        main_context.terminal.pool_result,
        group_context.scenarios,
        main_context.terminal.scenario_set,
        model,
        manifest.projected_roster_validation,
        selected_fold_ids=selected_folds,
        inner_scenarios_per_phase=inner_count,
    )
    terminal = ProjectedRosterConditionalTerminal(
        VectorizedMainResearchTerminal(
            main_context.terminal.pool_result,
            roster_panel.scenarios,
            main_context.terminal.canonical_rules,
        ),
        roster_panel,
        cvar_alpha=manifest.strategies.greedy.cvar_alpha,
    )
    state = state_from_payload(
        json.loads(Path(state_path).read_text(encoding="utf-8")),
        main_context.roll_rules,
    )
    if remaining_rolls != state.remaining_rolls:
        state = replace(state, remaining_rolls=remaining_rolls)
    _WORKER_CONTEXT = (
        manifest,
        main_context.roll_rules,
        terminal,
        state,
        source_version_id,
    )


def _run_worker_episode_batch(task: tuple[str, int]) -> tuple[EpisodeResult, ...]:
    if _WORKER_CONTEXT is None:
        raise MainResearchExperimentError("research episode worker was not initialized")
    manifest, rules, terminal, state, source_version_id = _WORKER_CONTEXT
    model_id, seed = task
    provider = MainRollProbabilityProvider(rules, manifest.probability_model(model_id))
    simulator = MainRollResearchSimulator(
        manifest,
        rules,
        terminal,
        source_version=source_version_id,
    )
    policies = _build_policies(manifest, rules, terminal, provider)
    try:
        return tuple(
            simulator.run_episode(
                state,
                policy,
                provider,
                episode_seed=seed,
            )
            for policy in policies
        )
    finally:
        clear = getattr(terminal, "clear_evaluation_cache", None)
        if clear is not None:
            clear()


def _seed_values(
    manifest: MainRollResearchManifest,
    mode: RunMode,
    *,
    smoke_count: int,
) -> tuple[int, ...]:
    if mode == "tuning":
        return manifest.splits.tuning.values
    if mode == "confirmation":
        return manifest.splits.confirmation.values
    if smoke_count < 1:
        raise MainResearchExperimentError("smoke_count must be positive")
    return manifest.splits.tuning.values[:smoke_count]


def _paired_interval(
    differences: np.ndarray,
    confidence_level: float,
) -> dict[str, float | None]:
    values = np.asarray(differences, dtype=float)
    mean = float(values.mean())
    if len(values) < 2 or np.isclose(values.std(ddof=1), 0.0):
        return {
            "mean": mean,
            "two_sided_lower": mean if len(values) >= 2 else None,
            "two_sided_upper": mean if len(values) >= 2 else None,
            "one_sided_lower": mean if len(values) >= 2 else None,
        }
    standard_error = float(values.std(ddof=1) / math.sqrt(len(values)))
    two_sided = float(stats.t.ppf((1.0 + confidence_level) / 2.0, len(values) - 1))
    one_sided = float(stats.t.ppf(confidence_level, len(values) - 1))
    return {
        "mean": mean,
        "two_sided_lower": mean - two_sided * standard_error,
        "two_sided_upper": mean + two_sided * standard_error,
        "one_sided_lower": mean - one_sided * standard_error,
    }


def _policy_summary(episodes: list[EpisodeResult]) -> dict[str, Any]:
    means = np.asarray([episode.final_terminal.mean for episode in episodes], dtype=float)
    cvars = np.asarray([episode.final_terminal.cvar10 for episode in episodes], dtype=float)
    outcomes = np.concatenate([episode.final_terminal.outcomes for episode in episodes])
    action_counts: Counter[str] = Counter()
    target_mode_steps = 0
    for episode in episodes:
        for step in episode.trace["steps"]:
            action_counts[str(step["decision"]["action_id"])] += 1
            mode = str(step["decision"]["diagnostics"].get("mode", ""))
            if "target" in mode and "fallback" not in mode:
                target_mode_steps += 1
    result = {
        "episode_count": len(episodes),
        "terminal_mean": {
            "mean": float(means.mean()),
            "median": float(np.median(means)),
            "minimum": float(means.min()),
            "maximum": float(means.max()),
        },
        "terminal_cvar10": {
            "mean": float(cvars.mean()),
            "median": float(np.median(cvars)),
        },
        "joint_roll_and_match_outcomes": {
            "mean": float(outcomes.mean()),
            "p10": float(np.quantile(outcomes, 0.1)),
            "p50": float(np.quantile(outcomes, 0.5)),
            "p90": float(np.quantile(outcomes, 0.9)),
        },
        "spent_rolls_mean": float(np.mean([episode.trace["spent_rolls"] for episode in episodes])),
        "target_mode_steps": target_mode_steps,
        "action_counts": dict(sorted(action_counts.items())),
    }
    cohort_ids = episodes[0].final_terminal.cohort_ids
    if cohort_ids:
        cohorts = sorted(set(cohort_ids))
        result["by_roster_fold"] = {
            str(cohort): {
                "terminal_mean": {
                    "mean": float(
                        np.mean(
                            [
                                episode.final_terminal.outcomes[
                                    np.asarray(episode.final_terminal.cohort_ids) == cohort
                                ].mean()
                                for episode in episodes
                            ]
                        )
                    )
                },
                "terminal_cvar10": {
                    "mean": float(
                        np.mean(
                            [
                                lower_tail_cvar(
                                    episode.final_terminal.outcomes[
                                        np.asarray(episode.final_terminal.cohort_ids) == cohort
                                    ],
                                    0.1,
                                )
                                for episode in episodes
                            ]
                        )
                    )
                },
            }
            for cohort in cohorts
        }
    return result


def _paired_comparison(
    challenger: list[EpisodeResult],
    greedy: list[EpisodeResult],
    confidence_level: float,
) -> dict[str, Any]:
    challenger_by_seed = {int(item.trace["episode_seed"]): item for item in challenger}
    greedy_by_seed = {int(item.trace["episode_seed"]): item for item in greedy}
    if set(challenger_by_seed) != set(greedy_by_seed):
        raise MainResearchExperimentError("paired policies do not share identical episode seeds")
    seeds = sorted(greedy_by_seed)
    mean_differences = np.asarray(
        [
            challenger_by_seed[seed].final_terminal.mean - greedy_by_seed[seed].final_terminal.mean
            for seed in seeds
        ],
        dtype=float,
    )
    cvar_differences = np.asarray(
        [
            challenger_by_seed[seed].final_terminal.cvar10 - greedy_by_seed[seed].final_terminal.cvar10
            for seed in seeds
        ],
        dtype=float,
    )
    greedy_mean = float(np.mean([greedy_by_seed[seed].final_terminal.mean for seed in seeds]))
    result = {
        "paired_seed_count": len(seeds),
        "mean_difference": _paired_interval(mean_differences, confidence_level),
        "cvar10_difference": _paired_interval(cvar_differences, confidence_level),
        "median_mean_difference": float(np.median(mean_differences)),
        "win_rate": float(np.mean(mean_differences > 0.0)),
        "tie_rate": float(np.mean(np.isclose(mean_differences, 0.0))),
        "relative_mean_gain": (
            float(mean_differences.mean() / abs(greedy_mean)) if greedy_mean != 0.0 else None
        ),
    }
    first_cohorts = greedy_by_seed[seeds[0]].final_terminal.cohort_ids
    if first_cohorts:
        cohorts = sorted(set(first_cohorts))
        by_cohort: dict[str, Any] = {}
        for cohort in cohorts:
            mean_rows = []
            cvar_rows = []
            greedy_rows = []
            for seed in seeds:
                challenger_terminal = challenger_by_seed[seed].final_terminal
                greedy_terminal = greedy_by_seed[seed].final_terminal
                if challenger_terminal.cohort_ids != greedy_terminal.cohort_ids:
                    raise MainResearchExperimentError(
                        "paired policies do not share roster-fold outcome alignment"
                    )
                mask = np.asarray(greedy_terminal.cohort_ids) == cohort
                challenger_values = challenger_terminal.outcomes[mask]
                greedy_values = greedy_terminal.outcomes[mask]
                mean_rows.append(float(challenger_values.mean() - greedy_values.mean()))
                cvar_rows.append(
                    lower_tail_cvar(challenger_values, 0.1) - lower_tail_cvar(greedy_values, 0.1)
                )
                greedy_rows.append(float(greedy_values.mean()))
            greedy_cohort_mean = float(np.mean(greedy_rows))
            by_cohort[str(cohort)] = {
                "paired_seed_count": len(seeds),
                "mean_difference": _paired_interval(np.asarray(mean_rows), confidence_level),
                "cvar10_difference": _paired_interval(np.asarray(cvar_rows), confidence_level),
                "relative_mean_gain": (
                    float(np.mean(mean_rows) / abs(greedy_cohort_mean)) if greedy_cohort_mean != 0.0 else None
                ),
            }
        result["by_roster_fold"] = by_cohort
    return result


def _build_policies(
    manifest: MainRollResearchManifest,
    rules: RollRuleSet,
    terminal: MainResearchTerminal,
    provider: MainRollProbabilityProvider,
):
    greedy = GreedyImmediatePolicy(
        rules,
        terminal,
        provider,
        manifest.strategies.greedy,
    )
    target = TargetSeekingPolicy(
        rules,
        terminal,
        provider,
        manifest.strategies.target,
        manifest.strategies.greedy,
    )
    hybrid = HorizonHybridPolicy(greedy, target, manifest.strategies.hybrid)
    return greedy, target, hybrid


def run_paired_experiment(
    manifest: MainRollResearchManifest,
    rules: RollRuleSet,
    terminal: MainResearchTerminal,
    state: MainRollState,
    *,
    source_version_id: str,
    mode: RunMode,
    smoke_count: int = 2,
    model_ids: tuple[str, ...] | None = None,
    roster_panel: ProjectedRosterPanel | None = None,
    worker_count: int = 1,
    parallel_worker_context: ParallelWorkerContext | None = None,
) -> ResearchExperimentResult:
    seeds = _seed_values(manifest, mode, smoke_count=smoke_count)
    selected_models = model_ids or tuple(model.model_id for model in manifest.probability_models)
    if len(selected_models) != len(set(selected_models)):
        raise MainResearchExperimentError("experiment probability models must be unique")
    for model_id in selected_models:
        manifest.probability_model(model_id)
    if mode == "tuning" and manifest.primary_probability_model not in selected_models:
        raise MainResearchExperimentError("tuning must include the frozen primary probability model")
    if mode == "confirmation" and set(selected_models) != {
        model.model_id for model in manifest.probability_models
    }:
        raise MainResearchExperimentError("confirmation must run every frozen probability sensitivity model")
    if worker_count < 1:
        raise MainResearchExperimentError("research worker count must be positive")
    if worker_count > 1 and parallel_worker_context is None:
        raise MainResearchExperimentError("parallel research requires a file-backed frozen worker context")

    simulator = MainRollResearchSimulator(
        manifest,
        rules,
        terminal,
        source_version=source_version_id,
    )
    episodes: list[EpisodeResult] = []
    grouped: dict[tuple[str, str], list[EpisodeResult]] = {}
    policy_order = tuple(
        specification.policy_id
        for specification in (
            manifest.strategies.greedy,
            manifest.strategies.target,
            manifest.strategies.hybrid,
        )
    )
    if worker_count == 1:
        for model_id in selected_models:
            provider = MainRollProbabilityProvider(rules, manifest.probability_model(model_id))
            policies = _build_policies(manifest, rules, terminal, provider)
            for seed in seeds:
                for policy in policies:
                    episode = simulator.run_episode(
                        state,
                        policy,
                        provider,
                        episode_seed=seed,
                    )
                    episodes.append(episode)
                    grouped.setdefault((model_id, policy.policy_id), []).append(episode)
    else:
        tasks = tuple((model_id, seed) for model_id in selected_models for seed in seeds)
        workers = min(worker_count, len(tasks))
        assert parallel_worker_context is not None
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_initialize_episode_worker_from_files,
            initargs=(*parallel_worker_context, source_version_id),
        ) as executor:
            batches = executor.map(_run_worker_episode_batch, tasks, chunksize=1)
            for (model_id, _), batch in zip(tasks, batches, strict=True):
                for episode in batch:
                    episodes.append(episode)
                    grouped.setdefault((model_id, episode.trace["policy_id"]), []).append(episode)

    confidence = manifest.release_gate.confidence_level
    model_reports: dict[str, Any] = {}
    for model_id in selected_models:
        greedy_episodes = grouped[(model_id, manifest.strategies.greedy.policy_id)]
        policies = {policy_id: _policy_summary(grouped[(model_id, policy_id)]) for policy_id in policy_order}
        comparisons = {
            policy_id: _paired_comparison(
                grouped[(model_id, policy_id)],
                greedy_episodes,
                confidence,
            )
            for policy_id in policy_order[1:]
        }
        model_reports[model_id] = {
            "policies": policies,
            "paired_vs_greedy": comparisons,
            "hybrid_vs_target": _paired_comparison(
                grouped[(model_id, manifest.strategies.hybrid.policy_id)],
                grouped[(model_id, manifest.strategies.target.policy_id)],
                confidence,
            ),
        }

    tuning_candidate_screen: dict[str, Any] = {}
    if mode == "tuning":
        tuning_values = manifest.splits.tuning.values
        validation_seeds = set(tuning_values[manifest.tuning_protocol.parameter_search_seed_count :])
        primary_id = manifest.primary_probability_model
        greedy_validation = [
            episode
            for episode in grouped[(primary_id, manifest.strategies.greedy.policy_id)]
            if int(episode.trace["episode_seed"]) in validation_seeds
        ]
        greedy_validation_summary = _policy_summary(greedy_validation)
        for policy_id in policy_order[1:]:
            challenger_validation = [
                episode
                for episode in grouped[(primary_id, policy_id)]
                if int(episode.trace["episode_seed"]) in validation_seeds
            ]
            comparison = _paired_comparison(
                challenger_validation,
                greedy_validation,
                confidence,
            )
            cvar_floor = -abs(greedy_validation_summary["terminal_cvar10"]["mean"]) * (
                manifest.tuning_protocol.cvar_noninferiority_fraction
            )
            checks = {
                "validation_mean_positive": (
                    comparison["mean_difference"]["mean"]
                    > manifest.tuning_protocol.minimum_validation_mean_difference
                ),
                "validation_cvar10_noninferior": (comparison["cvar10_difference"]["mean"] >= cvar_floor),
            }
            tuning_candidate_screen[policy_id] = {
                "status": "advance" if all(checks.values()) else "stop-for-futility",
                "parameter_search_seed_count": (manifest.tuning_protocol.parameter_search_seed_count),
                "candidate_validation_seed_count": len(validation_seeds),
                "candidate_validation_seed_range": {
                    "first": min(validation_seeds),
                    "last": max(validation_seeds),
                },
                "comparison_vs_greedy": comparison,
                "checks": checks,
                "cvar10_noninferiority_floor": cvar_floor,
            }

    sensitivity_complete = set(selected_models) == {model.model_id for model in manifest.probability_models}
    sensitivity: dict[str, Any] = {}
    for policy_id in policy_order[1:]:
        differences = {
            model_id: model_reports[model_id]["paired_vs_greedy"][policy_id]["mean_difference"]["mean"]
            for model_id in selected_models
        }
        signs = {0 if np.isclose(value, 0.0) else 1 if value > 0.0 else -1 for value in differences.values()}
        sensitivity[policy_id] = {
            "mean_difference_by_model": differences,
            "classification": (
                "stable-positive"
                if signs == {1}
                else "stable-nonnegative"
                if signs.issubset({0, 1}) and 1 in signs
                else "stable-nonpositive"
                if signs.issubset({-1, 0})
                else "model-dependent"
            ),
        }
    gates: dict[str, Any] = {}
    primary = model_reports.get(manifest.primary_probability_model)
    for policy_id in policy_order[1:]:
        if mode != "confirmation" or primary is None:
            gates[policy_id] = {
                "status": "not-evaluated",
                "reason": "Only a full confirmation run may evaluate the research gate.",
            }
            continue
        comparison = primary["paired_vs_greedy"][policy_id]
        greedy_summary = primary["policies"][manifest.strategies.greedy.policy_id]
        cvar_floor = -abs(greedy_summary["terminal_cvar10"]["mean"]) * (
            manifest.release_gate.cvar_noninferiority_fraction
        )
        fold_checks: dict[str, Any] = {}
        for fold_id, fold_comparison in comparison.get("by_roster_fold", {}).items():
            greedy_fold = greedy_summary.get("by_roster_fold", {}).get(fold_id, {})
            greedy_fold_mean = float(greedy_fold.get("terminal_mean", {}).get("mean", 0.0))
            greedy_fold_cvar = float(greedy_fold.get("terminal_cvar10", {}).get("mean", 0.0))
            mean_floor = -abs(greedy_fold_mean) * (manifest.release_gate.roster_fold_noninferiority_fraction)
            cvar_fold_floor = -abs(greedy_fold_cvar) * (
                manifest.release_gate.roster_fold_noninferiority_fraction
            )
            fold_checks[fold_id] = {
                "mean_noninferior": (
                    fold_comparison["mean_difference"]["one_sided_lower"] is not None
                    and fold_comparison["mean_difference"]["one_sided_lower"] >= mean_floor
                ),
                "cvar10_noninferior": (
                    fold_comparison["cvar10_difference"]["one_sided_lower"] is not None
                    and fold_comparison["cvar10_difference"]["one_sided_lower"] >= cvar_fold_floor
                ),
                "mean_floor": mean_floor,
                "cvar10_floor": cvar_fold_floor,
            }
        checks = {
            "primary_one_sided_mean_ci_above_zero": (
                comparison["mean_difference"]["one_sided_lower"] is not None
                and comparison["mean_difference"]["one_sided_lower"] > 0.0
            ),
            "minimum_relative_mean_gain": (
                comparison["relative_mean_gain"] is not None
                and comparison["relative_mean_gain"] >= manifest.release_gate.minimum_relative_mean_gain
            ),
            "cvar10_noninferiority": (
                comparison["cvar10_difference"]["one_sided_lower"] is not None
                and comparison["cvar10_difference"]["one_sided_lower"] >= cvar_floor
            ),
            "probability_sensitivity_report_complete": sensitivity_complete,
            "nonnegative_mean_in_every_probability_model": all(
                value >= -1e-12 for value in sensitivity[policy_id]["mean_difference_by_model"].values()
            ),
            "every_roster_fold_noninferior": bool(fold_checks)
            and all(
                all(row[key] for key in ("mean_noninferior", "cvar10_noninferior"))
                for row in fold_checks.values()
            ),
        }
        gates[policy_id] = {
            "status": "pass" if all(checks.values()) else "fail",
            "checks": checks,
            "roster_fold_checks": fold_checks,
            "automatic_web_promotion": False,
        }

    strategy_selection: dict[str, Any]
    if mode == "tuning":
        advancing = [
            policy_id for policy_id, row in tuning_candidate_screen.items() if row["status"] == "advance"
        ]
        strategy_selection = (
            {
                "status": "pending-confirmation",
                "selected_policy_id": None,
                "advancing_policy_ids": advancing,
                "reason": "At least one challenger passed the frozen tuning validation screen.",
            }
            if advancing
            else {
                "status": "tuning-futility-fallback",
                "selected_policy_id": manifest.strategies.greedy.policy_id,
                "advancing_policy_ids": [],
                "reason": (
                    "No challenger passed the independent tuning-validation screen; "
                    "confirmation is unnecessary for retaining the safety baseline."
                ),
            }
        )
    elif mode != "confirmation" or primary is None or not sensitivity_complete:
        strategy_selection = {
            "status": "not-evaluated",
            "selected_policy_id": None,
            "reason": "Only the complete held-out confirmation may select a Web candidate.",
        }
    else:
        target_id = manifest.strategies.target.policy_id
        hybrid_id = manifest.strategies.hybrid.policy_id
        target_pass = gates[target_id]["status"] == "pass"
        hybrid_pass = gates[hybrid_id]["status"] == "pass"
        if not target_pass and not hybrid_pass:
            strategy_selection = {
                "status": "fallback",
                "selected_policy_id": manifest.strategies.greedy.policy_id,
                "reason": "Neither challenger passed every frozen projected robustness gate.",
            }
        elif target_pass and not hybrid_pass:
            strategy_selection = {
                "status": "selected",
                "selected_policy_id": target_id,
                "reason": "Target passed and Hybrid did not pass the frozen gates.",
            }
        elif hybrid_pass and not target_pass:
            strategy_selection = {
                "status": "selected",
                "selected_policy_id": hybrid_id,
                "reason": "Hybrid passed and Target did not pass the frozen gates.",
            }
        else:
            direct = primary["hybrid_vs_target"]
            direct_sensitivity = {
                model_id: model_reports[model_id]["hybrid_vs_target"]["mean_difference"]["mean"]
                for model_id in selected_models
            }
            hybrid_material = (
                direct["mean_difference"]["one_sided_lower"] is not None
                and direct["mean_difference"]["one_sided_lower"] > 0.0
                and direct["relative_mean_gain"] is not None
                and direct["relative_mean_gain"] >= manifest.release_gate.direct_t_vs_h_minimum_relative_gain
                and all(value >= -1e-12 for value in direct_sensitivity.values())
            )
            strategy_selection = {
                "status": "selected",
                "selected_policy_id": hybrid_id if hybrid_material else target_id,
                "reason": (
                    "Hybrid materially exceeded Target under the frozen direct gate."
                    if hybrid_material
                    else "Both passed; the frozen complexity preference retains Target."
                ),
                "hybrid_vs_target": direct,
                "mean_difference_by_probability_model": direct_sensitivity,
            }

    body = {
        "schema_version": 2,
        "analysis_type": "main-roll-strategy-paired-experiment",
        "research_only": True,
        "web_integration": False,
        "automatic_web_promotion": False,
        "mode": mode,
        "gate_evaluation_eligible": mode == "confirmation" and sensitivity_complete,
        "release_eligible": False,
        "as_of": manifest.as_of,
        "source_version": source_version_id,
        "manifest_sha256": manifest.semantic_hash,
        "rule_snapshot_sha256": manifest.source.rule_snapshot_sha256,
        "main_release_sha256": manifest.source.main_release_sha256,
        "eligibility_mode": manifest.source.eligibility_mode,
        "terminal_objective": (
            "expected-roster-conditional-team-matching"
            if roster_panel is not None
            else "fixed-team-across-projected-scenarios"
        ),
        "projected_roster_panel_sha256": (roster_panel.semantic_hash if roster_panel is not None else None),
        "projected_roster_fold_ids": (
            sorted(set(int(value) for value in roster_panel.fold_ids)) if roster_panel is not None else []
        ),
        "starting_state_sha256": state_sha256(state),
        "remaining_rolls": state.remaining_rolls,
        "seed_count": len(seeds),
        "seed_range": {"first": seeds[0], "last": seeds[-1]},
        "execution_worker_count": worker_count,
        "probability_models": list(selected_models),
        "policy_order": list(policy_order),
        "model_reports": model_reports,
        "probability_sensitivity": sensitivity,
        "research_gates": gates,
        "tuning_candidate_screen": tuning_candidate_screen,
        "strategy_selection": strategy_selection,
        "limitations": [
            "Probability-model results are sensitivity evidence, not Valve backend rates.",
            "Projected and actual Main eligibility runs must be reported separately.",
            "A passing research gate never modifies or promotes the current Web advisor.",
        ],
    }
    report = {**body, "experiment_sha256": sha256_json(body)}
    return ResearchExperimentResult(
        report,
        tuple(episodes),
        None if roster_panel is None else roster_panel.payload(),
    )


def write_research_experiment_bundle(
    result: ResearchExperimentResult,
    manifest: MainRollResearchManifest,
    *,
    output_root: Path,
    allowed_root: Path,
) -> Path:
    selected_root = output_root.resolve()
    boundary = allowed_root.resolve()
    if not selected_root.is_relative_to(boundary):
        raise MainResearchExperimentError("research output must stay under the allowed artifact root")
    run_id = (
        manifest.as_of.replace("-", "").replace(":", "") + "-" + str(result.report["experiment_sha256"])[:12]
    )
    destination = selected_root / run_id
    report_bytes = canonical_json(result.report) + b"\n"
    manifest_bytes = canonical_json(manifest.model_dump(mode="json")) + b"\n"
    files: dict[Path, bytes] = {
        Path("manifest.json"): manifest_bytes,
        Path("report.json"): report_bytes,
    }
    checksums = {
        "manifest.json": sha256_bytes(manifest_bytes),
        "report.json": sha256_bytes(report_bytes),
    }
    if result.roster_panel is not None:
        panel_bytes = canonical_json(result.roster_panel) + b"\n"
        files[Path("projected-roster-panel.json")] = panel_bytes
        checksums["projected-roster-panel.json"] = sha256_bytes(panel_bytes)
    for episode in result.episodes:
        relative = Path(
            "episodes",
            str(episode.trace["probability_model"]),
            str(episode.trace["policy_id"]),
            f"{episode.trace['episode_seed']}.json",
        )
        content = canonical_json(episode.trace) + b"\n"
        files[relative] = content
        checksums[relative.as_posix()] = sha256_bytes(content)
    checksum_bytes = canonical_json(checksums) + b"\n"
    files[Path("checksums.json")] = checksum_bytes
    if destination.exists():
        existing_files = {path.relative_to(destination) for path in destination.rglob("*") if path.is_file()}
        if existing_files == set(files) and all(
            (destination / relative).read_bytes() == content for relative, content in files.items()
        ):
            return destination
        raise MainResearchExperimentError("research run directory already exists with other content")
    destination.mkdir(parents=True)
    for relative, content in files.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return destination


def _frozen_main_release_path(manifest: MainRollResearchManifest) -> Path:
    cutoff = manifest.as_of.replace("-", "").replace(":", "")
    selected = (
        PATHS.root
        / "deploy/runtime/releases"
        / f"main-roll-{cutoff}-{manifest.source.main_release_sha256[:12]}.json.zst"
    ).resolve()
    runtime_root = (PATHS.root / "deploy/runtime/releases").resolve()
    if not selected.is_relative_to(runtime_root):
        raise MainResearchExperimentError("frozen Main release escaped the runtime release directory")
    if not selected.is_file():
        raise MainResearchExperimentError("frozen Main research release is unavailable")
    if sha256_file(selected) != manifest.source.main_release_file_sha256:
        raise MainResearchExperimentError("frozen Main release file differs from the research manifest")
    return selected


def _validate_runtime_sources(manifest: MainRollResearchManifest) -> None:
    _frozen_main_release_path(manifest)
    snapshot_path = PATHS.root / "data/raw/rules" / manifest.source.rule_snapshot_id / "rule_snapshot.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MainResearchExperimentError("frozen client Rule snapshot is unavailable") from error
    if snapshot.get("snapshot_sha256") != manifest.source.rule_snapshot_sha256:
        raise MainResearchExperimentError("client Rule snapshot identity differs from the manifest")
    if snapshot.get("canonical_rules_sha256") != manifest.source.canonical_rules_sha256:
        raise MainResearchExperimentError("canonical Rule file differs from the client snapshot")
    if rules_hash(PATHS.rules) != manifest.source.canonical_rules_sha256:
        raise MainResearchExperimentError("current canonical Rule file differs from the manifest")


def load_frozen_main_research_context(group_context, manifest: MainRollResearchManifest):
    """Load the manifest-pinned projected release without consulting the production pointer."""

    _validate_runtime_sources(manifest)
    main_context = load_main_solver_release_context(
        group_context,
        path=_frozen_main_release_path(manifest),
        legacy_research_strategy_catalog=load_main_advice_strategy_catalog(
            PATHS.config / "models/fantasy-main-advice-strategies-v1.json"
        ),
    )
    if main_context.eligibility_mode != manifest.source.eligibility_mode:
        raise MainResearchExperimentError("frozen Main eligibility mode differs from the manifest")
    if main_context.as_of != manifest.as_of:
        raise MainResearchExperimentError("frozen Main cutoff differs from the manifest")
    if sha256_json(group_context.canonical_rules) != manifest.source.main_release_canonical_rules_sha256:
        raise MainResearchExperimentError("frozen Main release rules differ from the manifest")
    if sha256_json(asdict(main_context.roll_rules)) != manifest.source.roll_rules_sha256:
        raise MainResearchExperimentError("frozen Roll rules differ from the manifest")
    if group_context.scenarios.semantic_hash != manifest.source.group_scenario_sha256:
        raise MainResearchExperimentError("frozen Group Scenarios differ from the manifest")
    if group_context.scenarios.as_of != manifest.source.group_scenario_as_of:
        raise MainResearchExperimentError("frozen Group Scenario cutoff differs from the manifest")
    if main_context.terminal.scenario_set.semantic_hash != manifest.source.main_scenario_sha256:
        raise MainResearchExperimentError("frozen Main Scenarios differ from the manifest")
    if main_context.terminal.pool_result.semantic_hash != manifest.source.main_pool_sha256:
        raise MainResearchExperimentError("frozen Main Series pools differ from the manifest")
    if main_context.terminal.scenario_set.model_sha256 != manifest.source.team_strength_model_sha256:
        raise MainResearchExperimentError("frozen Main Team-strength model differs from the manifest")
    return main_context


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated Main Roll strategy research")
    parser.add_argument("--state", type=Path, required=True, help="confirmed five-slot Main state JSON")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PATHS.root / "config/research/fantasy-main-roll-simulator-v1.json",
    )
    parser.add_argument("--mode", choices=("smoke", "tuning", "confirmation"), default="smoke")
    parser.add_argument("--smoke-count", type=int, default=2)
    parser.add_argument(
        "--models",
        help="comma-separated model IDs; confirmation requires the complete frozen family",
    )
    parser.add_argument(
        "--smoke-roll-limit",
        type=int,
        help="smoke-only temporary horizon cap; the report remains release-ineligible",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PATHS.root / "artifacts/research/main-roll-simulator",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="isolated episode workers; deterministic results are merged in frozen task order",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    manifest = load_main_roll_research_manifest(arguments.manifest.resolve())
    group_context = load_solver_release_context()
    main_context = load_frozen_main_research_context(group_context, manifest)
    if sha256_json(group_context.canonical_rules) != manifest.source.main_release_canonical_rules_sha256:
        raise MainResearchExperimentError("loaded Main release rules differ from the manifest")
    if sha256_json(asdict(main_context.roll_rules)) != manifest.source.roll_rules_sha256:
        raise MainResearchExperimentError("loaded Roll rules differ from the manifest")
    if main_context.as_of != manifest.as_of:
        raise MainResearchExperimentError("loaded Main context cutoff differs from the manifest")
    frozen_main_scenarios = main_context.terminal.scenario_set
    frozen_pool = main_context.terminal.pool_result
    if group_context.scenarios.semantic_hash != manifest.source.group_scenario_sha256:
        raise MainResearchExperimentError("loaded Group Scenarios differ from the manifest")
    if group_context.scenarios.as_of != manifest.source.group_scenario_as_of:
        raise MainResearchExperimentError("loaded Group Scenario cutoff differs from the manifest")
    if frozen_main_scenarios.semantic_hash != manifest.source.main_scenario_sha256:
        raise MainResearchExperimentError("loaded Main Scenarios differ from the manifest")
    if frozen_pool.semantic_hash != manifest.source.main_pool_sha256:
        raise MainResearchExperimentError("loaded Main Series pools differ from the manifest")

    state_path = arguments.state.resolve()
    frozen_state_path = (PATHS.root / manifest.starting_state.relative_path).resolve()
    if arguments.mode != "smoke" and state_path != frozen_state_path:
        raise MainResearchExperimentError("frozen experiments require the manifest starting state")
    if state_path == frozen_state_path and sha256_file(state_path) != manifest.starting_state.file_sha256:
        raise MainResearchExperimentError("starting-state file differs from the manifest")
    state = state_from_payload(
        json.loads(state_path.read_text(encoding="utf-8")),
        main_context.roll_rules,
    )
    if state_path == frozen_state_path and state_sha256(state) != manifest.starting_state.state_sha256:
        raise MainResearchExperimentError("starting-state semantics differ from the manifest")
    if arguments.smoke_roll_limit is not None:
        if arguments.mode != "smoke":
            raise MainResearchExperimentError("smoke-roll-limit is valid only in smoke mode")
        if not 1 <= arguments.smoke_roll_limit <= state.remaining_rolls:
            raise MainResearchExperimentError("smoke-roll-limit is outside the observed Roll budget")
        state = replace(state, remaining_rolls=arguments.smoke_roll_limit)
    models = None
    if arguments.models:
        models = tuple(item.strip() for item in arguments.models.split(",") if item.strip())
    model, model_report = load_strength_model_as_of(as_of=manifest.as_of)
    blocking = [issue.message for issue in model_report.issues if issue.severity == "blocking"]
    if blocking:
        raise MainResearchExperimentError("frozen Team-strength model is blocked: " + "; ".join(blocking))
    if sha256_json(model.as_dict()) != manifest.source.team_strength_model_sha256:
        raise MainResearchExperimentError("loaded Team-strength model differs from the manifest")
    roster_spec = manifest.projected_roster_validation
    if arguments.mode == "smoke":
        selected_folds = (roster_spec.tuning_folds[0],)
        inner_count = min(roster_spec.convergence_inner_scenario_counts)
    elif arguments.mode == "tuning":
        selected_folds = roster_spec.tuning_folds
        inner_count = roster_spec.inner_scenarios_per_phase
    else:
        selected_folds = roster_spec.confirmation_folds
        inner_count = roster_spec.inner_scenarios_per_phase
    roster_panel = build_projected_roster_panel(
        frozen_pool,
        group_context.scenarios,
        frozen_main_scenarios,
        model,
        roster_spec,
        selected_fold_ids=selected_folds,
        inner_scenarios_per_phase=inner_count,
    )
    terminal = ProjectedRosterConditionalTerminal(
        VectorizedMainResearchTerminal(
            frozen_pool,
            roster_panel.scenarios,
            main_context.terminal.canonical_rules,
        ),
        roster_panel,
        cvar_alpha=manifest.strategies.greedy.cvar_alpha,
    )
    result = run_paired_experiment(
        manifest,
        main_context.roll_rules,
        terminal,
        state,
        source_version_id=source_version(),
        mode=arguments.mode,
        smoke_count=arguments.smoke_count,
        model_ids=models,
        roster_panel=roster_panel,
        worker_count=arguments.workers,
        parallel_worker_context=(
            str(arguments.manifest.resolve()),
            str(state_path),
            tuple(selected_folds),
            int(inner_count),
            state.remaining_rolls,
        ),
    )
    allowed_root = PATHS.root / "artifacts/research/main-roll-simulator"
    destination = write_research_experiment_bundle(
        result,
        manifest,
        output_root=arguments.output_root,
        allowed_root=allowed_root,
    )
    print(destination)
    print(json.dumps(result.report["research_gates"], ensure_ascii=False, sort_keys=True))
    print(json.dumps(result.report["strategy_selection"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MainResearchExperimentError",
    "ResearchExperimentResult",
    "run_paired_experiment",
    "write_research_experiment_bundle",
]
