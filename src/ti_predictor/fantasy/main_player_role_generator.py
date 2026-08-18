"""Research-only Player-role conditional Fantasy generator for TI 2026 Main.

The module is intentionally independent of the consumer Web and frozen solver
release paths.  It models individual current-player statistics, then restores
within-Game dependence with a regularized joint residual model.  Historical
absolute five-player Game vectors are never used as future outcomes.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import pandas as pd
from pydantic import Field, field_validator, model_validator
from scipy.special import expit, ndtr, ndtri
from sklearn.linear_model import LogisticRegression

from ti_predictor.config import (
    load_rules,
    load_team_strength_policy,
    load_tournament_manifest,
)
from ti_predictor.forecasting import _available_by_as_of
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.identity import canonicalize_match_team_ids
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.models.evidence import build_evidence_set
from ti_predictor.models.policy import EvidenceScopePolicy
from ti_predictor.models.ratings import TeamStrengthModel, fit_team_strengths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import StrictModel, as_utc
from ti_predictor.storage import read_parquet_if_exists

ROLE_IDS = ("core", "mid", "support")


class MainPlayerRoleGeneratorError(ValueError):
    """The research contract or Player-role generator input is invalid."""


class JointResidualSampler(Protocol):
    """Structural contract shared by research-only joint residual layers."""

    @property
    def dimension(self) -> int: ...

    def sample(self, rng: np.random.Generator, *, size: int) -> np.ndarray: ...


class PlayerRoleEvidenceConfig(StrictModel):
    scope: Literal["global-positive-weight-current-main-players"]
    time_half_life_days: float = Field(gt=0.0)
    maximum_game_parameter_mass: float = Field(gt=0.0, lt=1.0)
    maximum_series_parameter_mass: float = Field(gt=0.0, lt=1.0)
    maximum_residual_game_mass: float = Field(gt=0.0, lt=1.0)
    maximum_residual_series_mass: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def validate_caps(self) -> PlayerRoleEvidenceConfig:
        if self.maximum_game_parameter_mass > self.maximum_series_parameter_mass:
            raise ValueError("Game parameter mass cannot exceed Series parameter mass")
        if self.maximum_residual_game_mass > self.maximum_residual_series_mass:
            raise ValueError("residual Game mass cannot exceed residual Series mass")
        return self


class MarginalTuningConfig(StrictModel):
    ridge_alphas: list[float] = Field(min_length=1)
    recent_effective_sample_constants: list[float] = Field(min_length=1)
    recent_residual_caps_sigma: list[float] = Field(min_length=1)

    @field_validator(
        "ridge_alphas",
        "recent_effective_sample_constants",
        "recent_residual_caps_sigma",
    )
    @classmethod
    def validate_positive_grid(cls, values: list[float]) -> list[float]:
        if any(value <= 0.0 or not np.isfinite(value) for value in values):
            raise ValueError("marginal tuning grids must contain finite positive values")
        if len(set(values)) != len(values):
            raise ValueError("marginal tuning grid values must be unique")
        return values


class JointTuningConfig(StrictModel):
    factor_ranks: list[int] = Field(min_length=1)
    covariance_shrinkages: list[float] = Field(min_length=1)
    latent_scales: list[float] = Field(min_length=1)
    latent_clip: float = Field(gt=0.0)

    @field_validator("factor_ranks")
    @classmethod
    def validate_factor_ranks(cls, values: list[int]) -> list[int]:
        if any(value < 1 for value in values) or len(set(values)) != len(values):
            raise ValueError("joint factor ranks must be unique positive integers")
        return values

    @field_validator("covariance_shrinkages")
    @classmethod
    def validate_shrinkages(cls, values: list[float]) -> list[float]:
        if any(not 0.0 <= value <= 1.0 for value in values) or len(set(values)) != len(values):
            raise ValueError("covariance shrinkages must be unique values inside [0, 1]")
        return values

    @field_validator("latent_scales")
    @classmethod
    def validate_latent_scales(cls, values: list[float]) -> list[float]:
        if any(value <= 0.0 or not np.isfinite(value) for value in values):
            raise ValueError("joint latent scales must be finite and positive")
        if len(set(values)) != len(values):
            raise ValueError("joint latent scales must be unique")
        return values


class TuningSelectionConfig(StrictModel):
    procedure: Literal["staged-marginal-then-joint"]
    joint_subprocedure: Literal["factor-shrinkage-then-latent-scale"]
    primary_metric: Literal["mean-series-top2-crps"]
    fixed_factor_rank_for_marginal_stage: int = Field(ge=1)
    fixed_covariance_shrinkage_for_marginal_stage: float = Field(ge=0.0, le=1.0)
    fixed_latent_scale_for_marginal_stage: float = Field(gt=0.0)
    tie_break_order: list[Literal["lower-complexity", "stronger-shrinkage", "lexicographic"]]
    tuning_samples_per_series: int = Field(ge=8, le=256)

    @field_validator("tie_break_order")
    @classmethod
    def validate_tie_break_order(cls, values: list[str]) -> list[str]:
        expected = ["lower-complexity", "stronger-shrinkage", "lexicographic"]
        if values != expected:
            raise ValueError("tuning tie-break order must remain frozen")
        return values


class PlayerRoleSimulationConfig(StrictModel):
    synthetic_samples_per_context: int = Field(ge=2, le=64)
    inner_samples_per_path: int = Field(ge=1, le=64)
    seeds: list[int] = Field(min_length=1, max_length=8)
    cvar_alpha: float = Field(gt=0.0, le=1.0)

    @field_validator("seeds")
    @classmethod
    def validate_unique_seeds(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("simulation seeds must be unique")
        return values


class PlayerRoleFoldConfig(StrictModel):
    fold_id: str = Field(min_length=1)
    league_id: int = Field(gt=0)
    train_as_of: datetime
    test_end: datetime

    @field_validator("train_as_of", "test_end")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        cutoff = as_utc(value)
        if cutoff is None:
            raise ValueError("fold timestamps require an explicit UTC offset")
        return cutoff

    @model_validator(mode="after")
    def validate_order(self) -> PlayerRoleFoldConfig:
        if self.test_end <= self.train_as_of:
            raise ValueError("fold test_end must be later than train_as_of")
        return self


class PlayerRoleGateConfig(StrictModel):
    minimum_series_crps_improvement: float = Field(ge=0.0)
    series_crps_one_sided_confidence: float = Field(gt=0.5, lt=1.0)
    maximum_joint_energy_relative_loss: float = Field(ge=0.0)
    maximum_role_crps_relative_loss: float = Field(ge=0.0)
    coverage_80_lower: float = Field(ge=0.0, le=1.0)
    coverage_80_upper: float = Field(ge=0.0, le=1.0)
    coverage_90_lower: float = Field(ge=0.0, le=1.0)
    coverage_90_upper: float = Field(ge=0.0, le=1.0)
    maximum_leave_one_game_mean_change: float = Field(ge=0.0)
    maximum_leave_one_series_mean_change: float = Field(ge=0.0)
    protected_rank_margin: float = Field(ge=0.0)
    maximum_monte_carlo_relative_standard_error: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_intervals(self) -> PlayerRoleGateConfig:
        if self.coverage_80_lower > self.coverage_80_upper:
            raise ValueError("80 percent coverage interval is reversed")
        if self.coverage_90_lower > self.coverage_90_upper:
            raise ValueError("90 percent coverage interval is reversed")
        return self


class MainPlayerRoleGeneratorConfig(StrictModel):
    schema_version: Literal[1]
    experiment_id: Literal["ti2026-main-player-role-generator-v1"]
    period: Literal["main"]
    as_of: datetime
    evidence: PlayerRoleEvidenceConfig
    marginal_tuning: MarginalTuningConfig
    joint_tuning: JointTuningConfig
    tuning_selection: TuningSelectionConfig
    simulation: PlayerRoleSimulationConfig
    tuning_folds: list[PlayerRoleFoldConfig] = Field(min_length=1)
    confirmation_fold: PlayerRoleFoldConfig
    gates: PlayerRoleGateConfig
    coach_title_policy: Literal["excluded-from-player-role-generator-v1"]
    research_only: Literal[True]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        cutoff = as_utc(value)
        if cutoff is None:
            raise ValueError("Player-role generator requires explicit UTC as_of")
        return cutoff

    @model_validator(mode="after")
    def validate_fold_contract(self) -> MainPlayerRoleGeneratorConfig:
        ordered = sorted(self.tuning_folds, key=lambda fold: fold.train_as_of)
        if ordered != self.tuning_folds:
            raise ValueError("tuning folds must be ordered by train_as_of")
        league_ids = [fold.league_id for fold in self.tuning_folds]
        if len(set(league_ids)) != len(league_ids):
            raise ValueError("tuning fold leagues must be unique")
        if self.confirmation_fold.league_id in set(league_ids):
            raise ValueError("confirmation league cannot also be a tuning league")
        if self.confirmation_fold.train_as_of <= self.tuning_folds[-1].test_end:
            raise ValueError("confirmation must begin after every tuning fold")
        if self.as_of < self.confirmation_fold.test_end:
            raise ValueError("final as_of cannot precede confirmation completion")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


def load_main_player_role_generator_config(
    path: str | Path,
) -> MainPlayerRoleGeneratorConfig:
    return MainPlayerRoleGeneratorConfig.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def _bounded_simplex_projection(weights: np.ndarray, capacities: np.ndarray) -> np.ndarray:
    numeric = np.asarray(weights, dtype=float).reshape(-1)
    limits = np.asarray(capacities, dtype=float).reshape(-1)
    if numeric.shape != limits.shape or not len(numeric):
        raise MainPlayerRoleGeneratorError("probability weights and capacities must align")
    if (
        not np.isfinite(numeric).all()
        or not np.isfinite(limits).all()
        or np.any(numeric < 0.0)
        or np.any(limits <= 0.0)
    ):
        raise MainPlayerRoleGeneratorError("probability inputs must be finite and nonnegative")
    if numeric.sum() <= 0.0:
        raise MainPlayerRoleGeneratorError("probability weights must contain positive mass")
    if limits.sum() < 1.0 - 1e-12:
        raise MainPlayerRoleGeneratorError("probability caps are infeasible")

    base = numeric / numeric.sum()
    result = np.zeros_like(base)
    active = np.ones(len(base), dtype=bool)
    remaining = 1.0
    for _ in range(len(base) + 1):
        if remaining <= 1e-14:
            break
        active_indexes = np.flatnonzero(active)
        if not len(active_indexes):
            break
        active_base = base[active_indexes]
        if active_base.sum() <= 0.0:
            proposal = np.full(len(active_indexes), remaining / len(active_indexes))
        else:
            proposal = remaining * active_base / active_base.sum()
        saturated = proposal > limits[active_indexes] + 1e-15
        if not np.any(saturated):
            result[active_indexes] = proposal
            remaining = 0.0
            break
        saturated_indexes = active_indexes[saturated]
        result[saturated_indexes] = limits[saturated_indexes]
        active[saturated_indexes] = False
        remaining = 1.0 - float(result.sum())
    if remaining > 1e-10:
        raise MainPlayerRoleGeneratorError("probability cap projection did not converge")
    result /= result.sum()
    if np.any(result > limits + 1e-10):
        raise MainPlayerRoleGeneratorError("probability cap projection violated a hard limit")
    return result


def cap_probability_mass(weights: Sequence[float] | np.ndarray, *, maximum_mass: float) -> np.ndarray:
    """Normalize positive weights while bounding every observation's probability mass."""

    if not 0.0 < maximum_mass <= 1.0:
        raise MainPlayerRoleGeneratorError("maximum probability mass must lie inside (0, 1]")
    numeric = np.asarray(weights, dtype=float).reshape(-1)
    return _bounded_simplex_projection(numeric, np.full(len(numeric), float(maximum_mass)))


def cap_grouped_probability_mass(
    weights: Sequence[float] | np.ndarray,
    groups: Sequence[Any] | np.ndarray,
    *,
    maximum_item_mass: float,
    maximum_group_mass: float,
) -> np.ndarray:
    """Apply simultaneous item and group probability limits by deterministic water filling."""

    numeric = np.asarray(weights, dtype=float).reshape(-1)
    labels = np.asarray(groups).reshape(-1)
    if numeric.shape != labels.shape or not len(numeric):
        raise MainPlayerRoleGeneratorError("grouped probability inputs must align")
    if not 0.0 < maximum_item_mass <= maximum_group_mass <= 1.0:
        raise MainPlayerRoleGeneratorError("grouped probability limits are invalid")

    unique, inverse = np.unique(labels, return_inverse=True)
    group_weights = np.asarray([numeric[inverse == index].sum() for index in range(len(unique))])
    group_sizes = np.bincount(inverse, minlength=len(unique)).astype(float)
    group_capacities = np.minimum(maximum_group_mass, group_sizes * maximum_item_mass)
    group_mass = _bounded_simplex_projection(group_weights, group_capacities)
    result = np.zeros_like(numeric)
    for group_index, total in enumerate(group_mass):
        positions = np.flatnonzero(inverse == group_index)
        local_cap = min(1.0, maximum_item_mass / float(total))
        local = cap_probability_mass(numeric[positions], maximum_mass=local_cap)
        result[positions] = float(total) * local
    result /= result.sum()
    if result.max() > maximum_item_mass + 1e-10:
        raise MainPlayerRoleGeneratorError("item probability cap was not preserved")
    for group_index in range(len(unique)):
        if result[inverse == group_index].sum() > maximum_group_mass + 1e-10:
            raise MainPlayerRoleGeneratorError("group probability cap was not preserved")
    return result


def cap_nested_evidence_weights(
    weights: Sequence[float] | np.ndarray,
    game_ids: Sequence[Any] | np.ndarray,
    series_ids: Sequence[Any] | np.ndarray,
    *,
    maximum_game_mass: float,
    maximum_series_mass: float,
) -> np.ndarray:
    """Cap nested Series and Game mass, then distribute each Game across its player rows."""

    numeric = np.asarray(weights, dtype=float).reshape(-1)
    games = np.asarray(game_ids).reshape(-1)
    series = np.asarray(series_ids).reshape(-1)
    if numeric.shape != games.shape or numeric.shape != series.shape or not len(numeric):
        raise MainPlayerRoleGeneratorError("nested evidence inputs must align")
    unique_games, game_inverse = np.unique(games, return_inverse=True)
    game_weights = np.asarray(
        [numeric[game_inverse == index].sum() for index in range(len(unique_games))],
        dtype=float,
    )
    game_series = np.empty(len(unique_games), dtype=object)
    for game_index in range(len(unique_games)):
        labels = np.unique(series[game_inverse == game_index])
        if len(labels) != 1:
            raise MainPlayerRoleGeneratorError("one Game cannot belong to multiple Series")
        game_series[game_index] = labels[0]
    game_mass = cap_grouped_probability_mass(
        game_weights,
        game_series,
        maximum_item_mass=maximum_game_mass,
        maximum_group_mass=maximum_series_mass,
    )
    result = np.zeros_like(numeric)
    for game_index, total in enumerate(game_mass):
        positions = np.flatnonzero(game_inverse == game_index)
        local = numeric[positions]
        if local.sum() <= 0.0:
            local = np.ones(len(positions), dtype=float)
        result[positions] = float(total) * local / local.sum()
    result /= result.sum()
    return result


def bounded_recent_adjustment(
    residual_mean: float,
    *,
    effective_sample_size: float,
    shrinkage_constant: float,
    cap: float,
) -> float:
    """Shrink a recent residual toward zero and apply an explicit symmetric limit."""

    if effective_sample_size < 0.0 or shrinkage_constant <= 0.0 or cap < 0.0:
        raise MainPlayerRoleGeneratorError("recent adjustment parameters are invalid")
    shrinkage = effective_sample_size / (effective_sample_size + shrinkage_constant)
    return float(np.clip(float(residual_mean) * shrinkage, -cap, cap))


@dataclass(frozen=True)
class ContextEncoder:
    """Stable design matrix for Player-role and future-known/simulated Game context."""

    player_ids: tuple[int, ...]
    player_roles: tuple[str, ...]
    current_team_ids: tuple[int, ...]
    player_current_team_ids: tuple[int, ...]
    duration_center: float
    duration_scale: float

    def __post_init__(self) -> None:
        if not len(self.player_ids) or len(set(self.player_ids)) != len(self.player_ids):
            raise MainPlayerRoleGeneratorError("context encoder player IDs must be unique")
        if len(self.player_roles) != len(self.player_ids) or len(self.player_current_team_ids) != len(
            self.player_ids
        ):
            raise MainPlayerRoleGeneratorError("context encoder player metadata does not align")
        if any(role not in ROLE_IDS for role in self.player_roles):
            raise MainPlayerRoleGeneratorError("context encoder contains an unknown Fantasy role")
        if len(set(self.current_team_ids)) != len(self.current_team_ids):
            raise MainPlayerRoleGeneratorError("context encoder Team IDs must be unique")
        if any(team_id not in self.current_team_ids for team_id in self.player_current_team_ids):
            raise MainPlayerRoleGeneratorError("a player current Team is outside the Main roster")
        if self.duration_scale <= 0.0 or not np.isfinite(self.duration_scale):
            raise MainPlayerRoleGeneratorError("duration scale must be finite and positive")

    @property
    def feature_count(self) -> int:
        # intercept + Role + Player + active current-Team + nine numeric context fields
        return 1 + len(ROLE_IDS) + len(self.player_ids) + len(self.current_team_ids) + 9

    @property
    def player_index(self) -> Mapping[int, int]:
        return {account_id: index for index, account_id in enumerate(self.player_ids)}

    @property
    def team_index(self) -> Mapping[int, int]:
        return {team_id: index for index, team_id in enumerate(self.current_team_ids)}

    @property
    def role_by_player(self) -> Mapping[int, str]:
        return dict(zip(self.player_ids, self.player_roles, strict=True))

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        required = {
            "account_id",
            "current_team_id",
            "played_for_current_team",
            "won_game",
            "opponent_probability",
            "best_of",
            "series_won",
            "series_length",
            "game_index",
            "duration",
        }
        missing = required.difference(frame.columns)
        if missing:
            raise MainPlayerRoleGeneratorError(
                "context frame is missing columns: " + ", ".join(sorted(missing))
            )
        count = len(frame)
        matrix = np.zeros((count, self.feature_count), dtype=float)
        matrix[:, 0] = 1.0
        player_map = self.player_index
        team_map = self.team_index
        role_map = self.role_by_player
        offset = 1
        role_offset = offset
        offset += len(ROLE_IDS)
        player_offset = offset
        offset += len(self.player_ids)
        team_offset = offset
        offset += len(self.current_team_ids)

        account_ids = pd.to_numeric(frame["account_id"], errors="coerce")
        current_team_ids = pd.to_numeric(frame["current_team_id"], errors="coerce")
        if account_ids.isna().any() or current_team_ids.isna().any():
            raise MainPlayerRoleGeneratorError("context player or Team identity is missing")
        for row_index, (account_raw, team_raw) in enumerate(
            zip(account_ids.astype(int), current_team_ids.astype(int), strict=True)
        ):
            if account_raw not in player_map or team_raw not in team_map:
                raise MainPlayerRoleGeneratorError("context contains an unknown player or current Team")
            role = role_map[account_raw]
            matrix[row_index, role_offset + ROLE_IDS.index(role)] = 1.0
            matrix[row_index, player_offset + player_map[account_raw]] = 1.0
            if float(frame.iloc[row_index]["played_for_current_team"]) > 0.5:
                matrix[row_index, team_offset + team_map[team_raw]] = 1.0

        won = pd.to_numeric(frame["won_game"], errors="raise").to_numpy(dtype=float) - 0.5
        opponent = (
            pd.to_numeric(frame["opponent_probability"], errors="raise").to_numpy(dtype=float)
            - 0.5
        )
        best_of = pd.to_numeric(frame["best_of"], errors="raise").to_numpy(dtype=int)
        series_won = (
            pd.to_numeric(frame["series_won"], errors="raise").to_numpy(dtype=float) - 0.5
        )
        series_length = pd.to_numeric(frame["series_length"], errors="raise").to_numpy(dtype=float)
        game_index = pd.to_numeric(frame["game_index"], errors="raise").to_numpy(dtype=float)
        duration = pd.to_numeric(frame["duration"], errors="raise").to_numpy(dtype=float)
        if np.any(duration <= 0.0):
            raise MainPlayerRoleGeneratorError("context duration must be positive")
        progress = np.divide(
            game_index,
            np.maximum(series_length - 1.0, 1.0),
        ) - 0.5
        numeric = np.column_stack(
            (
                won,
                opponent,
                won * opponent,
                (best_of == 2).astype(float),
                (best_of == 5).astype(float),
                series_won,
                (series_length - 3.0) / 2.0,
                progress,
                (np.log1p(duration) - self.duration_center) / self.duration_scale,
            )
        )
        if not np.isfinite(numeric).all():
            raise MainPlayerRoleGeneratorError("context design contains a non-finite value")
        matrix[:, offset:] = numeric
        return matrix


def _quantile_from_sorted(values: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    ordered = np.asarray(values, dtype=float).reshape(-1)
    if not len(ordered):
        return np.zeros_like(probabilities, dtype=float)
    ordered = np.sort(ordered, kind="stable")
    clipped = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    positions = clipped * (len(ordered) - 1)
    lower = np.floor(positions).astype(int)
    upper = np.ceil(positions).astype(int)
    fraction = positions - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


@dataclass(frozen=True)
class StatMarginalModel:
    stat_id: str
    mean_coefficients: np.ndarray
    zero_coefficients: np.ndarray
    positive_residual_quantiles: Mapping[str, np.ndarray]
    recent_mean_adjustments: Mapping[int, float]
    recent_zero_adjustments: Mapping[int, float]
    integer_output: bool
    upper_bound: float | None = None

    def __post_init__(self) -> None:
        mean = np.ascontiguousarray(self.mean_coefficients, dtype=float)
        zero = np.ascontiguousarray(self.zero_coefficients, dtype=float)
        if mean.ndim != 1 or zero.shape != mean.shape:
            raise MainPlayerRoleGeneratorError("marginal coefficient vectors must align")
        object.__setattr__(self, "mean_coefficients", mean)
        object.__setattr__(self, "zero_coefficients", zero)
        quantiles = {
            role: np.sort(np.ascontiguousarray(values, dtype=float))
            for role, values in self.positive_residual_quantiles.items()
        }
        if set(quantiles) != set(ROLE_IDS) and not set(quantiles).issubset(set(ROLE_IDS)):
            raise MainPlayerRoleGeneratorError("marginal residual quantiles contain an unknown role")
        if self.upper_bound is not None and self.upper_bound <= 0.0:
            raise MainPlayerRoleGeneratorError("marginal upper bound must be positive")
        object.__setattr__(self, "positive_residual_quantiles", quantiles)

    def sample(
        self,
        context: pd.DataFrame,
        encoder: ContextEncoder,
        latent: np.ndarray,
        *,
        design: np.ndarray | None = None,
    ) -> np.ndarray:
        matrix = encoder.transform(context) if design is None else np.asarray(design, dtype=float)
        if matrix.shape[0] != len(context):
            raise MainPlayerRoleGeneratorError("precomputed marginal design does not align")
        if matrix.shape[1] != len(self.mean_coefficients):
            raise MainPlayerRoleGeneratorError("marginal model and context encoder do not align")
        latent_values = np.asarray(latent, dtype=float).reshape(-1)
        if len(latent_values) != len(context) or not np.isfinite(latent_values).all():
            raise MainPlayerRoleGeneratorError("marginal latent values do not align with context")
        accounts = pd.to_numeric(context["account_id"], errors="raise").astype(int).to_numpy()
        mean_adjustment = np.asarray(
            [float(self.recent_mean_adjustments.get(int(account_id), 0.0)) for account_id in accounts]
        )
        zero_adjustment = np.asarray(
            [float(self.recent_zero_adjustments.get(int(account_id), 0.0)) for account_id in accounts]
        )
        positive_location = matrix @ self.mean_coefficients + mean_adjustment
        zero_probability = expit(matrix @ self.zero_coefficients + zero_adjustment)
        uniform = np.clip(ndtr(latent_values), 1e-9, 1.0 - 1e-9)
        is_zero = uniform < zero_probability
        positive_probability = np.divide(
            uniform - zero_probability,
            np.maximum(1.0 - zero_probability, 1e-9),
        )
        roles = encoder.role_by_player
        residual = np.zeros(len(context), dtype=float)
        for role in ROLE_IDS:
            mask = np.asarray([roles[int(account_id)] == role for account_id in accounts])
            if np.any(mask):
                residual[mask] = _quantile_from_sorted(
                    self.positive_residual_quantiles.get(role, np.asarray([0.0])),
                    positive_probability[mask],
                )
        values = np.expm1(np.maximum(0.0, positive_location + residual))
        values[is_zero] = 0.0
        values = np.maximum(values, 0.0)
        if self.integer_output:
            values = np.rint(values)
            values[~is_zero] = np.maximum(values[~is_zero], 1.0)
        if self.upper_bound is not None:
            values = np.minimum(values, float(self.upper_bound))
        return values.astype(np.float32)

    def latent_from_observed(
        self,
        context: pd.DataFrame,
        encoder: ContextEncoder,
        observed: Sequence[float] | np.ndarray,
        *,
        design: np.ndarray | None = None,
    ) -> np.ndarray:
        """Map observed nonnegative values to Gaussian-rank residuals for joint fitting."""

        values = np.asarray(observed, dtype=float).reshape(-1)
        if len(values) != len(context) or np.any(values < 0.0) or not np.isfinite(values).all():
            raise MainPlayerRoleGeneratorError("observed marginal values must be aligned and nonnegative")
        matrix = encoder.transform(context) if design is None else np.asarray(design, dtype=float)
        if matrix.shape[0] != len(context):
            raise MainPlayerRoleGeneratorError("precomputed marginal design does not align")
        accounts = pd.to_numeric(context["account_id"], errors="raise").astype(int).to_numpy()
        mean_adjustment = np.asarray(
            [float(self.recent_mean_adjustments.get(int(account_id), 0.0)) for account_id in accounts]
        )
        zero_adjustment = np.asarray(
            [float(self.recent_zero_adjustments.get(int(account_id), 0.0)) for account_id in accounts]
        )
        positive_location = matrix @ self.mean_coefficients + mean_adjustment
        zero_probability = expit(matrix @ self.zero_coefficients + zero_adjustment)
        roles = encoder.role_by_player
        uniform = np.empty(len(values), dtype=float)
        zero_mask = values <= 0.0
        if np.any(zero_mask):
            fractions = []
            match_ids = pd.to_numeric(context.loc[zero_mask, "match_id"], errors="coerce")
            zero_accounts = accounts[zero_mask]
            if match_ids.isna().any():
                fractions = [0.5] * int(zero_mask.sum())
            else:
                for match_id, account_id in zip(
                    match_ids.astype(int), zero_accounts, strict=True
                ):
                    digest = hashlib.sha256(
                        f"pit:{self.stat_id}:{match_id}:{int(account_id)}".encode()
                    ).digest()
                    fractions.append(
                        (int.from_bytes(digest[:8], "big") + 0.5) / (2**64)
                    )
            uniform[zero_mask] = np.asarray(fractions) * zero_probability[zero_mask]
        residual = np.log1p(values) - positive_location
        for role in ROLE_IDS:
            mask = np.asarray(
                [roles[int(account_id)] == role for account_id in accounts]
            ) & ~zero_mask
            if not np.any(mask):
                continue
            support = np.sort(
                np.asarray(self.positive_residual_quantiles.get(role, np.asarray([0.0])), dtype=float)
            )
            ranks = np.searchsorted(support, residual[mask], side="right")
            positive_probability = (ranks + 0.5) / (len(support) + 1.0)
            uniform[mask] = zero_probability[mask] + (
                1.0 - zero_probability[mask]
            ) * positive_probability
        return ndtri(np.clip(uniform, 1e-6, 1.0 - 1e-6))


@dataclass(frozen=True)
class JointResidualModel:
    loadings: np.ndarray
    idiosyncratic_variance: np.ndarray
    training_center: np.ndarray
    training_scale: np.ndarray
    sample_scale: float = 1.0

    def __post_init__(self) -> None:
        loadings = np.ascontiguousarray(self.loadings, dtype=float)
        variance = np.ascontiguousarray(self.idiosyncratic_variance, dtype=float)
        center = np.ascontiguousarray(self.training_center, dtype=float)
        scale = np.ascontiguousarray(self.training_scale, dtype=float)
        if loadings.ndim != 2 or variance.shape != (loadings.shape[0],):
            raise MainPlayerRoleGeneratorError("joint residual dimensions do not align")
        if center.shape != variance.shape or scale.shape != variance.shape:
            raise MainPlayerRoleGeneratorError("joint residual normalization does not align")
        if np.any(variance < 0.0) or np.any(scale <= 0.0):
            raise MainPlayerRoleGeneratorError("joint residual variance or scale is invalid")
        if self.sample_scale <= 0.0 or not np.isfinite(self.sample_scale):
            raise MainPlayerRoleGeneratorError("joint residual sample scale is invalid")
        object.__setattr__(self, "loadings", loadings)
        object.__setattr__(self, "idiosyncratic_variance", variance)
        object.__setattr__(self, "training_center", center)
        object.__setattr__(self, "training_scale", scale)

    @property
    def dimension(self) -> int:
        return self.loadings.shape[0]

    @property
    def factor_rank(self) -> int:
        return self.loadings.shape[1]

    def sample(self, rng: np.random.Generator, *, size: int) -> np.ndarray:
        if size < 1:
            raise MainPlayerRoleGeneratorError("joint residual sample size must be positive")
        factors = rng.normal(size=(size, self.factor_rank))
        independent = rng.normal(size=(size, self.dimension))
        values = factors @ self.loadings.T
        values += independent * np.sqrt(self.idiosyncratic_variance)[None, :]
        return values * float(self.sample_scale)


@dataclass(frozen=True)
class JointResidualTrainingSet:
    """Complete five-player conditional residual rows with capped sampling mass."""

    values: np.ndarray
    probabilities: np.ndarray
    match_ids: np.ndarray
    series_ids: np.ndarray

    def __post_init__(self) -> None:
        values = np.ascontiguousarray(self.values, dtype=float)
        probabilities = np.ascontiguousarray(self.probabilities, dtype=float).reshape(-1)
        match_ids = np.ascontiguousarray(self.match_ids, dtype=np.int64).reshape(-1)
        series_ids = np.ascontiguousarray(self.series_ids, dtype=np.int64).reshape(-1)
        if values.ndim != 2 or values.shape[0] < 2:
            raise MainPlayerRoleGeneratorError("joint residual training matrix is invalid")
        if not (
            values.shape[0]
            == len(probabilities)
            == len(match_ids)
            == len(series_ids)
        ):
            raise MainPlayerRoleGeneratorError("joint residual training metadata does not align")
        if (
            not np.isfinite(values).all()
            or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0.0)
            or probabilities.sum() <= 0.0
        ):
            raise MainPlayerRoleGeneratorError("joint residual training values are invalid")
        probabilities /= probabilities.sum()
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "probabilities", probabilities)
        object.__setattr__(self, "match_ids", match_ids)
        object.__setattr__(self, "series_ids", series_ids)

    @property
    def semantic_hash(self) -> str:
        payload = hashlib.sha256()
        for array in (
            self.values,
            self.probabilities,
            self.match_ids,
            self.series_ids,
        ):
            contiguous = np.ascontiguousarray(array)
            payload.update(str(contiguous.shape).encode())
            payload.update(contiguous.dtype.str.encode())
            payload.update(contiguous.tobytes())
        return payload.hexdigest()

    @property
    def effective_sample_size(self) -> float:
        return _effective_sample_size(self.probabilities)


def fit_joint_residual_model(
    values: np.ndarray,
    weights: Sequence[float] | np.ndarray,
    *,
    factor_rank: int,
    covariance_shrinkage: float,
    latent_scale: float = 1.0,
) -> JointResidualModel:
    """Fit a deterministic low-rank correlation model to complete within-Game residual blocks."""

    matrix = np.asarray(values, dtype=float)
    mass = np.asarray(weights, dtype=float).reshape(-1)
    if matrix.ndim != 2 or matrix.shape[0] != len(mass) or matrix.shape[0] < 2:
        raise MainPlayerRoleGeneratorError("joint residual training rows and weights must align")
    if not np.isfinite(matrix).all() or not np.isfinite(mass).all() or np.any(mass < 0.0):
        raise MainPlayerRoleGeneratorError("joint residual training input must be finite")
    if mass.sum() <= 0.0:
        raise MainPlayerRoleGeneratorError("joint residual training weights have no mass")
    if not 1 <= factor_rank < matrix.shape[1]:
        raise MainPlayerRoleGeneratorError("joint factor rank must be inside the residual dimension")
    if not 0.0 <= covariance_shrinkage <= 1.0:
        raise MainPlayerRoleGeneratorError("joint covariance shrinkage must lie inside [0, 1]")
    if latent_scale <= 0.0 or not np.isfinite(latent_scale):
        raise MainPlayerRoleGeneratorError("joint latent scale must be finite and positive")

    mass = mass / mass.sum()
    center = mass @ matrix
    centered = matrix - center[None, :]
    variance = mass @ np.square(centered)
    scale = np.sqrt(np.maximum(variance, 1e-8))
    standardized = centered / scale[None, :]
    covariance = (standardized * mass[:, None]).T @ standardized
    covariance = (covariance + covariance.T) / 2.0
    covariance = (1.0 - covariance_shrinkage) * covariance + covariance_shrinkage * np.eye(
        covariance.shape[0]
    )
    diagonal = np.sqrt(np.maximum(np.diag(covariance), 1e-12))
    correlation = covariance / diagonal[:, None] / diagonal[None, :]
    correlation = (correlation + correlation.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(correlation)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.maximum(eigenvalues[order], 0.0)
    eigenvectors = eigenvectors[:, order]
    tail = eigenvalues[factor_rank:]
    noise_floor = float(np.median(tail)) if len(tail) else 0.0
    strengths = np.sqrt(np.maximum(eigenvalues[:factor_rank] - noise_floor, 0.0))
    loadings = eigenvectors[:, :factor_rank] * strengths[None, :]
    row_mass = np.sum(np.square(loadings), axis=1)
    excessive = row_mass >= 1.0
    if np.any(excessive):
        loadings[excessive] *= np.sqrt((1.0 - 1e-8) / row_mass[excessive])[:, None]
        row_mass = np.sum(np.square(loadings), axis=1)
    idiosyncratic = np.maximum(1.0 - row_mass, 0.0)
    return JointResidualModel(loadings, idiosyncratic, center, scale, float(latent_scale))


INTEGER_STAT_IDS = frozenset(
    {
        "kills",
        "deaths",
        "creep_score",
        "gpm",
        "madstone_collected",
        "tower_kills",
        "wards_placed",
        "camps_stacked",
        "runes_grabbed",
        "smokes_used",
        "watchers_taken",
        "lotuses_gained",
        "roshan_kills",
        "first_blood",
        "tormentor_kills",
        "courier_kills",
    }
)


@dataclass(frozen=True)
class PlayerRoleEvidence:
    frame: pd.DataFrame
    team_ids: tuple[int, ...]
    stat_ids: tuple[str, ...]
    player_ids_by_team: np.ndarray
    player_roles_by_team: tuple[tuple[str, ...], ...]
    as_of: datetime
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        frame = self.frame.copy()
        players = np.ascontiguousarray(self.player_ids_by_team, dtype=np.int64)
        if len(self.team_ids) != 8 or len(set(self.team_ids)) != 8:
            raise MainPlayerRoleGeneratorError("Player-role evidence requires eight Main Teams")
        if players.shape != (8, 5):
            raise MainPlayerRoleGeneratorError(
                "Player-role evidence requires eight ordered five-player rosters"
            )
        if len(set(players.reshape(-1).tolist())) != 40:
            raise MainPlayerRoleGeneratorError("Player-role evidence current player IDs must be unique")
        if len(self.player_roles_by_team) != 8 or any(
            tuple(roles) != ("core", "core", "mid", "support", "support")
            for roles in self.player_roles_by_team
        ):
            raise MainPlayerRoleGeneratorError("Player-role evidence roster roles are not canonical")
        required = {
            "match_id",
            "series_id",
            "account_id",
            "historical_team_id",
            "current_team_id",
            "played_for_current_team",
            "won_game",
            "opponent_probability",
            "best_of",
            "series_won",
            "series_length",
            "game_index",
            "duration",
            "evidence_weight",
            "start_time",
        }
        missing = required.difference(frame.columns)
        if missing:
            raise MainPlayerRoleGeneratorError(
                "Player-role evidence is missing columns: " + ", ".join(sorted(missing))
            )
        if any(stat_id not in frame for stat_id in self.stat_ids):
            raise MainPlayerRoleGeneratorError("Player-role evidence is missing a Fantasy Stat")
        cutoff = as_utc(self.as_of)
        if cutoff is None:
            raise MainPlayerRoleGeneratorError("Player-role evidence requires explicit UTC as_of")
        starts = pd.to_datetime(frame["start_time"], utc=True, errors="coerce")
        if starts.isna().any() or starts.gt(pd.Timestamp(cutoff)).any():
            raise MainPlayerRoleGeneratorError("Player-role evidence contains unavailable future rows")
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "player_ids_by_team", players)
        object.__setattr__(self, "as_of", cutoff)

    @property
    def player_ids(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.player_ids_by_team.reshape(-1))

    @property
    def player_roles(self) -> tuple[str, ...]:
        return tuple(role for roles in self.player_roles_by_team for role in roles)

    @property
    def player_current_team_ids(self) -> tuple[int, ...]:
        return tuple(team_id for team_id in self.team_ids for _ in range(5))


@dataclass(frozen=True)
class PlayerRoleEvidenceBuildResult:
    """Governed evidence plus the training-cutoff Team-strength context model."""

    evidence: PlayerRoleEvidence
    strength_model: TeamStrengthModel
    strength_report: Mapping[str, Any]


def _supported_series_format(series_type: int, game_count: int) -> int | None:
    if series_type == 1 and game_count in {2, 3}:
        return 3
    if series_type == 2 and game_count in {3, 4, 5}:
        return 5
    if series_type == 3 and game_count == 2:
        return 2
    return None


def _canonical_team_side(
    observation_team_id: int,
    match: Mapping[str, Any],
) -> tuple[int, int] | None:
    """Resolve an observation's source Team against raw or canonical match identity."""

    radiant = match.get("radiant_team_id")
    dire = match.get("dire_team_id")
    if pd.isna(radiant) or pd.isna(dire):
        return None
    radiant_id = int(radiant)
    dire_id = int(dire)
    radiant_raw = match.get("radiant_raw_team_id", radiant_id)
    dire_raw = match.get("dire_raw_team_id", dire_id)
    radiant_candidates = {radiant_id}
    dire_candidates = {dire_id}
    if radiant_raw is not None and not pd.isna(radiant_raw):
        radiant_candidates.add(int(radiant_raw))
    if dire_raw is not None and not pd.isna(dire_raw):
        dire_candidates.add(int(dire_raw))
    if observation_team_id in radiant_candidates:
        return radiant_id, dire_id
    if observation_team_id in dire_candidates:
        return dire_id, radiant_id
    return None


def _series_contexts(
    matches: pd.DataFrame,
) -> tuple[dict[tuple[int, int], dict[str, Any]], Counter[str]]:
    """Index completed supported Series context by canonical Team and Game."""

    contexts: dict[tuple[int, int], dict[str, Any]] = {}
    rejection: Counter[str] = Counter()
    eligible = matches.loc[
        matches["series_id"].notna() & matches["series_type"].notna()
    ].copy()
    eligible["series_id"] = pd.to_numeric(eligible["series_id"], errors="coerce")
    eligible["series_type"] = pd.to_numeric(eligible["series_type"], errors="coerce")
    eligible = eligible.dropna(subset=["series_id", "series_type"])
    eligible = eligible.astype({"series_id": int, "series_type": int})
    for _, games in eligible.groupby("series_id", sort=True):
        games = games.sort_values(["start_time", "match_id"], kind="stable")
        if games["series_type"].nunique(dropna=False) != 1:
            rejection["mixed_series_type"] += 1
            continue
        best_of = _supported_series_format(int(games["series_type"].iloc[0]), len(games))
        if best_of is None:
            rejection["unsupported_or_incomplete_series"] += 1
            continue
        first = games.iloc[0]
        if pd.isna(first["radiant_team_id"]) or pd.isna(first["dire_team_id"]):
            rejection["missing_team_identity"] += 1
            continue
        participants = {int(first["radiant_team_id"]), int(first["dire_team_id"])}
        if any(
            {int(row.radiant_team_id), int(row.dire_team_id)} != participants
            for row in games.itertuples(index=False)
        ):
            rejection["participant_change"] += 1
            continue
        for team_id in sorted(participants):
            results: list[bool] = []
            opponents: list[int] = []
            for row in games.itertuples(index=False):
                if int(row.radiant_team_id) == team_id:
                    results.append(bool(row.radiant_win))
                    opponents.append(int(row.dire_team_id))
                else:
                    results.append(not bool(row.radiant_win))
                    opponents.append(int(row.radiant_team_id))
            if len(set(opponents)) != 1:
                rejection["opponent_change"] += 1
                continue
            series_won = sum(results) > len(results) / 2.0
            for game_index, (match_id, won_game) in enumerate(
                zip(games["match_id"].astype(int), results, strict=True)
            ):
                contexts[(int(match_id), team_id)] = {
                    "opponent_team_id": opponents[game_index],
                    "won_game": won_game,
                    "best_of": best_of,
                    "series_won": series_won,
                    "series_length": len(games),
                    "game_index": game_index,
                }
    return contexts, rejection


def _report_payload(report: Any) -> dict[str, Any]:
    if hasattr(report, "as_dict"):
        return dict(report.as_dict())
    if hasattr(report, "model_dump"):
        return dict(report.model_dump(mode="json"))
    return dict(report)


def build_player_role_evidence(
    *,
    training_cutoff: datetime,
    available_as_of: datetime,
    paths: ProjectPaths = PATHS,
) -> PlayerRoleEvidenceBuildResult:
    """Build Player-role evidence from immutable local data without touching runtime state.

    ``available_as_of`` governs which local captures may be read. ``training_cutoff`` is
    the event-time split: Games at or after it are excluded from model fitting.  They
    differ for reconstructed rolling validation and are identical for the final fit.
    """

    cutoff = as_utc(training_cutoff)
    availability = as_utc(available_as_of)
    if cutoff is None or availability is None:
        raise MainPlayerRoleGeneratorError(
            "Player-role evidence requires explicit UTC training and availability cutoffs"
        )
    if availability < cutoff:
        raise MainPlayerRoleGeneratorError(
            "available_as_of cannot precede the Player-role training cutoff"
        )
    evidence_paths = main_evidence_paths(paths, require=True)
    manifest = load_tournament_manifest(evidence_paths.tournament)
    rules = load_rules(evidence_paths.rules)
    team_ids = tuple(int(value) for value in manifest.main_event_seeds)
    if len(team_ids) != 8 or len(set(team_ids)) != 8:
        raise MainPlayerRoleGeneratorError(
            "Player-role evidence requires the frozen actual eight Main Teams"
        )

    matches_path = evidence_paths.processed / "matches.parquet"
    observations_path = evidence_paths.processed / "fantasy_performance_samples.parquet"
    patches_path = evidence_paths.processed / "patches.parquet"
    matches = _available_by_as_of(read_parquet_if_exists(matches_path), availability)
    observations = _available_by_as_of(
        read_parquet_if_exists(observations_path), availability
    )
    patches = _available_by_as_of(read_parquet_if_exists(patches_path), availability)
    if matches.empty or observations.empty or patches.empty:
        raise MainPlayerRoleGeneratorError(
            "the frozen Main snapshot lacks matches, Fantasy observations, or patches"
        )
    matches, identity_audit = canonicalize_match_team_ids(
        matches,
        manifest.team_identity_bridges,
        as_of=availability,
        registration_identities={
            team.team_id: team.registration_identity
            for team in manifest.teams
            if team.registration_identity is not None
        },
    )
    matches["start_time"] = pd.to_datetime(matches["start_time"], utc=True, errors="coerce")
    observations["start_time"] = pd.to_datetime(
        observations["start_time"], utc=True, errors="coerce"
    )
    training_matches = matches.loc[
        matches["start_time"].notna() & matches["start_time"].lt(pd.Timestamp(cutoff))
    ].copy()
    training_observations = observations.loc[
        observations["start_time"].notna()
        & observations["start_time"].lt(pd.Timestamp(cutoff))
    ].copy()

    strength_policy = load_team_strength_policy(
        manifest,
        config_root=evidence_paths.config,
        period="main",
    )
    strength_model, strength_report = fit_team_strengths(
        training_matches,
        patches,
        as_of=cutoff,
        policy=strength_policy,
        target_team_ids=set(team_ids),
    )
    blocking_strength = [
        issue.message for issue in strength_report.issues if issue.severity == "blocking"
    ]
    if blocking_strength:
        raise MainPlayerRoleGeneratorError(
            "training-cutoff Team-strength evidence is blocked: "
            + "; ".join(blocking_strength)
        )
    fantasy_policy = strength_policy.model_copy(
        update={
            "policy_id": f"{strength_policy.policy_id}-player-role-generator-history",
            "evidence_scope": EvidenceScopePolicy(mode="global"),
        }
    )
    fantasy_evidence = build_evidence_set(
        training_matches,
        patches,
        as_of=cutoff,
        policy=fantasy_policy,
        target_patch_family=strength_model.target_patch_family,
        evidence_channel="fantasy",
    )
    blocking_fantasy = [
        issue.message for issue in fantasy_evidence.issues if issue.severity == "blocking"
    ]
    if blocking_fantasy:
        raise MainPlayerRoleGeneratorError(
            "training-cutoff Fantasy evidence is blocked: " + "; ".join(blocking_fantasy)
        )
    weight_frame = fantasy_evidence.matches[["match_id", "evidence_weight"]].copy()
    weight_frame["match_id"] = pd.to_numeric(weight_frame["match_id"], errors="coerce")
    weight_frame = weight_frame.dropna(subset=["match_id"]).astype({"match_id": int})
    weight_by_match = {
        int(row.match_id): float(row.evidence_weight)
        for row in weight_frame.itertuples(index=False)
        if float(row.evidence_weight) > 0.0
    }
    positive_matches = training_matches.loc[
        pd.to_numeric(training_matches["match_id"], errors="coerce").isin(weight_by_match)
    ].copy()
    positive_matches["match_id"] = positive_matches["match_id"].astype(int)
    match_by_id = {
        int(row["match_id"]): row for row in positive_matches.to_dict(orient="records")
    }
    series_context, series_rejection = _series_contexts(positive_matches)

    player_metadata: dict[int, tuple[int, str]] = {}
    player_ids_by_team: list[list[int]] = []
    player_roles_by_team: list[tuple[str, ...]] = []
    team_by_id = {int(team.team_id): team for team in manifest.teams}
    for team_id in team_ids:
        team = team_by_id[team_id]
        ordered_players: list[int] = []
        ordered_roles: list[str] = []
        for role in ROLE_IDS:
            for player in team.players[role]:
                account_id = int(player.account_id)
                ordered_players.append(account_id)
                ordered_roles.append(role)
                player_metadata[account_id] = (team_id, role)
        player_ids_by_team.append(ordered_players)
        player_roles_by_team.append(tuple(ordered_roles))
    if len(player_metadata) != 40:
        raise MainPlayerRoleGeneratorError("Main Player-role roster does not contain forty players")

    stat_ids = tuple(str(value) for value in rules["fantasy"]["stats"])
    provenance = {
        stat_id: str(rules["fantasy"]["stats"][stat_id]["provenance"])
        for stat_id in stat_ids
    }
    training_observations["match_id"] = pd.to_numeric(
        training_observations["match_id"], errors="coerce"
    )
    training_observations["account_id"] = pd.to_numeric(
        training_observations["account_id"], errors="coerce"
    )
    training_observations = training_observations.dropna(
        subset=["match_id", "account_id"]
    ).astype({"match_id": int, "account_id": int})
    training_observations = training_observations.loc[
        training_observations["account_id"].isin(player_metadata)
        & training_observations["match_id"].isin(match_by_id)
    ].copy()
    if training_observations.duplicated(["match_id", "account_id"]).any():
        raise MainPlayerRoleGeneratorError(
            "Player-role source contains duplicate account/Game observations"
        )

    rows: list[dict[str, Any]] = []
    rejection: Counter[str] = Counter(series_rejection)
    for observation in training_observations.to_dict(orient="records"):
        account_id = int(observation["account_id"])
        match_id = int(observation["match_id"])
        current_team_id, current_role = player_metadata[account_id]
        declared_role = observation.get("role")
        if (
            declared_role is not None
            and not pd.isna(declared_role)
            and str(declared_role) != current_role
        ):
            rejection["historical_role_conflict"] += 1
            continue
        source_team = observation.get("team_id")
        if source_team is None or pd.isna(source_team):
            rejection["missing_observation_team"] += 1
            continue
        match = match_by_id[match_id]
        side = _canonical_team_side(int(source_team), match)
        if side is None:
            rejection["observation_team_not_in_match"] += 1
            continue
        historical_team_id, opponent_team_id = side
        context = series_context.get((match_id, historical_team_id))
        if context is None:
            rejection["missing_supported_series_context"] += 1
            continue
        duration = match.get("duration", observation.get("duration"))
        if duration is None or pd.isna(duration) or float(duration) <= 0.0:
            rejection["missing_duration"] += 1
            continue
        row: dict[str, Any] = {
            "match_id": match_id,
            "series_id": int(match["series_id"]),
            "account_id": account_id,
            "historical_team_id": historical_team_id,
            "opponent_team_id": opponent_team_id,
            "current_team_id": current_team_id,
            "current_role": current_role,
            "played_for_current_team": float(historical_team_id == current_team_id),
            "won_game": float(bool(context["won_game"])),
            "opponent_probability": float(
                strength_model.predict(historical_team_id, opponent_team_id)
            ),
            "best_of": int(context["best_of"]),
            "series_won": float(bool(context["series_won"])),
            "series_length": int(context["series_length"]),
            "game_index": int(context["game_index"]),
            "duration": float(duration),
            "evidence_weight": float(weight_by_match[match_id]),
            "start_time": pd.Timestamp(match["start_time"]),
            "source_sha256": observation.get("source_sha256"),
        }
        for stat_id in stat_ids:
            value = observation.get(stat_id)
            actual_provenance = observation.get(f"{stat_id}_provenance")
            valid = (
                value is not None
                and not pd.isna(value)
                and actual_provenance == provenance[stat_id]
            )
            numeric = float(value) if valid else np.nan
            if valid and numeric < 0.0:
                # OpenDota occasionally emits negative aggregate stun durations.
                # They cannot be legal raw Fantasy outcomes and remain missing;
                # critically, they are not silently converted to zero.
                rejection[f"negative_{stat_id}_kept_null"] += 1
                numeric = np.nan
            row[stat_id] = numeric
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise MainPlayerRoleGeneratorError("Player-role evidence produced no governed rows")
    frame = frame.sort_values(
        ["start_time", "series_id", "match_id", "current_team_id", "account_id"],
        kind="stable",
    ).reset_index(drop=True)
    player_counts = frame.groupby("account_id")["match_id"].nunique()
    missing_players = sorted(set(player_metadata) - set(int(value) for value in player_counts.index))
    if missing_players:
        raise MainPlayerRoleGeneratorError(
            "Player-role evidence is missing current player IDs: "
            + ", ".join(str(value) for value in missing_players)
        )
    audit = {
        "schema_version": 1,
        "kind": "ti2026-main-player-role-evidence",
        "training_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "available_as_of": availability.isoformat().replace("+00:00", "Z"),
        "reconstructed_time_split": availability > cutoff,
        "team_ids": list(team_ids),
        "player_count": len(player_metadata),
        "player_game_rows": len(frame),
        "games": int(frame["match_id"].nunique()),
        "series": int(frame["series_id"].nunique()),
        "player_game_minimum": int(player_counts.min()),
        "player_game_median": float(player_counts.median()),
        "player_game_maximum": int(player_counts.max()),
        "stat_available_rows": {
            stat_id: int(frame[stat_id].notna().sum()) for stat_id in stat_ids
        },
        "rejection_counts": dict(sorted(rejection.items())),
        "fantasy_evidence_audit": fantasy_evidence.audit,
        "fantasy_evidence_warnings": sorted(
            issue.message for issue in fantasy_evidence.issues if issue.severity == "warning"
        ),
        "strength_warnings": sorted(
            issue.message for issue in strength_report.issues if issue.severity == "warning"
        ),
        "identity_audit": identity_audit,
        "source_sha256": {
            "matches": sha256_file(matches_path),
            "observations": sha256_file(observations_path),
            "patches": sha256_file(patches_path),
            "rules": sha256_file(evidence_paths.rules),
            "manifest": sha256_file(evidence_paths.tournament),
        },
    }
    audit["semantic_hash"] = sha256_json(
        {
            "training_cutoff": audit["training_cutoff"],
            "available_as_of": audit["available_as_of"],
            "team_ids": audit["team_ids"],
            "match_ids": sorted(int(value) for value in frame["match_id"].unique()),
            "account_ids": sorted(int(value) for value in frame["account_id"].unique()),
            "stat_available_rows": audit["stat_available_rows"],
            "sources": audit["source_sha256"],
        }
    )
    evidence = PlayerRoleEvidence(
        frame=frame,
        team_ids=team_ids,
        stat_ids=stat_ids,
        player_ids_by_team=np.asarray(player_ids_by_team, dtype=np.int64),
        player_roles_by_team=tuple(player_roles_by_team),
        as_of=cutoff,
        audit=audit,
    )
    return PlayerRoleEvidenceBuildResult(
        evidence=evidence,
        strength_model=strength_model,
        strength_report=_report_payload(strength_report),
    )


def _duration_design(frame: pd.DataFrame) -> np.ndarray:
    required = {
        "won_game",
        "opponent_probability",
        "best_of",
        "series_won",
        "series_length",
        "game_index",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise MainPlayerRoleGeneratorError(
            "duration context is missing columns: " + ", ".join(sorted(missing))
        )
    won = pd.to_numeric(frame["won_game"], errors="raise").to_numpy(dtype=float) - 0.5
    opponent = (
        pd.to_numeric(frame["opponent_probability"], errors="raise").to_numpy(dtype=float)
        - 0.5
    )
    best_of = pd.to_numeric(frame["best_of"], errors="raise").to_numpy(dtype=int)
    series_won = (
        pd.to_numeric(frame["series_won"], errors="raise").to_numpy(dtype=float) - 0.5
    )
    series_length = pd.to_numeric(
        frame["series_length"], errors="raise"
    ).to_numpy(dtype=float)
    game_index = pd.to_numeric(frame["game_index"], errors="raise").to_numpy(dtype=float)
    progress = np.divide(game_index, np.maximum(series_length - 1.0, 1.0)) - 0.5
    matrix = np.column_stack(
        (
            np.ones(len(frame), dtype=float),
            won,
            opponent,
            won * opponent,
            (best_of == 2).astype(float),
            (best_of == 5).astype(float),
            series_won,
            (series_length - 3.0) / 2.0,
            progress,
        )
    )
    if not np.isfinite(matrix).all():
        raise MainPlayerRoleGeneratorError("duration context contains a non-finite value")
    return matrix


@dataclass(frozen=True)
class GameDurationModel:
    """A shared Game-duration layer used before Player Stat generation."""

    coefficients: np.ndarray
    residual_quantiles: np.ndarray
    lower_seconds: float
    upper_seconds: float

    def __post_init__(self) -> None:
        coefficients = np.ascontiguousarray(self.coefficients, dtype=float).reshape(-1)
        quantiles = np.sort(
            np.ascontiguousarray(self.residual_quantiles, dtype=float).reshape(-1),
            kind="stable",
        )
        if coefficients.shape != (9,) or not len(quantiles):
            raise MainPlayerRoleGeneratorError("duration model dimensions are invalid")
        if (
            not np.isfinite(coefficients).all()
            or not np.isfinite(quantiles).all()
            or not 0.0 < self.lower_seconds < self.upper_seconds
        ):
            raise MainPlayerRoleGeneratorError("duration model values are invalid")
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "residual_quantiles", quantiles)

    def sample(
        self,
        context: pd.DataFrame,
        *,
        rng: np.random.Generator,
    ) -> np.ndarray:
        design = _duration_design(context)
        uniform = rng.random(len(context))
        residual = _quantile_from_sorted(self.residual_quantiles, uniform)
        durations = np.expm1(design @ self.coefficients + residual)
        return np.clip(durations, self.lower_seconds, self.upper_seconds).astype(np.float32)


@dataclass(frozen=True)
class PlayerRoleGeneratorModel:
    encoder: ContextEncoder
    stat_ids: tuple[str, ...]
    player_ids_by_team: np.ndarray
    marginal_models: Mapping[str, StatMarginalModel]
    duration_model: GameDurationModel
    joint_residual: JointResidualSampler
    audit: Mapping[str, Any]
    semantic_hash: str

    def __post_init__(self) -> None:
        players = np.ascontiguousarray(self.player_ids_by_team, dtype=np.int64)
        if players.shape != (len(self.encoder.current_team_ids), 5):
            raise MainPlayerRoleGeneratorError("generator model player roster does not align")
        if tuple(self.marginal_models) != self.stat_ids:
            raise MainPlayerRoleGeneratorError("generator marginal models do not follow Stat order")
        expected_dimension = 5 * len(self.stat_ids)
        if self.joint_residual.dimension != expected_dimension:
            raise MainPlayerRoleGeneratorError("joint residual dimension does not match five-player Stats")
        object.__setattr__(self, "player_ids_by_team", players)

    def sample_durations(
        self,
        *,
        opponent_probability: float,
        won_game: bool,
        best_of: int,
        series_won: bool,
        series_length: int,
        game_index: int,
        size: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        if size < 1:
            raise MainPlayerRoleGeneratorError("future duration sample size must be positive")
        context = pd.DataFrame(
            {
                "won_game": np.full(size, float(bool(won_game))),
                "opponent_probability": np.full(size, float(opponent_probability)),
                "best_of": np.full(size, int(best_of)),
                "series_won": np.full(size, float(bool(series_won))),
                "series_length": np.full(size, int(series_length)),
                "game_index": np.full(size, int(game_index)),
            }
        )
        return self.duration_model.sample(context, rng=rng)

    def sample_team_games(
        self,
        *,
        team_id: int,
        opponent_probability: float,
        won_game: bool,
        best_of: int,
        series_won: bool,
        series_length: int,
        game_index: int,
        durations: Sequence[float] | np.ndarray,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Generate raw five-player Stat matrices for one coherent future Team-side context."""

        try:
            team_index = self.encoder.current_team_ids.index(int(team_id))
        except ValueError as error:
            raise MainPlayerRoleGeneratorError("future context contains a non-Main Team") from error
        duration_values = np.asarray(durations, dtype=float).reshape(-1)
        if not len(duration_values) or np.any(duration_values <= 0.0):
            raise MainPlayerRoleGeneratorError("future generated durations must be positive")
        sample_count = len(duration_values)
        players = self.player_ids_by_team[team_index]
        context = pd.DataFrame(
            {
                "account_id": np.tile(players, sample_count),
                "current_team_id": int(team_id),
                "played_for_current_team": 1.0,
                "won_game": float(bool(won_game)),
                "opponent_probability": float(opponent_probability),
                "best_of": int(best_of),
                "series_won": float(bool(series_won)),
                "series_length": float(series_length),
                "game_index": float(game_index),
                "duration": np.repeat(duration_values, 5),
            }
        )
        latent = self.joint_residual.sample(rng, size=sample_count).reshape(
            sample_count,
            5,
            len(self.stat_ids),
        )
        design = self.encoder.transform(context)
        generated = np.empty((sample_count, 5, len(self.stat_ids)), dtype=np.float32)
        for stat_index, stat_id in enumerate(self.stat_ids):
            values = self.marginal_models[stat_id].sample(
                context,
                self.encoder,
                latent[:, :, stat_index].reshape(-1),
                design=design,
            )
            generated[:, :, stat_index] = values.reshape(sample_count, 5)
        if np.any(generated < 0.0) or not np.isfinite(generated).all():
            raise MainPlayerRoleGeneratorError("generated raw Fantasy Stats are invalid")
        return generated


def _fit_weighted_ridge(
    matrix: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    *,
    alpha: float,
) -> np.ndarray:
    design = np.asarray(matrix, dtype=float)
    values = np.asarray(target, dtype=float).reshape(-1)
    mass = np.asarray(weights, dtype=float).reshape(-1)
    if design.shape[0] != len(values) or len(values) != len(mass):
        raise MainPlayerRoleGeneratorError("weighted ridge input does not align")
    if alpha <= 0.0:
        raise MainPlayerRoleGeneratorError("weighted ridge alpha must be positive")
    scaled = mass / max(float(mass.mean()), 1e-12)
    penalty = np.eye(design.shape[1], dtype=float) * float(alpha)
    penalty[0, 0] = 0.0
    left = design.T @ (design * scaled[:, None]) + penalty
    right = design.T @ (values * scaled)
    try:
        return np.linalg.solve(left, right)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(left, right, rcond=None)[0]


def _fit_weighted_logistic(
    matrix: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    *,
    alpha: float,
) -> np.ndarray:
    design = np.asarray(matrix, dtype=float)
    values = np.asarray(target, dtype=int).reshape(-1)
    mass = np.asarray(weights, dtype=float).reshape(-1)
    if len(np.unique(values)) < 2:
        probability = (float(np.dot(mass, values)) + 0.5) / (float(mass.sum()) + 1.0)
        coefficients = np.zeros(design.shape[1], dtype=float)
        coefficients[0] = float(np.log(probability / (1.0 - probability)))
        return coefficients
    model = LogisticRegression(
        C=1.0 / float(alpha),
        fit_intercept=False,
        solver="lbfgs",
        max_iter=1000,
        random_state=0,
    )
    model.fit(design, values, sample_weight=mass / max(float(mass.mean()), 1e-12))
    return np.asarray(model.coef_[0], dtype=float)


def _effective_sample_size(weights: np.ndarray) -> float:
    mass = np.asarray(weights, dtype=float).reshape(-1)
    if not len(mass) or mass.sum() <= 0.0:
        return 0.0
    probability = mass / mass.sum()
    return float(1.0 / np.sum(np.square(probability)))


def _weighted_quantile_grid(
    values: np.ndarray,
    weights: np.ndarray,
    *,
    points: int = 257,
) -> np.ndarray:
    numeric = np.asarray(values, dtype=float).reshape(-1)
    mass = np.asarray(weights, dtype=float).reshape(-1)
    if len(numeric) != len(mass) or not len(numeric):
        return np.asarray([0.0], dtype=float)
    order = np.argsort(numeric, kind="stable")
    numeric = numeric[order]
    mass = mass[order]
    mass = mass / mass.sum()
    cumulative = np.cumsum(mass)
    probabilities = np.linspace(0.0, 1.0, points)
    return np.interp(probabilities, cumulative, numeric, left=numeric[0], right=numeric[-1])


def _marginal_model_hash(model: StatMarginalModel) -> dict[str, Any]:
    return {
        "stat_id": model.stat_id,
        "mean_coefficients": model.mean_coefficients.tolist(),
        "zero_coefficients": model.zero_coefficients.tolist(),
        "positive_residual_quantiles": {
            role: values.tolist() for role, values in sorted(model.positive_residual_quantiles.items())
        },
        "recent_mean_adjustments": {
            str(key): value for key, value in sorted(model.recent_mean_adjustments.items())
        },
        "recent_zero_adjustments": {
            str(key): value for key, value in sorted(model.recent_zero_adjustments.items())
        },
        "integer_output": model.integer_output,
        "upper_bound": model.upper_bound,
    }


def build_joint_residual_training_set(
    evidence: PlayerRoleEvidence,
    *,
    encoder: ContextEncoder,
    marginal_models: Mapping[str, StatMarginalModel],
    maximum_residual_game_mass: float,
    maximum_residual_series_mass: float,
) -> JointResidualTrainingSet:
    """Extract capped complete-Game residual rows after conditional marginals are removed."""

    if tuple(marginal_models) != evidence.stat_ids:
        raise MainPlayerRoleGeneratorError(
            "joint residual marginals do not follow the evidence Stat order"
        )
    frame = evidence.frame
    complete_frames: list[pd.DataFrame] = []
    complete_weights: list[float] = []
    complete_match_ids: list[int] = []
    complete_series_ids: list[int] = []
    team_index = {team_id: index for index, team_id in enumerate(evidence.team_ids)}
    for (current_team_id, match_id), group in frame.groupby(
        ["current_team_id", "match_id"], sort=True
    ):
        if int(current_team_id) not in team_index or group["historical_team_id"].nunique() != 1:
            continue
        expected = evidence.player_ids_by_team[team_index[int(current_team_id)]]
        indexed = group.set_index("account_id", drop=False)
        if any(int(account_id) not in indexed.index for account_id in expected):
            continue
        ordered = indexed.loc[list(expected)]
        if isinstance(ordered, pd.Series):
            ordered = ordered.to_frame().T
        if len(ordered) != 5 or any(
            pd.to_numeric(ordered[stat_id], errors="coerce").isna().any()
            for stat_id in evidence.stat_ids
        ):
            continue
        complete_frames.append(ordered.reset_index(drop=True))
        complete_weights.append(float(pd.to_numeric(ordered["evidence_weight"]).mean()))
        complete_match_ids.append(int(match_id))
        complete_series_ids.append(int(ordered["series_id"].iloc[0]))
    if len(complete_frames) < 20:
        raise MainPlayerRoleGeneratorError(
            "insufficient complete Games for joint residual fitting"
        )
    complete_frame = pd.concat(complete_frames, ignore_index=True)
    complete_design = encoder.transform(complete_frame)
    complete_matrix = np.empty(
        (len(complete_frames), 5, len(evidence.stat_ids)), dtype=float
    )
    for stat_index, stat_id in enumerate(evidence.stat_ids):
        complete_matrix[:, :, stat_index] = marginal_models[
            stat_id
        ].latent_from_observed(
            complete_frame,
            encoder,
            pd.to_numeric(complete_frame[stat_id], errors="raise").to_numpy(
                dtype=float
            ),
            design=complete_design,
        ).reshape(len(complete_frames), 5)
    probabilities = cap_grouped_probability_mass(
        np.asarray(complete_weights, dtype=float),
        np.asarray(complete_series_ids),
        maximum_item_mass=maximum_residual_game_mass,
        maximum_group_mass=maximum_residual_series_mass,
    )
    return JointResidualTrainingSet(
        values=complete_matrix.reshape(len(complete_frames), -1),
        probabilities=probabilities,
        match_ids=np.asarray(complete_match_ids),
        series_ids=np.asarray(complete_series_ids),
    )


def fit_player_role_generator_from_frame(
    evidence: PlayerRoleEvidence,
    *,
    ridge_alpha: float,
    recent_effective_sample_constant: float,
    recent_residual_cap_sigma: float,
    factor_rank: int,
    covariance_shrinkage: float,
    latent_scale: float = 1.0,
    maximum_game_parameter_mass: float,
    maximum_series_parameter_mass: float,
    maximum_residual_game_mass: float,
    maximum_residual_series_mass: float,
) -> PlayerRoleGeneratorModel:
    """Fit one deterministic research-only generator from an already governed evidence frame."""

    frame = evidence.frame.copy()
    base_weights = pd.to_numeric(frame["evidence_weight"], errors="coerce").to_numpy(dtype=float)
    if np.any(base_weights <= 0.0) or not np.isfinite(base_weights).all():
        raise MainPlayerRoleGeneratorError("Player-role evidence weights must be finite and positive")
    duration_values = pd.to_numeric(frame["duration"], errors="coerce").to_numpy(dtype=float)
    duration_mass = cap_nested_evidence_weights(
        base_weights,
        frame["match_id"].to_numpy(),
        frame["series_id"].to_numpy(),
        maximum_game_mass=maximum_game_parameter_mass,
        maximum_series_mass=maximum_series_parameter_mass,
    )
    log_duration = np.log1p(duration_values)
    duration_center = float(np.dot(duration_mass, log_duration))
    duration_scale = float(
        np.sqrt(np.dot(duration_mass, np.square(log_duration - duration_center)))
    )
    duration_scale = max(duration_scale, 1e-3)
    encoder = ContextEncoder(
        player_ids=evidence.player_ids,
        player_roles=evidence.player_roles,
        current_team_ids=evidence.team_ids,
        player_current_team_ids=evidence.player_current_team_ids,
        duration_center=duration_center,
        duration_scale=duration_scale,
    )

    duration_frame = (
        frame.sort_values(["start_time", "match_id", "current_team_id"], kind="stable")
        .drop_duplicates(["current_team_id", "match_id"], keep="last")
        .reset_index(drop=True)
    )
    duration_weights = cap_nested_evidence_weights(
        pd.to_numeric(duration_frame["evidence_weight"], errors="coerce").to_numpy(dtype=float),
        duration_frame["match_id"].to_numpy(),
        duration_frame["series_id"].to_numpy(),
        maximum_game_mass=maximum_game_parameter_mass,
        maximum_series_mass=maximum_series_parameter_mass,
    )
    duration_design = _duration_design(duration_frame)
    duration_target = np.log1p(
        pd.to_numeric(duration_frame["duration"], errors="raise").to_numpy(dtype=float)
    )
    duration_coefficients = _fit_weighted_ridge(
        duration_design,
        duration_target,
        duration_weights,
        alpha=ridge_alpha,
    )
    duration_residual = duration_target - duration_design @ duration_coefficients
    duration_quantiles = _weighted_quantile_grid(duration_residual, duration_weights)
    duration_support = _weighted_quantile_grid(
        np.expm1(duration_target), duration_weights, points=1001
    )
    duration_model = GameDurationModel(
        coefficients=duration_coefficients,
        residual_quantiles=duration_quantiles,
        lower_seconds=max(300.0, float(duration_support[5])),
        upper_seconds=max(301.0, float(duration_support[-6])),
    )

    marginal_models: dict[str, StatMarginalModel] = {}
    marginal_audit: dict[str, Any] = {}
    for stat_id in evidence.stat_ids:
        numeric = pd.to_numeric(frame[stat_id], errors="coerce")
        available = numeric.notna().to_numpy()
        if available.sum() < max(20, encoder.feature_count // 2):
            raise MainPlayerRoleGeneratorError(f"insufficient Player-role evidence for {stat_id}")
        selected = frame.loc[available].copy()
        target = numeric.loc[available].to_numpy(dtype=float)
        if np.any(target < 0.0):
            raise MainPlayerRoleGeneratorError(f"negative raw Fantasy Stat observed for {stat_id}")
        weights = cap_nested_evidence_weights(
            base_weights[available],
            selected["match_id"].to_numpy(),
            selected["series_id"].to_numpy(),
            maximum_game_mass=maximum_game_parameter_mass,
            maximum_series_mass=maximum_series_parameter_mass,
        )
        design = encoder.transform(selected)
        is_zero = (target <= 0.0).astype(int)
        zero_coefficients = _fit_weighted_logistic(
            design,
            is_zero,
            weights,
            alpha=ridge_alpha,
        )
        positive = target > 0.0
        if positive.sum() < 5:
            raise MainPlayerRoleGeneratorError(f"insufficient positive Player-role evidence for {stat_id}")
        mean_coefficients = _fit_weighted_ridge(
            design[positive],
            np.log1p(target[positive]),
            weights[positive],
            alpha=ridge_alpha,
        )

        positive_location = design @ mean_coefficients
        zero_probability = expit(design @ zero_coefficients)
        positive_residual = np.log1p(target) - positive_location
        role_by_player = encoder.role_by_player
        accounts = selected["account_id"].astype(int).to_numpy()
        roles = np.asarray([role_by_player[int(account_id)] for account_id in accounts])
        residual_scale_by_role: dict[str, float] = {}
        for role in ROLE_IDS:
            mask = positive & (roles == role)
            if not np.any(mask):
                residual_scale_by_role[role] = float(np.std(positive_residual[positive]))
                continue
            local_weight = weights[mask] / weights[mask].sum()
            local_center = float(np.dot(local_weight, positive_residual[mask]))
            residual_scale_by_role[role] = float(
                np.sqrt(np.dot(local_weight, np.square(positive_residual[mask] - local_center)))
            )

        recent_mean: dict[int, float] = {}
        recent_zero: dict[int, float] = {}
        starts = pd.to_datetime(selected["start_time"], utc=True)
        age_days = np.maximum(
            0.0,
            (pd.Timestamp(evidence.as_of) - starts).dt.total_seconds().to_numpy(dtype=float) / 86400.0,
        )
        recent_multiplier = np.power(0.5, age_days / 60.0)
        for account_id in evidence.player_ids:
            player = accounts == account_id
            player_positive = player & positive
            if np.any(player_positive):
                local_weight = weights[player_positive] * recent_multiplier[player_positive]
                effective = _effective_sample_size(local_weight)
                residual_mean = float(
                    np.dot(local_weight / local_weight.sum(), positive_residual[player_positive])
                )
                role = role_by_player[account_id]
                cap = recent_residual_cap_sigma * max(residual_scale_by_role[role], 1e-6)
                recent_mean[account_id] = bounded_recent_adjustment(
                    residual_mean,
                    effective_sample_size=effective,
                    shrinkage_constant=recent_effective_sample_constant,
                    cap=cap,
                )
            if np.any(player):
                local_weight = weights[player] * recent_multiplier[player]
                effective = _effective_sample_size(local_weight)
                binary_residual = float(
                    np.dot(
                        local_weight / local_weight.sum(),
                        is_zero[player] - zero_probability[player],
                    )
                )
                denominator = float(
                    np.average(
                        np.maximum(zero_probability[player] * (1.0 - zero_probability[player]), 1e-3),
                        weights=local_weight,
                    )
                )
                recent_zero[account_id] = bounded_recent_adjustment(
                    binary_residual / denominator,
                    effective_sample_size=effective,
                    shrinkage_constant=recent_effective_sample_constant,
                    cap=1.0,
                )

        adjusted_location = positive_location + np.asarray(
            [recent_mean.get(int(account_id), 0.0) for account_id in accounts]
        )
        adjusted_residual = np.log1p(target) - adjusted_location
        quantiles: dict[str, np.ndarray] = {}
        global_positive = positive
        for role in ROLE_IDS:
            mask = positive & (roles == role)
            if not np.any(mask):
                mask = global_positive
            quantiles[role] = _weighted_quantile_grid(adjusted_residual[mask], weights[mask])
        marginal = StatMarginalModel(
            stat_id=stat_id,
            mean_coefficients=mean_coefficients,
            zero_coefficients=zero_coefficients,
            positive_residual_quantiles=quantiles,
            recent_mean_adjustments=recent_mean,
            recent_zero_adjustments=recent_zero,
            integer_output=stat_id in INTEGER_STAT_IDS,
            upper_bound=(
                1.0 if stat_id in {"first_blood", "teamfight_participation"} else None
            ),
        )
        marginal_models[stat_id] = marginal
        marginal_audit[stat_id] = {
            "available_rows": int(available.sum()),
            "positive_rows": int(positive.sum()),
            "zero_rate": float(np.average(is_zero, weights=weights)),
            "effective_sample_size": _effective_sample_size(weights),
            "maximum_game_mass": float(
                max(
                    weights[selected["match_id"].to_numpy() == match_id].sum()
                    for match_id in selected["match_id"].unique()
                )
            ),
            "maximum_series_mass": float(
                max(
                    weights[selected["series_id"].to_numpy() == series_id].sum()
                    for series_id in selected["series_id"].unique()
                )
            ),
        }

    residual_training = build_joint_residual_training_set(
        evidence,
        encoder=encoder,
        marginal_models=marginal_models,
        maximum_residual_game_mass=maximum_residual_game_mass,
        maximum_residual_series_mass=maximum_residual_series_mass,
    )
    if len(residual_training.values) < factor_rank + 2:
        raise MainPlayerRoleGeneratorError("insufficient complete Games for joint residual fitting")
    joint = fit_joint_residual_model(
        residual_training.values,
        residual_training.probabilities,
        factor_rank=factor_rank,
        covariance_shrinkage=covariance_shrinkage,
        latent_scale=latent_scale,
    )
    audit = {
        "as_of": evidence.as_of.isoformat().replace("+00:00", "Z"),
        "training_rows": len(frame),
        "complete_joint_games": len(residual_training.values),
        "complete_joint_series": len(set(residual_training.series_ids.tolist())),
        "maximum_residual_game_mass": float(residual_training.probabilities.max()),
        "maximum_residual_series_mass": float(
            max(
                residual_training.probabilities[
                    residual_training.series_ids == series_id
                ].sum()
                for series_id in set(residual_training.series_ids.tolist())
            )
        ),
        "ridge_alpha": float(ridge_alpha),
        "recent_effective_sample_constant": float(recent_effective_sample_constant),
        "recent_residual_cap_sigma": float(recent_residual_cap_sigma),
        "factor_rank": int(factor_rank),
        "covariance_shrinkage": float(covariance_shrinkage),
        "latent_scale": float(latent_scale),
        "duration": {
            "training_rows": len(duration_frame),
            "effective_sample_size": _effective_sample_size(duration_weights),
            "lower_seconds": duration_model.lower_seconds,
            "upper_seconds": duration_model.upper_seconds,
        },
        "marginals": marginal_audit,
    }
    semantic_hash = sha256_json(
        {
            "encoder": {
                "player_ids": encoder.player_ids,
                "player_roles": encoder.player_roles,
                "current_team_ids": encoder.current_team_ids,
                "player_current_team_ids": encoder.player_current_team_ids,
                "duration_center": encoder.duration_center,
                "duration_scale": encoder.duration_scale,
            },
            "stat_ids": evidence.stat_ids,
            "duration": {
                "coefficients": duration_model.coefficients.tolist(),
                "residual_quantiles": duration_model.residual_quantiles.tolist(),
                "lower_seconds": duration_model.lower_seconds,
                "upper_seconds": duration_model.upper_seconds,
            },
            "marginals": [_marginal_model_hash(marginal_models[stat_id]) for stat_id in evidence.stat_ids],
            "joint": {
                "loadings": joint.loadings.tolist(),
                "idiosyncratic_variance": joint.idiosyncratic_variance.tolist(),
                "training_center": joint.training_center.tolist(),
                "training_scale": joint.training_scale.tolist(),
                "sample_scale": joint.sample_scale,
            },
            "audit": audit,
        }
    )
    return PlayerRoleGeneratorModel(
        encoder=encoder,
        stat_ids=evidence.stat_ids,
        player_ids_by_team=evidence.player_ids_by_team,
        marginal_models=marginal_models,
        duration_model=duration_model,
        joint_residual=joint,
        audit=audit,
        semantic_hash=semantic_hash,
    )


__all__ = [
    "ContextEncoder",
    "GameDurationModel",
    "INTEGER_STAT_IDS",
    "JointResidualModel",
    "JointResidualSampler",
    "JointResidualTrainingSet",
    "MainPlayerRoleGeneratorConfig",
    "MainPlayerRoleGeneratorError",
    "PlayerRoleEvidence",
    "PlayerRoleEvidenceBuildResult",
    "PlayerRoleGeneratorModel",
    "StatMarginalModel",
    "bounded_recent_adjustment",
    "build_joint_residual_training_set",
    "build_player_role_evidence",
    "cap_grouped_probability_mass",
    "cap_nested_evidence_weights",
    "cap_probability_mass",
    "fit_joint_residual_model",
    "fit_player_role_generator_from_frame",
    "load_main_player_role_generator_config",
]
