"""Read-only P6 audit between frozen playbooks and the bounded reference solver."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ti_predictor.fantasy.playbook import PlaybookPolicy
from ti_predictor.fantasy.roll import (
    GroupRollState,
    RefreshRollAction,
    RollAction,
    RollOffer,
)
from ti_predictor.fantasy.scenarios import CommonScenarioSet, ScenarioDraws
from ti_predictor.fantasy.solver import (
    BranchCappedRollSolver,
    WeightedOutcomeDistribution,
    exact_fixed_offer_oracle,
)
from ti_predictor.fantasy.valuation import RiskConfiguration
from ti_predictor.hashing import sha256_json


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class HeldOutScenarioPolicy(StrictModel):
    count: int = Field(gt=0)
    sampling: Literal["fixed_without_replacement_from_source_indexes"]
    exclude_p4_validation_indexes: Literal[True]
    exclude_p5_validation_indexes: Literal[True]


class ConditionalStatePolicy(StrictModel):
    coverage_case_count: Literal[9]
    remaining_rolls: tuple[Literal[1, 2, 3], ...]
    current_offer: Literal["frozen_offer_of_each_p4_coverage_case"]
    replacement_offer_schedule: Literal["subsequent_p4_coverage_offers_cyclic"]
    future_offer_randomness_integrated: Literal[False]

    @model_validator(mode="after")
    def validate_horizons(self) -> ConditionalStatePolicy:
        if self.remaining_rolls != (1, 2, 3):
            raise ValueError("P6 conditional horizons must remain exactly 1, 2 and 3")
        return self


class EditionAuditPolicy(StrictModel):
    edition: Literal["rate-agnostic", "primary-model"]
    risk_preference: Literal["default-knee"]
    mean_retention_epsilon: Literal[0.01, 0.02]
    models: tuple[str, ...]


class ConfidencePolicy(StrictModel):
    level: Literal[0.95]
    method: Literal["independent_weighted_outcome_bootstrap"]
    replicates: int = Field(ge=1000)
    sample_size: int = Field(ge=64)
    compute_only_for_p4_common_activations: Literal[True]


class SignificancePolicy(StrictModel):
    common_session_frequency: Literal[0.1]
    baseline_material_loss: Literal[0.1]
    strict_material_loss: Literal[0.05]
    directionally_wrong: Literal["manual_action_strictly_dominated_by_refresh_in_both_mean_and_cvar10"]


class ReleasePolicy(StrictModel):
    allowed_labels: tuple[Literal["baseline-reliable", "strict-reliable", "draft", "inapplicable"], ...]
    solver_disagreement_alone_changes_manual: Literal[False]
    manual_revision_allowed: Literal[False]
    ui_is_release_gate: Literal[False]


class CrossAuditPolicy(StrictModel):
    schema_version: Literal[1]
    policy_id: Literal["fantasy-group-read-only-cross-audit-v1"]
    period: Literal["group"]
    as_of: str
    seed: int = Field(ge=0)
    source_playbook_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_playbook_validation_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_solver_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_solver_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_scenario_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    playbook_sha256: dict[str, str]
    held_out_scenarios: HeldOutScenarioPolicy
    conditional_states: ConditionalStatePolicy
    editions: tuple[EditionAuditPolicy, ...]
    published_rule_count: Literal[12]
    cvar_alpha: Literal[0.1]
    confidence: ConfidencePolicy
    significance: SignificancePolicy
    release: ReleasePolicy
    runtime_target_seconds: int = Field(gt=0)
    runtime_hard_ceiling_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_contract(self) -> CrossAuditPolicy:
        if self.runtime_target_seconds > self.runtime_hard_ceiling_seconds:
            raise ValueError("P6 runtime target cannot exceed its hard ceiling")
        if tuple(item.edition for item in self.editions) != ("rate-agnostic", "primary-model"):
            raise ValueError("P6 must keep the frozen Rate-agnostic then Primary-model order")
        rate, primary = self.editions
        if rate.mean_retention_epsilon != 0.01 or primary.mean_retention_epsilon != 0.02:
            raise ValueError("P6 edition epsilon knees drifted")
        if rate.models != (
            "client-weight-primary-v1",
            "flattened-weights-v1",
            "sharpened-weights-v1",
        ):
            raise ValueError("P6 Rate-agnostic model scope drifted")
        if primary.models != ("client-weight-primary-v1",):
            raise ValueError("P6 Primary-model release scope drifted")
        if set(self.playbook_sha256) != {"rate-agnostic", "primary-model"}:
            raise ValueError("P6 needs both frozen playbook hashes")
        if any(len(value) != 64 for value in self.playbook_sha256.values()):
            raise ValueError("P6 playbook hashes must be SHA-256 values")
        if self.release.allowed_labels != (
            "baseline-reliable",
            "strict-reliable",
            "draft",
            "inapplicable",
        ):
            raise ValueError("P6 release labels drifted")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))

    @property
    def expected_row_count(self) -> int:
        cells = self.conditional_states.coverage_case_count * len(self.conditional_states.remaining_rolls)
        return cells * sum(len(item.models) for item in self.editions)


class CrossAuditPolicyV2(CrossAuditPolicy):
    policy_id: Literal["fantasy-group-read-only-cross-audit-v2"]
    source_solver_evidence_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_solver_evidence_scope: Literal["historical-v1-effectiveness-only"]
    stop_new_computation_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_v2_contract(self) -> CrossAuditPolicyV2:
        if not (
            self.runtime_target_seconds
            < self.stop_new_computation_seconds
            < self.runtime_hard_ceiling_seconds
        ):
            raise ValueError("v2 target, stop-new-work point and hard ceiling are inconsistent")
        if self.source_solver_policy_sha256 == self.source_solver_evidence_policy_sha256:
            raise ValueError("v2 must distinguish its audit policy from historical P5 evidence")
        return self


@dataclass(frozen=True)
class HeldOutScenarioAudit:
    p4_indexes_sha256: str
    p5_indexes_sha256: str
    p6_indexes_sha256: str
    p4_p5_overlap_count: int
    p4_p6_overlap_count: int
    p5_p6_overlap_count: int
    source_count: int
    selected_count: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "p4_indexes_sha256": self.p4_indexes_sha256,
            "p5_indexes_sha256": self.p5_indexes_sha256,
            "p6_indexes_sha256": self.p6_indexes_sha256,
            "p4_p5_overlap_count": self.p4_p5_overlap_count,
            "p4_p6_overlap_count": self.p4_p6_overlap_count,
            "p5_p6_overlap_count": self.p5_p6_overlap_count,
            "source_count": self.source_count,
            "selected_count": self.selected_count,
        }


def load_cross_audit_policy(path: Path) -> CrossAuditPolicy:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    policy_type = CrossAuditPolicyV2 if "source_solver_evidence_scope" in payload else CrossAuditPolicy
    return policy_type.model_validate_json(text)


def _seed(base_seed: int, *parts: Any) -> int:
    payload = ":".join([str(base_seed), *(str(part) for part in parts)]).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little", signed=False)


def fixed_subset_indexes(*, source_count: int, count: int, seed: int, label: str) -> np.ndarray:
    """Reproduce a named fixed subset without treating a new seed as proof of disjointness."""

    if count <= 0 or count > source_count:
        raise ValueError("fixed subset count is outside the source Scenario set")
    rng = np.random.default_rng(_seed(seed, label))
    return np.sort(rng.choice(source_count, size=count, replace=False)).astype(np.int64)


def build_held_out_scenarios(
    source: CommonScenarioSet,
    policy: CrossAuditPolicy,
    *,
    p4_seed: int,
    p4_count: int,
    p5_seed: int,
    p5_count: int,
) -> tuple[CommonScenarioSet, HeldOutScenarioAudit]:
    """Create P6 indexes explicitly disjoint from both prior validation subsets."""

    source_count = len(source.scenario_ids)
    p4 = fixed_subset_indexes(
        source_count=source_count,
        count=p4_count,
        seed=p4_seed,
        label="scenario-subset",
    )
    p5 = fixed_subset_indexes(
        source_count=source_count,
        count=p5_count,
        seed=p5_seed,
        label="p5-scenario-subset",
    )
    excluded = np.union1d(p4, p5)
    available = np.setdiff1d(np.arange(source_count, dtype=np.int64), excluded)
    count = policy.held_out_scenarios.count
    if count > len(available):
        raise ValueError("P6 cannot draw its declared disjoint Scenario count")
    rng = np.random.default_rng(_seed(policy.seed, "p6-held-out-scenario-subset"))
    selected = np.sort(rng.choice(available, size=count, replace=False)).astype(np.int64)
    draws = tuple(
        ScenarioDraws(
            target_team_id=item.target_team_id,
            role=item.role,
            pool_sha256=item.pool_sha256,
            block_indexes=item.block_indexes[selected],
        )
        for item in source.draws
    )
    scenario_set = CommonScenarioSet(
        policy_id=f"{source.policy_id}:p6-held-out-{count}",
        data_snapshot_sha256=source.data_snapshot_sha256,
        as_of=source.as_of,
        seed=policy.seed,
        team_ids=source.team_ids,
        scenario_ids=np.arange(count, dtype=np.int64),
        group_categories=source.group_categories[selected],
        series_counts=source.series_counts[selected],
        draws=draws,
    )
    p4_set, p5_set, p6_set = set(p4.tolist()), set(p5.tolist()), set(selected.tolist())
    audit = HeldOutScenarioAudit(
        p4_indexes_sha256=sha256_json(p4.tolist()),
        p5_indexes_sha256=sha256_json(p5.tolist()),
        p6_indexes_sha256=sha256_json(selected.tolist()),
        p4_p5_overlap_count=len(p4_set & p5_set),
        p4_p6_overlap_count=len(p4_set & p6_set),
        p5_p6_overlap_count=len(p5_set & p6_set),
        source_count=source_count,
        selected_count=len(selected),
    )
    if audit.p4_p6_overlap_count or audit.p5_p6_overlap_count:
        raise AssertionError("P6 held-out Scenario indexes overlap a prior validation subset")
    return scenario_set, audit


def action_identity(action: RollAction) -> str:
    if isinstance(action, RefreshRollAction):
        return "refresh"
    return f"{action.banner_role}:{action.operation_id}"


def common_activation_frequencies(
    p4_evidence: Mapping[str, Any],
) -> dict[tuple[str, str, str, str], float]:
    """Index the P4-confirmed Common rows by exact release scope and rule activation."""

    result: dict[tuple[str, str, str, str], float] = {}
    rows = p4_evidence.get("common_situation_conditional_loss", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("P4 Common-situation evidence is malformed")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("P4 Common-situation row is malformed")
        key = (
            str(row["edition"]),
            str(row["model_id"]),
            str(row["case_id"]),
            str(row["situation"]),
        )
        result[key] = max(result.get(key, 0.0), float(row["session_frequency"]))
    return result


def _sample_weighted(
    distribution: WeightedOutcomeDistribution,
    *,
    rng: np.random.Generator,
    replicates: int,
    sample_size: int,
) -> np.ndarray:
    cumulative = np.cumsum(distribution.weights)
    cumulative[-1] = 1.0
    uniforms = rng.random((replicates, sample_size))
    indexes = np.searchsorted(cumulative, uniforms, side="right")
    return distribution.values[indexes]


def _sample_cvar(samples: np.ndarray, alpha: float) -> np.ndarray:
    ordered = np.sort(samples, axis=1)
    tail_mass = samples.shape[1] * alpha
    whole = int(np.floor(tail_mass))
    fraction = tail_mass - whole
    if whole == 0:
        return ordered[:, 0]
    total = ordered[:, :whole].sum(axis=1)
    if fraction > 1e-12:
        total += fraction * ordered[:, whole]
    return total / tail_mass


def independent_weighted_loss_bounds(
    reference: WeightedOutcomeDistribution,
    candidate: WeightedOutcomeDistribution,
    *,
    alpha: float,
    confidence: ConfidencePolicy,
    seed: int,
) -> dict[str, float]:
    """Return preregistered diagnostic upper bounds without claiming paired Series inference."""

    left = _sample_weighted(
        reference,
        rng=np.random.default_rng(_seed(seed, "reference")),
        replicates=confidence.replicates,
        sample_size=confidence.sample_size,
    )
    right = _sample_weighted(
        candidate,
        rng=np.random.default_rng(_seed(seed, "candidate")),
        replicates=confidence.replicates,
        sample_size=confidence.sample_size,
    )
    reference_mean = max(abs(reference.mean), 1e-12)
    reference_cvar = max(abs(reference.cvar(alpha)), 1e-12)
    mean_loss = np.maximum(0.0, left.mean(axis=1) - right.mean(axis=1)) / reference_mean
    cvar_loss = np.maximum(0.0, _sample_cvar(left, alpha) - _sample_cvar(right, alpha)) / reference_cvar
    return {
        "mean_loss_upper95_fraction": float(np.quantile(mean_loss, confidence.level)),
        "cvar10_loss_upper95_fraction": float(np.quantile(cvar_loss, confidence.level)),
    }


def audit_one_condition(
    *,
    policy: CrossAuditPolicy,
    manual: PlaybookPolicy,
    solver: BranchCappedRollSolver,
    state: GroupRollState,
    replacement_offers: Sequence[RollOffer],
    edition: EditionAuditPolicy,
    model_id: str,
    case_id: str,
    horizon: int,
    common_frequency: float | None,
) -> dict[str, Any]:
    """Compare one frozen manual action to solver and exact conditional action values."""

    risk = RiskConfiguration(edition.mean_retention_epsilon, policy.cvar_alpha)
    manual_decision = manual.decide(
        state,
        candidate_rule_count=policy.published_rule_count,
        risk_preference=edition.risk_preference,
    )
    solver_decision = solver.decide(
        state,
        model_id=model_id,
        epsilon=edition.mean_retention_epsilon,
    )
    oracle = exact_fixed_offer_oracle(
        state,
        replacement_offers,
        rules=manual.rules,
        terminal=solver.terminal,
        model_id=model_id,
        risk=risk,
    )
    if oracle.selected_action is None:
        raise AssertionError("P6 oracle unexpectedly returned a terminal-only decision")
    values = {item.action: item for item in oracle.action_values}
    oracle_value = values[oracle.selected_action]
    manual_value = values[manual_decision.action]
    refresh_action = next(action for action in values if isinstance(action, RefreshRollAction))
    refresh_value = values[refresh_action]
    mean_loss = max(0.0, oracle_value.mean - manual_value.mean) / max(abs(oracle_value.mean), 1e-12)
    cvar_loss = max(0.0, oracle_value.cvar - manual_value.cvar) / max(abs(oracle_value.cvar), 1e-12)
    situation = manual_decision.rule_id or "fallback"
    is_common = (
        common_frequency is not None and common_frequency >= policy.significance.common_session_frequency
    )
    bounds: dict[str, float | None] = {
        "mean_loss_upper95_fraction": None,
        "cvar10_loss_upper95_fraction": None,
    }
    if is_common:
        bounds.update(
            independent_weighted_loss_bounds(
                oracle_value.distribution,
                manual_value.distribution,
                alpha=policy.cvar_alpha,
                confidence=policy.confidence,
                seed=_seed(policy.seed, edition.edition, model_id, case_id, horizon, situation),
            )
        )
    directionally_wrong = bool(
        is_common
        and manual_value.mean < refresh_value.mean - 1e-9
        and manual_value.cvar < refresh_value.cvar - 1e-9
    )
    upper_values = [value for value in bounds.values() if value is not None]
    baseline_exception = bool(
        is_common and upper_values and max(upper_values) > policy.significance.baseline_material_loss
    )
    strict_exception = bool(
        is_common and upper_values and max(upper_values) > policy.significance.strict_material_loss
    )
    return {
        "edition": edition.edition,
        "model_id": model_id,
        "epsilon": edition.mean_retention_epsilon,
        "case_id": case_id,
        "horizon": horizon,
        "manual_situation": situation,
        "manual_action": action_identity(manual_decision.action),
        "manual_explanation": manual_decision.explanation,
        "solver_preferred_action": action_identity(solver_decision.preferred_action),
        "solver_executed_action": action_identity(solver_decision.executed_action),
        "solver_resolved": solver_decision.resolved,
        "solver_resolution_reason": solver_decision.resolution_reason,
        "oracle_action": action_identity(oracle.selected_action),
        "manual_solver_disagreement": manual_decision.action != solver_decision.preferred_action,
        "manual_oracle_disagreement": manual_decision.action != oracle.selected_action,
        "manual_mean": manual_value.mean,
        "manual_cvar10": manual_value.cvar,
        "oracle_mean": oracle_value.mean,
        "oracle_cvar10": oracle_value.cvar,
        "refresh_mean": refresh_value.mean,
        "refresh_cvar10": refresh_value.cvar,
        "mean_loss_fraction": mean_loss,
        "cvar10_loss_fraction": cvar_loss,
        **bounds,
        "p4_session_frequency": common_frequency,
        "p4_common_activation": is_common,
        "directionally_wrong": directionally_wrong,
        "baseline_material_exception": baseline_exception or directionally_wrong,
        "strict_material_exception": strict_exception or directionally_wrong,
        "conditional_offer_schedule": [list(offer.operation_ids) for offer in replacement_offers],
    }


def release_labels(
    p4_gate: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    complete: bool,
) -> dict[str, dict[str, Any]]:
    """P6 can preserve or downgrade a P4 label, never promote a frozen draft."""

    labels: dict[str, dict[str, Any]] = {}
    for edition in ("rate-agnostic", "primary-model"):
        source = p4_gate.get(edition)
        if not isinstance(source, Mapping):
            raise ValueError(f"P4 gate is missing edition: {edition}")
        p4_status = str(source.get("p4_status"))
        if p4_status not in {"baseline-reliable", "strict-reliable", "draft", "inapplicable"}:
            raise ValueError(f"P4 recorded an invalid release status for {edition}")
        exceptions = [
            row
            for row in rows
            if row.get("edition") == edition and row.get("baseline_material_exception") is True
        ]
        if p4_status in {"draft", "inapplicable"}:
            final = p4_status
        elif not complete or exceptions:
            final = "draft"
        else:
            final = p4_status
        labels[edition] = {
            "p4_status": p4_status,
            "p6_status": final,
            "baseline_material_exception_count": len(exceptions),
            "promotion_permitted": False,
        }
    return labels
