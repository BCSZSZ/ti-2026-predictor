"""Build the immutable V1/B1/hybrid Main terminal Forecast archive."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field, field_validator, model_validator

from ti_predictor.config import load_rules
from ti_predictor.fantasy.main_conditional_truth import (
    GAME_TEMPLATE_SENTINEL,
    MAX_SERIES_GAMES,
    RESULT_CODE,
    SERIES_NODE_COUNT,
    SERIES_SIDE_COUNT,
    JointGameTemplateSet,
    MainConditionalTruthConfig,
    _array_sha256,
    _ConditionalSampler,
    legal_series_sequences,
    opponent_strength_band,
)
from ti_predictor.fantasy.main_multi_forecast import (
    MAIN_FORECAST_ARTIFACT_TYPE,
    MAIN_FORECAST_MODELS,
)
from ti_predictor.fantasy.main_player_role_generator import (
    PlayerRoleGeneratorModel,
    build_player_role_evidence,
    fit_player_role_generator_from_frame,
)
from ti_predictor.forecasting import load_strength_model_as_of
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.runs import source_tree_hash, source_version
from ti_predictor.schemas import StrictModel, as_utc


class MainMultiForecastBuildError(ValueError):
    """The formal three-model evidence build cannot be reproduced safely."""


class FrozenB1BuildParameters(StrictModel):
    ridge_alpha: float = Field(gt=0.0)
    recent_effective_sample_constant: float = Field(gt=0.0)
    recent_residual_cap_sigma: float = Field(gt=0.0)
    factor_rank: int = Field(ge=1)
    covariance_shrinkage: float = Field(ge=0.0, le=1.0)
    latent_scale: float = Field(gt=0.0)
    maximum_game_parameter_mass: float = Field(gt=0.0, le=1.0)
    maximum_series_parameter_mass: float = Field(gt=0.0, le=1.0)
    maximum_residual_game_mass: float = Field(gt=0.0, le=1.0)
    maximum_residual_series_mass: float = Field(gt=0.0, le=1.0)


class MainMultiForecastBuildConfig(StrictModel):
    schema_version: Literal[1]
    release_id: Literal["ti2026-main-parallel-fantasy-forecast-v1"]
    period: Literal["main"]
    as_of: datetime
    source_v1_manifest_sha256: str
    models: list[str]
    seeds: list[int] = Field(min_length=1, max_length=8)
    inner_samples_per_path: int = Field(ge=1, le=64)
    synthetic_samples_per_context: int = Field(ge=2, le=64)
    maximum_final_series_mass: float = Field(gt=0.0, lt=1.0)
    minimum_conditioned_series: int = Field(ge=1, le=20)
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    b1: FrozenB1BuildParameters

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        cutoff = as_utc(value)
        if cutoff is None:
            raise ValueError("parallel Forecast build requires explicit UTC as_of")
        return cutoff

    @model_validator(mode="after")
    def validate_contract(self) -> MainMultiForecastBuildConfig:
        if tuple(self.models) != MAIN_FORECAST_MODELS:
            raise ValueError("parallel Forecast models must retain the frozen display order")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("parallel Forecast seeds must be unique")
        if len(self.source_v1_manifest_sha256) != 64:
            raise ValueError("parallel Forecast source v1 manifest hash is invalid")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


@dataclass(frozen=True, order=True)
class SyntheticGameContext:
    team_index: int
    opponent_index: int
    won_game: int
    best_of: int
    series_won: int
    series_length: int
    game_index: int


@dataclass(frozen=True)
class SyntheticTemplateBank:
    scores: np.ndarray
    template_ids: Mapping[SyntheticGameContext, np.ndarray]
    audit: Mapping[str, Any]


def load_main_multi_forecast_build_config(path: Path) -> MainMultiForecastBuildConfig:
    return MainMultiForecastBuildConfig.model_validate_json(path.read_text(encoding="utf-8"))


def _validate_source_v1(
    root: Path,
    config: MainMultiForecastBuildConfig,
) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    checksums_path = root / "checksums.json"
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise MainMultiForecastBuildError("source v1 evidence is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed = manifest.pop("manifest_sha256", None)
    if claimed != sha256_json(manifest) or claimed != config.source_v1_manifest_sha256:
        raise MainMultiForecastBuildError("source v1 manifest identity differs from frozen config")
    manifest["manifest_sha256"] = claimed
    if (
        manifest.get("artifact_type") != "ti2026-main-conditional-truth-evidence"
        or manifest.get("as_of") != config.as_of.isoformat().replace("+00:00", "Z")
        or tuple(manifest.get("team_ids", ())) == ()
        or tuple(manifest.get("config", {}).get("seeds", ())) != tuple(config.seeds)
        or int(manifest.get("inner_samples_per_path", 0)) != config.inner_samples_per_path
    ):
        raise MainMultiForecastBuildError("source v1 contract differs from parallel Forecast config")
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    for name, expected in checksums.items():
        path = root / str(name)
        if not path.is_file() or sha256_file(path) != str(expected):
            raise MainMultiForecastBuildError(f"source v1 checksum failed: {name}")
    return manifest


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {name: np.asarray(payload[name]) for name in payload.files}


def _joint_templates(
    root: Path,
    manifest: Mapping[str, Any],
) -> JointGameTemplateSet:
    arrays = _load_npz(root / "templates.npz")
    return JointGameTemplateSet(
        team_ids=tuple(int(value) for value in manifest["team_ids"]),
        stat_ids=tuple(str(value) for value in manifest["stat_ids"]),
        audit=json.loads((root / "pool-audit.json").read_text(encoding="utf-8")),
        semantic_hash=str(manifest["provenance"]["template_semantic_hash"]),
        **arrays,
    )


def _fit_frozen_b1(
    config: MainMultiForecastBuildConfig,
    *,
    paths: ProjectPaths,
) -> tuple[PlayerRoleGeneratorModel, Mapping[str, Any], Any]:
    evidence = build_player_role_evidence(
        training_cutoff=config.as_of,
        available_as_of=config.as_of,
        paths=paths,
    )
    parameters = config.b1
    model = fit_player_role_generator_from_frame(
        evidence.evidence,
        ridge_alpha=parameters.ridge_alpha,
        recent_effective_sample_constant=parameters.recent_effective_sample_constant,
        recent_residual_cap_sigma=parameters.recent_residual_cap_sigma,
        factor_rank=parameters.factor_rank,
        covariance_shrinkage=parameters.covariance_shrinkage,
        latent_scale=parameters.latent_scale,
        maximum_game_parameter_mass=parameters.maximum_game_parameter_mass,
        maximum_series_parameter_mass=parameters.maximum_series_parameter_mass,
        maximum_residual_game_mass=parameters.maximum_residual_game_mass,
        maximum_residual_series_mass=parameters.maximum_residual_series_mass,
    )
    return model, evidence.evidence.audit, evidence.strength_model


def _prediction_semantic_hash(model: Any) -> str:
    """Hash only fields that can affect ``predict``.

    The rolling fit does not retain a rejected calibration candidate, while the
    frozen publication loader preserves it for audit.  When calibration was not
    accepted that candidate is deliberately excluded from prediction identity.
    """

    payload = dict(model.as_dict())
    if not bool(payload.get("calibration_accepted")):
        payload.pop("calibration_candidate", None)
    return sha256_json(payload)


def _all_contexts(
    team_ids: tuple[int, ...],
    strength_model: Any,
) -> tuple[SyntheticGameContext, ...]:
    contexts: set[SyntheticGameContext] = set()
    for team_index, team_id in enumerate(team_ids):
        for opponent_index, opponent_id in enumerate(team_ids):
            if team_index == opponent_index:
                continue
            probability = float(strength_model.predict(team_id, opponent_id))
            for best_of in (3, 5):
                for series_won in (0, 1):
                    sequences, _ = legal_series_sequences(
                        probability,
                        best_of=best_of,
                        target_wins=bool(series_won),
                    )
                    for sequence in sequences:
                        for game_index, won_game in enumerate(sequence):
                            contexts.add(
                                SyntheticGameContext(
                                    team_index,
                                    opponent_index,
                                    int(won_game),
                                    best_of,
                                    series_won,
                                    len(sequence),
                                    game_index,
                                )
                            )
    return tuple(sorted(contexts))


def _derived_seed(base: int, label: str) -> int:
    digest = hashlib.sha256(f"{base}:main-parallel-forecast:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _score_generated_stats(
    raw: np.ndarray,
    stat_ids: tuple[str, ...],
    rules: Mapping[str, Any],
) -> np.ndarray:
    values = np.asarray(raw, dtype=np.float32)
    result = np.empty_like(values)
    for index, stat_id in enumerate(stat_ids):
        rule = rules["fantasy"]["stats"][stat_id]
        source = values[..., index]
        if rule["mode"] == "linear":
            scored = source * float(rule["factor"])
        elif rule["mode"] == "inverse":
            scored = float(rule["base"]) - source * float(rule["factor"])
            scored = np.maximum(float(rule.get("floor", -np.inf)), scored)
        else:
            raise MainMultiForecastBuildError(f"unknown Fantasy score mode: {rule['mode']}")
        if "cap" in rule:
            scored = np.minimum(float(rule["cap"]), scored)
        result[..., index] = scored
    if np.any(result < 0.0) or not np.isfinite(result).all():
        raise MainMultiForecastBuildError("B1 synthetic score templates are invalid")
    return result


def build_synthetic_template_bank(
    model: PlayerRoleGeneratorModel,
    *,
    team_ids: tuple[int, ...],
    strength_model: Any,
    historical_template_count: int,
    samples_per_context: int,
    base_seed: int,
    rules: Mapping[str, Any],
) -> SyntheticTemplateBank:
    contexts = _all_contexts(team_ids, strength_model)
    generated: list[np.ndarray] = []
    identities: dict[SyntheticGameContext, np.ndarray] = {}
    for context_index, context in enumerate(contexts):
        probability = float(
            strength_model.predict(
                team_ids[context.team_index],
                team_ids[context.opponent_index],
            )
        )
        rng = np.random.default_rng(
            _derived_seed(base_seed, f"synthetic-context:{context_index}:{context}")
        )
        durations = model.sample_durations(
            opponent_probability=probability,
            won_game=bool(context.won_game),
            best_of=context.best_of,
            series_won=bool(context.series_won),
            series_length=context.series_length,
            game_index=context.game_index,
            size=samples_per_context,
            rng=rng,
        )
        raw = model.sample_team_games(
            team_id=team_ids[context.team_index],
            opponent_probability=probability,
            won_game=bool(context.won_game),
            best_of=context.best_of,
            series_won=bool(context.series_won),
            series_length=context.series_length,
            game_index=context.game_index,
            durations=durations,
            rng=rng,
        )
        scored = _score_generated_stats(raw, model.stat_ids, rules)
        start = historical_template_count + context_index * samples_per_context
        identities[context] = np.arange(start, start + samples_per_context, dtype=np.uint16)
        generated.append(scored)
    scores = np.concatenate(generated, axis=0).astype(np.float32)
    if historical_template_count + len(scores) >= int(GAME_TEMPLATE_SENTINEL):
        raise MainMultiForecastBuildError("combined v1/B1 template bank exceeds uint16 identity space")
    return SyntheticTemplateBank(
        scores=scores,
        template_ids=identities,
        audit={
            "context_count": len(contexts),
            "samples_per_context": samples_per_context,
            "synthetic_template_count": len(scores),
            "historical_template_count": historical_template_count,
            "combined_template_count": historical_template_count + len(scores),
            "scores_sha256": _array_sha256(scores),
        },
    )


def _assign_b1_ids(
    *,
    participants: np.ndarray,
    winners: np.ndarray,
    shared_left_results: np.ndarray,
    bank: SyntheticTemplateBank,
    seed: int,
) -> np.ndarray:
    inner, path_count = shared_left_results.shape[:2]
    result = np.full(
        (inner, path_count, SERIES_NODE_COUNT, SERIES_SIDE_COUNT, MAX_SERIES_GAMES),
        GAME_TEMPLATE_SENTINEL,
        dtype=np.uint16,
    )
    rng = np.random.default_rng(_derived_seed(seed, "b1-template-draws"))
    for node in range(SERIES_NODE_COUNT):
        best_of = 5 if node == SERIES_NODE_COUNT - 1 else 3
        for side in range(SERIES_SIDE_COUNT):
            team_by_path = participants[:, node, side]
            opponent_by_path = participants[:, node, 1 - side]
            series_won_by_path = (team_by_path == winners[:, node]).astype(np.int8)
            side_results = shared_left_results[:, :, node]
            if side == 1:
                side_results = np.where(side_results < 0, -1, 1 - side_results)
            lengths = (side_results >= 0).sum(axis=2)
            for team_index in np.unique(team_by_path):
                for opponent_index in np.unique(opponent_by_path[team_by_path == team_index]):
                    pair = (team_by_path == team_index) & (opponent_by_path == opponent_index)
                    for series_won in (0, 1):
                        path_indexes = np.flatnonzero(pair & (series_won_by_path == series_won))
                        if not len(path_indexes):
                            continue
                        for game_index in range(best_of):
                            game_results = side_results[:, path_indexes, game_index]
                            local_lengths = lengths[:, path_indexes]
                            for series_length in range(best_of // 2 + 1, best_of + 1):
                                for won_game in (0, 1):
                                    positions = np.argwhere(
                                        (local_lengths == series_length) & (game_results == won_game)
                                    )
                                    if not len(positions):
                                        continue
                                    context = SyntheticGameContext(
                                        int(team_index),
                                        int(opponent_index),
                                        won_game,
                                        best_of,
                                        series_won,
                                        series_length,
                                        game_index,
                                    )
                                    choices = bank.template_ids[context]
                                    selected = rng.choice(choices, size=len(positions), replace=True)
                                    result[
                                        positions[:, 0],
                                        path_indexes[positions[:, 1]],
                                        node,
                                        side,
                                        game_index,
                                    ] = selected
    expected_valid = np.repeat(
        shared_left_results[..., None, :] >= 0,
        SERIES_SIDE_COUNT,
        axis=3,
    )
    if not np.array_equal(result != GAME_TEMPLATE_SENTINEL, expected_valid):
        raise MainMultiForecastBuildError("B1 draw panel does not preserve legal Series lengths")
    return result


def _hybridize_ids(
    *,
    v1_ids: np.ndarray,
    b1_ids: np.ndarray,
    source_series: np.ndarray,
    participants: np.ndarray,
    winners: np.ndarray,
    historical: JointGameTemplateSet,
    strength_model: Any,
    source_config: MainConditionalTruthConfig,
    maximum_final_series_mass: float,
    seed: int,
) -> tuple[np.ndarray, Mapping[str, Any]]:
    result = b1_ids.copy()
    sampler = _ConditionalSampler(historical, source_config)
    rng = np.random.default_rng(_derived_seed(seed, "hybrid-component-draws"))
    kept_series_sides = 0
    total_series_sides = int(np.prod(source_series.shape))
    copied_games = 0
    cross_series_fallback_games = 0
    retained_sources: Counter[int] = Counter()
    for node in range(SERIES_NODE_COUNT):
        best_of = 5 if node == SERIES_NODE_COUNT - 1 else 3
        for side in range(SERIES_SIDE_COUNT):
            team_by_path = participants[:, node, side]
            opponent_by_path = participants[:, node, 1 - side]
            series_won_by_path = (team_by_path == winners[:, node]).astype(np.int8)
            for team_index in np.unique(team_by_path):
                for opponent_index in np.unique(opponent_by_path[team_by_path == team_index]):
                    pair = (team_by_path == team_index) & (opponent_by_path == opponent_index)
                    probability = float(
                        strength_model.predict(
                            historical.team_ids[int(team_index)],
                            historical.team_ids[int(opponent_index)],
                        )
                    )
                    band = opponent_strength_band(
                        probability,
                        source_config.opponent_probability_boundaries,
                    )
                    for series_won in (RESULT_CODE["loss"], RESULT_CODE["win"]):
                        path_indexes = np.flatnonzero(pair & (series_won_by_path == series_won))
                        if not len(path_indexes):
                            continue
                        candidates, _ = sampler.series_candidates(
                            int(team_index),
                            best_of,
                            series_won,
                            band,
                        )
                        weights = historical.series_weights[candidates].astype(float)
                        probabilities = weights / weights.sum()
                        retained = np.minimum(probabilities, maximum_final_series_mass)
                        keep_by_source = np.zeros(len(historical.series_ids), dtype=float)
                        keep_by_source[candidates] = retained / probabilities
                        selected_sources = source_series[:, path_indexes, node, side]
                        keep = rng.random(selected_sources.shape) < keep_by_source[selected_sources]
                        kept_series_sides += int(keep.sum())
                        for source_index, count in zip(
                            *np.unique(selected_sources[keep], return_counts=True),
                            strict=True,
                        ):
                            retained_sources[int(source_index)] += int(count)
                        for game_index in range(best_of):
                            historical_ids = v1_ids[:, path_indexes, node, side, game_index]
                            valid = historical_ids != GAME_TEMPLATE_SENTINEL
                            safe = np.where(valid, historical_ids, 0).astype(np.int64)
                            same_source = historical.game_series_indexes[safe] == selected_sources
                            use_historical = keep & valid & same_source
                            target = result[:, path_indexes, node, side, game_index]
                            target[use_historical] = historical_ids[use_historical]
                            result[:, path_indexes, node, side, game_index] = target
                            copied_games += int(use_historical.sum())
                            cross_series_fallback_games += int((keep & valid & ~same_source).sum())
    if not np.array_equal(
        result != GAME_TEMPLATE_SENTINEL,
        v1_ids != GAME_TEMPLATE_SENTINEL,
    ):
        raise MainMultiForecastBuildError("hybrid draw panel changed legal Series lengths")
    return result, {
        "maximum_final_series_mass": maximum_final_series_mass,
        "total_series_side_draws": total_series_sides,
        "retained_v1_series_side_draws": kept_series_sides,
        "retained_v1_series_side_rate": kept_series_sides / total_series_sides,
        "v1_game_draws": copied_games,
        "b1_game_draws": int((result != GAME_TEMPLATE_SENTINEL).sum()) - copied_games,
        "cross_series_game_fallbacks_to_b1": cross_series_fallback_games,
        "maximum_realized_source_series_side_share": (
            max(retained_sources.values(), default=0) / total_series_sides
        ),
    }


def _atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.npz")
    np.savez_compressed(temporary, **arrays)
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_deterministic_zip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            name = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, path.read_bytes())
    os.replace(temporary, destination)


def build_main_multi_forecast_release(
    config: MainMultiForecastBuildConfig,
    *,
    source_v1_root: Path,
    output_root: Path,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    """Promote frozen research inputs into a checksummed Web-consumable archive."""

    source_root = source_v1_root.resolve()
    source_manifest = _validate_source_v1(source_root, config)
    historical = _joint_templates(source_root, source_manifest)
    outer = _load_npz(source_root / "outer-paths.npz")
    participants = np.asarray(outer["participants"], dtype=np.int16)
    winners = np.asarray(outer["winners"], dtype=np.int16)
    probabilities = np.asarray(outer["probabilities"], dtype=float)
    evidence_paths = main_evidence_paths(paths, require=True)
    b1_model, b1_evidence_audit, b1_training_strength_model = _fit_frozen_b1(
        config,
        paths=paths,
    )
    strength_model, strength_report = load_strength_model_as_of(
        as_of=config.as_of,
        paths=evidence_paths,
        period="main",
    )
    blocking = [issue.message for issue in strength_report.issues if issue.severity == "blocking"]
    if blocking:
        raise MainMultiForecastBuildError(
            "frozen Team-strength evidence is blocked: " + "; ".join(blocking)
        )
    model_sha256 = sha256_json(strength_model.as_dict())
    if model_sha256 != source_manifest["provenance"]["model_sha256"]:
        raise MainMultiForecastBuildError("source v1 and frozen Team-strength model differ")
    if _prediction_semantic_hash(b1_training_strength_model) != _prediction_semantic_hash(
        strength_model
    ):
        raise MainMultiForecastBuildError("B1 and source v1 use different Team-strength predictions")
    if tuple(b1_model.stat_ids) != historical.stat_ids:
        raise MainMultiForecastBuildError("B1 and source v1 use different Fantasy Stat order")
    rules = load_rules(evidence_paths.rules)
    bank = build_synthetic_template_bank(
        b1_model,
        team_ids=historical.team_ids,
        strength_model=strength_model,
        historical_template_count=len(historical.scores),
        samples_per_context=config.synthetic_samples_per_context,
        base_seed=config.seeds[0],
        rules=rules,
    )
    combined_scores = np.concatenate((historical.scores, bank.scores), axis=0).astype(np.float32)
    identity = sha256_json(
        {
            "config_sha256": config.semantic_hash,
            "source_v1_manifest_sha256": config.source_v1_manifest_sha256,
            "b1_model_sha256": b1_model.semantic_hash,
            "source_tree_sha256": source_tree_hash(paths),
        }
    )
    root = output_root.resolve() / f"main-parallel-forecast-{identity[:12]}"
    root.mkdir(parents=True, exist_ok=True)
    _atomic_npz(root / "templates.npz", scores=combined_scores)
    _atomic_npz(
        root / "outer-paths.npz",
        participants=participants,
        winners=winners,
        probabilities=probabilities,
    )
    source_config = MainConditionalTruthConfig.model_validate(source_manifest["config"])
    seed_audits = []
    for seed in config.seeds:
        source_draws = _load_npz(source_root / f"draws-{seed}.npz")
        v1_ids = np.asarray(source_draws["game_template_ids"], dtype=np.uint16)
        shared = np.asarray(source_draws["shared_left_game_results"], dtype=np.int8)
        source_series = np.asarray(source_draws["source_series_indexes"], dtype=np.int16)
        b1_ids = _assign_b1_ids(
            participants=participants,
            winners=winners,
            shared_left_results=shared,
            bank=bank,
            seed=seed,
        )
        hybrid_ids, hybrid_audit = _hybridize_ids(
            v1_ids=v1_ids,
            b1_ids=b1_ids,
            source_series=source_series,
            participants=participants,
            winners=winners,
            historical=historical,
            strength_model=strength_model,
            source_config=source_config,
            maximum_final_series_mass=config.maximum_final_series_mass,
            seed=seed,
        )
        arrays = {
            MAIN_FORECAST_MODELS[0]: v1_ids,
            MAIN_FORECAST_MODELS[1]: b1_ids,
            MAIN_FORECAST_MODELS[2]: hybrid_ids,
        }
        for model_id, game_ids in arrays.items():
            _atomic_npz(
                root / f"draws-{model_id}-{seed}.npz",
                game_template_ids=game_ids,
            )
        seed_audits.append(
            {
                "seed": seed,
                "v1_game_template_ids_sha256": _array_sha256(v1_ids),
                "b1_game_template_ids_sha256": _array_sha256(b1_ids),
                "hybrid_game_template_ids_sha256": _array_sha256(hybrid_ids),
                "hybrid": hybrid_audit,
            }
        )
        _atomic_json(root / f"seed-{seed}-audit.json", seed_audits[-1])
        del source_draws, v1_ids, shared, source_series, b1_ids, hybrid_ids
    limitations = [
        "三套结果都是截至 as_of 的模型预测，不是未来比赛真值，也不自动替用户投票。",
        (
            "V1 保留历史完整五人 Game 模板；B1 条件合成未来表现；"
            "混合把每个 V1 来源 Series 的最终概率质量限制为 10%。"
        ),
        "双败路径穷举 16,384 条；每条路径 16 个 Fantasy 内层样本并用 3 个独立种子重复。",
        "赛制结果使用冻结 Team-strength 模型；BO3/BO5 每轮比分与 Game 结果在每个样本中保持合法一致。",
        "Title 使用当前 Main 运行时的独立边际证据，并按每套模型各自选择的三队重新排名。",
    ]
    manifest = {
        "schema_version": 1,
        "artifact_type": MAIN_FORECAST_ARTIFACT_TYPE,
        "release_id": config.release_id,
        "status": "ready",
        "web_integration": True,
        "runtime_pointer_writes": False,
        "as_of": config.as_of.isoformat().replace("+00:00", "Z"),
        "team_ids": list(historical.team_ids),
        "stat_ids": list(historical.stat_ids),
        "seeds": list(config.seeds),
        "inner_samples_per_path": config.inner_samples_per_path,
        "outer_path_count": len(probabilities),
        "weighted_scenario_count": (
            len(probabilities) * config.inner_samples_per_path * len(config.seeds)
        ),
        "cvar_alpha": config.cvar_alpha,
        "models": [
            {
                "model_id": MAIN_FORECAST_MODELS[0],
                "evidence_status": "published-comparison",
                "method": "weighted-result-conditioned-joint-five-player-historical-template",
            },
            {
                "model_id": MAIN_FORECAST_MODELS[1],
                "evidence_status": "published-comparison",
                "method": "frozen-player-role-conditional-generator-b1",
            },
            {
                "model_id": MAIN_FORECAST_MODELS[2],
                "evidence_status": "published-comparison",
                "method": "v1-source-series-mass-capped-at-0.10-remainder-to-b1",
            },
        ],
        "config": config.model_dump(mode="json"),
        "provenance": {
            "source_version": source_version(paths),
            "source_tree_sha256": source_tree_hash(paths),
            "source_v1_manifest_sha256": config.source_v1_manifest_sha256,
            "source_v1_archive_files_sha256": sha256_json(
                json.loads((source_root / "checksums.json").read_text(encoding="utf-8"))
            ),
            "main_snapshot_manifest_sha256": sha256_file(evidence_paths.processed / "manifest.json"),
            "rules_sha256": sha256_file(evidence_paths.rules),
            "team_strength_model_sha256": model_sha256,
            "team_strength_prediction_semantic_sha256": _prediction_semantic_hash(
                strength_model
            ),
            "b1_training_strength_model_sha256": sha256_json(
                b1_training_strength_model.as_dict()
            ),
            "b1_model_sha256": b1_model.semantic_hash,
            "b1_evidence_audit_sha256": sha256_json(b1_evidence_audit),
            "historical_template_scores_sha256": _array_sha256(historical.scores),
            "synthetic_template_bank": dict(bank.audit),
            "combined_template_scores_sha256": _array_sha256(combined_scores),
        },
        "seed_audits": seed_audits,
        "limitations": limitations,
    }
    checked = sorted(
        path.relative_to(root).as_posix()
        for path in root.iterdir()
        if path.is_file() and path.name not in {"manifest.json", "checksums.json"}
    )
    checksums = {name: sha256_file(root / name) for name in checked}
    _atomic_json(root / "checksums.json", checksums)
    manifest["manifest_sha256"] = sha256_json(manifest)
    _atomic_json(root / "manifest.json", manifest)
    archive = output_root.resolve() / f"main-parallel-forecast-{manifest['manifest_sha256'][:12]}.zip"
    _write_deterministic_zip(root, archive)
    return {
        "artifact_root": str(root),
        "archive_path": str(archive),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha256_file(archive),
        "manifest_sha256": manifest["manifest_sha256"],
        "as_of": manifest["as_of"],
        "models": list(MAIN_FORECAST_MODELS),
        "weighted_scenario_count_per_model": manifest["weighted_scenario_count"],
        "b1_model_sha256": b1_model.semantic_hash,
    }


__all__ = [
    "FrozenB1BuildParameters",
    "MainMultiForecastBuildConfig",
    "MainMultiForecastBuildError",
    "SyntheticGameContext",
    "SyntheticTemplateBank",
    "build_main_multi_forecast_release",
    "build_synthetic_template_bank",
    "load_main_multi_forecast_build_config",
]
