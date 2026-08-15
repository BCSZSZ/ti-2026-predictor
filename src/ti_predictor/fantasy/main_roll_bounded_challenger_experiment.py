"""Staged, runtime-bounded comparison of research-only Main Roll challengers.

The module is intentionally absent from the shared CLI and every consumer runtime.  It
uses a fresh synthetic coverage suite, screens three fixed challengers on 100 cases,
confirms at most two on 900 disjoint cases, and writes only below its research artifact
root.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ti_predictor.fantasy.main_roll_bounded_challenger_contract import (
    MainRollBoundedChallengerManifest,
    load_main_roll_bounded_challenger_manifest,
)
from ti_predictor.fantasy.main_roll_bounded_challenger_strategies import (
    build_bounded_challenger_policy,
)
from ti_predictor.fantasy.main_roll_research_contract import MainRollResearchManifest
from ti_predictor.fantasy.main_roll_research_coverage import (
    _build_frozen_terminal,
    _comparison,
    _fold_summary,
    _noninferiority_checks,
    _validate_loaded_release,
)
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import (
    MainResearchTerminal,
    MainRollResearchSimulator,
    state_sha256,
)
from ti_predictor.fantasy.main_roll_research_states import (
    build_starting_state_records,
    episode_seed,
    generate_starting_state,
    load_base_research_manifest,
    load_starting_state_coverage_manifest,
    sensitivity_state_indices,
    starting_state_record,
    state_index_semantic_hash,
)
from ti_predictor.fantasy.roll import RollRuleSet
from ti_predictor.hashing import canonical_json, sha256_bytes, sha256_file, sha256_json
from ti_predictor.paths import PATHS
from ti_predictor.runs import source_version

ExecutionStage = Literal["smoke", "development", "confirmation", "sensitivity"]


class MainBoundedChallengerExperimentError(ValueError):
    """A bounded experiment violates its frozen design or artifact boundary."""


@dataclass(frozen=True)
class BoundedTaskOutput:
    record: dict[str, Any]
    traces: tuple[tuple[str, dict[str, Any]], ...]


_WORKER_CONTEXT: (
    tuple[
        MainRollBoundedChallengerManifest,
        MainRollResearchManifest,
        RollRuleSet,
        MainResearchTerminal,
        str,
    ]
    | None
) = None


def _load_base_manifest(
    manifest: MainRollBoundedChallengerManifest,
) -> MainRollResearchManifest:
    return load_base_research_manifest(  # type: ignore[arg-type]
        manifest,
        repository_root=PATHS.root,
    )[1]


def _artifact_run_id(manifest: MainRollBoundedChallengerManifest) -> str:
    compact = manifest.as_of.replace("-", "").replace(":", "").replace("Z", "Z")
    return f"{compact}-{manifest.semantic_hash[:12]}"


def _resolve_artifact_root(
    manifest: MainRollBoundedChallengerManifest,
    *,
    output_root: Path,
) -> Path:
    allowed = (PATHS.root / "artifacts/research/main-roll-bounded-challengers").resolve()
    requested = output_root.resolve()
    if requested != allowed:
        raise MainBoundedChallengerExperimentError(
            "bounded challengers may write only to their dedicated research artifact root"
        )
    return requested / _artifact_run_id(manifest)


def _write_exact_or_verify(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise MainBoundedChallengerExperimentError(
                f"existing immutable research artifact differs: {path}"
            )
        return
    path.write_bytes(content)


def _load_prior_coverage(
    manifest: MainRollBoundedChallengerManifest,
) -> Any:
    reference = manifest.prior_coverage_manifest
    path = (PATHS.root / reference.relative_path).resolve()
    if not path.is_relative_to(PATHS.root.resolve()):
        raise MainBoundedChallengerExperimentError("prior coverage path escaped the repository")
    if sha256_file(path) != reference.file_sha256:
        raise MainBoundedChallengerExperimentError("prior coverage file SHA-256 differs")
    prior = load_starting_state_coverage_manifest(path)
    if prior.semantic_hash != reference.semantic_sha256:
        raise MainBoundedChallengerExperimentError("prior coverage semantic SHA-256 differs")
    return prior


def _load_parent_experiment(
    manifest: MainRollBoundedChallengerManifest,
) -> MainRollBoundedChallengerManifest | None:
    reference = manifest.parent_bounded_challenger_manifest
    if reference is None:
        return None
    path = (PATHS.root / reference.relative_path).resolve()
    if not path.is_relative_to(PATHS.root.resolve()):
        raise MainBoundedChallengerExperimentError("parent experiment path escaped the repository")
    if sha256_file(path) != reference.file_sha256:
        raise MainBoundedChallengerExperimentError("parent experiment file SHA-256 differs")
    parent = load_main_roll_bounded_challenger_manifest(path)
    if parent.semantic_hash != reference.semantic_sha256:
        raise MainBoundedChallengerExperimentError("parent experiment semantic SHA-256 differs")
    return parent


def prepare_bundle(
    manifest: MainRollBoundedChallengerManifest,
    base: MainRollResearchManifest,
    rules: RollRuleSet,
    *,
    manifest_path: Path,
    artifact_root: Path,
) -> tuple[dict[str, Any], ...]:
    records = build_starting_state_records(manifest, rules)  # type: ignore[arg-type]
    prior = _load_prior_coverage(manifest)
    parent = _load_parent_experiment(manifest)
    prior_records = build_starting_state_records(prior, rules)
    current_hashes = {str(record["state_sha256"]) for record in records}
    prior_hashes = {str(record["state_sha256"]) for record in prior_records}
    overlap = current_hashes & prior_hashes
    if overlap:
        raise MainBoundedChallengerExperimentError(
            "new bounded-challenger states overlap the hypothesis-generating suite"
        )

    manifest_file_hash = sha256_file(manifest_path)
    base_path = PATHS.root / manifest.base_research_manifest.relative_path
    index_bytes = b"".join(canonical_json(record) + b"\n" for record in records)
    summary = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-state-index",
        "research_only": True,
        "web_integration": False,
        "runtime_pointer_writes": False,
        "as_of": manifest.as_of,
        "manifest_file_sha256": manifest_file_hash,
        "manifest_semantic_sha256": manifest.semantic_hash,
        "base_research_manifest_file_sha256": sha256_file(base_path),
        "base_research_manifest_semantic_sha256": base.semantic_hash,
        "prior_coverage_manifest_semantic_sha256": prior.semantic_hash,
        "state_count": len(records),
        "development_state_count": manifest.splits.development.count,
        "confirmation_state_count": manifest.splits.confirmation.count,
        "state_index_sha256": state_index_semantic_hash(records),
        "state_index_file_sha256": sha256_bytes(index_bytes),
        "prior_state_overlap_count": 0,
    }
    if parent is not None:
        summary["parent_bounded_challenger_manifest_semantic_sha256"] = parent.semantic_hash
        summary["revision_basis"] = manifest.revision_basis
        summary["roll_tape_namespace_semantic_sha256"] = manifest.roll_tape_namespace_semantic_sha256
    _write_exact_or_verify(
        artifact_root / "bounded-challenger-manifest.json",
        canonical_json(manifest.model_dump(mode="json", exclude_none=True)) + b"\n",
    )
    _write_exact_or_verify(
        artifact_root / "base-research-manifest.json",
        canonical_json(base.model_dump(mode="json")) + b"\n",
    )
    _write_exact_or_verify(artifact_root / "starting-states.jsonl", index_bytes)
    _write_exact_or_verify(
        artifact_root / "starting-state-index-summary.json",
        canonical_json(summary) + b"\n",
    )
    return records


def _initialize_worker(
    manifest_path: str,
    selected_folds: tuple[int, ...],
    inner_count: int,
    source_version_id: str,
) -> None:
    global _WORKER_CONTEXT
    manifest = load_main_roll_bounded_challenger_manifest(Path(manifest_path))
    base = _load_base_manifest(manifest)
    rules, terminal, _ = _build_frozen_terminal(
        base,
        selected_folds=selected_folds,
        inner_count=inner_count,
    )
    _WORKER_CONTEXT = manifest, base, rules, terminal, source_version_id


def _build_policy(
    policy_id: str,
    manifest: MainRollBoundedChallengerManifest,
    rules: RollRuleSet,
    terminal: MainResearchTerminal,
    provider: MainRollProbabilityProvider,
):
    strategies = manifest.strategies
    return build_bounded_challenger_policy(
        policy_id,
        rules=rules,
        terminal=terminal,
        provider=provider,
        baseline_specification=strategies.baseline,
        safe_band_specification=strategies.safe_band,
        local_tie_specification=strategies.local_tie,
        selective_two_step_specification=strategies.selective_two_step,
    )


def run_bounded_task(
    manifest: MainRollBoundedChallengerManifest,
    base: MainRollResearchManifest,
    rules: RollRuleSet,
    terminal: MainResearchTerminal,
    *,
    state_index: int,
    probability_model_id: str,
    policy_ids: tuple[str, ...],
    source_version_id: str,
    remaining_rolls: int | None = None,
) -> BoundedTaskOutput:
    state = generate_starting_state(manifest, rules, state_index)  # type: ignore[arg-type]
    if remaining_rolls is not None:
        if not 1 <= remaining_rolls <= state.remaining_rolls:
            raise MainBoundedChallengerExperimentError("smoke Roll limit is invalid")
        state = replace(state, remaining_rolls=remaining_rolls)
    seed = episode_seed(  # type: ignore[arg-type]
        manifest,
        state_index,
        probability_model_id,
        namespace_sha256=manifest.roll_tape_namespace_semantic_sha256,
    )
    episodes: list[Any] = []
    elapsed_by_policy: dict[str, float] = {}
    for policy_id in policy_ids:
        clear = getattr(terminal, "clear_evaluation_cache", None)
        if clear is not None:
            clear()
        provider = MainRollProbabilityProvider(
            rules,
            base.probability_model(probability_model_id),
        )
        policy = _build_policy(policy_id, manifest, rules, terminal, provider)
        simulator = MainRollResearchSimulator(
            base,
            rules,
            terminal,
            source_version=source_version_id,
        )
        started = time.perf_counter()
        episode = simulator.run_episode(state, policy, provider, episode_seed=seed)
        elapsed_by_policy[policy_id] = time.perf_counter() - started
        episodes.append(episode)

    if len({episode.initial_terminal.semantic_hash for episode in episodes}) != 1:
        raise MainBoundedChallengerExperimentError(
            "paired bounded policies disagree about initial terminal value"
        )

    traces: list[tuple[str, dict[str, Any]]] = []
    policy_rows: dict[str, Any] = {}
    for episode in episodes:
        policy_id = str(episode.trace["policy_id"])
        trace_bytes = canonical_json(episode.trace) + b"\n"
        modes = Counter(
            str(step["decision"]["diagnostics"].get("mode", "unknown")) for step in episode.trace["steps"]
        )
        traces.append((policy_id, episode.trace))
        policy_rows[policy_id] = {
            "final_terminal": episode.final_terminal.summary_payload(),
            "final_by_roster_fold": _fold_summary(episode.final_terminal),
            "spent_rolls": int(episode.trace["spent_rolls"]),
            "unspent_rolls": int(episode.trace["unspent_rolls"]),
            "stop_reason": str(episode.trace["stop_reason"]),
            "active_elapsed_seconds": elapsed_by_policy[policy_id],
            "decision_mode_counts": dict(sorted(modes.items())),
            "trace_sha256": str(episode.trace["trace_sha256"]),
            "trace_file_sha256": sha256_bytes(trace_bytes),
        }
    state_row = starting_state_record(manifest, rules, state_index)  # type: ignore[arg-type]
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-task",
        "research_only": True,
        "web_integration": False,
        "automatic_web_promotion": False,
        "as_of": manifest.as_of,
        "source_version": source_version_id,
        "bounded_manifest_sha256": manifest.semantic_hash,
        "base_research_manifest_sha256": base.semantic_hash,
        "main_release_sha256": base.source.main_release_sha256,
        "state_index": state_index,
        "split": manifest.split_for(state_index),
        "generated_state_sha256": state_row["state_sha256"],
        "state_sha256": state_sha256(state),
        "generator_key_sha256": state_row["generator_key_sha256"],
        "sensitivity_selected": state_row["sensitivity_selected"],
        "starting_state_strata": state_row["strata"],
        "remaining_rolls": state.remaining_rolls,
        "probability_model_id": probability_model_id,
        "episode_seed": seed,
        "roll_tape_namespace_semantic_sha256": (
            manifest.roll_tape_namespace_semantic_sha256 or manifest.semantic_hash
        ),
        "paired_policy_ids": list(policy_ids),
        "initial_terminal": episodes[0].initial_terminal.summary_payload(),
        "policies": policy_rows,
    }
    return BoundedTaskOutput(
        record={**body, "result_sha256": sha256_json(body)},
        traces=tuple(traces),
    )


def _run_worker_task(
    task: tuple[int, str, tuple[str, ...], int | None],
) -> BoundedTaskOutput:
    if _WORKER_CONTEXT is None:
        raise MainBoundedChallengerExperimentError("bounded worker was not initialized")
    manifest, base, rules, terminal, source_version_id = _WORKER_CONTEXT
    state_index, model_id, policy_ids, remaining_rolls = task
    try:
        return run_bounded_task(
            manifest,
            base,
            rules,
            terminal,
            state_index=state_index,
            probability_model_id=model_id,
            policy_ids=policy_ids,
            source_version_id=source_version_id,
            remaining_rolls=remaining_rolls,
        )
    finally:
        clear = getattr(terminal, "clear_evaluation_cache", None)
        if clear is not None:
            clear()


def _task_paths(
    artifact_root: Path,
    stage_name: str,
    state_index: int,
    model_id: str,
) -> tuple[Path, Path]:
    stem = f"state-{state_index:04d}__{model_id}"
    root = artifact_root / "stages" / stage_name
    return root / "results" / f"{stem}.json", root / "episodes" / stem


def _validate_task_record(
    record: dict[str, Any],
    manifest: MainRollBoundedChallengerManifest,
    *,
    state_index: int,
    model_id: str,
    policy_ids: tuple[str, ...],
    source_version_id: str,
) -> None:
    body = {key: value for key, value in record.items() if key != "result_sha256"}
    if sha256_json(body) != record.get("result_sha256"):
        raise MainBoundedChallengerExperimentError("bounded task result hash differs")
    expected = (
        record.get("bounded_manifest_sha256") == manifest.semantic_hash
        and int(record.get("state_index", -1)) == state_index
        and record.get("probability_model_id") == model_id
        and tuple(record.get("paired_policy_ids", ())) == policy_ids
        and record.get("source_version") == source_version_id
    )
    if not expected:
        raise MainBoundedChallengerExperimentError(
            "existing bounded task belongs to a different frozen execution"
        )


def _load_completed_task(
    artifact_root: Path,
    stage_name: str,
    state_index: int,
    model_id: str,
    manifest: MainRollBoundedChallengerManifest,
    policy_ids: tuple[str, ...],
    source_version_id: str,
) -> dict[str, Any] | None:
    result_path, episode_root = _task_paths(
        artifact_root,
        stage_name,
        state_index,
        model_id,
    )
    if not result_path.exists():
        return None
    record = json.loads(result_path.read_text(encoding="utf-8"))
    _validate_task_record(
        record,
        manifest,
        state_index=state_index,
        model_id=model_id,
        policy_ids=policy_ids,
        source_version_id=source_version_id,
    )
    for policy_id in policy_ids:
        trace_path = episode_root / f"{policy_id}.json"
        expected_hash = record["policies"][policy_id]["trace_file_sha256"]
        if not trace_path.exists() or sha256_file(trace_path) != expected_hash:
            raise MainBoundedChallengerExperimentError("bounded task trace is missing or has changed")
    return record


def _persist_task_output(
    artifact_root: Path,
    stage_name: str,
    output: BoundedTaskOutput,
) -> dict[str, Any]:
    record = output.record
    result_path, episode_root = _task_paths(
        artifact_root,
        stage_name,
        int(record["state_index"]),
        str(record["probability_model_id"]),
    )
    for policy_id, trace in output.traces:
        _write_exact_or_verify(
            episode_root / f"{policy_id}.json",
            canonical_json(trace) + b"\n",
        )
    _write_exact_or_verify(result_path, canonical_json(record) + b"\n")
    return record


def _policy_summary(records: list[dict[str, Any]], policy_id: str) -> dict[str, Any]:
    means = np.asarray(
        [record["policies"][policy_id]["final_terminal"]["mean"] for record in records],
        dtype=float,
    )
    cvars = np.asarray(
        [record["policies"][policy_id]["final_terminal"]["cvar10"] for record in records],
        dtype=float,
    )
    elapsed = np.asarray(
        [record["policies"][policy_id]["active_elapsed_seconds"] for record in records],
        dtype=float,
    )
    modes = Counter(
        {
            mode: sum(
                int(record["policies"][policy_id]["decision_mode_counts"].get(mode, 0)) for record in records
            )
            for mode in {
                str(mode)
                for record in records
                for mode in record["policies"][policy_id]["decision_mode_counts"]
            }
        }
    )
    return {
        "state_count": len(records),
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
            np.mean([record["policies"][policy_id]["spent_rolls"] for record in records])
        ),
        "active_elapsed_seconds": {
            "total": float(elapsed.sum()),
            "mean": float(elapsed.mean()),
            "maximum": float(elapsed.max()),
        },
        "decision_mode_counts": dict(sorted(modes.items())),
        "stop_reason_counts": dict(
            sorted(Counter(str(record["policies"][policy_id]["stop_reason"]) for record in records).items())
        ),
    }


def analyze_bounded_records(
    records: list[dict[str, Any]],
    manifest: MainRollBoundedChallengerManifest,
    *,
    include_starting_strata: bool,
) -> dict[str, Any]:
    if not records:
        raise MainBoundedChallengerExperimentError("bounded analysis requires records")
    policy_ids = tuple(records[0]["paired_policy_ids"])
    baseline_id = manifest.strategies.baseline.policy_id
    if not policy_ids or policy_ids[0] != baseline_id:
        raise MainBoundedChallengerExperimentError(
            "bounded analysis requires Greedy as the first paired policy"
        )
    model_ids = tuple(dict.fromkeys(str(row["probability_model_id"]) for row in records))
    reports: dict[str, Any] = {}
    for model_id in model_ids:
        selected = [row for row in records if row["probability_model_id"] == model_id]
        summaries = {policy_id: _policy_summary(selected, policy_id) for policy_id in policy_ids}
        reports[model_id] = {
            "policies": summaries,
            "paired_vs_baseline": {
                policy_id: _comparison(
                    selected,
                    policy_id,
                    baseline_id,
                    confidence_level=manifest.confirmation_gate.confidence_level,
                    include_starting_strata=include_starting_strata,
                )
                for policy_id in policy_ids[1:]
            },
        }
    return {
        "probability_model_ids": list(model_ids),
        "policy_ids": list(policy_ids),
        "model_reports": reports,
    }


def _stage_name(stage: ExecutionStage, candidate_id: str | None, roll_limit: int | None) -> str:
    if stage == "smoke":
        return f"smoke-rolls-{roll_limit}"
    if stage in {"confirmation", "sensitivity"}:
        if candidate_id is None:
            raise MainBoundedChallengerExperimentError(f"{stage} requires a candidate")
        return f"{stage}__{candidate_id}"
    return "development-primary"


def _stage_tasks(
    manifest: MainRollBoundedChallengerManifest,
    stage: ExecutionStage,
    *,
    policy_ids: tuple[str, ...],
    smoke_count: int,
    smoke_roll_limit: int | None,
) -> tuple[tuple[int, str, tuple[str, ...], int | None], ...]:
    if stage == "smoke":
        indices = manifest.splits.development.values[:smoke_count]
        models = (manifest.primary_probability_model,)
        roll_limit = smoke_roll_limit
    elif stage == "development":
        indices = manifest.splits.development.values
        models = (manifest.primary_probability_model,)
        roll_limit = None
    elif stage == "confirmation":
        indices = manifest.splits.confirmation.values
        models = (manifest.primary_probability_model,)
        roll_limit = None
    else:
        indices = sensitivity_state_indices(manifest)  # type: ignore[arg-type]
        models = tuple(
            model_id
            for model_id in manifest.sensitivity_panel.probability_model_ids
            if model_id != manifest.primary_probability_model
        )
        roll_limit = None
    return tuple((index, model_id, policy_ids, roll_limit) for model_id in models for index in indices)


def _stage_report(
    manifest: MainRollBoundedChallengerManifest,
    base: MainRollResearchManifest,
    *,
    stage: ExecutionStage,
    stage_name: str,
    records: list[dict[str, Any]],
    worker_count: int,
    wall_seconds: float,
    selected_folds: tuple[int, ...],
    panel_sha256: str,
    state_index_sha256: str,
) -> dict[str, Any]:
    analysis = analyze_bounded_records(
        records,
        manifest,
        include_starting_strata=stage in {"development", "confirmation"},
    )
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-stage",
        "research_only": True,
        "web_integration": False,
        "release_eligible": False,
        "automatic_web_promotion": False,
        "stage": stage,
        "artifact_stage_name": stage_name,
        "complete": True,
        "as_of": manifest.as_of,
        "interpretation": manifest.interpretation,
        "bounded_manifest_sha256": manifest.semantic_hash,
        "base_research_manifest_sha256": base.semantic_hash,
        "main_release_sha256": base.source.main_release_sha256,
        "state_index_sha256": state_index_sha256,
        "projected_roster_panel_sha256": panel_sha256,
        "projected_roster_fold_ids": list(selected_folds),
        "source_versions": sorted({str(record["source_version"]) for record in records}),
        "execution_worker_count": worker_count,
        "stage_wall_seconds": wall_seconds,
        "task_count": len(records),
        "state_count": len({int(record["state_index"]) for record in records}),
        "probability_model_ids": analysis["probability_model_ids"],
        "policy_ids": analysis["policy_ids"],
        "model_reports": analysis["model_reports"],
        "limitations": [
            "Synthetic legal coverage is not a player-population expectation.",
            "Measured elapsed time is machine- and load-specific runtime evidence.",
            "No result from this path modifies Web, OCR, advisors, or runtime pointers.",
        ],
    }
    return {**body, "stage_report_sha256": sha256_json(body)}


def run_stage(
    manifest: MainRollBoundedChallengerManifest,
    base: MainRollResearchManifest,
    *,
    manifest_path: Path,
    artifact_root: Path,
    stage: ExecutionStage,
    policy_ids: tuple[str, ...],
    worker_count: int,
    candidate_id: str | None = None,
    smoke_count: int = 2,
    smoke_roll_limit: int | None = 2,
) -> Path:
    if worker_count < 1:
        raise MainBoundedChallengerExperimentError("worker count must be positive")
    if stage != "smoke" and worker_count != manifest.runtime_gate.reference_worker_count:
        raise MainBoundedChallengerExperimentError(
            "runtime-gated stages require the frozen eight-worker reference"
        )
    current_source_version = source_version()
    state_records = build_starting_state_records(manifest, _validate_loaded_release(base)[1].roll_rules)  # type: ignore[arg-type]
    index_hash = state_index_semantic_hash(state_records)
    stage_name = _stage_name(stage, candidate_id, smoke_roll_limit)
    tasks = _stage_tasks(
        manifest,
        stage,
        policy_ids=policy_ids,
        smoke_count=smoke_count,
        smoke_roll_limit=smoke_roll_limit,
    )
    completed: list[dict[str, Any]] = []
    pending: list[tuple[int, str, tuple[str, ...], int | None]] = []
    for state_index, model_id, ids, roll_limit in tasks:
        record = _load_completed_task(
            artifact_root,
            stage_name,
            state_index,
            model_id,
            manifest,
            ids,
            current_source_version,
        )
        if record is None:
            pending.append((state_index, model_id, ids, roll_limit))
        else:
            completed.append(record)

    existing_report = artifact_root / "stages" / stage_name / "report.json"
    if not pending and existing_report.exists():
        _read_stage_report(artifact_root, stage_name)
        print(f"stage already complete: {existing_report}", flush=True)
        return existing_report

    roster = base.projected_roster_validation
    if stage == "smoke":
        selected_folds = (roster.confirmation_folds[0],)
        inner_count = min(roster.convergence_inner_scenario_counts)
    else:
        selected_folds = roster.confirmation_folds
        inner_count = roster.inner_scenarios_per_phase
    print(
        f"bounded stage={stage_name} tasks={len(tasks)} resume={len(completed)} "
        f"pending={len(pending)} workers={min(worker_count, max(1, len(pending)))}",
        flush=True,
    )
    started = time.monotonic()
    if pending:
        workers = min(worker_count, len(pending))
        if workers == 1:
            _initialize_worker(
                str(manifest_path.resolve()),
                selected_folds,
                inner_count,
                current_source_version,
            )
            for task in pending:
                completed.append(
                    _persist_task_output(
                        artifact_root,
                        stage_name,
                        _run_worker_task(task),
                    )
                )
        else:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_initialize_worker,
                initargs=(
                    str(manifest_path.resolve()),
                    selected_folds,
                    inner_count,
                    current_source_version,
                ),
            ) as executor:
                futures = {executor.submit(_run_worker_task, task): task for task in pending}
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
                        elapsed = max(time.monotonic() - started, 1e-9)
                        remaining = (len(tasks) - done) / (done / elapsed)
                        print(
                            f"progress {done}/{len(tasks)} elapsed={elapsed:.1f}s "
                            f"eta={remaining:.1f}s rate={done / elapsed:.3f}/s",
                            flush=True,
                        )
    wall_seconds = time.monotonic() - started
    completed.sort(key=lambda row: (str(row["probability_model_id"]), int(row["state_index"])))
    if len(completed) != len(tasks):
        raise MainBoundedChallengerExperimentError("bounded stage task count is incomplete")
    _, _, panel = _build_frozen_terminal(
        base,
        selected_folds=selected_folds,
        inner_count=inner_count,
    )
    report = _stage_report(
        manifest,
        base,
        stage=stage,
        stage_name=stage_name,
        records=completed,
        worker_count=worker_count,
        wall_seconds=wall_seconds,
        selected_folds=selected_folds,
        panel_sha256=panel.semantic_hash,
        state_index_sha256=index_hash,
    )
    report_path = artifact_root / "stages" / stage_name / "report.json"
    _write_exact_or_verify(report_path, canonical_json(report) + b"\n")
    print(f"stage report: {report_path}", flush=True)
    return report_path


def _read_stage_report(artifact_root: Path, stage_name: str) -> dict[str, Any]:
    path = artifact_root / "stages" / stage_name / "report.json"
    if not path.exists():
        raise MainBoundedChallengerExperimentError(f"required stage is missing: {stage_name}")
    report = json.loads(path.read_text(encoding="utf-8"))
    body = {key: value for key, value in report.items() if key != "stage_report_sha256"}
    if sha256_json(body) != report.get("stage_report_sha256"):
        raise MainBoundedChallengerExperimentError(f"stage report hash differs: {stage_name}")
    return report


def screen_development(
    manifest: MainRollBoundedChallengerManifest,
    *,
    artifact_root: Path,
) -> Path:
    report = _read_stage_report(artifact_root, "development-primary")
    primary = report["model_reports"][manifest.primary_probability_model]
    baseline_id = manifest.strategies.baseline.policy_id
    baseline_cvar = float(primary["policies"][baseline_id]["terminal_cvar10"]["mean"])
    scale = manifest.splits.confirmation.count / manifest.splits.development.count
    workers = manifest.runtime_gate.reference_worker_count
    complexity = {policy_id: rank for rank, policy_id in enumerate(manifest.strategies.candidate_policy_ids)}
    rows: dict[str, Any] = {}
    eligible_ids: list[str] = []
    for policy_id in manifest.strategies.candidate_policy_ids:
        comparison = primary["paired_vs_baseline"][policy_id]
        active = float(primary["policies"][policy_id]["active_elapsed_seconds"]["total"])
        projected = active * scale / workers
        mean_difference = float(comparison["mean_difference"]["mean"])
        cvar_difference = float(comparison["cvar10_difference"]["mean"])
        relative = float(comparison["relative_mean_gain"] or 0.0)
        within_max = projected <= (manifest.runtime_gate.maximum_confirmation_seconds_per_candidate)
        within_ideal = projected <= (manifest.runtime_gate.ideal_confirmation_seconds_per_candidate)
        runtime_eligible = within_ideal or (
            within_max and relative >= manifest.runtime_gate.conditional_runtime_minimum_relative_gain
        )
        checks = {
            "positive_development_mean": mean_difference
            > manifest.runtime_gate.minimum_development_mean_difference,
            "development_cvar_noninferior": cvar_difference
            >= -abs(baseline_cvar) * manifest.runtime_gate.cvar_noninferiority_fraction,
            "projected_runtime_within_two_hours": within_max,
            "runtime_advancement_rule": runtime_eligible,
        }
        eligible = all(checks.values())
        rows[policy_id] = {
            "eligible": eligible,
            "checks": checks,
            "mean_difference": mean_difference,
            "cvar10_difference": cvar_difference,
            "relative_mean_gain": relative,
            "development_active_seconds_total": active,
            "projected_confirmation_seconds": projected,
            "runtime_class": "ideal" if within_ideal else "conditional" if within_max else "reject",
            "frozen_complexity_rank": complexity[policy_id],
        }
        if eligible:
            eligible_ids.append(policy_id)
    advanced = sorted(
        eligible_ids,
        key=lambda policy_id: (
            -rows[policy_id]["mean_difference"],
            -rows[policy_id]["cvar10_difference"],
            rows[policy_id]["frozen_complexity_rank"],
        ),
    )[: manifest.runtime_gate.advancement_limit]
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-development-screen",
        "research_only": True,
        "web_integration": False,
        "automatic_web_promotion": False,
        "bounded_manifest_sha256": manifest.semantic_hash,
        "development_stage_report_sha256": report["stage_report_sha256"],
        "baseline_policy_id": baseline_id,
        "candidate_rows": rows,
        "advanced_policy_ids": advanced,
        "advancement_limit": manifest.runtime_gate.advancement_limit,
        "confirmation_data_seen": False,
    }
    payload = {**body, "screen_sha256": sha256_json(body)}
    path = artifact_root / "development-screen.json"
    _write_exact_or_verify(path, canonical_json(payload) + b"\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    return path


def _read_screen(
    manifest: MainRollBoundedChallengerManifest,
    artifact_root: Path,
) -> dict[str, Any]:
    path = artifact_root / "development-screen.json"
    if not path.exists():
        raise MainBoundedChallengerExperimentError("development screen has not been frozen")
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = {key: value for key, value in payload.items() if key != "screen_sha256"}
    if (
        sha256_json(body) != payload.get("screen_sha256")
        or payload.get("bounded_manifest_sha256") != manifest.semantic_hash
    ):
        raise MainBoundedChallengerExperimentError("development screen hash differs")
    return payload


def _primary_gate(
    comparison: dict[str, Any],
    manifest: MainRollBoundedChallengerManifest,
    *,
    candidate_active_wall_seconds: float,
) -> dict[str, Any]:
    gate = manifest.confirmation_gate
    cvar_floor = -abs(float(comparison["baseline_terminal_cvar10"])) * (gate.cvar_noninferiority_fraction)
    fold_checks = {
        fold_id: _noninferiority_checks(
            row,
            fraction=gate.stratum_noninferiority_fraction,
        )
        for fold_id, row in comparison["by_roster_fold"].items()
    }
    stratum_checks: dict[str, dict[str, Any]] = {}
    eligible_strata: list[dict[str, Any]] = []
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
            result = {"paired_state_count": int(row["paired_state_count"]), "eligible": eligible, **checks}
            stratum_checks[dimension][category] = result
            if eligible:
                eligible_strata.append(result)
    checks = {
        "primary_one_sided_mean_ci_above_zero": comparison["mean_difference"]["one_sided_lower"] is not None
        and float(comparison["mean_difference"]["one_sided_lower"]) > 0.0,
        "minimum_relative_mean_gain": comparison["relative_mean_gain"] is not None
        and float(comparison["relative_mean_gain"]) >= gate.minimum_relative_mean_gain,
        "cvar10_noninferiority": comparison["cvar10_difference"]["one_sided_lower"] is not None
        and float(comparison["cvar10_difference"]["one_sided_lower"]) >= cvar_floor,
        "every_roster_fold_noninferior": bool(fold_checks)
        and all(row["mean_noninferior"] and row["cvar10_noninferior"] for row in fold_checks.values()),
        "every_eligible_starting_state_stratum_noninferior": bool(eligible_strata)
        and all(row["mean_noninferior"] and row["cvar10_noninferior"] for row in eligible_strata),
        "candidate_runtime_within_two_hours": candidate_active_wall_seconds
        <= manifest.runtime_gate.maximum_confirmation_seconds_per_candidate,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "cvar10_noninferiority_floor": cvar_floor,
        "candidate_active_wall_seconds": candidate_active_wall_seconds,
        "roster_fold_checks": fold_checks,
        "starting_state_stratum_checks": stratum_checks,
    }


def select_confirmation(
    manifest: MainRollBoundedChallengerManifest,
    *,
    artifact_root: Path,
) -> Path:
    screen = _read_screen(manifest, artifact_root)
    baseline_id = manifest.strategies.baseline.policy_id
    rows: dict[str, Any] = {}
    passing: list[str] = []
    for policy_id in screen["advanced_policy_ids"]:
        stage_name = _stage_name("confirmation", policy_id, None)
        report = _read_stage_report(artifact_root, stage_name)
        primary = report["model_reports"][manifest.primary_probability_model]
        comparison = primary["paired_vs_baseline"][policy_id]
        active_total = float(primary["policies"][policy_id]["active_elapsed_seconds"]["total"])
        active_wall = active_total / manifest.runtime_gate.reference_worker_count
        gate = _primary_gate(
            comparison,
            manifest,
            candidate_active_wall_seconds=active_wall,
        )
        rows[policy_id] = {
            "stage_report_sha256": report["stage_report_sha256"],
            "comparison": comparison,
            "primary_gate": gate,
        }
        if gate["status"] == "pass":
            passing.append(policy_id)
    if passing:
        winner = min(
            passing,
            key=lambda policy_id: (
                -float(rows[policy_id]["comparison"]["mean_difference"]["mean"]),
                manifest.strategies.candidate_policy_ids.index(policy_id),
            ),
        )
        status = "primary-winner-awaiting-sensitivity"
        reason = "Highest-mean challenger among those passing every primary confirmation gate."
    else:
        winner = baseline_id
        status = "fallback"
        reason = "No challenger passed every primary confirmation and runtime gate."
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-confirmation-selection",
        "research_only": True,
        "web_integration": False,
        "automatic_web_promotion": False,
        "bounded_manifest_sha256": manifest.semantic_hash,
        "development_screen_sha256": screen["screen_sha256"],
        "candidate_rows": rows,
        "primary_selected_policy_id": winner,
        "status": status,
        "reason": reason,
    }
    payload = {**body, "selection_sha256": sha256_json(body)}
    path = artifact_root / "confirmation-selection.json"
    _write_exact_or_verify(path, canonical_json(payload) + b"\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    return path


def _read_confirmation_selection(
    manifest: MainRollBoundedChallengerManifest,
    artifact_root: Path,
) -> dict[str, Any]:
    path = artifact_root / "confirmation-selection.json"
    if not path.exists():
        raise MainBoundedChallengerExperimentError("confirmation selection is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = {key: value for key, value in payload.items() if key != "selection_sha256"}
    if (
        sha256_json(body) != payload.get("selection_sha256")
        or payload.get("bounded_manifest_sha256") != manifest.semantic_hash
    ):
        raise MainBoundedChallengerExperimentError("confirmation selection hash differs")
    return payload


def _load_stage_records(artifact_root: Path, stage_name: str) -> list[dict[str, Any]]:
    root = artifact_root / "stages" / stage_name / "results"
    if not root.exists():
        raise MainBoundedChallengerExperimentError(f"stage results are missing: {stage_name}")
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("*.json"))]


def _integrity_manifest(artifact_root: Path) -> Path:
    rows = []
    for path in sorted(item for item in artifact_root.rglob("*") if item.is_file()):
        if path.name == "checksums.json":
            continue
        rows.append(
            {
                "relative_path": path.relative_to(artifact_root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-integrity",
        "file_count": len(rows),
        "total_bytes": sum(row["size"] for row in rows),
        "files": rows,
    }
    payload = {**body, "integrity_sha256": sha256_json(body)}
    path = artifact_root / "checksums.json"
    path.write_bytes(canonical_json(payload) + b"\n")
    return path


def finalize_bundle(
    manifest: MainRollBoundedChallengerManifest,
    *,
    artifact_root: Path,
) -> Path:
    screen = _read_screen(manifest, artifact_root)
    selection = _read_confirmation_selection(manifest, artifact_root)
    baseline_id = manifest.strategies.baseline.policy_id
    primary_winner = str(selection["primary_selected_policy_id"])
    sensitivity_means: dict[str, float] = {}
    sensitivity_report_sha256: str | None = None
    cross_model_pass: bool | None = None
    if primary_winner == baseline_id:
        final_policy = baseline_id
        final_status = "fallback"
        final_reason = "No challenger passed the frozen primary confirmation gates."
    else:
        confirmation_stage = _stage_name("confirmation", primary_winner, None)
        primary_records = _load_stage_records(artifact_root, confirmation_stage)
        selected_indices = set(sensitivity_state_indices(manifest))  # type: ignore[arg-type]
        primary_subset = [row for row in primary_records if int(row["state_index"]) in selected_indices]
        sensitivity_stage = _stage_name("sensitivity", primary_winner, None)
        sensitivity_report = _read_stage_report(artifact_root, sensitivity_stage)
        sensitivity_report_sha256 = sensitivity_report["stage_report_sha256"]
        sensitivity_records = _load_stage_records(artifact_root, sensitivity_stage)
        sensitivity_analysis = analyze_bounded_records(
            primary_subset + sensitivity_records,
            manifest,
            include_starting_strata=False,
        )
        for model_id in manifest.sensitivity_panel.probability_model_ids:
            sensitivity_means[model_id] = float(
                sensitivity_analysis["model_reports"][model_id]["paired_vs_baseline"][primary_winner][
                    "mean_difference"
                ]["mean"]
            )
        cross_model_pass = all(value >= -1e-12 for value in sensitivity_means.values())
        if cross_model_pass:
            final_policy = primary_winner
            final_status = "selected-research-candidate"
            final_reason = "Primary winner remained nonnegative in every frozen probability model."
        else:
            final_policy = baseline_id
            final_status = "fallback"
            final_reason = "Primary winner failed the frozen cross-model nonnegative-mean gate."
    body = {
        "schema_version": 1,
        "analysis_type": "main-roll-bounded-challenger-final",
        "complete": True,
        "research_only": True,
        "web_integration": False,
        "runtime_pointer_writes": False,
        "automatic_web_promotion": False,
        "as_of": manifest.as_of,
        "interpretation": manifest.interpretation,
        "bounded_manifest_sha256": manifest.semantic_hash,
        "development_screen_sha256": screen["screen_sha256"],
        "confirmation_selection_sha256": selection["selection_sha256"],
        "sensitivity_stage_report_sha256": sensitivity_report_sha256,
        "development": screen,
        "confirmation": selection,
        "sensitivity_mean_differences": sensitivity_means,
        "cross_model_nonnegative": cross_model_pass,
        "strategy_selection": {
            "status": final_status,
            "selected_policy_id": final_policy,
            "reason": final_reason,
        },
        "limitations": [
            "This is design-weighted synthetic coverage, not a player-population estimate.",
            "Projected sixteen-Team evidence remains separate from future actual-eight evidence.",
            "The result does not modify or automatically promote any Web strategy.",
        ],
    }
    payload = {**body, "final_report_sha256": sha256_json(body)}
    path = artifact_root / "final-report.json"
    _write_exact_or_verify(path, canonical_json(payload) + b"\n")
    _integrity_manifest(artifact_root)
    print(json.dumps(payload["strategy_selection"], ensure_ascii=False), flush=True)
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated runtime-bounded Main Roll challenger research")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PATHS.root / "config/research/fantasy-main-roll-bounded-challengers-v1.json",
    )
    parser.add_argument(
        "--stage",
        choices=(
            "prepare",
            "smoke",
            "development",
            "screen",
            "confirmation",
            "select",
            "sensitivity",
            "finalize",
        ),
        required=True,
    )
    parser.add_argument("--policy")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--smoke-count", type=int, default=2)
    parser.add_argument("--smoke-roll-limit", type=int, default=2)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PATHS.root / "artifacts/research/main-roll-bounded-challengers",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    manifest_path = arguments.manifest.resolve()
    manifest = load_main_roll_bounded_challenger_manifest(manifest_path)
    base = _load_base_manifest(manifest)
    _, main_context = _validate_loaded_release(base)
    artifact_root = _resolve_artifact_root(manifest, output_root=arguments.output_root)
    records = prepare_bundle(
        manifest,
        base,
        main_context.roll_rules,
        manifest_path=manifest_path,
        artifact_root=artifact_root,
    )
    print(f"artifact root: {artifact_root}", flush=True)
    print(f"bounded manifest SHA-256: {manifest.semantic_hash}", flush=True)
    print(f"state index SHA-256: {state_index_semantic_hash(records)}", flush=True)
    baseline_id = manifest.strategies.baseline.policy_id
    if arguments.stage == "prepare":
        return 0
    if arguments.stage == "smoke":
        run_stage(
            manifest,
            base,
            manifest_path=manifest_path,
            artifact_root=artifact_root,
            stage="smoke",
            policy_ids=manifest.strategies.policy_ids,
            worker_count=arguments.workers,
            smoke_count=arguments.smoke_count,
            smoke_roll_limit=arguments.smoke_roll_limit,
        )
        return 0
    if arguments.stage == "development":
        run_stage(
            manifest,
            base,
            manifest_path=manifest_path,
            artifact_root=artifact_root,
            stage="development",
            policy_ids=manifest.strategies.policy_ids,
            worker_count=arguments.workers,
        )
        return 0
    if arguments.stage == "screen":
        screen_development(manifest, artifact_root=artifact_root)
        return 0
    if arguments.stage == "confirmation":
        screen = _read_screen(manifest, artifact_root)
        policy_id = arguments.policy
        if policy_id not in screen["advanced_policy_ids"]:
            raise MainBoundedChallengerExperimentError(
                "confirmation policy was not advanced by the frozen development screen"
            )
        run_stage(
            manifest,
            base,
            manifest_path=manifest_path,
            artifact_root=artifact_root,
            stage="confirmation",
            policy_ids=(baseline_id, policy_id),
            worker_count=arguments.workers,
            candidate_id=policy_id,
        )
        return 0
    if arguments.stage == "select":
        select_confirmation(manifest, artifact_root=artifact_root)
        return 0
    if arguments.stage == "sensitivity":
        selection = _read_confirmation_selection(manifest, artifact_root)
        policy_id = str(selection["primary_selected_policy_id"])
        if policy_id == baseline_id:
            print("No challenger passed primary confirmation; sensitivity is not required.")
            return 0
        run_stage(
            manifest,
            base,
            manifest_path=manifest_path,
            artifact_root=artifact_root,
            stage="sensitivity",
            policy_ids=(baseline_id, policy_id),
            worker_count=arguments.workers,
            candidate_id=policy_id,
        )
        return 0
    finalize_bundle(manifest, artifact_root=artifact_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BoundedTaskOutput",
    "MainBoundedChallengerExperimentError",
    "analyze_bounded_records",
    "finalize_bundle",
    "prepare_bundle",
    "run_bounded_task",
    "run_stage",
    "screen_development",
    "select_confirmation",
]
