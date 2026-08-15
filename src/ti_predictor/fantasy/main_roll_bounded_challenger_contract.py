"""Frozen contract for runtime-bounded, research-only Main Roll challengers.

This contract is intentionally separate from the earlier G/T/H coverage manifest.  The
earlier 1,000 synthetic cases have already informed the hypotheses in this study, so this
version freezes a new generator seed, new Roll tapes, explicit candidate runtime limits,
and an independent 100/900 screen-and-confirm split.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ti_predictor.fantasy.main_roll_research_contract import GreedyStrategySpec
from ti_predictor.fantasy.main_roll_research_states import (
    BaseResearchManifestReference,
    CoverageIndexRange,
    SensitivityPanelSpec,
    StartingStateGeneratorSpec,
)
from ti_predictor.hashing import sha256_json
from ti_predictor.schemas import as_utc


class BoundedChallengerContractError(ValueError):
    """A bounded-challenger manifest violates its research or runtime boundary."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BoundedChallengerSplits(_StrictModel):
    development: CoverageIndexRange
    confirmation: CoverageIndexRange
    development_use: Literal["candidate-screen-and-parameter-freeze-only"]

    @model_validator(mode="after")
    def validate_split(self) -> BoundedChallengerSplits:
        development = set(self.development.values)
        confirmation = set(self.confirmation.values)
        if development & confirmation:
            raise BoundedChallengerContractError("development and confirmation cases must be disjoint")
        combined = sorted(development | confirmation)
        if combined != list(range(len(combined))):
            raise BoundedChallengerContractError(
                "bounded-challenger case indices must form one zero-based range"
            )
        if self.development.count != 100 or self.confirmation.count != 900:
            raise BoundedChallengerContractError(
                "bounded challengers require 100 development and 900 confirmation cases"
            )
        return self


class PriorCoverageManifestReference(_StrictModel):
    relative_path: str = Field(min_length=1)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise BoundedChallengerContractError("prior coverage manifest path must stay repository-relative")
        return value


class SafeBandStrategySpec(_StrictModel):
    policy_id: Literal["main-greedy-safe-band-v1"]
    mean_band_fraction: float = Field(gt=0.0, le=0.01)
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    improvement_tolerance: float = Field(ge=0.0)


class LocalTieStrategySpec(_StrictModel):
    policy_id: Literal["main-greedy-local-configuration-tiebreak-v1"]
    mean_band_fraction: float = Field(gt=0.0, le=0.01)
    cvar_retention_fraction: float = Field(ge=0.0, le=0.01)
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    improvement_tolerance: float = Field(ge=0.0)


class SelectiveTwoStepStrategySpec(_StrictModel):
    policy_id: Literal[
        "main-greedy-selective-two-step-v1",
        "main-greedy-selective-two-step-v2",
    ]
    ambiguity_fraction: float = Field(gt=0.0, le=0.01)
    minimum_override_fraction: float = Field(ge=0.0, le=0.01)
    sample_count: int = Field(ge=2, le=16)
    candidate_limit: Literal[2]
    max_triggers_per_episode: int = Field(ge=1, le=8)
    decision_seed: int = Field(ge=0)
    cvar_alpha: float = Field(gt=0.0, le=1.0)


class BoundedChallengerStrategies(_StrictModel):
    baseline: GreedyStrategySpec
    safe_band: SafeBandStrategySpec
    local_tie: LocalTieStrategySpec
    selective_two_step: SelectiveTwoStepStrategySpec

    @property
    def candidate_policy_ids(self) -> tuple[str, ...]:
        return (
            self.safe_band.policy_id,
            self.local_tie.policy_id,
            self.selective_two_step.policy_id,
        )

    @property
    def policy_ids(self) -> tuple[str, ...]:
        return (self.baseline.policy_id, *self.candidate_policy_ids)


class CandidateRuntimeGate(_StrictModel):
    reference_worker_count: int = Field(ge=1, le=64)
    ideal_confirmation_seconds_per_candidate: Literal[3600]
    maximum_confirmation_seconds_per_candidate: Literal[7200]
    projection_method: Literal["development-active-seconds-linear-scale"]
    advancement_limit: int = Field(ge=1, le=2)
    minimum_development_mean_difference: float = Field(ge=0.0)
    cvar_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)
    conditional_runtime_minimum_relative_gain: float = Field(ge=0.0, lt=1.0)
    ranking: Literal["mean-then-cvar-then-frozen-complexity"]


class BoundedConfirmationGate(_StrictModel):
    confidence_level: float = Field(gt=0.5, lt=1.0)
    minimum_relative_mean_gain: float = Field(ge=0.0, lt=1.0)
    cvar_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)
    stratum_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)
    minimum_stratum_count: int = Field(ge=2)
    require_primary_mean_ci_above_zero: Literal[True]
    require_nonnegative_mean_all_probability_models: Literal[True]
    require_every_eligible_stratum_noninferior: Literal[True]
    require_every_roster_fold_noninferior: Literal[True]
    automatic_web_promotion: Literal[False]


class MainRollBoundedChallengerManifest(_StrictModel):
    schema_version: Literal[1]
    experiment_id: Literal[
        "ti2026-main-roll-bounded-challengers-v1",
        "ti2026-main-roll-bounded-challengers-v2",
    ]
    period: Literal["main"]
    as_of: str
    research_only: Literal[True]
    web_integration: Literal[False]
    runtime_pointer_writes: Literal[False]
    dota_client_control: Literal[False]
    interpretation: Literal["synthetic-legal-coverage-not-player-population-expectation"]
    base_research_manifest: BaseResearchManifestReference
    prior_coverage_manifest: PriorCoverageManifestReference
    prior_coverage_exclusion: Literal["hypothesis-generating-only-not-reused-for-development-or-confirmation"]
    parent_bounded_challenger_manifest: PriorCoverageManifestReference | None = None
    revision_basis: Literal["v1-development-100-state-trigger-budget-revision-before-confirmation"] | None = (
        None
    )
    roll_tape_namespace_semantic_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    generator: StartingStateGeneratorSpec
    splits: BoundedChallengerSplits
    primary_probability_model: Literal["client-weight-primary-v1"]
    paired_roll_tape: Literal["same-within-state-and-model-across-baseline-and-challengers"]
    sensitivity_panel: SensitivityPanelSpec
    strategies: BoundedChallengerStrategies
    runtime_gate: CandidateRuntimeGate
    confirmation_gate: BoundedConfirmationGate
    coverage_dimensions: tuple[
        Literal[
            "average-quality-band",
            "direct-quality-increment-offer",
            "conditional-trait-ready-banner-band",
            "initial-terminal-value-rank-quartile",
        ],
        ...,
    ]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: str) -> str:
        parsed = as_utc(value)
        canonical = None if parsed is None else parsed.isoformat().replace("+00:00", "Z")
        if canonical != value:
            raise BoundedChallengerContractError("bounded-challenger as_of must be canonical UTC")
        return value

    @model_validator(mode="after")
    def validate_design(self) -> MainRollBoundedChallengerManifest:
        is_revision = self.experiment_id.endswith("-v2")
        if is_revision != (self.strategies.selective_two_step.policy_id.endswith("-v2")):
            raise BoundedChallengerContractError(
                "bounded-challenger experiment and selective-two-step policy versions must match"
            )
        if is_revision and (
            self.parent_bounded_challenger_manifest is None
            or self.revision_basis is None
            or self.roll_tape_namespace_semantic_sha256 is None
        ):
            raise BoundedChallengerContractError(
                "a bounded-challenger revision must identify its parent, development basis, "
                "and Roll tape namespace"
            )
        if not is_revision and (
            self.parent_bounded_challenger_manifest is not None
            or self.revision_basis is not None
            or self.roll_tape_namespace_semantic_sha256 is not None
        ):
            raise BoundedChallengerContractError(
                "the initial bounded-challenger experiment cannot declare revision metadata"
            )
        if (
            is_revision
            and self.parent_bounded_challenger_manifest is not None
            and self.roll_tape_namespace_semantic_sha256
            != self.parent_bounded_challenger_manifest.semantic_sha256
        ):
            raise BoundedChallengerContractError(
                "the revision Roll tape namespace must match its parent semantic SHA-256"
            )
        if self.sensitivity_panel.confirmation_state_count != 100:
            raise BoundedChallengerContractError(
                "bounded-challenger sensitivity requires 100 confirmation cases"
            )
        if self.runtime_gate.reference_worker_count != 8:
            raise BoundedChallengerContractError(
                "the frozen runtime comparison uses the observed eight-worker baseline"
            )
        expected_dimensions = {
            "average-quality-band",
            "direct-quality-increment-offer",
            "conditional-trait-ready-banner-band",
            "initial-terminal-value-rank-quartile",
        }
        if set(self.coverage_dimensions) != expected_dimensions or len(self.coverage_dimensions) != 4:
            raise BoundedChallengerContractError("bounded-challenger coverage dimensions are incomplete")
        if len(set(self.strategies.policy_ids)) != len(self.strategies.policy_ids):
            raise BoundedChallengerContractError("bounded-challenger policy IDs must be unique")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json", exclude_none=True))

    @property
    def state_indices(self) -> tuple[int, ...]:
        return self.splits.development.values + self.splits.confirmation.values

    def split_for(self, state_index: int) -> Literal["development", "confirmation"]:
        if state_index in self.splits.development.values:
            return "development"
        if state_index in self.splits.confirmation.values:
            return "confirmation"
        raise BoundedChallengerContractError(
            f"state index {state_index} is outside the bounded-challenger split"
        )


def load_main_roll_bounded_challenger_manifest(
    path: Path,
) -> MainRollBoundedChallengerManifest:
    return MainRollBoundedChallengerManifest.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "BoundedChallengerContractError",
    "MainRollBoundedChallengerManifest",
    "load_main_roll_bounded_challenger_manifest",
]
