"""Frozen contracts for the isolated Main Roll strategy research path.

Nothing in the Web or live advisor stack imports this module.  It describes offline
experiments only and deliberately carries explicit flags that prohibit runtime-pointer
writes, Dota client control, and Web integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ti_predictor.hashing import sha256_json
from ti_predictor.schemas import as_utc

SHA256_PATTERN = r"^[0-9a-f]{64}$"
PRIMARY_MODEL_ID = "client-weight-primary-v1"


class ResearchContractError(ValueError):
    """A research manifest is incomplete or crosses a production boundary."""


class ResearchStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FrozenResearchSource(ResearchStrictModel):
    rule_snapshot_id: str = Field(min_length=1)
    rule_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_rules_sha256: str = Field(pattern=SHA256_PATTERN)
    main_release_canonical_rules_sha256: str = Field(pattern=SHA256_PATTERN)
    roll_rules_sha256: str = Field(pattern=SHA256_PATTERN)
    main_release_sha256: str = Field(pattern=SHA256_PATTERN)
    main_release_file_sha256: str = Field(pattern=SHA256_PATTERN)
    group_scenario_sha256: str = Field(pattern=SHA256_PATTERN)
    group_scenario_as_of: str
    main_scenario_sha256: str = Field(pattern=SHA256_PATTERN)
    main_pool_sha256: str = Field(pattern=SHA256_PATTERN)
    team_strength_model_sha256: str = Field(pattern=SHA256_PATTERN)
    eligibility_mode: Literal["projected", "actual"]

    @field_validator("group_scenario_as_of")
    @classmethod
    def validate_group_scenario_as_of(cls, value: str) -> str:
        parsed = as_utc(value)
        canonical = None if parsed is None else parsed.isoformat().replace("+00:00", "Z")
        if canonical != value:
            raise ResearchContractError("source Group Scenario cutoff must be canonical UTC")
        return value


class FrozenStartingState(ResearchStrictModel):
    relative_path: str = Field(min_length=1)
    file_sha256: str = Field(pattern=SHA256_PATTERN)
    state_sha256: str = Field(pattern=SHA256_PATTERN)
    source_image_sha256: str = Field(pattern=SHA256_PATTERN)
    ocr_observation_sha256: str = Field(pattern=SHA256_PATTERN)
    remaining_rolls: Literal[30]

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ResearchContractError("starting-state path must stay relative to the repository")
        return value


class ProjectedRosterValidationSpec(ResearchStrictModel):
    scenario_kind: Literal["projected-derived-eight-team-roster"]
    objective: Literal["expected-roster-conditional-team-matching"]
    outer_source: Literal["all-frozen-group-scenario-rows"]
    outer_scenario_count: Literal[256]
    outer_weighting: Literal["empirical-row-equal"]
    fold_count: int = Field(ge=2, le=32)
    fold_salt: str = Field(min_length=1)
    tuning_folds: tuple[int, ...]
    confirmation_folds: tuple[int, ...]
    inner_scenarios_per_phase: int = Field(ge=2, le=128)
    inner_seed: int = Field(ge=0)
    convergence_inner_scenario_counts: tuple[int, ...]
    team_selection_phase: Literal["independent-inner-selection"]
    outcome_phase: Literal["independent-inner-evaluation"]

    @model_validator(mode="after")
    def validate_folds_and_inner_counts(self) -> ProjectedRosterValidationSpec:
        tuning = set(self.tuning_folds)
        confirmation = set(self.confirmation_folds)
        expected = set(range(self.fold_count))
        if not tuning or not confirmation or tuning & confirmation or tuning | confirmation != expected:
            raise ResearchContractError(
                "projected roster tuning and confirmation folds must partition every fold"
            )
        if not self.convergence_inner_scenario_counts or any(
            value < 2 or value > 128 for value in self.convergence_inner_scenario_counts
        ):
            raise ResearchContractError("projected inner convergence counts are invalid")
        if self.inner_scenarios_per_phase not in self.convergence_inner_scenario_counts:
            raise ResearchContractError("frozen inner Scenario count must be convergence-tested")
        return self


class ProbabilityModelSpec(ResearchStrictModel):
    model_id: str = Field(min_length=1)
    offer_weight_power: float = Field(gt=0.0, le=4.0)
    quality_weight_power: float = Field(gt=0.0, le=4.0)
    repeat_current_factor: float = Field(gt=0.0, le=1.0)
    multi_target_correlation: float = Field(ge=0.0, lt=1.0)
    random_target_sampling: Literal["uniform"]
    increment_boundary: Literal["clamp"]
    replacement_offer: Literal["independent"]


class GreedyStrategySpec(ResearchStrictModel):
    policy_id: Literal["main-greedy-immediate-v1"]
    mean_retention_epsilon: float = Field(ge=0.0, lt=1.0)
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    improvement_tolerance: float = Field(ge=0.0)


class TargetStrategySpec(ResearchStrictModel):
    policy_id: Literal["main-target-seeking-v1", "main-target-shape-distance-v2"]
    evaluation_mode: Literal["sampled-reachability", "exact-distance-potential"]
    decision_seed: int = Field(ge=0)
    candidate_limit: int = Field(ge=1, le=32)
    fractal_quality_permutation_limit: int = Field(ge=1, le=120)
    reachability_samples: int = Field(ge=4, le=4096)
    reachability_action_limit: int = Field(ge=2, le=32)
    potential_weight: float = Field(ge=0.0, le=10.0)
    maximum_immediate_loss_fraction: float = Field(ge=0.0, lt=1.0)
    cvar_alpha: float = Field(gt=0.0, le=1.0)


class HybridStrategySpec(ResearchStrictModel):
    policy_id: Literal["main-horizon-hybrid-v1", "main-horizon-hybrid-v2"]
    switch_mode: Literal["fixed", "adaptive-hit-time"]
    fixed_remaining_threshold: int = Field(ge=1, le=29)
    hit_time_quantile: float = Field(gt=0.5, lt=1.0)
    safety_buffer: int = Field(ge=0, le=10)
    minimum_reach_probability: float = Field(ge=0.0, le=1.0)


class StrategyFamilySpec(ResearchStrictModel):
    greedy: GreedyStrategySpec
    target: TargetStrategySpec
    hybrid: HybridStrategySpec


class SeedRange(ResearchStrictModel):
    start: int = Field(ge=0)
    count: int = Field(ge=2, le=100_000)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(range(self.start, self.start + self.count))


class ExperimentSplitSpec(ResearchStrictModel):
    tuning: SeedRange
    confirmation: SeedRange

    @model_validator(mode="after")
    def validate_disjoint(self) -> ExperimentSplitSpec:
        if set(self.tuning.values) & set(self.confirmation.values):
            raise ResearchContractError("tuning and confirmation seeds must be disjoint")
        return self


class TuningProtocolSpec(ResearchStrictModel):
    parameter_search_seed_count: int = Field(ge=1)
    candidate_validation_seed_count: int = Field(ge=2)
    minimum_validation_mean_difference: float = Field(ge=0.0)
    cvar_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)

    def validate_against(self, tuning: SeedRange) -> None:
        if self.parameter_search_seed_count + self.candidate_validation_seed_count != tuning.count:
            raise ResearchContractError(
                "tuning parameter-search and validation seeds must partition the tuning range"
            )


class ReleaseGateSpec(ResearchStrictModel):
    confidence_level: float = Field(gt=0.5, lt=1.0)
    minimum_relative_mean_gain: float = Field(ge=0.0, lt=1.0)
    cvar_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)
    require_primary_mean_ci_above_zero: Literal[True]
    require_probability_sensitivity_report: Literal[True]
    require_nonnegative_mean_all_probability_models: Literal[True]
    roster_fold_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)
    require_every_confirmation_fold_noninferior: Literal[True]
    direct_t_vs_h_minimum_relative_gain: float = Field(ge=0.0, lt=1.0)
    complexity_preference: Literal["target-unless-hybrid-materially-better"]
    automatic_web_promotion: Literal[False]


class MainRollResearchManifest(ResearchStrictModel):
    schema_version: Literal[2]
    experiment_id: str = Field(min_length=1)
    period: Literal["main"]
    as_of: str
    research_only: Literal[True]
    web_integration: Literal[False]
    runtime_pointer_writes: Literal[False]
    dota_client_control: Literal[False]
    source: FrozenResearchSource
    starting_state: FrozenStartingState
    projected_roster_validation: ProjectedRosterValidationSpec
    probability_models: tuple[ProbabilityModelSpec, ...]
    primary_probability_model: str
    strategies: StrategyFamilySpec
    splits: ExperimentSplitSpec
    tuning_protocol: TuningProtocolSpec
    release_gate: ReleaseGateSpec

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: str) -> str:
        parsed = as_utc(value)
        if parsed is None:
            raise ResearchContractError("research manifest requires an explicit UTC as_of")
        canonical = parsed.isoformat().replace("+00:00", "Z")
        if value != canonical:
            raise ResearchContractError("research manifest as_of must be canonical UTC with Z")
        return value

    @model_validator(mode="after")
    def validate_models(self) -> MainRollResearchManifest:
        self.tuning_protocol.validate_against(self.splits.tuning)
        if self.source.eligibility_mode != "projected":
            raise ResearchContractError("this manifest version is reserved for projected-derived validation")
        model_ids = tuple(model.model_id for model in self.probability_models)
        if len(model_ids) != len(set(model_ids)):
            raise ResearchContractError("probability model IDs must be unique")
        if self.primary_probability_model != PRIMARY_MODEL_ID:
            raise ResearchContractError("the frozen primary probability model ID changed")
        if self.primary_probability_model not in model_ids:
            raise ResearchContractError("primary probability model is not declared")
        required = {
            PRIMARY_MODEL_ID,
            "flattened-weights-v1",
            "sharpened-weights-v1",
            "repeat-suppressed-v1",
            "correlated-multi-target-v1",
        }
        if not required.issubset(model_ids):
            raise ResearchContractError("the required probability sensitivity family is incomplete")
        if (
            self.strategies.target.evaluation_mode == "exact-distance-potential"
            and self.strategies.hybrid.switch_mode != "fixed"
        ):
            raise ResearchContractError(
                "exact-distance Target requires the preregistered fixed-horizon Hybrid"
            )
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))

    def probability_model(self, model_id: str) -> ProbabilityModelSpec:
        for model in self.probability_models:
            if model.model_id == model_id:
                return model
        raise ResearchContractError(f"unknown research probability model: {model_id}")


def load_main_roll_research_manifest(path: Path) -> MainRollResearchManifest:
    return MainRollResearchManifest.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "MainRollResearchManifest",
    "ProbabilityModelSpec",
    "ResearchContractError",
    "load_main_roll_research_manifest",
]
