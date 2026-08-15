"""Versioned user-facing strategy catalog for Main current-screen advice."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ti_predictor.hashing import sha256_json
from ti_predictor.paths import PATHS
from ti_predictor.schemas import StrictModel

GREEDY_MAIN_STRATEGY_ID = "main-greedy-immediate-v1"
G_LITE_MAIN_STRATEGY_ID = "main-greedy-selective-two-step-v1"


class MainAdviceStrategyError(ValueError):
    """A Main advice strategy catalog is incomplete or internally inconsistent."""


class GreedyMainStrategySpec(StrictModel):
    strategy_id: Literal["main-greedy-immediate-v1"]
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    improvement_tolerance: float = Field(ge=0.0)
    evaluated_mean_retention_epsilon: Literal[0.0]


class GLiteResearchEvidence(StrictModel):
    bounded_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_screen_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_state_count: Literal[100]
    relative_mean_gain: float
    evidence_status: Literal["development-positive-user-opt-in-not-confirmed"]


class GLiteMainStrategySpec(StrictModel):
    strategy_id: Literal["main-greedy-selective-two-step-v1"]
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    ambiguity_fraction: Literal[0.0005]
    minimum_override_fraction: Literal[0.0001]
    sample_count: Literal[4]
    candidate_limit: Literal[2]
    max_triggers_per_episode: Literal[4]
    decision_seed: Literal[2026081504]
    cvar_alpha: Literal[0.1]
    research_evidence: GLiteResearchEvidence


class MainAdviceStrategies(StrictModel):
    greedy: GreedyMainStrategySpec
    g_lite: GLiteMainStrategySpec

    @property
    def ids(self) -> tuple[str, str]:
        return self.greedy.strategy_id, self.g_lite.strategy_id


class MainAdviceStrategyCatalog(StrictModel):
    schema_version: Literal[1]
    catalog_id: Literal["ti2026-main-advice-strategies-v1"]
    period: Literal["main"]
    default_strategy_id: Literal["main-greedy-immediate-v1"]
    default_risk_profile: Literal["mean-first"]
    primary_transition_model: Literal["client-weight-primary-v1"]
    promotion_decision: Literal["user-selected-dual-strategy-2026-08-15"]
    automatic_web_promotion: Literal[False]
    strategies: MainAdviceStrategies

    @model_validator(mode="after")
    def validate_catalog(self) -> MainAdviceStrategyCatalog:
        if self.strategies.ids != (GREEDY_MAIN_STRATEGY_ID, G_LITE_MAIN_STRATEGY_ID):
            raise MainAdviceStrategyError("Main strategy catalog IDs or order drifted")
        if self.strategies.g_lite.research_evidence.relative_mean_gain <= 0.0:
            raise MainAdviceStrategyError("G-Lite opt-in evidence must retain its positive point estimate")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))

    def label(self, strategy_id: str) -> str:
        if strategy_id == self.strategies.greedy.strategy_id:
            return self.strategies.greedy.label
        if strategy_id == self.strategies.g_lite.strategy_id:
            return self.strategies.g_lite.label
        raise MainAdviceStrategyError(f"unknown Main advice strategy: {strategy_id}")


def load_main_advice_strategy_catalog(
    path: Path = PATHS.config / "models" / "fantasy-main-advice-strategies-v1.json",
) -> MainAdviceStrategyCatalog:
    return MainAdviceStrategyCatalog.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "GREEDY_MAIN_STRATEGY_ID",
    "G_LITE_MAIN_STRATEGY_ID",
    "GLiteMainStrategySpec",
    "GreedyMainStrategySpec",
    "MainAdviceStrategies",
    "MainAdviceStrategyCatalog",
    "MainAdviceStrategyError",
    "load_main_advice_strategy_catalog",
]
