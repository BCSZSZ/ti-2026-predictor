"""Deterministic synthetic starting-state coverage for isolated Main Roll research.

The generator samples only client-legal support.  Its equal coverage weights are an
experimental design and are not a claim about the population distribution of screens.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ti_predictor.fantasy.main_roll import MainRollState, validate_main_state
from ti_predictor.fantasy.main_roll_research_contract import (
    MainRollResearchManifest,
    load_main_roll_research_manifest,
)
from ti_predictor.fantasy.main_roll_research_simulator import state_payload, state_sha256
from ti_predictor.fantasy.roll import (
    INCREASE_ONE_QUALITY,
    INCREASE_TWO_DECREASE_ONE,
    BannerState,
    EmblemState,
    RollOffer,
    RollRuleSet,
)
from ti_predictor.hashing import sha256_file, sha256_json

SHA256_PATTERN = r"^[0-9a-f]{64}$"
PRIMARY_MODEL_ID = "client-weight-primary-v1"
REQUIRED_MODEL_IDS = (
    PRIMARY_MODEL_ID,
    "flattened-weights-v1",
    "sharpened-weights-v1",
    "repeat-suppressed-v1",
    "correlated-multi-target-v1",
)


class StartingStateCoverageError(ValueError):
    """A starting-state coverage manifest or generated state is invalid."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BaseResearchManifestReference(_StrictModel):
    relative_path: str = Field(min_length=1)
    file_sha256: str = Field(pattern=SHA256_PATTERN)
    semantic_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise StartingStateCoverageError("base research manifest path must stay repository-relative")
        return value


class StartingStateGeneratorSpec(_StrictModel):
    generator_id: Literal["main-uniform-legal-start-v1"]
    master_seed: int = Field(ge=0)
    distribution_kind: Literal["non-probability-weighted-uniform-legal-coverage"]
    key_derivation: Literal["sha256-counter-rejection-v1"]
    remaining_rolls: Literal[30]
    stat_sampling: Literal["uniform-over-client-legal-stats-per-slot-color"]
    quality_sampling: Literal["uniform-over-client-legal-tiers"]
    trait_sampling: Literal["uniform-over-client-legal-traits"]
    offer_sampling: Literal["ordered-uniform-without-replacement-over-positive-weight-operations"]


class CoverageIndexRange(_StrictModel):
    start: int = Field(ge=0)
    count: int = Field(ge=1, le=100_000)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(range(self.start, self.start + self.count))


class StartingStateCoverageSplits(_StrictModel):
    development: CoverageIndexRange
    confirmation: CoverageIndexRange
    development_use: Literal["pipeline-only-no-policy-tuning"]

    @model_validator(mode="after")
    def validate_disjoint_contiguous(self) -> StartingStateCoverageSplits:
        development = set(self.development.values)
        confirmation = set(self.confirmation.values)
        if development & confirmation:
            raise StartingStateCoverageError("development and confirmation states must be disjoint")
        combined = sorted(development | confirmation)
        if combined != list(range(len(combined))):
            raise StartingStateCoverageError("coverage state indices must form one zero-based range")
        return self


class SensitivityPanelSpec(_StrictModel):
    selection: Literal["lowest-sha256-rank-before-outcomes"]
    selection_salt: str = Field(min_length=1)
    confirmation_state_count: int = Field(ge=2, le=100_000)
    probability_model_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_models(self) -> SensitivityPanelSpec:
        if self.probability_model_ids != REQUIRED_MODEL_IDS:
            raise StartingStateCoverageError(
                "coverage sensitivity panel must retain the frozen five-model order"
            )
        return self


class StartingStateCoverageGateSpec(_StrictModel):
    confidence_level: float = Field(gt=0.5, lt=1.0)
    minimum_relative_mean_gain: float = Field(ge=0.0, lt=1.0)
    cvar_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)
    stratum_noninferiority_fraction: float = Field(ge=0.0, lt=1.0)
    minimum_stratum_count: int = Field(ge=2)
    require_primary_mean_ci_above_zero: Literal[True]
    require_nonnegative_mean_all_probability_models: Literal[True]
    require_every_eligible_stratum_noninferior: Literal[True]
    require_every_roster_fold_noninferior: Literal[True]
    direct_t_vs_h_minimum_relative_gain: float = Field(ge=0.0, lt=1.0)
    complexity_preference: Literal["target-unless-hybrid-materially-better"]
    automatic_web_promotion: Literal[False]


class MainStartingStateCoverageManifest(_StrictModel):
    schema_version: Literal[1]
    experiment_id: str = Field(min_length=1)
    period: Literal["main"]
    as_of: str
    research_only: Literal[True]
    web_integration: Literal[False]
    runtime_pointer_writes: Literal[False]
    dota_client_control: Literal[False]
    interpretation: Literal["synthetic-legal-coverage-not-player-population-expectation"]
    base_research_manifest: BaseResearchManifestReference
    generator: StartingStateGeneratorSpec
    splits: StartingStateCoverageSplits
    primary_probability_model: Literal["client-weight-primary-v1"]
    paired_roll_tape: Literal["same-within-state-and-model-across-g-t-h"]
    sensitivity_panel: SensitivityPanelSpec
    coverage_dimensions: tuple[
        Literal[
            "average-quality-band",
            "direct-quality-increment-offer",
            "conditional-trait-ready-banner-band",
            "initial-terminal-value-rank-quartile",
        ],
        ...,
    ]
    coverage_gate: StartingStateCoverageGateSpec

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: str) -> str:
        if not value.endswith("Z"):
            raise StartingStateCoverageError("coverage as_of must be canonical UTC with Z")
        return value

    @model_validator(mode="after")
    def validate_design(self) -> MainStartingStateCoverageManifest:
        total = self.splits.development.count + self.splits.confirmation.count
        if total != 1_000:
            raise StartingStateCoverageError("the frozen coverage design requires exactly 1,000 states")
        if self.splits.development.count != 100 or self.splits.confirmation.count != 900:
            raise StartingStateCoverageError(
                "the frozen coverage split must be 100 development / 900 confirmation"
            )
        if self.sensitivity_panel.confirmation_state_count != 100:
            raise StartingStateCoverageError("the frozen sensitivity panel requires 100 states")
        if self.sensitivity_panel.confirmation_state_count > self.splits.confirmation.count:
            raise StartingStateCoverageError("sensitivity panel exceeds confirmation state count")
        expected_dimensions = {
            "average-quality-band",
            "direct-quality-increment-offer",
            "conditional-trait-ready-banner-band",
            "initial-terminal-value-rank-quartile",
        }
        if set(self.coverage_dimensions) != expected_dimensions or len(self.coverage_dimensions) != 4:
            raise StartingStateCoverageError("the frozen coverage dimensions are incomplete")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))

    @property
    def state_indices(self) -> tuple[int, ...]:
        return self.splits.development.values + self.splits.confirmation.values

    def split_for(self, state_index: int) -> Literal["development", "confirmation"]:
        if state_index in range(
            self.splits.development.start,
            self.splits.development.start + self.splits.development.count,
        ):
            return "development"
        if state_index in range(
            self.splits.confirmation.start,
            self.splits.confirmation.start + self.splits.confirmation.count,
        ):
            return "confirmation"
        raise StartingStateCoverageError(f"state index {state_index} is outside the frozen split")


def load_starting_state_coverage_manifest(path: Path) -> MainStartingStateCoverageManifest:
    return MainStartingStateCoverageManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_base_research_manifest(
    coverage: MainStartingStateCoverageManifest,
    *,
    repository_root: Path,
) -> tuple[Path, MainRollResearchManifest]:
    path = (repository_root / coverage.base_research_manifest.relative_path).resolve()
    if not path.is_relative_to(repository_root.resolve()):
        raise StartingStateCoverageError("base research manifest escaped the repository")
    if sha256_file(path) != coverage.base_research_manifest.file_sha256:
        raise StartingStateCoverageError("base research manifest file SHA-256 differs")
    manifest = load_main_roll_research_manifest(path)
    if manifest.semantic_hash != coverage.base_research_manifest.semantic_sha256:
        raise StartingStateCoverageError("base research manifest semantic SHA-256 differs")
    if manifest.as_of != coverage.as_of:
        raise StartingStateCoverageError("coverage and base research cutoffs differ")
    if coverage.primary_probability_model != manifest.primary_probability_model:
        raise StartingStateCoverageError("coverage and base primary probability models differ")
    base_models = tuple(model.model_id for model in manifest.probability_models)
    if base_models != coverage.sensitivity_panel.probability_model_ids:
        raise StartingStateCoverageError("coverage and base probability-model families differ")
    return path, manifest


def _key_digest(coverage: MainStartingStateCoverageManifest, *parts: object) -> bytes:
    key = ":".join(
        (
            coverage.generator.generator_id,
            str(coverage.generator.master_seed),
            *(str(part) for part in parts),
        )
    )
    return hashlib.sha256(key.encode("utf-8")).digest()


def _uniform_index(
    coverage: MainStartingStateCoverageManifest,
    size: int,
    *parts: object,
) -> int:
    if size < 1:
        raise StartingStateCoverageError("uniform keyed choice requires non-empty support")
    limit = (1 << 256) - ((1 << 256) % size)
    counter = 0
    while True:
        value = int.from_bytes(_key_digest(coverage, *parts, counter), "big")
        if value < limit:
            return value % size
        counter += 1


def _choice(
    coverage: MainStartingStateCoverageManifest,
    values: Sequence[Any],
    *parts: object,
) -> Any:
    return values[_uniform_index(coverage, len(values), *parts)]


def generator_key_sha256(
    coverage: MainStartingStateCoverageManifest,
    state_index: int,
) -> str:
    return _key_digest(coverage, "state", state_index).hex()


def generate_starting_state(
    coverage: MainStartingStateCoverageManifest,
    rules: RollRuleSet,
    state_index: int,
) -> MainRollState:
    coverage.split_for(state_index)
    qualities = tuple(tier for tier, _ in rules.quality_weights)
    banners: list[BannerState] = []
    for role in rules.roles:
        emblems: list[EmblemState] = []
        colors = rules.colors_for(role)[:5]
        for slot_index, color in enumerate(colors):
            emblems.append(
                EmblemState(
                    stat_id=_choice(
                        coverage,
                        rules.stats_for(color),
                        "state",
                        state_index,
                        "stat",
                        role,
                        slot_index,
                    ),
                    quality_tier=_choice(
                        coverage,
                        qualities,
                        "state",
                        state_index,
                        "quality",
                        role,
                        slot_index,
                    ),
                    trait_id=_choice(
                        coverage,
                        rules.traits,
                        "state",
                        state_index,
                        "trait",
                        role,
                        slot_index,
                    ),
                )
            )
        banners.append(BannerState(role=role, emblems=tuple(emblems)))

    remaining = list(operation.operation_id for operation in rules.offered_operations)
    offer: list[int] = []
    for offer_index in range(rules.offer_size):
        selected = _choice(
            coverage,
            remaining,
            "state",
            state_index,
            "offer",
            offer_index,
        )
        offer.append(int(selected))
        remaining.remove(selected)
    state = MainRollState(
        banners=tuple(banners),
        offer=RollOffer(tuple(offer)),
        remaining_rolls=coverage.generator.remaining_rolls,
    )
    validate_main_state(state, rules)
    return state


def _conditional_trait_ready(banner: BannerState) -> bool:
    traits = tuple(emblem.trait_id for emblem in banner.emblems)
    qualities = tuple(emblem.quality_tier for emblem in banner.emblems)
    return (
        ("fractal" in traits and len(set(qualities)) == len(qualities))
        or traits.count("unique") == 1
        or traits.count("friendly") >= 3
    )


def starting_state_strata(state: MainRollState, rules: RollRuleSet) -> dict[str, str]:
    qualities = [emblem.quality_tier for banner in state.banners for emblem in banner.emblems]
    average_quality = sum(qualities) / len(qualities)
    if average_quality <= 2.75:
        quality_band = "low-le-2.75"
    elif average_quality <= 3.25:
        quality_band = "central-2.75-to-3.25"
    else:
        quality_band = "high-gt-3.25"
    mutations = {rules.operation(operation_id).mutation for operation_id in state.offer.operation_ids}
    increment_offer = bool(mutations & {INCREASE_ONE_QUALITY, INCREASE_TWO_DECREASE_ONE})
    ready_banner_count = sum(_conditional_trait_ready(banner) for banner in state.banners)
    ready_band = "none" if ready_banner_count == 0 else "one" if ready_banner_count == 1 else "two-or-three"
    return {
        "average-quality-band": quality_band,
        "direct-quality-increment-offer": "available" if increment_offer else "absent",
        "conditional-trait-ready-banner-band": ready_band,
    }


def episode_seed(
    coverage: MainStartingStateCoverageManifest,
    state_index: int,
    probability_model_id: str,
    *,
    namespace_sha256: str | None = None,
) -> int:
    if probability_model_id not in coverage.sensitivity_panel.probability_model_ids:
        raise StartingStateCoverageError(f"unknown coverage probability model: {probability_model_id}")
    namespace = namespace_sha256 or coverage.semantic_hash
    digest = hashlib.sha256(f"{namespace}:episode:{state_index}:{probability_model_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def sensitivity_state_indices(
    coverage: MainStartingStateCoverageManifest,
) -> tuple[int, ...]:
    salt = coverage.sensitivity_panel.selection_salt
    ranked = sorted(
        coverage.splits.confirmation.values,
        key=lambda state_index: hashlib.sha256(
            f"{coverage.semantic_hash}:{salt}:{state_index}".encode()
        ).digest(),
    )
    return tuple(sorted(ranked[: coverage.sensitivity_panel.confirmation_state_count]))


def starting_state_record(
    coverage: MainStartingStateCoverageManifest,
    rules: RollRuleSet,
    state_index: int,
    *,
    sensitivity_indices: set[int] | None = None,
) -> dict[str, Any]:
    state = generate_starting_state(coverage, rules, state_index)
    selected = sensitivity_indices or set(sensitivity_state_indices(coverage))
    return {
        "state_index": state_index,
        "split": coverage.split_for(state_index),
        "generator_key_sha256": generator_key_sha256(coverage, state_index),
        "state_sha256": state_sha256(state),
        "sensitivity_selected": state_index in selected,
        "strata": starting_state_strata(state, rules),
        "state": state_payload(state),
    }


def build_starting_state_records(
    coverage: MainStartingStateCoverageManifest,
    rules: RollRuleSet,
) -> tuple[dict[str, Any], ...]:
    sensitivity = set(sensitivity_state_indices(coverage))
    records = tuple(
        starting_state_record(
            coverage,
            rules,
            state_index,
            sensitivity_indices=sensitivity,
        )
        for state_index in coverage.state_indices
    )
    hashes = [str(record["state_sha256"]) for record in records]
    if len(hashes) != len(set(hashes)):
        raise StartingStateCoverageError("the frozen 1,000-state suite contains a collision")
    return records


def state_index_semantic_hash(records: Sequence[Mapping[str, Any]]) -> str:
    return sha256_json(list(records))


__all__ = [
    "MainStartingStateCoverageManifest",
    "StartingStateCoverageError",
    "build_starting_state_records",
    "episode_seed",
    "generate_starting_state",
    "generator_key_sha256",
    "load_base_research_manifest",
    "load_starting_state_coverage_manifest",
    "sensitivity_state_indices",
    "starting_state_record",
    "starting_state_strata",
    "state_index_semantic_hash",
]
