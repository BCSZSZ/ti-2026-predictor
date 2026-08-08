from __future__ import annotations

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
        return self
