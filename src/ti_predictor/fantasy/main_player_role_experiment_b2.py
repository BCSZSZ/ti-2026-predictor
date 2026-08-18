"""Resumable tuning, blind event-block validation, and TI diagnosis for B2."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ti_predictor.config import load_rules
from ti_predictor.fantasy.main_player_role_backtest import (
    BacktestResult,
    PlayerRoleHoldout,
    build_hash_fixed_banner_panel,
    build_player_role_holdout,
    evaluate_fold,
)
from ti_predictor.fantasy.main_player_role_generator import (
    PlayerRoleEvidenceBuildResult,
    PlayerRoleGeneratorModel,
    build_player_role_evidence,
    fit_player_role_generator_from_frame,
)
from ti_predictor.fantasy.main_player_role_generator_b2 import (
    MainPlayerRoleGeneratorB2Config,
    fit_empirical_copula_generator,
    load_main_player_role_generator_b2_config,
)
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import source_tree_hash, source_version


class MainPlayerRoleExperimentB2Error(ValueError):
    """A frozen B2 experiment checkpoint or selection is invalid."""


@dataclass(frozen=True)
class PreparedB2Fold:
    fold_id: str
    evidence_build: PlayerRoleEvidenceBuildResult
    holdout: PlayerRoleHoldout
    b1_model: PlayerRoleGeneratorModel
    b1_result: BacktestResult


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    )
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _artifact_root(
    config: MainPlayerRoleGeneratorB2Config,
    *,
    paths: ProjectPaths,
) -> Path:
    evidence_paths = main_evidence_paths(paths, require=True)
    snapshot_manifest = evidence_paths.processed / "manifest.json"
    identity = sha256_json(
        {
            "config_sha256": config.semantic_hash,
            "snapshot_manifest_sha256": sha256_file(snapshot_manifest),
            "source_tree_sha256": source_tree_hash(paths),
        }
    )
    return (
        paths.artifacts
        / "research"
        / "main-player-role-generator-b2"
        / f"{config.as_of:%Y-%m-%d}-{identity[:12]}"
    )


def _fit_b1(
    config: MainPlayerRoleGeneratorB2Config,
    evidence_build: PlayerRoleEvidenceBuildResult,
) -> PlayerRoleGeneratorModel:
    parameters = config.frozen_b1
    caps = config.evidence
    return fit_player_role_generator_from_frame(
        evidence_build.evidence,
        ridge_alpha=parameters.ridge_alpha,
        recent_effective_sample_constant=parameters.recent_effective_sample_constant,
        recent_residual_cap_sigma=parameters.recent_residual_cap_sigma,
        factor_rank=parameters.factor_rank,
        covariance_shrinkage=parameters.covariance_shrinkage,
        latent_scale=parameters.latent_scale,
        maximum_game_parameter_mass=caps.maximum_game_parameter_mass,
        maximum_series_parameter_mass=caps.maximum_series_parameter_mass,
        maximum_residual_game_mass=caps.maximum_residual_game_mass,
        maximum_residual_series_mass=caps.maximum_residual_series_mass,
    )


def _fit_b2(
    prepared: PreparedB2Fold,
    config: MainPlayerRoleGeneratorB2Config,
    parameters: Mapping[str, float],
) -> PlayerRoleGeneratorModel:
    caps = config.evidence
    frozen = config.frozen_b1
    return fit_empirical_copula_generator(
        prepared.b1_model,
        prepared.evidence_build.evidence,
        empirical_mix=float(parameters["empirical_mix"]),
        latent_scale=float(parameters["latent_scale"]),
        factor_rank=frozen.factor_rank,
        covariance_shrinkage=frozen.covariance_shrinkage,
        maximum_residual_game_mass=caps.maximum_residual_game_mass,
        maximum_residual_series_mass=caps.maximum_residual_series_mass,
    )


def _prepare_fold(
    config: MainPlayerRoleGeneratorB2Config,
    fold: Any,
    *,
    rules: Mapping[str, Any],
    panel: tuple[Any, ...],
    paths: ProjectPaths,
) -> PreparedB2Fold:
    evidence_build = build_player_role_evidence(
        training_cutoff=fold.train_as_of,
        available_as_of=config.as_of,
        paths=paths,
    )
    holdout = build_player_role_holdout(
        fold_id=fold.fold_id,
        league_id=fold.league_id,
        train_cutoff=fold.train_as_of,
        test_end=fold.test_end,
        available_as_of=config.as_of,
        strength_model=evidence_build.strength_model,
        paths=paths,
    )
    b1_model = _fit_b1(config, evidence_build)
    b1_result = evaluate_fold(
        model=b1_model,
        training_evidence=evidence_build.evidence,
        holdout=holdout,
        rules=rules,
        panel=panel,
        sample_count=config.copula_tuning.tuning_samples_per_series,
        seeds=config.simulation.seeds,
    )
    return PreparedB2Fold(
        fold_id=fold.fold_id,
        evidence_build=evidence_build,
        holdout=holdout,
        b1_model=b1_model,
        b1_result=b1_result,
    )


def _evaluate_b2(
    prepared: PreparedB2Fold,
    config: MainPlayerRoleGeneratorB2Config,
    parameters: Mapping[str, float],
    *,
    rules: Mapping[str, Any],
    panel: tuple[Any, ...],
) -> BacktestResult:
    model = _fit_b2(prepared, config, parameters)
    return evaluate_fold(
        model=model,
        training_evidence=prepared.evidence_build.evidence,
        holdout=prepared.holdout,
        rules=rules,
        panel=panel,
        sample_count=config.copula_tuning.tuning_samples_per_series,
        seeds=config.simulation.seeds,
    )


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    numeric = np.asarray(values, dtype=float)
    mass = np.asarray(weights, dtype=float)
    if len(numeric) != len(mass) or not len(numeric) or mass.sum() <= 0.0:
        raise MainPlayerRoleExperimentB2Error("aggregate values and weights are invalid")
    return float(np.dot(numeric, mass / mass.sum()))


def _aggregate_pair(
    b2_results: Sequence[BacktestResult],
    b1_results: Sequence[BacktestResult],
) -> dict[str, Any]:
    if len(b2_results) != len(b1_results) or not b2_results:
        raise MainPlayerRoleExperimentB2Error("B2 and B1 fold results do not align")
    projection_weights = [float(result.metrics["series_projection_records"]) for result in b2_results]
    joint_weights = [float(result.metrics["joint_games"]) for result in b2_results]
    b2_crps = _weighted_mean(
        [float(result.metrics["b_series_crps"]) for result in b2_results],
        projection_weights,
    )
    b1_crps = _weighted_mean(
        [float(result.metrics["b_series_crps"]) for result in b1_results],
        projection_weights,
    )
    b2_energy = _weighted_mean(
        [float(result.metrics["b_joint_energy"]) for result in b2_results],
        joint_weights,
    )
    b1_energy = _weighted_mean(
        [float(result.metrics["b_joint_energy"]) for result in b1_results],
        joint_weights,
    )
    coverage80 = _weighted_mean(
        [float(result.metrics["b_coverage80"]) for result in b2_results],
        projection_weights,
    )
    coverage90 = _weighted_mean(
        [float(result.metrics["b_coverage90"]) for result in b2_results],
        projection_weights,
    )
    return {
        "fold_count": len(b2_results),
        "series_projection_records": int(sum(projection_weights)),
        "joint_games": int(sum(joint_weights)),
        "b2_series_crps": b2_crps,
        "b1_series_crps": b1_crps,
        "series_crps_relative_loss_vs_b1": (b2_crps - b1_crps) / max(b1_crps, 1e-12),
        "b2_joint_energy": b2_energy,
        "b1_joint_energy": b1_energy,
        "joint_energy_relative_improvement_vs_b1": (b1_energy - b2_energy) / max(b1_energy, 1e-12),
        "b2_coverage80": coverage80,
        "b2_coverage90": coverage90,
        "coverage_distance": _coverage_distance(coverage80, 0.75, 0.85)
        + _coverage_distance(coverage90, 0.86, 0.94),
        "fold_metrics": [
            {
                "fold_id": b2.fold_id,
                "b2": dict(b2.metrics),
                "b1": dict(b1.metrics),
            }
            for b2, b1 in zip(b2_results, b1_results, strict=True)
        ],
        "b2_result_sha256": [result.semantic_hash for result in b2_results],
        "b1_result_sha256": [result.semantic_hash for result in b1_results],
    }


def _coverage_distance(value: float, lower: float, upper: float) -> float:
    if value < lower:
        return lower - value
    if value > upper:
        return value - upper
    return 0.0


def _candidate_key(parameters: Mapping[str, float]) -> str:
    return sha256_json(dict(sorted(parameters.items())))


def _load_checkpoint(path: Path, *, contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract") != dict(contract):
        raise MainPlayerRoleExperimentB2Error(f"B2 checkpoint contract differs from the frozen run: {path}")
    rows = list(payload.get("candidates", []))
    if payload.get("semantic_hash") != sha256_json(rows):
        raise MainPlayerRoleExperimentB2Error(f"B2 checkpoint hash is invalid: {path}")
    return rows


def _write_checkpoint(
    path: Path,
    *,
    contract: Mapping[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    _atomic_json(
        path,
        {
            "schema_version": 2,
            "contract": dict(contract),
            "completed_candidates": len(rows),
            "candidates": rows,
            "semantic_hash": sha256_json(rows),
        },
    )


def _select_candidate(
    rows: Sequence[dict[str, Any]],
    *,
    maximum_crps_relative_loss: float,
) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if float(row["aggregate"]["series_crps_relative_loss_vs_b1"]) <= maximum_crps_relative_loss
    ]
    if not eligible:
        raise MainPlayerRoleExperimentB2Error(
            "no B2 candidate preserves frozen B1 Series CRPS within the pre-registered limit"
        )
    return min(
        eligible,
        key=lambda row: (
            float(row["aggregate"]["b2_joint_energy"]),
            float(row["aggregate"]["coverage_distance"]),
            float(row["parameters"]["empirical_mix"]),
            abs(float(row["parameters"]["latent_scale"]) - 1.0),
            str(row["candidate_key"]),
        ),
    )


def run_tuning(
    config: MainPlayerRoleGeneratorB2Config,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    root = _artifact_root(config, paths=paths)
    root.mkdir(parents=True, exist_ok=True)
    rules = load_rules(paths.rules)
    panel = build_hash_fixed_banner_panel(rules)
    prepared = [
        _prepare_fold(config, fold, rules=rules, panel=panel, paths=paths) for fold in config.tuning_folds
    ]
    _atomic_json(
        root / "tuning-fold-audits.json",
        {
            item.fold_id: {
                "training": item.evidence_build.evidence.audit,
                "holdout": item.holdout.audit,
                "b1_result_sha256": item.b1_result.semantic_hash,
            }
            for item in prepared
        },
    )
    contract = {
        "stage": "b2-empirical-copula-tuning",
        "config_sha256": config.semantic_hash,
        "source_tree_sha256": source_tree_hash(paths),
        "fold_ids": [item.fold_id for item in prepared],
        "panel_sha256": sha256_json(
            [
                {
                    "projection_id": item.projection_id,
                    "role": item.role,
                    "stat_ids": item.stat_ids,
                    "multipliers": item.multipliers.tolist(),
                }
                for item in panel
            ]
        ),
    }
    checkpoint_path = root / "tuning-candidates.json"
    rows = _load_checkpoint(checkpoint_path, contract=contract)
    completed = {str(row["candidate_key"]) for row in rows}
    candidates = [
        {"empirical_mix": mix, "latent_scale": scale}
        for mix, scale in product(
            config.copula_tuning.empirical_mixes,
            config.copula_tuning.latent_scales,
        )
    ]
    for index, parameters in enumerate(candidates, start=1):
        key = _candidate_key(parameters)
        if key in completed:
            continue
        print(f"[B2 tuning] candidate {index}/{len(candidates)} {parameters}", flush=True)
        b2_results = [
            _evaluate_b2(
                item,
                config,
                parameters,
                rules=rules,
                panel=panel,
            )
            for item in prepared
        ]
        aggregate = _aggregate_pair(
            b2_results,
            [item.b1_result for item in prepared],
        )
        rows.append(
            {
                "candidate_key": key,
                "parameters": parameters,
                "aggregate": aggregate,
            }
        )
        completed.add(key)
        _write_checkpoint(checkpoint_path, contract=contract, rows=rows)
        print(
            f"[B2 tuning] Energy={aggregate['b2_joint_energy']:.6f} "
            f"vs B1={aggregate['joint_energy_relative_improvement_vs_b1']:+.3%} "
            f"CRPS loss={aggregate['series_crps_relative_loss_vs_b1']:+.3%}",
            flush=True,
        )
    selected = _select_candidate(
        rows,
        maximum_crps_relative_loss=(config.copula_tuning.maximum_crps_relative_loss_vs_b1),
    )
    result = {
        "schema_version": 2,
        "kind": "ti2026-main-player-role-b2-tuning-selection",
        "status": "research-only-b2-tuning-complete",
        "config": config.model_dump(mode="json"),
        "config_sha256": config.semantic_hash,
        "source_version": source_version(paths),
        "source_tree_sha256": source_tree_hash(paths),
        "artifact_root": str(root.resolve()),
        "selected_parameters": selected["parameters"],
        "selected_candidate": selected,
        "eligible_candidates": sum(
            float(row["aggregate"]["series_crps_relative_loss_vs_b1"])
            <= config.copula_tuning.maximum_crps_relative_loss_vs_b1
            for row in rows
        ),
        "candidate_count": len(rows),
    }
    result["selection_sha256"] = sha256_json(result)
    _atomic_json(root / "selected-parameters.json", result)
    print(f"[B2 tuning] selected {result['selected_parameters']}", flush=True)
    return result


def _combine_records(
    results: Sequence[BacktestResult],
    *,
    kind: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in results:
        source = result.series_records if kind == "series" else result.joint_records
        rows.extend({"fold_id": result.fold_id, **dict(row)} for row in source)
    return pd.DataFrame(rows)


def _bootstrap_mean_bound(
    values: np.ndarray,
    *,
    confidence: float,
    seed: int,
    side: str,
    replicates: int = 10_000,
) -> dict[str, Any]:
    numeric = np.asarray(values, dtype=float).reshape(-1)
    if not len(numeric) or side not in {"lower", "upper"}:
        raise MainPlayerRoleExperimentB2Error("bootstrap input is invalid")
    rng = np.random.default_rng(int(seed))
    indexes = rng.integers(0, len(numeric), size=(replicates, len(numeric)))
    distribution = numeric[indexes].mean(axis=1)
    quantile = 1.0 - confidence if side == "lower" else confidence
    return {
        "blocks": len(numeric),
        "mean": float(numeric.mean()),
        f"one_sided_{side}_bound": float(np.quantile(distribution, quantile)),
        "confidence": float(confidence),
        "replicates": replicates,
    }


def _validation_statistics(
    b2_results: Sequence[BacktestResult],
    b1_results: Sequence[BacktestResult],
    *,
    config: MainPlayerRoleGeneratorB2Config,
) -> dict[str, Any]:
    aggregate = _aggregate_pair(b2_results, b1_results)
    series = _combine_records(b2_results, kind="series")
    joint = _combine_records(b2_results, kind="joint")
    b1_joint = _combine_records(b1_results, kind="joint").rename(columns={"b_energy": "b1_energy"})
    joint = joint.merge(
        b1_joint[["fold_id", "match_id", "series_id", "team_id", "b1_energy"]],
        on=["fold_id", "match_id", "series_id", "team_id"],
        how="inner",
        validate="one_to_one",
    )
    confidence = config.gates.series_crps_one_sided_confidence
    crps_blocks = (
        series.dropna(subset=["v1_crps"])
        .assign(delta=lambda frame: frame["v1_crps"] - frame["b_crps"])
        .groupby(["fold_id", "series_id", "team_id"], sort=True)["delta"]
        .mean()
        .to_numpy(dtype=float)
    )
    common_v1 = joint.dropna(subset=["v1_energy"]).copy()
    v1_energy_loss = (common_v1["b_energy"] - common_v1["v1_energy"]) / common_v1["v1_energy"].clip(
        lower=1e-12
    )
    v1_energy_blocks = (
        common_v1.assign(relative_loss=v1_energy_loss)
        .groupby(["fold_id", "series_id"], sort=True)["relative_loss"]
        .mean()
        .to_numpy(dtype=float)
    )
    b1_energy_blocks = (
        joint.assign(
            relative_loss=(joint["b_energy"] - joint["b1_energy"]) / joint["b1_energy"].clip(lower=1e-12)
        )
        .groupby(["fold_id", "series_id"], sort=True)["relative_loss"]
        .mean()
        .to_numpy(dtype=float)
    )
    seeds = config.simulation.seeds
    return {
        "aggregate": aggregate,
        "crps_vs_v1": _bootstrap_mean_bound(
            crps_blocks,
            confidence=confidence,
            seed=seeds[0],
            side="lower",
        ),
        "joint_energy_vs_v1": _bootstrap_mean_bound(
            v1_energy_blocks,
            confidence=confidence,
            seed=seeds[1],
            side="upper",
        ),
        "joint_energy_vs_b1": _bootstrap_mean_bound(
            b1_energy_blocks,
            confidence=confidence,
            seed=seeds[2],
            side="upper",
        ),
        "combined_series_records": len(series),
        "combined_joint_records": len(joint),
    }


def _gate_checks(
    statistics: Mapping[str, Any],
    b2_results: Sequence[BacktestResult],
    *,
    config: MainPlayerRoleGeneratorB2Config,
) -> dict[str, bool]:
    aggregate = statistics["aggregate"]
    projection_weights = [float(result.metrics["series_projection_records"]) for result in b2_results]
    common_b2_crps = _weighted_mean(
        [float(result.metrics["common_b_series_crps"]) for result in b2_results],
        projection_weights,
    )
    v1_crps = _weighted_mean(
        [float(result.metrics["v1_series_crps"]) for result in b2_results],
        projection_weights,
    )
    joint_weights = [float(result.metrics["joint_games"]) for result in b2_results]
    common_b2_energy = _weighted_mean(
        [float(result.metrics["common_b_joint_energy"]) for result in b2_results],
        joint_weights,
    )
    v1_energy = _weighted_mean(
        [float(result.metrics["v1_joint_energy"]) for result in b2_results],
        joint_weights,
    )
    role_checks: list[bool] = []
    for role in ("core", "mid", "support"):
        b2 = _weighted_mean(
            [float(result.metrics["role_metrics"][role]["common_b_crps"]) for result in b2_results],
            projection_weights,
        )
        v1 = _weighted_mean(
            [float(result.metrics["role_metrics"][role]["v1_crps"]) for result in b2_results],
            projection_weights,
        )
        role_checks.append((v1 - b2) / max(v1, 1e-12) >= -config.gates.maximum_role_crps_relative_loss)
    b2_regrets = [
        (float(result.metrics["b_mean_regret"]), weight)
        for result, weight in zip(b2_results, projection_weights, strict=True)
        if result.metrics["b_mean_regret"] is not None
    ]
    v1_regrets = [
        (float(result.metrics["v1_mean_regret"]), weight)
        for result, weight in zip(b2_results, projection_weights, strict=True)
        if result.metrics["v1_mean_regret"] is not None
    ]
    regret_ok = bool(b2_regrets and v1_regrets) and _weighted_mean(
        [item[0] for item in b2_regrets], [item[1] for item in b2_regrets]
    ) <= _weighted_mean([item[0] for item in v1_regrets], [item[1] for item in v1_regrets])
    return {
        "series_crps_relative_improvement_vs_v1": (
            (v1_crps - common_b2_crps) / max(v1_crps, 1e-12) >= config.gates.minimum_series_crps_improvement
        ),
        "series_crps_lower_bound_positive": (statistics["crps_vs_v1"]["one_sided_lower_bound"] > 0.0),
        "joint_energy_point_better_than_v1": common_b2_energy <= v1_energy,
        "joint_energy_upper_noninferior_to_v1": (
            statistics["joint_energy_vs_v1"]["one_sided_upper_bound"]
            <= config.gates.maximum_joint_energy_relative_loss
        ),
        "joint_energy_point_better_than_b1": (aggregate["b2_joint_energy"] <= aggregate["b1_joint_energy"]),
        "joint_energy_upper_better_than_b1": (
            statistics["joint_energy_vs_b1"]["one_sided_upper_bound"]
            <= config.maximum_joint_energy_relative_loss_vs_b1
        ),
        "coverage80": (
            config.gates.coverage_80_lower <= aggregate["b2_coverage80"] <= config.gates.coverage_80_upper
        ),
        "coverage90": (
            config.gates.coverage_90_lower <= aggregate["b2_coverage90"] <= config.gates.coverage_90_upper
        ),
        "role_crps_noninferior_to_v1": all(role_checks),
        "team_choice_regret_noninferior_to_v1": regret_ok,
    }


def _load_selection(
    config: MainPlayerRoleGeneratorB2Config,
    *,
    paths: ProjectPaths,
) -> tuple[Path, dict[str, Any]]:
    root = _artifact_root(config, paths=paths)
    selection_path = root / "selected-parameters.json"
    if not selection_path.is_file():
        raise MainPlayerRoleExperimentB2Error("B2 tuning selection is missing")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("config_sha256") != config.semantic_hash:
        raise MainPlayerRoleExperimentB2Error("B2 tuning selection config hash differs")
    return root, selection


def _run_panel(
    config: MainPlayerRoleGeneratorB2Config,
    folds: Sequence[Any],
    *,
    paths: ProjectPaths,
) -> tuple[list[PreparedB2Fold], list[BacktestResult], dict[str, Any]]:
    _, selection = _load_selection(config, paths=paths)
    parameters = dict(selection["selected_parameters"])
    rules = load_rules(paths.rules)
    panel = build_hash_fixed_banner_panel(rules)
    prepared: list[PreparedB2Fold] = []
    results: list[BacktestResult] = []
    for index, fold in enumerate(folds, start=1):
        print(f"[B2 panel] preparing {index}/{len(folds)} {fold.fold_id}", flush=True)
        item = _prepare_fold(config, fold, rules=rules, panel=panel, paths=paths)
        prepared.append(item)
        results.append(_evaluate_b2(item, config, parameters, rules=rules, panel=panel))
    return prepared, results, selection


def run_confirmation(
    config: MainPlayerRoleGeneratorB2Config,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    root, _ = _load_selection(config, paths=paths)
    prepared, b2_results, selection = _run_panel(config, config.confirmation_folds, paths=paths)
    statistics = _validation_statistics(
        b2_results,
        [item.b1_result for item in prepared],
        config=config,
    )
    gates = _gate_checks(statistics, b2_results, config=config)
    payload = {
        "schema_version": 2,
        "kind": "ti2026-main-player-role-b2-blind-event-block-validation",
        "status": (
            "accuracy-and-calibration-gates-passed"
            if all(gates.values())
            else "accuracy-or-calibration-gate-failed"
        ),
        "validation_semantics": "blind-unused-event-blocks-not-forward-after-tuning",
        "config_sha256": config.semantic_hash,
        "selection_sha256": selection["selection_sha256"],
        "selected_parameters": selection["selected_parameters"],
        "statistics": statistics,
        "gate_checks": gates,
        "folds": [
            {
                "fold_id": item.fold_id,
                "training_audit": item.evidence_build.evidence.audit,
                "holdout_audit": item.holdout.audit,
                "b2_result_sha256": b2.semantic_hash,
                "b1_result_sha256": item.b1_result.semantic_hash,
                "b2_metrics": dict(b2.metrics),
                "b1_metrics": dict(item.b1_result.metrics),
            }
            for item, b2 in zip(prepared, b2_results, strict=True)
        ],
    }
    payload["confirmation_sha256"] = sha256_json(payload)
    _atomic_json(root / "confirmation-unused-event-blocks.json", payload)
    print(f"[B2 confirmation] status={payload['status']} checks={gates}", flush=True)
    return payload


def run_ti_diagnostic(
    config: MainPlayerRoleGeneratorB2Config,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    root, _ = _load_selection(config, paths=paths)
    prepared, b2_results, selection = _run_panel(config, [config.diagnostic_fold], paths=paths)
    statistics = _validation_statistics(
        b2_results,
        [prepared[0].b1_result],
        config=config,
    )
    payload = {
        "schema_version": 2,
        "kind": "ti2026-main-player-role-b2-consumed-ti-diagnostic",
        "status": "diagnostic-only-not-independent-confirmation",
        "config_sha256": config.semantic_hash,
        "selection_sha256": selection["selection_sha256"],
        "selected_parameters": selection["selected_parameters"],
        "statistics": statistics,
        "b2_metrics": dict(b2_results[0].metrics),
        "b1_metrics": dict(prepared[0].b1_result.metrics),
        "b2_result_sha256": b2_results[0].semantic_hash,
        "b1_result_sha256": prepared[0].b1_result.semantic_hash,
    }
    payload["diagnostic_sha256"] = sha256_json(payload)
    _atomic_json(root / "diagnostic-ti-consumed.json", payload)
    print("[B2 diagnostic] TI consumed panel complete", flush=True)
    return payload


def run_experiment(
    config_path: Path,
    *,
    mode: str,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    config = load_main_player_role_generator_b2_config(config_path)
    if mode == "tune":
        return run_tuning(config, paths=paths)
    if mode == "confirm":
        return run_confirmation(config, paths=paths)
    if mode == "diagnose":
        return run_ti_diagnostic(config, paths=paths)
    if mode == "all":
        run_tuning(config, paths=paths)
        confirmation = run_confirmation(config, paths=paths)
        diagnostic = run_ti_diagnostic(config, paths=paths)
        return {
            "status": confirmation["status"],
            "confirmation": confirmation,
            "diagnostic": diagnostic,
        }
    raise MainPlayerRoleExperimentB2Error(f"unknown B2 experiment mode {mode!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/research/fantasy-main-player-role-generator-v2.json"),
    )
    parser.add_argument("--mode", choices=("tune", "confirm", "diagnose", "all"), default="all")
    arguments = parser.parse_args()
    result = run_experiment(arguments.config, mode=arguments.mode)
    print(json.dumps({"status": result["status"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()


__all__ = [
    "MainPlayerRoleExperimentB2Error",
    "PreparedB2Fold",
    "run_confirmation",
    "run_experiment",
    "run_ti_diagnostic",
    "run_tuning",
]
