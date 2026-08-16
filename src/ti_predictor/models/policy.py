from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class _PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PatchWeights(_PolicyModel):
    target: float = Field(ge=0.0, le=1.0)
    immediate_prior: float = Field(ge=0.0, le=1.0)
    earlier: float = Field(ge=0.0, le=1.0)


class CurrentExactPatchWeight(_PolicyModel):
    patch_name: str = Field(pattern=r"^\d+\.\d+[a-z]+$")
    active_from: AwareDatetime
    multiplier: float = Field(gt=0.0, le=10.0)


class CurrentEventStageScope(_PolicyModel):
    event_id: str = Field(min_length=1)
    target_period: Literal["main"]
    league_id: int = Field(gt=0)
    stage_id: str = Field(min_length=1)
    completed_at: AwareDatetime
    snapshot_available_at: AwareDatetime
    match_ids: tuple[int, ...] = Field(min_length=1)
    match_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str = Field(min_length=1)
    provenance: Literal["exact", "derived"]

    @model_validator(mode="after")
    def validate_frozen_game_scope(self) -> CurrentEventStageScope:
        if len(self.match_ids) != len(set(self.match_ids)):
            raise ValueError("current-event stage match_ids must be unique")
        if any(match_id <= 0 for match_id in self.match_ids):
            raise ValueError("current-event stage match_ids must contain only positive stable IDs")
        if self.snapshot_available_at < self.completed_at:
            raise ValueError("current-event stage snapshot cannot predate stage completion")
        payload = ",".join(str(match_id) for match_id in sorted(self.match_ids))
        actual_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if actual_hash != self.match_ids_sha256:
            raise ValueError("current-event stage match_ids_sha256 does not match match_ids")
        return self


class EloPolicy(_PolicyModel):
    initial_rating: float
    k_factor: float = Field(gt=0.0)
    scale: float = Field(gt=0.0)


class GlickoPolicy(_PolicyModel):
    initial_rating: float
    initial_deviation: float = Field(gt=0.0)
    deviation_increase_per_30_days: float = Field(ge=0.0)


class EnsemblePolicy(_PolicyModel):
    elo_weight: float = Field(ge=0.0, le=1.0)
    glicko_weight: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> EnsemblePolicy:
        if abs(self.elo_weight + self.glicko_weight - 1.0) > 1e-12:
            raise ValueError("ensemble weights must sum to 1")
        return self


class CalibrationPolicy(_PolicyModel):
    rolling_initial_fraction: float = Field(gt=0.0, lt=1.0)
    rolling_folds: int = Field(ge=2)
    minimum_games_per_window: int = Field(ge=2)
    probability_floor: float = Field(gt=0.0, lt=0.5)
    probability_ceiling: float = Field(gt=0.5, lt=1.0)

    @model_validator(mode="after")
    def rolling_windows_fit(self) -> CalibrationPolicy:
        remaining = 1.0 - self.rolling_initial_fraction
        if remaining / self.rolling_folds <= 0.0:
            raise ValueError("rolling validation windows must have positive width")
        if self.probability_floor >= self.probability_ceiling:
            raise ValueError("calibration probability bounds are reversed")
        return self


class EvidenceScopePolicy(_PolicyModel):
    mode: Literal["global", "target_connected_component"] = "global"


class HoldoutPolicy(_PolicyModel):
    league_id: int = Field(gt=0)
    target_patch_family: str = Field(pattern=r"^\d+\.\d+$")
    target_team_ids: tuple[int, ...] = ()
    expected_games: int = Field(gt=0)
    minimum_same_patch_games_per_team: int = Field(gt=0)

    @model_validator(mode="after")
    def target_team_ids_are_stable_and_unique(self) -> HoldoutPolicy:
        if any(team_id <= 0 for team_id in self.target_team_ids):
            raise ValueError("target_team_ids must contain only positive stable IDs")
        if len(self.target_team_ids) != len(set(self.target_team_ids)):
            raise ValueError("target_team_ids must not contain duplicates")
        return self


class TeamStrengthPolicy(_PolicyModel):
    schema_version: int = Field(ge=1)
    policy_id: str = Field(min_length=1)
    decision_record: str = Field(min_length=1)
    evidence_scope: EvidenceScopePolicy = Field(default_factory=EvidenceScopePolicy)
    patch_weights: PatchWeights
    current_exact_patch_weight: CurrentExactPatchWeight | None = None
    current_event_stage_scope: CurrentEventStageScope | None = None
    team_strength_current_event_stage_multiplier: float = Field(default=1.0, gt=0.0, le=10.0)
    fantasy_current_event_stage_multiplier: float = Field(default=1.0, gt=0.0, le=10.0)
    tier_weights: dict[str, float]
    time_half_life_days: float = Field(gt=0.0)
    elo: EloPolicy
    glicko: GlickoPolicy
    ensemble: EnsemblePolicy
    calibration: CalibrationPolicy
    ti2025_holdout: HoldoutPolicy

    @model_validator(mode="after")
    def validate_locked_weights(self) -> TeamStrengthPolicy:
        if set(self.tier_weights) != {"premium", "professional"}:
            raise ValueError("tier_weights must define only premium and professional")
        if any(value < 0.0 or value > 1.0 for value in self.tier_weights.values()):
            raise ValueError("tier weights must be between 0 and 1")
        if (
            self.evidence_scope.mode == "target_connected_component"
            and not self.ti2025_holdout.target_team_ids
        ):
            raise ValueError("target-connected policies must declare TI 2025 target_team_ids")
        if self.current_event_stage_scope is None and (
            self.team_strength_current_event_stage_multiplier != 1.0
            or self.fantasy_current_event_stage_multiplier != 1.0
        ):
            raise ValueError("current-event stage multipliers require a frozen stage scope")
        return self


class SwissScenarioPolicy(_PolicyModel):
    scenario_id: str = Field(min_length=1)
    roster_strength_multiplier: float = Field(gt=0.0, le=2.0)
    elimination_choice_strategy: Literal["model_optimal", "adversarial", "seeded_random"]


class SwissRosterShockPolicy(_PolicyModel):
    target_team_id: int = Field(gt=0)
    effective_from: AwareDatetime
    transform: Literal["positive_strength_odds"]
    provenance: Literal["derived"]
    source: str = Field(min_length=1)


class SwissBo3SelectionPolicy(_PolicyModel):
    minimum_holdout_series: int = Field(gt=0)
    selection_rule: Literal["independent_games_only_if_lower_log_loss_and_brier"]
    fallback_mode: Literal["direct_series"]


class SwissDurationProxyPolicy(_PolicyModel):
    distribution: Literal["clipped_normal"]
    mean_seconds: float = Field(gt=0.0)
    standard_deviation_seconds: float = Field(gt=0.0)
    minimum_seconds: int = Field(gt=0)
    maximum_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> SwissDurationProxyPolicy:
        if self.maximum_seconds <= self.minimum_seconds:
            raise ValueError("duration proxy maximum must exceed minimum")
        return self


class SwissSimulationPolicy(_PolicyModel):
    schema_version: Literal[1]
    policy_id: str = Field(min_length=1)
    as_of: AwareDatetime
    primary_scenario: str = Field(min_length=1)
    pairing_tie_break: Literal["seeded_random"]
    bo3_selection: SwissBo3SelectionPolicy
    roster_shock: SwissRosterShockPolicy
    duration_proxy: SwissDurationProxyPolicy
    scenarios: tuple[SwissScenarioPolicy, ...]

    @model_validator(mode="after")
    def validate_scenarios(self) -> SwissSimulationPolicy:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Swiss scenario IDs must be unique")
        if self.primary_scenario not in scenario_ids:
            raise ValueError("primary Swiss scenario is not declared")
        if not any(scenario.roster_strength_multiplier == 1.0 for scenario in self.scenarios):
            raise ValueError("Swiss scenarios require an unadjusted baseline")
        return self
