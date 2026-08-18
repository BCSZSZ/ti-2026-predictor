"""Research-only Series-capped v1/B1 Fantasy mixture."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import Field, field_validator, model_validator

from ti_predictor.fantasy.main_player_role_backtest import (
    EvaluationSeries,
    HistoricalSeriesTemplate,
    _series_candidates,
    sample_player_role_series,
)
from ti_predictor.fantasy.main_player_role_generator import (
    PlayerRoleEvidenceConfig,
    PlayerRoleFoldConfig,
    PlayerRoleGeneratorModel,
    PlayerRoleSimulationConfig,
)
from ti_predictor.fantasy.main_player_role_generator_b2 import FrozenB1Parameters
from ti_predictor.hashing import sha256_json
from ti_predictor.schemas import StrictModel, as_utc


class MainSeriesQuotaHybridError(ValueError):
    """The Series-capped hybrid contract or draw is invalid."""


class MainSeriesQuotaHybridConfig(StrictModel):
    schema_version: Literal[1]
    experiment_id: Literal[
        "ti2026-main-series-quota-v1-b1-hybrid",
        "ti2026-main-series-quota-v1-b1-hybrid-precision",
    ]
    period: Literal["main"]
    as_of: datetime
    maximum_final_series_mass: float = Field(gt=0.0, lt=1.0)
    truncated_mass_destination: Literal["frozen-b1"]
    minimum_conditioned_series: int = Field(ge=1)
    evidence: PlayerRoleEvidenceConfig
    frozen_b1: FrozenB1Parameters
    simulation: PlayerRoleSimulationConfig
    evaluation_folds: list[PlayerRoleFoldConfig] = Field(min_length=1)
    diagnostic_fold: PlayerRoleFoldConfig
    research_only: Literal[True]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        cutoff = as_utc(value)
        if cutoff is None:
            raise ValueError("Series quota hybrid requires explicit UTC as_of")
        return cutoff

    @model_validator(mode="after")
    def validate_fold_contract(self) -> MainSeriesQuotaHybridConfig:
        if sorted(self.evaluation_folds, key=lambda fold: fold.train_as_of) != self.evaluation_folds:
            raise ValueError("Series quota evaluation folds must be time ordered")
        league_ids = [fold.league_id for fold in self.evaluation_folds]
        if len(set(league_ids)) != len(league_ids):
            raise ValueError("Series quota evaluation leagues must be unique")
        if self.diagnostic_fold.league_id in set(league_ids):
            raise ValueError("Series quota diagnostic cannot be an evaluation league")
        if self.as_of < max(
            [self.diagnostic_fold.test_end, *(fold.test_end for fold in self.evaluation_folds)]
        ):
            raise ValueError("Series quota as_of cannot precede a fold completion")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


def load_main_series_quota_hybrid_config(
    path: str | Path,
) -> MainSeriesQuotaHybridConfig:
    return MainSeriesQuotaHybridConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class QuotaHybridDrawAudit:
    team_id: int
    target_series_id: int
    fallback_level: int | None
    candidate_series_count: int
    draws: int
    future_games_per_draw: int
    theoretical_v1_mass: float
    theoretical_b1_mass: float
    theoretical_max_primary_series_mass: float
    realized_v1_draws: int
    primary_series_counts: dict[int, int]
    actual_game_source_counts: dict[str, int]


def _derived_seed(base_seed: int, label: str) -> int:
    material = f"{int(base_seed)}:series-quota-hybrid:{label}"
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")


def _draw_v1_for_sources(
    *,
    candidates: list[HistoricalSeriesTemplate],
    source_indexes: np.ndarray,
    target: EvaluationSeries,
    b1_values: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, Counter[int], Counter[str]]:
    count = len(source_indexes)
    result = np.ascontiguousarray(b1_values, dtype=np.float32).copy()
    if result.shape != (
        count,
        len(target.match_ids),
        5,
        target.raw_stats.shape[-1],
    ):
        raise MainSeriesQuotaHybridError("quota hybrid B1 fallback values do not align")
    primary_counts: Counter[int] = Counter()
    game_counts: Counter[str] = Counter()
    for sample_index, source_index in enumerate(source_indexes):
        source = candidates[int(source_index)]
        primary_counts[source.series_id] += 1
        for game_index, desired_win in enumerate(target.won_games):
            local = [offset for offset, won in enumerate(source.won_games) if won == desired_win]
            if local:
                source_game = int(rng.choice(local))
                result[sample_index, game_index] = source.raw_stats[source_game]
                game_counts[f"{source.series_id}:{source_game}"] += 1
            # If the selected Series has no matching result, keep this Game's
            # already-generated B1 value. Borrowing from another Series would
            # bypass the final 10% source-Series quota.
    return result, primary_counts, game_counts


def sample_series_quota_hybrid(
    model: PlayerRoleGeneratorModel,
    templates: tuple[HistoricalSeriesTemplate, ...],
    target: EvaluationSeries,
    *,
    sample_count: int,
    seed: int,
    maximum_final_series_mass: float,
    minimum_conditioned_series: int = 3,
) -> tuple[np.ndarray, QuotaHybridDrawAudit]:
    """Draw v1 up to each Series cap and route every truncated probability to B1."""

    if sample_count < 1 or not 0.0 < maximum_final_series_mass < 1.0:
        raise MainSeriesQuotaHybridError("quota hybrid draw contract is invalid")
    b1 = sample_player_role_series(
        model,
        target,
        sample_count=sample_count,
        seed=_derived_seed(seed, "b1"),
    )
    if not any(item.team_id == target.current_team_id for item in templates):
        return b1, QuotaHybridDrawAudit(
            team_id=target.current_team_id,
            target_series_id=target.series_id,
            fallback_level=None,
            candidate_series_count=0,
            draws=sample_count,
            future_games_per_draw=len(target.match_ids),
            theoretical_v1_mass=0.0,
            theoretical_b1_mass=1.0,
            theoretical_max_primary_series_mass=0.0,
            realized_v1_draws=0,
            primary_series_counts={},
            actual_game_source_counts={},
        )
    candidates, fallback = _series_candidates(
        templates,
        target,
        minimum_conditioned_series=minimum_conditioned_series,
    )
    original = np.asarray([item.evidence_weight for item in candidates], dtype=float)
    original /= original.sum()
    retained = np.minimum(original, float(maximum_final_series_mass))
    v1_mass = float(retained.sum())
    b1_mass = 1.0 - v1_mass
    if v1_mass > 1.0 + 1e-12 or b1_mass < -1e-12:
        raise MainSeriesQuotaHybridError("quota hybrid probability mass is invalid")
    component_rng = np.random.default_rng(_derived_seed(seed, "component"))
    v1_positions = np.flatnonzero(component_rng.random(sample_count) < v1_mass)
    primary_counts: Counter[int] = Counter()
    game_counts: Counter[str] = Counter()
    if len(v1_positions):
        v1_rng = np.random.default_rng(_derived_seed(seed, "v1"))
        source_indexes = v1_rng.choice(
            len(candidates),
            size=len(v1_positions),
            replace=True,
            p=retained / v1_mass,
        )
        v1, primary_counts, game_counts = _draw_v1_for_sources(
            candidates=candidates,
            source_indexes=source_indexes,
            target=target,
            b1_values=b1[v1_positions],
            rng=v1_rng,
        )
        b1[v1_positions] = v1
    audit = QuotaHybridDrawAudit(
        team_id=target.current_team_id,
        target_series_id=target.series_id,
        fallback_level=fallback,
        candidate_series_count=len(candidates),
        draws=sample_count,
        future_games_per_draw=len(target.match_ids),
        theoretical_v1_mass=v1_mass,
        theoretical_b1_mass=max(0.0, b1_mass),
        theoretical_max_primary_series_mass=float(retained.max()),
        realized_v1_draws=len(v1_positions),
        primary_series_counts=dict(primary_counts),
        actual_game_source_counts=dict(game_counts),
    )
    return b1, audit


@dataclass
class SeriesQuotaHybridSampler:
    templates: tuple[HistoricalSeriesTemplate, ...]
    maximum_final_series_mass: float
    minimum_conditioned_series: int = 3
    audits: list[QuotaHybridDrawAudit] = field(default_factory=list)

    def __call__(
        self,
        model: PlayerRoleGeneratorModel,
        target: EvaluationSeries,
        *,
        sample_count: int,
        seed: int,
    ) -> np.ndarray:
        values, audit = sample_series_quota_hybrid(
            model,
            self.templates,
            target,
            sample_count=sample_count,
            seed=seed,
            maximum_final_series_mass=self.maximum_final_series_mass,
            minimum_conditioned_series=self.minimum_conditioned_series,
        )
        self.audits.append(audit)
        return values


__all__ = [
    "MainSeriesQuotaHybridConfig",
    "MainSeriesQuotaHybridError",
    "QuotaHybridDrawAudit",
    "SeriesQuotaHybridSampler",
    "load_main_series_quota_hybrid_config",
    "sample_series_quota_hybrid",
]
