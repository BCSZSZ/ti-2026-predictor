"""Resumable research runner for Main Player-role tuning and confirmation."""

from __future__ import annotations

import argparse
import json
import os
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
    paired_series_bootstrap_lower_bound,
)
from ti_predictor.fantasy.main_player_role_generator import (
    MainPlayerRoleGeneratorConfig,
    PlayerRoleEvidenceBuildResult,
    build_player_role_evidence,
    fit_player_role_generator_from_frame,
    load_main_player_role_generator_config,
)
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import source_tree_hash, source_version


class MainPlayerRoleExperimentError(ValueError):
    """A frozen experiment checkpoint or candidate selection is invalid."""


@dataclass(frozen=True)
class PreparedFold:
    fold_id: str
    evidence_build: PlayerRoleEvidenceBuildResult
    holdout: PlayerRoleHoldout


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
    config: MainPlayerRoleGeneratorConfig,
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
        / "main-player-role-generator"
        / f"{config.as_of:%Y-%m-%d}-{identity[:12]}"
    )


def _checkpoint(path: Path, *, contract: MappingLike, rows: list[dict[str, Any]]) -> None:
    _atomic_json(
        path,
        {
            "schema_version": 1,
            "contract": dict(contract),
            "completed_candidates": len(rows),
            "candidates": rows,
            "semantic_hash": sha256_json(rows),
        },
    )


MappingLike = dict[str, Any]


def _load_checkpoint(path: Path, *, contract: MappingLike) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract") != dict(contract):
        raise MainPlayerRoleExperimentError(f"checkpoint contract differs from the frozen run: {path}")
    rows = list(payload.get("candidates", []))
    if payload.get("semantic_hash") != sha256_json(rows):
        raise MainPlayerRoleExperimentError(f"checkpoint hash is invalid: {path}")
    return rows


def _prepare_fold(
    config: MainPlayerRoleGeneratorConfig,
    fold: Any,
    *,
    paths: ProjectPaths,
) -> PreparedFold:
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
    return PreparedFold(fold.fold_id, evidence_build, holdout)


def _fit_and_evaluate(
    prepared: PreparedFold,
    config: MainPlayerRoleGeneratorConfig,
    parameters: MappingLike,
    *,
    rules: MappingLike,
    panel: tuple[Any, ...],
) -> BacktestResult:
    model = fit_player_role_generator_from_frame(
        prepared.evidence_build.evidence,
        ridge_alpha=float(parameters["ridge_alpha"]),
        recent_effective_sample_constant=float(parameters["recent_effective_sample_constant"]),
        recent_residual_cap_sigma=float(parameters["recent_residual_cap_sigma"]),
        factor_rank=int(parameters["factor_rank"]),
        covariance_shrinkage=float(parameters["covariance_shrinkage"]),
        latent_scale=float(parameters["latent_scale"]),
        maximum_game_parameter_mass=config.evidence.maximum_game_parameter_mass,
        maximum_series_parameter_mass=config.evidence.maximum_series_parameter_mass,
        maximum_residual_game_mass=config.evidence.maximum_residual_game_mass,
        maximum_residual_series_mass=config.evidence.maximum_residual_series_mass,
    )
    return evaluate_fold(
        model=model,
        training_evidence=prepared.evidence_build.evidence,
        holdout=prepared.holdout,
        rules=rules,
        panel=panel,
        sample_count=config.tuning_selection.tuning_samples_per_series,
        seeds=config.simulation.seeds,
    )


def _aggregate(results: list[BacktestResult]) -> dict[str, Any]:
    if not results:
        raise MainPlayerRoleExperimentError("candidate has no fold results")
    weights = np.asarray([float(item.metrics["series_projection_records"]) for item in results])
    weights /= weights.sum()

    def weighted(key: str) -> float:
        return float(np.dot(weights, np.asarray([float(item.metrics[key]) for item in results])))

    return {
        "fold_count": len(results),
        "series": int(sum(int(item.metrics["series"]) for item in results)),
        "series_projection_records": int(
            sum(int(item.metrics["series_projection_records"]) for item in results)
        ),
        "b_series_crps": weighted("b_series_crps"),
        "common_b_series_crps": weighted("common_b_series_crps"),
        "v1_series_crps": weighted("v1_series_crps"),
        "series_crps_relative_improvement": weighted("series_crps_relative_improvement"),
        "b_coverage80": weighted("b_coverage80"),
        "b_coverage90": weighted("b_coverage90"),
        "b_joint_energy": weighted("b_joint_energy"),
        "common_b_joint_energy": weighted("common_b_joint_energy"),
        "v1_joint_energy": weighted("v1_joint_energy"),
        "joint_energy_relative_improvement": weighted("joint_energy_relative_improvement"),
        "fold_metrics": [dict(item.metrics) for item in results],
        "fold_result_sha256": [item.semantic_hash for item in results],
    }


def _candidate_key(parameters: MappingLike) -> str:
    return sha256_json(dict(sorted(parameters.items())))


def _run_stage(
    *,
    stage: str,
    candidates: list[MappingLike],
    prepared_folds: list[PreparedFold],
    config: MainPlayerRoleGeneratorConfig,
    rules: MappingLike,
    panel: tuple[Any, ...],
    root: Path,
) -> list[dict[str, Any]]:
    contract = {
        "stage": stage,
        "config_sha256": config.semantic_hash,
        "source_tree_sha256": source_tree_hash(PATHS),
        "fold_ids": [item.fold_id for item in prepared_folds],
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
    checkpoint_path = root / f"tuning-{stage}.json"
    rows = _load_checkpoint(checkpoint_path, contract=contract)
    completed = {str(row["candidate_key"]) for row in rows}
    for candidate_index, parameters in enumerate(candidates, start=1):
        key = _candidate_key(parameters)
        if key in completed:
            continue
        print(
            f"[{stage}] candidate {candidate_index}/{len(candidates)} {parameters}",
            flush=True,
        )
        fold_results = [
            _fit_and_evaluate(
                prepared,
                config,
                parameters,
                rules=rules,
                panel=panel,
            )
            for prepared in prepared_folds
        ]
        row = {
            "candidate_key": key,
            "parameters": dict(parameters),
            "aggregate": _aggregate(fold_results),
        }
        rows.append(row)
        completed.add(key)
        _checkpoint(checkpoint_path, contract=contract, rows=rows)
        print(
            f"[{stage}] CRPS={row['aggregate']['b_series_crps']:.6f} "
            f"coverage80={row['aggregate']['b_coverage80']:.4f}",
            flush=True,
        )
    return rows


def _select_marginal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        rows,
        key=lambda row: (
            float(row["aggregate"]["b_series_crps"]),
            -float(row["parameters"]["ridge_alpha"]),
            -float(row["parameters"]["recent_effective_sample_constant"]),
            float(row["parameters"]["recent_residual_cap_sigma"]),
            str(row["candidate_key"]),
        ),
    )


def _select_joint(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        rows,
        key=lambda row: (
            float(row["aggregate"]["b_series_crps"]),
            int(row["parameters"]["factor_rank"]),
            -float(row["parameters"]["covariance_shrinkage"]),
            str(row["candidate_key"]),
        ),
    )


def _select_scale(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        rows,
        key=lambda row: (
            float(row["aggregate"]["b_series_crps"]),
            abs(float(row["parameters"]["latent_scale"]) - 1.0),
            float(row["parameters"]["latent_scale"]),
            str(row["candidate_key"]),
        ),
    )


def run_tuning(
    config: MainPlayerRoleGeneratorConfig,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    root = _artifact_root(config, paths=paths)
    root.mkdir(parents=True, exist_ok=True)
    rules = load_rules(paths.rules)
    panel = build_hash_fixed_banner_panel(rules)
    prepared = [_prepare_fold(config, fold, paths=paths) for fold in config.tuning_folds]
    _atomic_json(
        root / "tuning-fold-audits.json",
        {
            item.fold_id: {
                "training": item.evidence_build.evidence.audit,
                "holdout": item.holdout.audit,
            }
            for item in prepared
        },
    )
    fixed = config.tuning_selection
    marginal_candidates = [
        {
            "ridge_alpha": ridge,
            "recent_effective_sample_constant": recent,
            "recent_residual_cap_sigma": cap,
            "factor_rank": fixed.fixed_factor_rank_for_marginal_stage,
            "covariance_shrinkage": fixed.fixed_covariance_shrinkage_for_marginal_stage,
            "latent_scale": fixed.fixed_latent_scale_for_marginal_stage,
        }
        for ridge, recent, cap in product(
            config.marginal_tuning.ridge_alphas,
            config.marginal_tuning.recent_effective_sample_constants,
            config.marginal_tuning.recent_residual_caps_sigma,
        )
    ]
    marginal_rows = _run_stage(
        stage="marginal",
        candidates=marginal_candidates,
        prepared_folds=prepared,
        config=config,
        rules=rules,
        panel=panel,
        root=root,
    )
    selected_marginal = _select_marginal(marginal_rows)
    base = dict(selected_marginal["parameters"])
    joint_candidates = [
        {
            **base,
            "factor_rank": rank,
            "covariance_shrinkage": shrinkage,
            "latent_scale": 1.0,
        }
        for rank, shrinkage in product(
            config.joint_tuning.factor_ranks,
            config.joint_tuning.covariance_shrinkages,
        )
    ]
    joint_rows = _run_stage(
        stage="joint-factor-shrinkage",
        candidates=joint_candidates,
        prepared_folds=prepared,
        config=config,
        rules=rules,
        panel=panel,
        root=root,
    )
    selected_joint = _select_joint(joint_rows)
    joint_base = dict(selected_joint["parameters"])
    scale_candidates = [{**joint_base, "latent_scale": scale} for scale in config.joint_tuning.latent_scales]
    scale_rows = _run_stage(
        stage="joint-latent-scale",
        candidates=scale_candidates,
        prepared_folds=prepared,
        config=config,
        rules=rules,
        panel=panel,
        root=root,
    )
    selected_scale = _select_scale(scale_rows)
    result = {
        "schema_version": 1,
        "kind": "ti2026-main-player-role-tuning-selection",
        "status": "research-only-tuning-complete",
        "config": config.model_dump(mode="json"),
        "config_sha256": config.semantic_hash,
        "source_version": source_version(paths),
        "source_tree_sha256": source_tree_hash(paths),
        "artifact_root": str(root.resolve()),
        "selected_parameters": selected_scale["parameters"],
        "selected_marginal_candidate": selected_marginal,
        "selected_joint_candidate": selected_joint,
        "selected_scale_candidate": selected_scale,
    }
    result["selection_sha256"] = sha256_json(result)
    _atomic_json(root / "selected-parameters.json", result)
    print(f"selected {result['selected_parameters']}", flush=True)
    return result


def _paired_energy_bootstrap(
    records: tuple[dict[str, Any], ...] | tuple[Any, ...],
    *,
    confidence: float,
    seed: int,
    replicates: int = 10_000,
) -> dict[str, Any]:
    frame = pd.DataFrame(records).dropna(subset=["b_energy", "v1_energy"])
    frame["relative_loss"] = (frame["b_energy"] - frame["v1_energy"]) / frame["v1_energy"].clip(lower=1e-12)
    grouped = frame.groupby("series_id", sort=True)["relative_loss"].mean().to_numpy()
    rng = np.random.default_rng(int(seed))
    indexes = rng.integers(0, len(grouped), size=(replicates, len(grouped)))
    distribution = grouped[indexes].mean(axis=1)
    return {
        "series_blocks": len(grouped),
        "mean_relative_loss": float(grouped.mean()),
        "one_sided_upper_bound": float(np.quantile(distribution, confidence)),
        "confidence": confidence,
        "replicates": replicates,
    }


def run_confirmation(
    config: MainPlayerRoleGeneratorConfig,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    root = _artifact_root(config, paths=paths)
    selection_path = root / "selected-parameters.json"
    if not selection_path.is_file():
        raise MainPlayerRoleExperimentError("tuning selection is missing")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("config_sha256") != config.semantic_hash:
        raise MainPlayerRoleExperimentError("tuning selection config hash differs")
    parameters = dict(selection["selected_parameters"])
    fold = _prepare_fold(config, config.confirmation_fold, paths=paths)
    rules = load_rules(paths.rules)
    panel = build_hash_fixed_banner_panel(rules)
    result = _fit_and_evaluate(
        fold,
        config,
        parameters,
        rules=rules,
        panel=panel,
    )
    crps_bootstrap = paired_series_bootstrap_lower_bound(
        result.series_records,
        confidence=config.gates.series_crps_one_sided_confidence,
        seed=config.simulation.seeds[0],
    )
    energy_bootstrap = _paired_energy_bootstrap(
        result.joint_records,
        confidence=config.gates.series_crps_one_sided_confidence,
        seed=config.simulation.seeds[1],
    )
    metrics = dict(result.metrics)
    gate_checks = {
        "series_crps_relative_improvement": (
            metrics["series_crps_relative_improvement"] >= config.gates.minimum_series_crps_improvement
        ),
        "series_crps_lower_bound_positive": (crps_bootstrap["one_sided_lower_bound"] > 0.0),
        "joint_energy_point_better": (metrics["joint_energy_relative_improvement"] >= 0.0),
        "joint_energy_upper_noninferior": (
            energy_bootstrap["one_sided_upper_bound"] <= config.gates.maximum_joint_energy_relative_loss
        ),
        "coverage80": (
            config.gates.coverage_80_lower <= metrics["b_coverage80"] <= config.gates.coverage_80_upper
        ),
        "coverage90": (
            config.gates.coverage_90_lower <= metrics["b_coverage90"] <= config.gates.coverage_90_upper
        ),
        "role_crps_noninferior": all(
            float(item["relative_improvement"]) >= -config.gates.maximum_role_crps_relative_loss
            for item in metrics["role_metrics"].values()
        ),
        "team_choice_regret_noninferior": (
            metrics["b_mean_regret"] is not None
            and metrics["v1_mean_regret"] is not None
            and metrics["b_mean_regret"] <= metrics["v1_mean_regret"]
        ),
    }
    payload = {
        "schema_version": 1,
        "kind": "ti2026-main-player-role-confirmation",
        "status": (
            "accuracy-and-calibration-gates-passed"
            if all(gate_checks.values())
            else "accuracy-or-calibration-gate-failed"
        ),
        "config_sha256": config.semantic_hash,
        "selection_sha256": selection["selection_sha256"],
        "selected_parameters": parameters,
        "fold_audit": {
            "training": fold.evidence_build.evidence.audit,
            "holdout": fold.holdout.audit,
        },
        "metrics": metrics,
        "crps_bootstrap": crps_bootstrap,
        "energy_bootstrap": energy_bootstrap,
        "gate_checks": gate_checks,
        "result_sha256": result.semantic_hash,
        "series_records": list(result.series_records),
        "joint_records": list(result.joint_records),
    }
    payload["confirmation_sha256"] = sha256_json(payload)
    _atomic_json(root / "confirmation.json", payload)
    print(
        f"confirmation status={payload['status']} checks={gate_checks}",
        flush=True,
    )
    return payload


def run_experiment(
    config_path: Path,
    *,
    mode: str,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    config = load_main_player_role_generator_config(config_path)
    if mode == "tune":
        return run_tuning(config, paths=paths)
    if mode == "confirm":
        return run_confirmation(config, paths=paths)
    if mode == "all":
        run_tuning(config, paths=paths)
        return run_confirmation(config, paths=paths)
    raise MainPlayerRoleExperimentError(f"unknown experiment mode {mode!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/research/fantasy-main-player-role-generator-v1.json"),
    )
    parser.add_argument("--mode", choices=("tune", "confirm", "all"), default="all")
    arguments = parser.parse_args()
    result = run_experiment(arguments.config, mode=arguments.mode)
    print(json.dumps({"status": result["status"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()


__all__ = [
    "MainPlayerRoleExperimentError",
    "PreparedFold",
    "run_confirmation",
    "run_experiment",
    "run_tuning",
]
