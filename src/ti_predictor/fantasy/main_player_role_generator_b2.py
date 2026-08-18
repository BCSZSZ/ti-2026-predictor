"""Research-only B2 empirical-copula joint layer for Main Fantasy generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field, field_validator, model_validator

from ti_predictor.fantasy.main_player_role_generator import (
    JointResidualModel,
    MainPlayerRoleGeneratorError,
    PlayerRoleEvidence,
    PlayerRoleEvidenceConfig,
    PlayerRoleFoldConfig,
    PlayerRoleGateConfig,
    PlayerRoleGeneratorModel,
    PlayerRoleSimulationConfig,
    build_joint_residual_training_set,
    cap_nested_evidence_weights,
    fit_joint_residual_model,
)
from ti_predictor.hashing import sha256_json
from ti_predictor.schemas import StrictModel, as_utc


class FrozenB1Parameters(StrictModel):
    ridge_alpha: float = Field(gt=0.0)
    recent_effective_sample_constant: float = Field(gt=0.0)
    recent_residual_cap_sigma: float = Field(gt=0.0)
    factor_rank: int = Field(ge=1)
    covariance_shrinkage: float = Field(ge=0.0, le=1.0)
    latent_scale: float = Field(gt=0.0)


class EmpiricalCopulaTuningConfig(StrictModel):
    empirical_mixes: list[float] = Field(min_length=1)
    latent_scales: list[float] = Field(min_length=1)
    maximum_crps_relative_loss_vs_b1: float = Field(ge=0.0)
    tuning_samples_per_series: int = Field(ge=8, le=256)

    @field_validator("empirical_mixes")
    @classmethod
    def validate_empirical_mixes(cls, values: list[float]) -> list[float]:
        if any(not 0.0 < value < 1.0 for value in values):
            raise ValueError("empirical mixture values must lie strictly inside (0, 1)")
        if len(set(values)) != len(values):
            raise ValueError("empirical mixture values must be unique")
        return values

    @field_validator("latent_scales")
    @classmethod
    def validate_latent_scales(cls, values: list[float]) -> list[float]:
        if any(value <= 0.0 or not np.isfinite(value) for value in values):
            raise ValueError("B2 latent scales must be finite and positive")
        if len(set(values)) != len(values):
            raise ValueError("B2 latent scales must be unique")
        return values


class MainPlayerRoleGeneratorB2Config(StrictModel):
    schema_version: Literal[2]
    experiment_id: Literal[
        "ti2026-main-player-role-generator-v2-empirical-copula"
    ]
    period: Literal["main"]
    as_of: datetime
    evidence: PlayerRoleEvidenceConfig
    frozen_b1: FrozenB1Parameters
    copula_tuning: EmpiricalCopulaTuningConfig
    simulation: PlayerRoleSimulationConfig
    tuning_folds: list[PlayerRoleFoldConfig] = Field(min_length=1)
    confirmation_folds: list[PlayerRoleFoldConfig] = Field(min_length=1)
    diagnostic_fold: PlayerRoleFoldConfig
    gates: PlayerRoleGateConfig
    maximum_joint_energy_relative_loss_vs_b1: float = Field(ge=0.0)
    coach_title_policy: Literal["excluded-from-player-role-generator-v2"]
    research_only: Literal[True]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        cutoff = as_utc(value)
        if cutoff is None:
            raise ValueError("B2 generator requires explicit UTC as_of")
        return cutoff

    @model_validator(mode="after")
    def validate_fold_contract(self) -> MainPlayerRoleGeneratorB2Config:
        if sorted(self.tuning_folds, key=lambda fold: fold.train_as_of) != self.tuning_folds:
            raise ValueError("B2 tuning folds must be ordered by train_as_of")
        if (
            sorted(self.confirmation_folds, key=lambda fold: fold.train_as_of)
            != self.confirmation_folds
        ):
            raise ValueError("B2 confirmation folds must be ordered by train_as_of")
        all_folds = [*self.tuning_folds, *self.confirmation_folds, self.diagnostic_fold]
        league_ids = [fold.league_id for fold in all_folds]
        if len(set(league_ids)) != len(league_ids):
            raise ValueError("B2 tuning, confirmation and diagnostic leagues must be disjoint")
        if self.as_of < max(fold.test_end for fold in all_folds):
            raise ValueError("B2 as_of cannot precede a fold's completion")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


def load_main_player_role_generator_b2_config(
    path: str | Path,
) -> MainPlayerRoleGeneratorB2Config:
    return MainPlayerRoleGeneratorB2Config.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


@dataclass(frozen=True)
class EmpiricalCopulaResidualModel:
    """Capped empirical residual shapes blended with independent smooth factor noise."""

    standardized_rows: np.ndarray
    probabilities: np.ndarray
    source_match_ids: np.ndarray
    source_series_ids: np.ndarray
    smooth_model: JointResidualModel
    empirical_mix: float
    sample_scale: float
    training_set_sha256: str

    def __post_init__(self) -> None:
        rows = np.ascontiguousarray(self.standardized_rows, dtype=float)
        probabilities = np.ascontiguousarray(self.probabilities, dtype=float).reshape(-1)
        match_ids = np.ascontiguousarray(self.source_match_ids, dtype=np.int64).reshape(-1)
        series_ids = np.ascontiguousarray(self.source_series_ids, dtype=np.int64).reshape(-1)
        if rows.ndim != 2 or rows.shape[0] < 2:
            raise MainPlayerRoleGeneratorError("empirical-copula residual rows are invalid")
        if not (
            rows.shape[0] == len(probabilities) == len(match_ids) == len(series_ids)
        ):
            raise MainPlayerRoleGeneratorError("empirical-copula source metadata does not align")
        if self.smooth_model.dimension != rows.shape[1]:
            raise MainPlayerRoleGeneratorError("empirical and smooth residual dimensions differ")
        if (
            not np.isfinite(rows).all()
            or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0.0)
            or probabilities.sum() <= 0.0
        ):
            raise MainPlayerRoleGeneratorError("empirical-copula values are not finite")
        if not 0.0 < self.empirical_mix < 1.0:
            raise MainPlayerRoleGeneratorError("empirical mixture must lie strictly inside (0, 1)")
        if self.sample_scale <= 0.0 or not np.isfinite(self.sample_scale):
            raise MainPlayerRoleGeneratorError("empirical-copula sample scale is invalid")
        if not self.training_set_sha256:
            raise MainPlayerRoleGeneratorError("empirical-copula training identity is missing")
        probabilities /= probabilities.sum()
        object.__setattr__(self, "standardized_rows", rows)
        object.__setattr__(self, "probabilities", probabilities)
        object.__setattr__(self, "source_match_ids", match_ids)
        object.__setattr__(self, "source_series_ids", series_ids)

    @property
    def dimension(self) -> int:
        return self.standardized_rows.shape[1]

    def sample(self, rng: np.random.Generator, *, size: int) -> np.ndarray:
        if size < 1:
            raise MainPlayerRoleGeneratorError(
                "empirical-copula residual sample size must be positive"
            )
        indexes = rng.choice(
            len(self.standardized_rows), size=size, replace=True, p=self.probabilities
        )
        empirical = self.standardized_rows[indexes]
        smooth = self.smooth_model.sample(rng, size=size)
        mixed = np.sqrt(self.empirical_mix) * empirical
        mixed += np.sqrt(1.0 - self.empirical_mix) * smooth
        return mixed * float(self.sample_scale)


def fit_empirical_copula_generator(
    base_model: PlayerRoleGeneratorModel,
    evidence: PlayerRoleEvidence,
    *,
    empirical_mix: float,
    latent_scale: float,
    factor_rank: int,
    covariance_shrinkage: float,
    maximum_residual_game_mass: float,
    maximum_residual_series_mass: float,
) -> PlayerRoleGeneratorModel:
    """Replace only a fitted B1 model's joint layer with the B2 residual copula."""

    training = build_joint_residual_training_set(
        evidence,
        encoder=base_model.encoder,
        marginal_models=base_model.marginal_models,
        maximum_residual_game_mass=maximum_residual_game_mass,
        maximum_residual_series_mass=maximum_residual_series_mass,
    )
    # A match can contribute two Team-side rows. Re-cap by stable match ID so the
    # promised Game limit applies to their combined sampling probability.
    probabilities = cap_nested_evidence_weights(
        training.probabilities,
        training.match_ids,
        training.series_ids,
        maximum_game_mass=maximum_residual_game_mass,
        maximum_series_mass=maximum_residual_series_mass,
    )
    smooth = fit_joint_residual_model(
        training.values,
        probabilities,
        factor_rank=factor_rank,
        covariance_shrinkage=covariance_shrinkage,
        latent_scale=1.0,
    )
    standardized = (
        training.values - smooth.training_center[None, :]
    ) / smooth.training_scale[None, :]
    joint = EmpiricalCopulaResidualModel(
        standardized_rows=standardized,
        probabilities=probabilities,
        source_match_ids=training.match_ids,
        source_series_ids=training.series_ids,
        smooth_model=smooth,
        empirical_mix=float(empirical_mix),
        sample_scale=float(latent_scale),
        training_set_sha256=training.semantic_hash,
    )
    match_mass = {
        int(match_id): float(probabilities[training.match_ids == match_id].sum())
        for match_id in np.unique(training.match_ids)
    }
    series_mass = {
        int(series_id): float(probabilities[training.series_ids == series_id].sum())
        for series_id in np.unique(training.series_ids)
    }
    joint_audit: dict[str, Any] = {
        "kind": "empirical-copula-residual-v2",
        "training_set_sha256": training.semantic_hash,
        "source_rows": len(training.values),
        "source_games": len(match_mass),
        "source_series": len(series_mass),
        "effective_source_rows": float(1.0 / np.sum(np.square(probabilities))),
        "maximum_source_row_mass": float(probabilities.max()),
        "maximum_source_game_mass": max(match_mass.values()),
        "maximum_source_series_mass": max(series_mass.values()),
        "empirical_mix": float(empirical_mix),
        "latent_scale": float(latent_scale),
        "factor_rank": int(factor_rank),
        "covariance_shrinkage": float(covariance_shrinkage),
        "copies_absolute_historical_stats": False,
    }
    audit = {**dict(base_model.audit), "b2_joint": joint_audit}
    semantic_hash = sha256_json(
        {
            "kind": "ti2026-main-player-role-generator-v2-empirical-copula",
            "base_model_sha256": base_model.semantic_hash,
            "training_set_sha256": training.semantic_hash,
            "probabilities": probabilities.tolist(),
            "empirical_mix": float(empirical_mix),
            "latent_scale": float(latent_scale),
            "smooth": {
                "loadings": smooth.loadings.tolist(),
                "idiosyncratic_variance": smooth.idiosyncratic_variance.tolist(),
                "training_center": smooth.training_center.tolist(),
                "training_scale": smooth.training_scale.tolist(),
            },
            "audit": audit,
        }
    )
    return replace(
        base_model,
        joint_residual=joint,
        audit=audit,
        semantic_hash=semantic_hash,
    )


__all__ = [
    "EmpiricalCopulaResidualModel",
    "EmpiricalCopulaTuningConfig",
    "FrozenB1Parameters",
    "MainPlayerRoleGeneratorB2Config",
    "fit_empirical_copula_generator",
    "load_main_player_role_generator_b2_config",
]
