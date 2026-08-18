"""Fixed-rule evaluation for the 10% Series-capped v1/B1 hybrid."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ti_predictor.config import load_rules
from ti_predictor.fantasy.main_player_role_backtest import (
    BacktestResult,
    PlayerRoleHoldout,
    build_hash_fixed_banner_panel,
    build_historical_series_templates,
    build_player_role_holdout,
    evaluate_fold,
)
from ti_predictor.fantasy.main_player_role_generator import (
    PlayerRoleEvidenceBuildResult,
    PlayerRoleGeneratorModel,
    build_player_role_evidence,
    fit_player_role_generator_from_frame,
)
from ti_predictor.fantasy.main_series_quota_hybrid import (
    MainSeriesQuotaHybridConfig,
    QuotaHybridDrawAudit,
    SeriesQuotaHybridSampler,
    load_main_series_quota_hybrid_config,
)
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import source_tree_hash, source_version


class MainSeriesQuotaExperimentError(ValueError):
    """The fixed quota evaluation contract or result is invalid."""


@dataclass(frozen=True)
class QuotaFoldResult:
    fold_id: str
    evidence_build: PlayerRoleEvidenceBuildResult
    holdout: PlayerRoleHoldout
    b1_model: PlayerRoleGeneratorModel
    b1_result: BacktestResult
    hybrid_result: BacktestResult
    draw_audits: tuple[QuotaHybridDrawAudit, ...]


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _artifact_root(
    config: MainSeriesQuotaHybridConfig,
    *,
    paths: ProjectPaths,
) -> Path:
    evidence_paths = main_evidence_paths(paths, require=True)
    identity = sha256_json(
        {
            "config_sha256": config.semantic_hash,
            "snapshot_manifest_sha256": sha256_file(
                evidence_paths.processed / "manifest.json"
            ),
            "source_tree_sha256": source_tree_hash(paths),
        }
    )
    return (
        paths.artifacts
        / "research"
        / "main-series-quota-hybrid"
        / f"{config.as_of:%Y-%m-%d}-{identity[:12]}"
    )


def _fit_b1(
    config: MainSeriesQuotaHybridConfig,
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


def _run_fold(
    config: MainSeriesQuotaHybridConfig,
    fold: Any,
    *,
    rules: Mapping[str, Any],
    panel: tuple[Any, ...],
    paths: ProjectPaths,
) -> QuotaFoldResult:
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
    model = _fit_b1(config, evidence_build)
    evaluation_arguments = {
        "model": model,
        "training_evidence": evidence_build.evidence,
        "holdout": holdout,
        "rules": rules,
        "panel": panel,
        "sample_count": config.simulation.inner_samples_per_path,
        "seeds": config.simulation.seeds,
        "minimum_conditioned_series": config.minimum_conditioned_series,
    }
    b1_result = evaluate_fold(**evaluation_arguments)
    templates = build_historical_series_templates(evidence_build.evidence)
    sampler = SeriesQuotaHybridSampler(
        templates=templates,
        maximum_final_series_mass=config.maximum_final_series_mass,
        minimum_conditioned_series=config.minimum_conditioned_series,
    )
    hybrid_result = evaluate_fold(
        **evaluation_arguments,
        candidate_sampler=sampler,
    )
    return QuotaFoldResult(
        fold_id=fold.fold_id,
        evidence_build=evidence_build,
        holdout=holdout,
        b1_model=model,
        b1_result=b1_result,
        hybrid_result=hybrid_result,
        draw_audits=tuple(sampler.audits),
    )


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    numeric = np.asarray(values, dtype=float)
    mass = np.asarray(weights, dtype=float)
    if len(numeric) != len(mass) or not len(numeric) or mass.sum() <= 0.0:
        raise MainSeriesQuotaExperimentError("quota aggregate input is invalid")
    return float(np.dot(numeric, mass / mass.sum()))


def _aggregate_metrics(folds: Sequence[QuotaFoldResult]) -> dict[str, Any]:
    projection_weights = [
        float(item.hybrid_result.metrics["series_projection_records"])
        for item in folds
    ]
    joint_weights = [float(item.hybrid_result.metrics["joint_games"]) for item in folds]

    def metric(label: str, key: str, *, joint: bool = False) -> float:
        results = [
            item.hybrid_result if label == "hybrid" else item.b1_result for item in folds
        ]
        return _weighted_mean(
            [float(result.metrics[key]) for result in results],
            joint_weights if joint else projection_weights,
        )

    hybrid_energy = metric("hybrid", "b_joint_energy", joint=True)
    b1_energy = metric("b1", "b_joint_energy", joint=True)
    hybrid_crps = metric("hybrid", "b_series_crps")
    b1_crps = metric("b1", "b_series_crps")
    common_hybrid_energy = metric("hybrid", "common_b_joint_energy", joint=True)
    v1_energy = metric("hybrid", "v1_joint_energy", joint=True)
    common_hybrid_crps = metric("hybrid", "common_b_series_crps")
    v1_crps = metric("hybrid", "v1_series_crps")
    return {
        "fold_count": len(folds),
        "joint_games": int(sum(joint_weights)),
        "series_projection_records": int(sum(projection_weights)),
        "hybrid_joint_energy": hybrid_energy,
        "b1_joint_energy": b1_energy,
        "hybrid_energy_relative_improvement_vs_b1": (b1_energy - hybrid_energy)
        / max(b1_energy, 1e-12),
        "common_hybrid_joint_energy": common_hybrid_energy,
        "v1_joint_energy": v1_energy,
        "hybrid_energy_relative_improvement_vs_v1": (v1_energy - common_hybrid_energy)
        / max(v1_energy, 1e-12),
        "hybrid_series_crps": hybrid_crps,
        "b1_series_crps": b1_crps,
        "hybrid_crps_relative_improvement_vs_b1": (b1_crps - hybrid_crps)
        / max(b1_crps, 1e-12),
        "common_hybrid_series_crps": common_hybrid_crps,
        "v1_series_crps": v1_crps,
        "hybrid_crps_relative_improvement_vs_v1": (v1_crps - common_hybrid_crps)
        / max(v1_crps, 1e-12),
        "hybrid_coverage80": metric("hybrid", "b_coverage80"),
        "hybrid_coverage90": metric("hybrid", "b_coverage90"),
        "b1_coverage80": metric("b1", "b_coverage80"),
        "b1_coverage90": metric("b1", "b_coverage90"),
        "hybrid_mean_regret": metric("hybrid", "b_mean_regret"),
        "b1_mean_regret": metric("b1", "b_mean_regret"),
        "v1_mean_regret": metric("hybrid", "v1_mean_regret"),
    }


def _record_frame(
    folds: Sequence[QuotaFoldResult],
    *,
    label: str,
    kind: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in folds:
        result = item.hybrid_result if label == "hybrid" else item.b1_result
        source = result.series_records if kind == "series" else result.joint_records
        rows.extend({"fold_id": item.fold_id, **dict(row)} for row in source)
    return pd.DataFrame(rows)


def _bootstrap_upper(
    values: np.ndarray,
    *,
    confidence: float,
    seed: int,
    replicates: int = 10_000,
) -> dict[str, Any]:
    numeric = np.asarray(values, dtype=float).reshape(-1)
    rng = np.random.default_rng(int(seed))
    indexes = rng.integers(0, len(numeric), size=(replicates, len(numeric)))
    distribution = numeric[indexes].mean(axis=1)
    return {
        "blocks": len(numeric),
        "mean_relative_loss": float(numeric.mean()),
        "one_sided_upper_bound": float(np.quantile(distribution, confidence)),
        "confidence": confidence,
        "replicates": replicates,
    }


def _paired_statistics(
    folds: Sequence[QuotaFoldResult],
    *,
    config: MainSeriesQuotaHybridConfig,
) -> dict[str, Any]:
    hybrid_joint = _record_frame(folds, label="hybrid", kind="joint")
    b1_joint = _record_frame(folds, label="b1", kind="joint").rename(
        columns={"b_energy": "b1_energy"}
    )
    joint = hybrid_joint.merge(
        b1_joint[
            ["fold_id", "match_id", "series_id", "team_id", "b1_energy"]
        ],
        on=["fold_id", "match_id", "series_id", "team_id"],
        validate="one_to_one",
    )
    b1_loss = (
        joint.assign(
            relative_loss=(joint["b_energy"] - joint["b1_energy"])
            / joint["b1_energy"].clip(lower=1e-12)
        )
        .groupby(["fold_id", "series_id"], sort=True)["relative_loss"]
        .mean()
        .to_numpy(dtype=float)
    )
    common = joint.dropna(subset=["v1_energy"])
    v1_loss = (
        common.assign(
            relative_loss=(common["b_energy"] - common["v1_energy"])
            / common["v1_energy"].clip(lower=1e-12)
        )
        .groupby(["fold_id", "series_id"], sort=True)["relative_loss"]
        .mean()
        .to_numpy(dtype=float)
    )
    return {
        "joint_energy_vs_b1": _bootstrap_upper(
            b1_loss,
            confidence=0.95,
            seed=config.simulation.seeds[0],
        ),
        "joint_energy_vs_v1": _bootstrap_upper(
            v1_loss,
            confidence=0.95,
            seed=config.simulation.seeds[1],
        ),
    }


def _concentration(audits: Sequence[QuotaHybridDrawAudit]) -> dict[str, Any]:
    by_team: dict[int, list[QuotaHybridDrawAudit]] = {}
    for audit in audits:
        by_team.setdefault(audit.team_id, []).append(audit)
    teams: dict[str, Any] = {}
    for team_id, items in sorted(by_team.items()):
        series_denominator = sum(item.draws for item in items)
        game_denominator = sum(
            item.draws * item.future_games_per_draw for item in items
        )
        primary: Counter[int] = Counter()
        actual_series: Counter[str] = Counter()
        games: Counter[str] = Counter()
        for item in items:
            primary.update(item.primary_series_counts)
            games.update(item.actual_game_source_counts)
            for key, count in item.actual_game_source_counts.items():
                actual_series[key.split(":", maxsplit=1)[0]] += count
        teams[str(team_id)] = {
            "contexts": len(items),
            "mean_theoretical_v1_mass": sum(
                item.draws * item.theoretical_v1_mass for item in items
            )
            / series_denominator,
            "mean_theoretical_b1_mass": sum(
                item.draws * item.theoretical_b1_mass for item in items
            )
            / series_denominator,
            "maximum_theoretical_primary_series_mass": max(
                item.theoretical_max_primary_series_mass for item in items
            ),
            "maximum_realized_primary_series_share": (
                max(primary.values(), default=0) / series_denominator
            ),
            "maximum_realized_actual_game_share": (
                max(games.values(), default=0) / game_denominator
            ),
            "maximum_realized_actual_series_share": (
                max(actual_series.values(), default=0) / game_denominator
            ),
            "realized_v1_share": sum(item.realized_v1_draws for item in items)
            / series_denominator,
            "series_draws": series_denominator,
            "game_draws": game_denominator,
        }
    all_items = list(audits)
    total_draws = sum(item.draws for item in all_items)
    return {
        "draw_contexts": len(all_items),
        "draws": total_draws,
        "maximum_theoretical_primary_series_mass": max(
            item.theoretical_max_primary_series_mass for item in all_items
        ),
        "mean_theoretical_v1_mass": sum(
            item.draws * item.theoretical_v1_mass for item in all_items
        )
        / total_draws,
        "mean_theoretical_b1_mass": sum(
            item.draws * item.theoretical_b1_mass for item in all_items
        )
        / total_draws,
        "teams": teams,
    }


def _panel_payload(
    folds: Sequence[QuotaFoldResult],
    *,
    config: MainSeriesQuotaHybridConfig,
    kind: str,
) -> dict[str, Any]:
    metrics = _aggregate_metrics(folds)
    paired = _paired_statistics(folds, config=config)
    concentration = _concentration(
        [audit for item in folds for audit in item.draw_audits]
    )
    payload = {
        "kind": kind,
        "metrics": metrics,
        "paired_statistics": paired,
        "concentration": concentration,
        "folds": [
            {
                "fold_id": item.fold_id,
                "training_audit": item.evidence_build.evidence.audit,
                "holdout_audit": item.holdout.audit,
                "hybrid_metrics": dict(item.hybrid_result.metrics),
                "b1_metrics": dict(item.b1_result.metrics),
                "hybrid_result_sha256": item.hybrid_result.semantic_hash,
                "b1_result_sha256": item.b1_result.semantic_hash,
                "draw_audits": [asdict(audit) for audit in item.draw_audits],
            }
            for item in folds
        ],
    }
    payload["semantic_hash"] = sha256_json(payload)
    return payload


def run_experiment(
    config_path: Path,
    *,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    config = load_main_series_quota_hybrid_config(config_path)
    root = _artifact_root(config, paths=paths)
    root.mkdir(parents=True, exist_ok=True)
    rules = load_rules(paths.rules)
    panel = build_hash_fixed_banner_panel(rules)
    evaluation: list[QuotaFoldResult] = []
    for index, fold in enumerate(config.evaluation_folds, start=1):
        print(f"[quota hybrid] evaluation {index}/{len(config.evaluation_folds)} {fold.fold_id}", flush=True)
        evaluation.append(
            _run_fold(config, fold, rules=rules, panel=panel, paths=paths)
        )
    evaluation_payload = _panel_payload(
        evaluation,
        config=config,
        kind="fixed-10-percent-series-quota-retrospective-evaluation",
    )
    _atomic_json(root / "evaluation.json", evaluation_payload)
    print("[quota hybrid] TI consumed diagnostic", flush=True)
    diagnostic_fold = _run_fold(
        config,
        config.diagnostic_fold,
        rules=rules,
        panel=panel,
        paths=paths,
    )
    diagnostic_payload = _panel_payload(
        [diagnostic_fold],
        config=config,
        kind="fixed-10-percent-series-quota-consumed-ti-diagnostic",
    )
    _atomic_json(root / "diagnostic-ti-consumed.json", diagnostic_payload)
    result = {
        "schema_version": 1,
        "kind": "ti2026-main-fixed-series-quota-hybrid-result",
        "status": "research-only-fixed-rule-evaluation-complete",
        "config": config.model_dump(mode="json"),
        "config_sha256": config.semantic_hash,
        "source_version": source_version(paths),
        "source_tree_sha256": source_tree_hash(paths),
        "artifact_root": str(root.resolve()),
        "evaluation": evaluation_payload,
        "diagnostic": diagnostic_payload,
    }
    result["result_sha256"] = sha256_json(result)
    _atomic_json(root / "result.json", result)
    print(json.dumps({"status": result["status"]}, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/research/fantasy-main-series-quota-hybrid-v1.json"),
    )
    arguments = parser.parse_args()
    run_experiment(arguments.config)


if __name__ == "__main__":
    main()


__all__ = ["MainSeriesQuotaExperimentError", "QuotaFoldResult", "run_experiment"]
