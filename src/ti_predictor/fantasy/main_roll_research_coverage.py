"""Staged 1,000-state coverage experiments for isolated Main Roll research.

This module is deliberately absent from the shared CLI and all Web imports.  It reads
the frozen research release, writes only beneath the research artifact root, and never
promotes a strategy.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
from scipy import stats

from ti_predictor.fantasy.main_roll_research_contract import MainRollResearchManifest
from ti_predictor.fantasy.main_roll_research_experiment import (
    _build_policies,
    _validate_runtime_sources,
)
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_rosters import (
    ProjectedRosterConditionalTerminal,
    ProjectedRosterPanel,
    build_projected_roster_panel,
)
from ti_predictor.fantasy.main_roll_research_simulator import (
    MainResearchTerminal,
    MainRollResearchSimulator,
    state_sha256,
)
from ti_predictor.fantasy.main_roll_research_states import (
    MainStartingStateCoverageManifest,
    build_starting_state_records,
    episode_seed,
    generate_starting_state,
    load_base_research_manifest,
    load_starting_state_coverage_manifest,
    sensitivity_state_indices,
    starting_state_record,
    state_index_semantic_hash,
)
from ti_predictor.fantasy.main_roll_research_terminal import VectorizedMainResearchTerminal
from ti_predictor.fantasy.main_solver_release import load_main_solver_release_context
from ti_predictor.fantasy.roll import RollRuleSet
from ti_predictor.fantasy.solver_release import load_solver_release_context
from ti_predictor.fantasy.valuation import lower_tail_cvar
from ti_predictor.forecasting import load_strength_model_as_of
from ti_predictor.hashing import canonical_json, sha256_bytes, sha256_file, sha256_json
from ti_predictor.paths import PATHS
from ti_predictor.runs import source_version

CoverageStage = Literal[
    "smoke",
    "development-primary",
    "confirmation-primary",
    "confirmation-sensitivity",
]


class MainStartingStateCoverageExperimentError(ValueError):
    """A coverage run violates its frozen design or artifact boundary."""


@dataclass(frozen=True)
class CoverageTaskOutput:
    record: dict[str, Any]
    traces: tuple[tuple[str, dict[str, Any]], ...]


_COVERAGE_WORKER_CONTEXT: (
    tuple[
        MainStartingStateCoverageManifest,
        MainRollResearchManifest,
        RollRuleSet,
        MainResearchTerminal,
        str,
    ]
    | None
) = None


def _validate_loaded_release(
    manifest: MainRollResearchManifest,
):
    _validate_runtime_sources(manifest)
    group_context = load_solver_release_context()
    main_context = load_main_solver_release_context(group_context)
    if sha256_json(group_context.canonical_rules) != manifest.source.main_release_canonical_rules_sha256:
        raise MainStartingStateCoverageExperimentError(
            "loaded Main release rules differ from the base research manifest"
        )
    if sha256_json(asdict(main_context.roll_rules)) != manifest.source.roll_rules_sha256:
        raise MainStartingStateCoverageExperimentError(
            "loaded Roll rules differ from the base research manifest"
        )
    if main_context.as_of != manifest.as_of:
        raise MainStartingStateCoverageExperimentError(
            "loaded Main cutoff differs from the base research manifest"
        )
    if group_context.scenarios.semantic_hash != manifest.source.group_scenario_sha256:
        raise MainStartingStateCoverageExperimentError("loaded Group Scenarios differ")
    if group_context.scenarios.as_of != manifest.source.group_scenario_as_of:
        raise MainStartingStateCoverageExperimentError("loaded Group Scenario cutoff differs")
    if main_context.terminal.scenario_set.semantic_hash != manifest.source.main_scenario_sha256:
        raise MainStartingStateCoverageExperimentError("loaded Main Scenarios differ")
    if main_context.terminal.pool_result.semantic_hash != manifest.source.main_pool_sha256:
        raise MainStartingStateCoverageExperimentError("loaded Main Series pools differ")
    return group_context, main_context


def _build_frozen_terminal(
    manifest: MainRollResearchManifest,
    *,
    selected_folds: tuple[int, ...],
    inner_count: int,
) -> tuple[RollRuleSet, ProjectedRosterConditionalTerminal, ProjectedRosterPanel]:
    group_context, main_context = _validate_loaded_release(manifest)
    model, model_report = load_strength_model_as_of(as_of=manifest.as_of)
    blocking = [issue.message for issue in model_report.issues if issue.severity == "blocking"]
    if blocking:
        raise MainStartingStateCoverageExperimentError(
            "frozen Team-strength model is blocked: " + "; ".join(blocking)
        )
    if sha256_json(model.as_dict()) != manifest.source.team_strength_model_sha256:
        raise MainStartingStateCoverageExperimentError("frozen Team-strength model differs")
    panel = build_projected_roster_panel(
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
            panel.scenarios,
            main_context.terminal.canonical_rules,
        ),
        panel,
        cvar_alpha=manifest.strategies.greedy.cvar_alpha,
    )
    return main_context.roll_rules, terminal, panel


def _initialize_coverage_worker(
    coverage_manifest_path: str,
    selected_folds: tuple[int, ...],
    inner_count: int,
    source_version_id: str,
) -> None:
    global _COVERAGE_WORKER_CONTEXT
    coverage = load_starting_state_coverage_manifest(Path(coverage_manifest_path))
    _, manifest = load_base_research_manifest(coverage, repository_root=PATHS.root)
    rules, terminal, _ = _build_frozen_terminal(
        manifest,
        selected_folds=selected_folds,
        inner_count=inner_count,
    )
    _COVERAGE_WORKER_CONTEXT = (
        coverage,
        manifest,
        rules,
        terminal,
        source_version_id,
    )


def _fold_summary(evaluation) -> dict[str, dict[str, float]]:
    if not evaluation.cohort_ids:
        return {}
    cohort_ids = np.asarray(evaluation.cohort_ids)
    return {
        str(fold_id): {
            "mean": float(evaluation.outcomes[cohort_ids == fold_id].mean()),
            "cvar10": float(lower_tail_cvar(evaluation.outcomes[cohort_ids == fold_id], 0.1)),
        }
        for fold_id in sorted(set(int(value) for value in evaluation.cohort_ids))
    }


def run_coverage_task(
    coverage: MainStartingStateCoverageManifest,
    manifest: MainRollResearchManifest,
    rules: RollRuleSet,
    terminal: MainResearchTerminal,
    *,
    state_index: int,
    probability_model_id: str,
    source_version_id: str,
    remaining_rolls: int | None = None,
) -> CoverageTaskOutput:
    state = generate_starting_state(coverage, rules, state_index)
    if remaining_rolls is not None:
        if not 1 <= remaining_rolls <= state.remaining_rolls:
            raise MainStartingStateCoverageExperimentError("smoke Roll limit is invalid")
        state = replace(state, remaining_rolls=remaining_rolls)
    provider = MainRollProbabilityProvider(
        rules,
        manifest.probability_model(probability_model_id),
    )
    simulator = MainRollResearchSimulator(
        manifest,
        rules,
        terminal,
        source_version=source_version_id,
    )
    policies = _build_policies(manifest, rules, terminal, provider)
    seed = episode_seed(coverage, state_index, probability_model_id)
    episodes = tuple(simulator.run_episode(state, policy, provider, episode_seed=seed) for policy in policies)
    initial_hashes = {episode.initial_terminal.semantic_hash for episode in episodes}
    if len(initial_hashes) != 1:
        raise MainStartingStateCoverageExperimentError(
            "paired policies disagree about the initial terminal value"
        )
    traces: list[tuple[str, dict[str, Any]]] = []
    policy_rows: dict[str, Any] = {}
    for episode in episodes:
        trace_bytes = canonical_json(episode.trace) + b"\n"
        policy_id = str(episode.trace["policy_id"])
        traces.append((policy_id, episode.trace))
        policy_rows[policy_id] = {
            "final_terminal": episode.final_terminal.summary_payload(),
            "final_by_roster_fold": _fold_summary(episode.final_terminal),
            "spent_rolls": int(episode.trace["spent_rolls"]),
            "unspent_rolls": int(episode.trace["unspent_rolls"]),
            "stop_reason": str(episode.trace["stop_reason"]),
            "trace_sha256": str(episode.trace["trace_sha256"]),
            "trace_file_sha256": sha256_bytes(trace_bytes),
        }
    state_row = starting_state_record(coverage, rules, state_index)
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-starting-state-coverage-task",
        "research_only": True,
        "web_integration": False,
        "automatic_web_promotion": False,
        "as_of": coverage.as_of,
        "source_version": source_version_id,
        "coverage_manifest_sha256": coverage.semantic_hash,
        "base_research_manifest_sha256": manifest.semantic_hash,
        "main_release_sha256": manifest.source.main_release_sha256,
        "state_index": state_index,
        "split": coverage.split_for(state_index),
        "generated_state_sha256": state_row["state_sha256"],
        "state_sha256": state_sha256(state),
        "generator_key_sha256": state_row["generator_key_sha256"],
        "sensitivity_selected": state_row["sensitivity_selected"],
        "starting_state_strata": state_row["strata"],
        "remaining_rolls": state.remaining_rolls,
        "probability_model_id": probability_model_id,
        "episode_seed": seed,
        "paired_policy_ids": [policy.policy_id for policy in policies],
        "initial_terminal": episodes[0].initial_terminal.summary_payload(),
        "policies": policy_rows,
    }
    return CoverageTaskOutput(
        record={**body, "result_sha256": sha256_json(body)},
        traces=tuple(traces),
    )


def _run_coverage_worker_task(task: tuple[int, str, int | None]) -> CoverageTaskOutput:
    if _COVERAGE_WORKER_CONTEXT is None:
        raise MainStartingStateCoverageExperimentError("coverage worker was not initialized")
    coverage, manifest, rules, terminal, source_version_id = _COVERAGE_WORKER_CONTEXT
    state_index, probability_model_id, remaining_rolls = task
    try:
        return run_coverage_task(
            coverage,
            manifest,
            rules,
            terminal,
            state_index=state_index,
            probability_model_id=probability_model_id,
            source_version_id=source_version_id,
            remaining_rolls=remaining_rolls,
        )
    finally:
        clear = getattr(terminal, "clear_evaluation_cache", None)
        if clear is not None:
            clear()


def _paired_interval(values: np.ndarray, confidence_level: float) -> dict[str, float | None]:
    differences = np.asarray(values, dtype=float)
    mean = float(differences.mean())
    if len(differences) < 2 or np.isclose(differences.std(ddof=1), 0.0):
        return {
            "mean": mean,
            "two_sided_lower": mean if len(differences) >= 2 else None,
            "two_sided_upper": mean if len(differences) >= 2 else None,
            "one_sided_lower": mean if len(differences) >= 2 else None,
        }
    standard_error = float(differences.std(ddof=1) / math.sqrt(len(differences)))
    two_sided = float(stats.t.ppf((1.0 + confidence_level) / 2.0, len(differences) - 1))
    one_sided = float(stats.t.ppf(confidence_level, len(differences) - 1))
    return {
        "mean": mean,
        "two_sided_lower": mean - two_sided * standard_error,
        "two_sided_upper": mean + two_sided * standard_error,
        "one_sided_lower": mean - one_sided * standard_error,
    }


def _record_policy_value(record: dict[str, Any], policy_id: str, key: str) -> float:
    return float(record["policies"][policy_id]["final_terminal"][key])


def _assign_initial_value_quartiles(records: list[dict[str, Any]]) -> dict[int, str]:
    ranked = sorted(
        records,
        key=lambda row: (float(row["initial_terminal"]["mean"]), int(row["state_index"])),
    )
    total = len(ranked)
    return {
        int(record["state_index"]): f"q{min(4, (rank * 4) // total + 1)}"
        for rank, record in enumerate(ranked)
    }


def _comparison(
    records: list[dict[str, Any]],
    challenger_id: str,
    baseline_id: str,
    *,
    confidence_level: float,
    include_starting_strata: bool,
) -> dict[str, Any]:
    mean_differences = np.asarray(
        [
            _record_policy_value(record, challenger_id, "mean")
            - _record_policy_value(record, baseline_id, "mean")
            for record in records
        ],
        dtype=float,
    )
    cvar_differences = np.asarray(
        [
            _record_policy_value(record, challenger_id, "cvar10")
            - _record_policy_value(record, baseline_id, "cvar10")
            for record in records
        ],
        dtype=float,
    )
    baseline_mean = float(np.mean([_record_policy_value(record, baseline_id, "mean") for record in records]))
    result: dict[str, Any] = {
        "paired_state_count": len(records),
        "mean_difference": _paired_interval(mean_differences, confidence_level),
        "cvar10_difference": _paired_interval(cvar_differences, confidence_level),
        "median_mean_difference": float(np.median(mean_differences)),
        "win_rate": float(np.mean(mean_differences > 0.0)),
        "tie_rate": float(np.mean(np.isclose(mean_differences, 0.0))),
        "relative_mean_gain": (
            float(mean_differences.mean() / abs(baseline_mean)) if baseline_mean else None
        ),
        "baseline_terminal_mean": baseline_mean,
        "baseline_terminal_cvar10": float(
            np.mean([_record_policy_value(record, baseline_id, "cvar10") for record in records])
        ),
    }
    fold_ids = sorted(
        {
            int(fold_id)
            for record in records
            for fold_id in record["policies"][baseline_id]["final_by_roster_fold"]
        }
    )
    result["by_roster_fold"] = {}
    for fold_id in fold_ids:
        key = str(fold_id)
        fold_records = [
            record
            for record in records
            if key in record["policies"][baseline_id]["final_by_roster_fold"]
            and key in record["policies"][challenger_id]["final_by_roster_fold"]
        ]
        mean_diff = np.asarray(
            [
                float(record["policies"][challenger_id]["final_by_roster_fold"][key]["mean"])
                - float(record["policies"][baseline_id]["final_by_roster_fold"][key]["mean"])
                for record in fold_records
            ]
        )
        cvar_diff = np.asarray(
            [
                float(record["policies"][challenger_id]["final_by_roster_fold"][key]["cvar10"])
                - float(record["policies"][baseline_id]["final_by_roster_fold"][key]["cvar10"])
                for record in fold_records
            ]
        )
        result["by_roster_fold"][key] = {
            "paired_state_count": len(fold_records),
            "mean_difference": _paired_interval(mean_diff, confidence_level),
            "cvar10_difference": _paired_interval(cvar_diff, confidence_level),
            "baseline_terminal_mean": float(
                np.mean(
                    [
                        record["policies"][baseline_id]["final_by_roster_fold"][key]["mean"]
                        for record in fold_records
                    ]
                )
            ),
            "baseline_terminal_cvar10": float(
                np.mean(
                    [
                        record["policies"][baseline_id]["final_by_roster_fold"][key]["cvar10"]
                        for record in fold_records
                    ]
                )
            ),
        }
    if include_starting_strata:
        quartiles = _assign_initial_value_quartiles(records)
        dimensions: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for record in records:
            values = dict(record["starting_state_strata"])
            values["initial-terminal-value-rank-quartile"] = quartiles[int(record["state_index"])]
            for dimension, value in values.items():
                dimensions.setdefault(dimension, {}).setdefault(str(value), []).append(record)
        result["by_starting_state_stratum"] = {}
        for dimension, categories in sorted(dimensions.items()):
            result["by_starting_state_stratum"][dimension] = {}
            for category, subset in sorted(categories.items()):
                subset_mean_diff = np.asarray(
                    [
                        _record_policy_value(record, challenger_id, "mean")
                        - _record_policy_value(record, baseline_id, "mean")
                        for record in subset
                    ]
                )
                subset_cvar_diff = np.asarray(
                    [
                        _record_policy_value(record, challenger_id, "cvar10")
                        - _record_policy_value(record, baseline_id, "cvar10")
                        for record in subset
                    ]
                )
                result["by_starting_state_stratum"][dimension][category] = {
                    "paired_state_count": len(subset),
                    "mean_difference": _paired_interval(subset_mean_diff, confidence_level),
                    "cvar10_difference": _paired_interval(subset_cvar_diff, confidence_level),
                    "baseline_terminal_mean": float(
                        np.mean([_record_policy_value(record, baseline_id, "mean") for record in subset])
                    ),
                    "baseline_terminal_cvar10": float(
                        np.mean([_record_policy_value(record, baseline_id, "cvar10") for record in subset])
                    ),
                }
    return result


def analyze_coverage_records(
    records: list[dict[str, Any]],
    manifest: MainRollResearchManifest,
    *,
    include_starting_strata: bool,
) -> dict[str, Any]:
    if not records:
        raise MainStartingStateCoverageExperimentError("coverage analysis requires records")
    model_ids = tuple(dict.fromkeys(str(record["probability_model_id"]) for record in records))
    policy_ids = tuple(records[0]["paired_policy_ids"])
    model_reports: dict[str, Any] = {}
    for model_id in model_ids:
        selected = [record for record in records if record["probability_model_id"] == model_id]
        policy_summaries: dict[str, Any] = {}
        for policy_id in policy_ids:
            means = np.asarray([_record_policy_value(record, policy_id, "mean") for record in selected])
            cvars = np.asarray([_record_policy_value(record, policy_id, "cvar10") for record in selected])
            policy_summaries[policy_id] = {
                "state_count": len(selected),
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
                "spent_rolls_mean": float(
                    np.mean([record["policies"][policy_id]["spent_rolls"] for record in selected])
                ),
                "stop_reason_counts": dict(
                    sorted(
                        Counter(
                            str(record["policies"][policy_id]["stop_reason"]) for record in selected
                        ).items()
                    )
                ),
            }
        greedy_id, target_id, hybrid_id = policy_ids
        model_reports[model_id] = {
            "policies": policy_summaries,
            "paired_vs_greedy": {
                target_id: _comparison(
                    selected,
                    target_id,
                    greedy_id,
                    confidence_level=manifest.release_gate.confidence_level,
                    include_starting_strata=include_starting_strata,
                ),
                hybrid_id: _comparison(
                    selected,
                    hybrid_id,
                    greedy_id,
                    confidence_level=manifest.release_gate.confidence_level,
                    include_starting_strata=include_starting_strata,
                ),
            },
            "hybrid_vs_target": _comparison(
                selected,
                hybrid_id,
                target_id,
                confidence_level=manifest.release_gate.confidence_level,
                include_starting_strata=include_starting_strata,
            ),
        }
    return {
        "probability_model_ids": list(model_ids),
        "policy_ids": list(policy_ids),
        "model_reports": model_reports,
    }


def _artifact_run_id(coverage: MainStartingStateCoverageManifest) -> str:
    timestamp = coverage.as_of.replace("-", "").replace(":", "")
    return f"{timestamp}-{coverage.semantic_hash[:12]}"


def _resolve_artifact_root(
    coverage: MainStartingStateCoverageManifest,
    *,
    output_root: Path,
    allowed_root: Path,
) -> Path:
    selected = output_root.resolve()
    allowed = allowed_root.resolve()
    if not selected.is_relative_to(allowed):
        raise MainStartingStateCoverageExperimentError(
            "coverage output must stay under the allowed research artifact root"
        )
    return selected / _artifact_run_id(coverage)


def _write_exact_or_verify(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise MainStartingStateCoverageExperimentError(
                f"research artifact already exists with different content: {path}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        if temporary.read_bytes() != content:
            raise MainStartingStateCoverageExperimentError(f"partial research artifact differs: {temporary}")
    else:
        temporary.write_bytes(content)
    temporary.replace(path)


def prepare_coverage_bundle(
    coverage: MainStartingStateCoverageManifest,
    manifest: MainRollResearchManifest,
    rules: RollRuleSet,
    *,
    coverage_manifest_path: Path,
    artifact_root: Path,
) -> tuple[dict[str, Any], ...]:
    records = build_starting_state_records(coverage, rules)
    index_hash = state_index_semantic_hash(records)
    manifest_bytes = canonical_json(coverage.model_dump(mode="json")) + b"\n"
    base_manifest_bytes = canonical_json(manifest.model_dump(mode="json")) + b"\n"
    index_bytes = b"".join(canonical_json(record) + b"\n" for record in records)
    summary_body = {
        "schema_version": 1,
        "analysis_type": "main-roll-synthetic-starting-state-index",
        "research_only": True,
        "web_integration": False,
        "as_of": coverage.as_of,
        "interpretation": coverage.interpretation,
        "coverage_manifest_sha256": coverage.semantic_hash,
        "coverage_manifest_file_sha256": sha256_file(coverage_manifest_path),
        "base_research_manifest_sha256": manifest.semantic_hash,
        "state_count": len(records),
        "development_state_count": coverage.splits.development.count,
        "confirmation_state_count": coverage.splits.confirmation.count,
        "sensitivity_state_count": sum(bool(record["sensitivity_selected"]) for record in records),
        "unique_state_sha256_count": len({record["state_sha256"] for record in records}),
        "state_index_sha256": index_hash,
        "state_index_file_sha256": sha256_bytes(index_bytes),
        "generator": coverage.generator.model_dump(mode="json"),
        "stratum_counts": {
            dimension: dict(
                sorted(
                    Counter(
                        str(record["strata"][dimension])
                        for record in records
                        if record["split"] == "confirmation"
                    ).items()
                )
            )
            for dimension in records[0]["strata"]
        },
        "limitations": [
            "States are equally weighted legal coverage, not a model of real screen frequency.",
            "The client initial joint distribution is unknown and is not inferred here.",
            "Development states are pipeline-only and cannot alter frozen policy parameters.",
        ],
    }
    summary = {**summary_body, "index_summary_sha256": sha256_json(summary_body)}
    _write_exact_or_verify(artifact_root / "coverage-manifest.json", manifest_bytes)
    _write_exact_or_verify(artifact_root / "base-research-manifest.json", base_manifest_bytes)
    _write_exact_or_verify(artifact_root / "starting-states.jsonl", index_bytes)
    _write_exact_or_verify(
        artifact_root / "starting-state-index-summary.json",
        canonical_json(summary) + b"\n",
    )
    return records


def _stage_path(stage: CoverageStage, *, smoke_roll_limit: int | None = None) -> str:
    if stage != "smoke":
        return stage
    suffix = "full" if smoke_roll_limit is None else f"r{smoke_roll_limit}"
    return f"smoke-{suffix}"


def _task_paths(
    artifact_root: Path,
    stage_name: str,
    state_index: int,
    model_id: str,
) -> tuple[Path, dict[str, Path]]:
    stage_root = artifact_root / "stages" / stage_name
    result = stage_root / "results" / model_id / f"{state_index:04d}.json"
    return result, {
        policy_id: stage_root / "episodes" / model_id / policy_id / f"{state_index:04d}.json"
        for policy_id in (
            "main-greedy-immediate-v1",
            "main-target-shape-distance-v2",
            "main-horizon-hybrid-v2",
        )
    }


def _validate_task_record(record: dict[str, Any]) -> None:
    result_hash = record.get("result_sha256")
    body = {key: value for key, value in record.items() if key != "result_sha256"}
    if result_hash != sha256_json(body):
        raise MainStartingStateCoverageExperimentError("coverage task result SHA-256 differs")


def _load_completed_task(
    artifact_root: Path,
    stage_name: str,
    state_index: int,
    model_id: str,
    coverage: MainStartingStateCoverageManifest,
) -> dict[str, Any] | None:
    result_path, trace_paths = _task_paths(artifact_root, stage_name, state_index, model_id)
    if not result_path.exists():
        return None
    try:
        record = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MainStartingStateCoverageExperimentError(
            f"completed coverage task is unreadable: {result_path}"
        ) from error
    _validate_task_record(record)
    if record.get("coverage_manifest_sha256") != coverage.semantic_hash:
        raise MainStartingStateCoverageExperimentError("completed task uses another coverage manifest")
    if int(record.get("state_index", -1)) != state_index:
        raise MainStartingStateCoverageExperimentError("completed task state index differs")
    if record.get("probability_model_id") != model_id:
        raise MainStartingStateCoverageExperimentError("completed task probability model differs")
    for policy_id, policy_row in record["policies"].items():
        path = trace_paths.get(policy_id)
        if path is None or not path.is_file():
            raise MainStartingStateCoverageExperimentError(f"completed task is missing the {policy_id} trace")
        if sha256_file(path) != policy_row["trace_file_sha256"]:
            raise MainStartingStateCoverageExperimentError(f"completed task trace SHA-256 differs: {path}")
    return record


def _persist_task_output(
    artifact_root: Path,
    stage_name: str,
    output: CoverageTaskOutput,
) -> dict[str, Any]:
    record = output.record
    _validate_task_record(record)
    state_index = int(record["state_index"])
    model_id = str(record["probability_model_id"])
    result_path, trace_paths = _task_paths(artifact_root, stage_name, state_index, model_id)
    traces = dict(output.traces)
    if set(traces) != set(record["policies"]):
        raise MainStartingStateCoverageExperimentError("task traces do not match paired policies")
    for policy_id, trace in traces.items():
        trace_bytes = canonical_json(trace) + b"\n"
        if sha256_bytes(trace_bytes) != record["policies"][policy_id]["trace_file_sha256"]:
            raise MainStartingStateCoverageExperimentError("task trace file SHA-256 changed")
        _write_exact_or_verify(trace_paths[policy_id], trace_bytes)
    _write_exact_or_verify(result_path, canonical_json(record) + b"\n")
    return record


def _stage_tasks(
    coverage: MainStartingStateCoverageManifest,
    stage: CoverageStage,
    *,
    smoke_count: int,
    smoke_roll_limit: int | None,
) -> tuple[tuple[int, str, int | None], ...]:
    if stage == "smoke":
        if not 1 <= smoke_count <= coverage.splits.development.count:
            raise MainStartingStateCoverageExperimentError("smoke state count is invalid")
        indices = coverage.splits.development.values[:smoke_count]
        models = (coverage.primary_probability_model,)
        roll_limit = smoke_roll_limit
    elif stage == "development-primary":
        indices = coverage.splits.development.values
        models = (coverage.primary_probability_model,)
        roll_limit = None
    elif stage == "confirmation-primary":
        indices = coverage.splits.confirmation.values
        models = (coverage.primary_probability_model,)
        roll_limit = None
    else:
        indices = sensitivity_state_indices(coverage)
        models = tuple(
            model_id
            for model_id in coverage.sensitivity_panel.probability_model_ids
            if model_id != coverage.primary_probability_model
        )
        roll_limit = None
    return tuple((state_index, model_id, roll_limit) for model_id in models for state_index in indices)


def _stage_report(
    coverage: MainStartingStateCoverageManifest,
    manifest: MainRollResearchManifest,
    *,
    stage: CoverageStage,
    stage_name: str,
    records: list[dict[str, Any]],
    task_count: int,
    worker_count: int,
    selected_folds: tuple[int, ...],
    roster_panel_sha256: str,
    state_index_sha256: str,
) -> dict[str, Any]:
    source_versions = sorted({str(record["source_version"]) for record in records})
    analysis = analyze_coverage_records(
        records,
        manifest,
        include_starting_strata=stage in {"development-primary", "confirmation-primary"},
    )
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-starting-state-coverage-stage",
        "research_only": True,
        "web_integration": False,
        "release_eligible": False,
        "automatic_web_promotion": False,
        "stage": stage,
        "artifact_stage_name": stage_name,
        "complete": True,
        "as_of": coverage.as_of,
        "interpretation": coverage.interpretation,
        "coverage_manifest_sha256": coverage.semantic_hash,
        "base_research_manifest_sha256": manifest.semantic_hash,
        "main_release_sha256": manifest.source.main_release_sha256,
        "state_index_sha256": state_index_sha256,
        "projected_roster_panel_sha256": roster_panel_sha256,
        "projected_roster_fold_ids": list(selected_folds),
        "source_versions": source_versions,
        "execution_worker_count": worker_count,
        "task_count": task_count,
        "state_count": len({int(record["state_index"]) for record in records}),
        "probability_model_ids": analysis["probability_model_ids"],
        "policy_ids": analysis["policy_ids"],
        "model_reports": analysis["model_reports"],
        "coverage_gate_evaluated": False,
        "limitations": [
            "This stage is synthetic legal coverage, not a player-population expectation.",
            "Only the complete final report evaluates the frozen coverage gates.",
            "No result from this path modifies Web or runtime pointers.",
        ],
    }
    return {**body, "stage_report_sha256": sha256_json(body)}


def run_coverage_stage(
    coverage: MainStartingStateCoverageManifest,
    manifest: MainRollResearchManifest,
    *,
    coverage_manifest_path: Path,
    artifact_root: Path,
    stage: CoverageStage,
    worker_count: int,
    smoke_count: int = 2,
    smoke_roll_limit: int | None = 2,
) -> Path:
    if worker_count < 1:
        raise MainStartingStateCoverageExperimentError("coverage worker count must be positive")
    full_records = build_starting_state_records(
        coverage,
        _validate_loaded_release(manifest)[1].roll_rules,
    )
    state_index_hash = state_index_semantic_hash(full_records)
    stage_name = _stage_path(stage, smoke_roll_limit=smoke_roll_limit)
    tasks = _stage_tasks(
        coverage,
        stage,
        smoke_count=smoke_count,
        smoke_roll_limit=smoke_roll_limit,
    )
    completed: list[dict[str, Any]] = []
    pending: list[tuple[int, str, int | None]] = []
    for state_index, model_id, roll_limit in tasks:
        record = _load_completed_task(
            artifact_root,
            stage_name,
            state_index,
            model_id,
            coverage,
        )
        if record is None:
            pending.append((state_index, model_id, roll_limit))
        else:
            completed.append(record)
    roster_spec = manifest.projected_roster_validation
    if stage == "smoke":
        selected_folds = (roster_spec.confirmation_folds[0],)
        inner_count = min(roster_spec.convergence_inner_scenario_counts)
    else:
        selected_folds = roster_spec.confirmation_folds
        inner_count = roster_spec.inner_scenarios_per_phase
    current_source_version = source_version()
    print(
        f"coverage stage={stage_name} tasks={len(tasks)} resume={len(completed)} "
        f"pending={len(pending)} workers={min(worker_count, max(1, len(pending)))}",
        flush=True,
    )
    start = time.monotonic()
    if pending:
        workers = min(worker_count, len(pending))
        if workers == 1:
            _initialize_coverage_worker(
                str(coverage_manifest_path.resolve()),
                selected_folds,
                inner_count,
                current_source_version,
            )
            for task in pending:
                completed.append(
                    _persist_task_output(
                        artifact_root,
                        stage_name,
                        _run_coverage_worker_task(task),
                    )
                )
                elapsed = max(time.monotonic() - start, 1e-9)
                done = len(completed)
                print(
                    f"progress {done}/{len(tasks)} elapsed={elapsed:.1f}s rate={done / elapsed:.3f}/s",
                    flush=True,
                )
        else:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_initialize_coverage_worker,
                initargs=(
                    str(coverage_manifest_path.resolve()),
                    selected_folds,
                    inner_count,
                    current_source_version,
                ),
            ) as executor:
                futures = {executor.submit(_run_coverage_worker_task, task): task for task in pending}
                for future in as_completed(futures):
                    completed.append(
                        _persist_task_output(
                            artifact_root,
                            stage_name,
                            future.result(),
                        )
                    )
                    done = len(completed)
                    if done == len(tasks) or done % max(1, min(10, len(tasks) // 10)) == 0:
                        elapsed = max(time.monotonic() - start, 1e-9)
                        remaining = (len(tasks) - done) / (done / elapsed)
                        print(
                            f"progress {done}/{len(tasks)} elapsed={elapsed:.1f}s "
                            f"eta={remaining:.1f}s rate={done / elapsed:.3f}/s",
                            flush=True,
                        )
    completed.sort(key=lambda record: (str(record["probability_model_id"]), int(record["state_index"])))
    if len(completed) != len(tasks):
        raise MainStartingStateCoverageExperimentError("coverage stage task count is incomplete")
    _, _, panel = _build_frozen_terminal(
        manifest,
        selected_folds=selected_folds,
        inner_count=inner_count,
    )
    report = _stage_report(
        coverage,
        manifest,
        stage=stage,
        stage_name=stage_name,
        records=completed,
        task_count=len(tasks),
        worker_count=worker_count,
        selected_folds=selected_folds,
        roster_panel_sha256=panel.semantic_hash,
        state_index_sha256=state_index_hash,
    )
    report_path = artifact_root / "stages" / stage_name / "report.json"
    _write_exact_or_verify(report_path, canonical_json(report) + b"\n")
    print(f"stage report: {report_path}", flush=True)
    return report_path


def _load_stage_records(
    artifact_root: Path,
    stage_name: str,
    expected_tasks: tuple[tuple[int, str, int | None], ...],
    coverage: MainStartingStateCoverageManifest,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for state_index, model_id, _ in expected_tasks:
        record = _load_completed_task(
            artifact_root,
            stage_name,
            state_index,
            model_id,
            coverage,
        )
        if record is None:
            raise MainStartingStateCoverageExperimentError(
                f"required stage task is incomplete: {stage_name}/{model_id}/{state_index}"
            )
        records.append(record)
    return records


def _noninferiority_checks(
    comparison: dict[str, Any],
    *,
    fraction: float,
) -> dict[str, Any]:
    mean_floor = -abs(float(comparison["baseline_terminal_mean"])) * fraction
    cvar_floor = -abs(float(comparison["baseline_terminal_cvar10"])) * fraction
    mean_lower = comparison["mean_difference"]["one_sided_lower"]
    cvar_lower = comparison["cvar10_difference"]["one_sided_lower"]
    return {
        "mean_noninferior": mean_lower is not None and float(mean_lower) >= mean_floor,
        "cvar10_noninferior": cvar_lower is not None and float(cvar_lower) >= cvar_floor,
        "mean_floor": mean_floor,
        "cvar10_floor": cvar_floor,
    }


def _build_final_report(
    coverage: MainStartingStateCoverageManifest,
    manifest: MainRollResearchManifest,
    *,
    state_index_hash: str,
    primary_records: list[dict[str, Any]],
    sensitivity_records: list[dict[str, Any]],
) -> dict[str, Any]:
    sensitivity_indices = set(sensitivity_state_indices(coverage))
    primary_sensitivity = [
        record for record in primary_records if int(record["state_index"]) in sensitivity_indices
    ]
    all_sensitivity = primary_sensitivity + sensitivity_records
    primary_analysis = analyze_coverage_records(
        primary_records,
        manifest,
        include_starting_strata=True,
    )
    sensitivity_analysis = analyze_coverage_records(
        all_sensitivity,
        manifest,
        include_starting_strata=False,
    )
    primary_id = coverage.primary_probability_model
    primary_report = primary_analysis["model_reports"][primary_id]
    model_reports = sensitivity_analysis["model_reports"]
    policy_ids = tuple(primary_analysis["policy_ids"])
    greedy_id, target_id, hybrid_id = policy_ids
    gate = coverage.coverage_gate
    sensitivity_means: dict[str, dict[str, float]] = {}
    gates: dict[str, Any] = {}
    for policy_id in (target_id, hybrid_id):
        sensitivity_means[policy_id] = {
            model_id: float(model_reports[model_id]["paired_vs_greedy"][policy_id]["mean_difference"]["mean"])
            for model_id in coverage.sensitivity_panel.probability_model_ids
        }
        comparison = primary_report["paired_vs_greedy"][policy_id]
        cvar_floor = -abs(float(comparison["baseline_terminal_cvar10"])) * (gate.cvar_noninferiority_fraction)
        fold_checks = {
            fold_id: _noninferiority_checks(
                row,
                fraction=gate.stratum_noninferiority_fraction,
            )
            for fold_id, row in comparison["by_roster_fold"].items()
        }
        stratum_checks: dict[str, dict[str, Any]] = {}
        for dimension, categories in comparison["by_starting_state_stratum"].items():
            stratum_checks[dimension] = {}
            for category, row in categories.items():
                eligible = int(row["paired_state_count"]) >= gate.minimum_stratum_count
                checks = (
                    _noninferiority_checks(
                        row,
                        fraction=gate.stratum_noninferiority_fraction,
                    )
                    if eligible
                    else {
                        "mean_noninferior": None,
                        "cvar10_noninferior": None,
                        "mean_floor": None,
                        "cvar10_floor": None,
                    }
                )
                stratum_checks[dimension][category] = {
                    "paired_state_count": int(row["paired_state_count"]),
                    "eligible": eligible,
                    **checks,
                }
        eligible_strata = [
            row for categories in stratum_checks.values() for row in categories.values() if row["eligible"]
        ]
        checks = {
            "primary_one_sided_mean_ci_above_zero": (
                comparison["mean_difference"]["one_sided_lower"] is not None
                and comparison["mean_difference"]["one_sided_lower"] > 0.0
            ),
            "minimum_relative_mean_gain": (
                comparison["relative_mean_gain"] is not None
                and comparison["relative_mean_gain"] >= gate.minimum_relative_mean_gain
            ),
            "cvar10_noninferiority": (
                comparison["cvar10_difference"]["one_sided_lower"] is not None
                and comparison["cvar10_difference"]["one_sided_lower"] >= cvar_floor
            ),
            "nonnegative_mean_in_every_probability_model": all(
                value >= -1e-12 for value in sensitivity_means[policy_id].values()
            ),
            "every_roster_fold_noninferior": bool(fold_checks)
            and all(row["mean_noninferior"] and row["cvar10_noninferior"] for row in fold_checks.values()),
            "every_eligible_starting_state_stratum_noninferior": bool(eligible_strata)
            and all(row["mean_noninferior"] and row["cvar10_noninferior"] for row in eligible_strata),
        }
        gates[policy_id] = {
            "status": "pass" if all(checks.values()) else "fail",
            "checks": checks,
            "cvar10_noninferiority_floor": cvar_floor,
            "roster_fold_checks": fold_checks,
            "starting_state_stratum_checks": stratum_checks,
            "automatic_web_promotion": False,
        }

    target_pass = gates[target_id]["status"] == "pass"
    hybrid_pass = gates[hybrid_id]["status"] == "pass"
    if not target_pass and not hybrid_pass:
        selection = {
            "status": "fallback",
            "selected_policy_id": greedy_id,
            "reason": "Neither challenger passed every frozen 1,000-state coverage gate.",
        }
    elif target_pass and not hybrid_pass:
        selection = {
            "status": "selected-research-candidate",
            "selected_policy_id": target_id,
            "reason": "Target passed the frozen coverage gates and Hybrid did not.",
        }
    elif hybrid_pass and not target_pass:
        selection = {
            "status": "selected-research-candidate",
            "selected_policy_id": hybrid_id,
            "reason": "Hybrid passed the frozen coverage gates and Target did not.",
        }
    else:
        direct = primary_report["hybrid_vs_target"]
        direct_sensitivity = {
            model_id: float(model_reports[model_id]["hybrid_vs_target"]["mean_difference"]["mean"])
            for model_id in coverage.sensitivity_panel.probability_model_ids
        }
        hybrid_material = (
            direct["mean_difference"]["one_sided_lower"] is not None
            and direct["mean_difference"]["one_sided_lower"] > 0.0
            and direct["relative_mean_gain"] is not None
            and direct["relative_mean_gain"] >= gate.direct_t_vs_h_minimum_relative_gain
            and all(value >= -1e-12 for value in direct_sensitivity.values())
        )
        selection = {
            "status": "selected-research-candidate",
            "selected_policy_id": hybrid_id if hybrid_material else target_id,
            "reason": (
                "Hybrid materially exceeded Target under the frozen direct gate."
                if hybrid_material
                else "Both passed; the frozen complexity preference retains Target."
            ),
            "hybrid_vs_target": direct,
            "mean_difference_by_probability_model": direct_sensitivity,
        }
    source_versions = sorted(
        {str(record["source_version"]) for record in primary_records + sensitivity_records}
    )
    if len(source_versions) != 1:
        raise MainStartingStateCoverageExperimentError(
            "confirmation primary and sensitivity stages used different source versions"
        )
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-1000-starting-state-coverage",
        "research_only": True,
        "web_integration": False,
        "release_eligible": False,
        "automatic_web_promotion": False,
        "complete": True,
        "as_of": coverage.as_of,
        "interpretation": coverage.interpretation,
        "coverage_manifest_sha256": coverage.semantic_hash,
        "base_research_manifest_sha256": manifest.semantic_hash,
        "main_release_sha256": manifest.source.main_release_sha256,
        "eligibility_mode": manifest.source.eligibility_mode,
        "source_version": source_versions[0],
        "state_index_sha256": state_index_hash,
        "generated_state_count": 1_000,
        "development_state_count": coverage.splits.development.count,
        "confirmation_state_count": len(primary_records),
        "sensitivity_state_count": len(primary_sensitivity),
        "primary_task_count": len(primary_records),
        "additional_sensitivity_task_count": len(sensitivity_records),
        "paired_policy_ids": list(policy_ids),
        "primary_probability_model": primary_id,
        "primary_confirmation": primary_report,
        "sensitivity_panel": {
            "state_indices": sorted(sensitivity_indices),
            "probability_model_ids": list(coverage.sensitivity_panel.probability_model_ids),
            "model_reports": model_reports,
            "mean_difference_vs_greedy": sensitivity_means,
        },
        "coverage_gates": gates,
        "strategy_selection": selection,
        "limitations": [
            "Equal legal-state coverage does not estimate the frequency of real player screens.",
            "Roll probability models are sensitivity assumptions, not Valve backend rates.",
            "Projected-derived eight-Team rosters are Forecast scenarios, not actual entrants.",
            "The frozen G/T/H policies were not retuned on confirmation states.",
            "A selected research candidate still requires a separate production decision.",
        ],
    }
    return {**body, "final_report_sha256": sha256_json(body)}


def _write_integrity_manifest(artifact_root: Path) -> Path:
    path = artifact_root / "checksums.json"
    files = sorted(
        item
        for item in artifact_root.rglob("*")
        if item.is_file() and item != path and not item.name.endswith(".partial")
    )
    checksums = {item.relative_to(artifact_root).as_posix(): sha256_file(item) for item in files}
    _write_exact_or_verify(path, canonical_json(checksums) + b"\n")
    return path


def finalize_coverage_bundle(
    coverage: MainStartingStateCoverageManifest,
    manifest: MainRollResearchManifest,
    rules: RollRuleSet,
    *,
    artifact_root: Path,
) -> Path:
    state_records = build_starting_state_records(coverage, rules)
    index_hash = state_index_semantic_hash(state_records)
    primary_tasks = _stage_tasks(
        coverage,
        "confirmation-primary",
        smoke_count=2,
        smoke_roll_limit=None,
    )
    sensitivity_tasks = _stage_tasks(
        coverage,
        "confirmation-sensitivity",
        smoke_count=2,
        smoke_roll_limit=None,
    )
    primary_records = _load_stage_records(
        artifact_root,
        "confirmation-primary",
        primary_tasks,
        coverage,
    )
    sensitivity_records = _load_stage_records(
        artifact_root,
        "confirmation-sensitivity",
        sensitivity_tasks,
        coverage,
    )
    report = _build_final_report(
        coverage,
        manifest,
        state_index_hash=index_hash,
        primary_records=primary_records,
        sensitivity_records=sensitivity_records,
    )
    path = artifact_root / "final-report.json"
    _write_exact_or_verify(path, canonical_json(report) + b"\n")
    _write_integrity_manifest(artifact_root)
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run isolated Main Roll synthetic starting-state coverage research"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PATHS.root / "config/research/fantasy-main-starting-state-coverage-v1.json",
    )
    parser.add_argument(
        "--stage",
        choices=(
            "prepare",
            "smoke",
            "development-primary",
            "confirmation-primary",
            "confirmation-sensitivity",
            "finalize",
        ),
        required=True,
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--smoke-count", type=int, default=2)
    parser.add_argument("--smoke-roll-limit", type=int, default=2)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PATHS.root / "artifacts/research/main-roll-starting-state-coverage",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    coverage_path = arguments.manifest.resolve()
    coverage = load_starting_state_coverage_manifest(coverage_path)
    _, manifest = load_base_research_manifest(coverage, repository_root=PATHS.root)
    _, main_context = _validate_loaded_release(manifest)
    allowed_root = PATHS.root / "artifacts/research/main-roll-starting-state-coverage"
    artifact_root = _resolve_artifact_root(
        coverage,
        output_root=arguments.output_root,
        allowed_root=allowed_root,
    )
    records = prepare_coverage_bundle(
        coverage,
        manifest,
        main_context.roll_rules,
        coverage_manifest_path=coverage_path,
        artifact_root=artifact_root,
    )
    print(f"artifact root: {artifact_root}", flush=True)
    print(f"coverage manifest SHA-256: {coverage.semantic_hash}", flush=True)
    print(f"starting-state index SHA-256: {state_index_semantic_hash(records)}", flush=True)
    if arguments.stage == "prepare":
        return 0
    if arguments.stage == "finalize":
        path = finalize_coverage_bundle(
            coverage,
            manifest,
            main_context.roll_rules,
            artifact_root=artifact_root,
        )
        report = json.loads(path.read_text(encoding="utf-8"))
        print(f"final report: {path}", flush=True)
        print(json.dumps(report["coverage_gates"], ensure_ascii=False, sort_keys=True), flush=True)
        print(json.dumps(report["strategy_selection"], ensure_ascii=False, sort_keys=True), flush=True)
        return 0
    run_coverage_stage(
        coverage,
        manifest,
        coverage_manifest_path=coverage_path,
        artifact_root=artifact_root,
        stage=arguments.stage,
        worker_count=arguments.workers,
        smoke_count=arguments.smoke_count,
        smoke_roll_limit=(arguments.smoke_roll_limit if arguments.stage == "smoke" else None),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CoverageTaskOutput",
    "MainStartingStateCoverageExperimentError",
    "analyze_coverage_records",
    "finalize_coverage_bundle",
    "prepare_coverage_bundle",
    "run_coverage_stage",
    "run_coverage_task",
]
