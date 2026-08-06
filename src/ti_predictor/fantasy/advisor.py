"""Local, manual-confirmation-first advisor primitives for Group Fantasy rolls.

The module deliberately separates immutable session/replay mechanics from the heavier
Scenario valuation context.  It never reads a Dota client or infers a realised outcome.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ti_predictor.fantasy.roll import (
    COLOR_TARGETS,
    INCREASE_ONE_QUALITY,
    INCREASE_TWO_DECREASE_ONE,
    ROLL_QUALITY,
    ROLL_STAT,
    ROLL_TRAIT,
    TARGET_ALL,
    TARGET_ALL_COLOR,
    TARGET_FIRST_COLOR,
    TARGET_LAST_COLOR,
    TARGET_ONE_COLOR,
    ApplyRollAction,
    BannerState,
    EmblemState,
    GroupRollState,
    RefreshRollAction,
    RollAction,
    RollActionError,
    RollOffer,
    RollRuleSet,
    apply_realized_transition,
    enumerate_mutation_outcomes,
    legal_actions,
    refresh_transition,
    validate_group_state,
)
from ti_predictor.hashing import sha256_json


class AdvisorPolicyError(ValueError):
    """The frozen P7 policy or one of its source identities is invalid."""


class AdvisorSessionError(ValueError):
    """A saved advisor session cannot be safely replayed."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvisorScenarioPolicy(StrictModel):
    sha256: str
    count: int = Field(ge=1)
    scope: str


class AdvisorInputPolicy(StrictModel):
    roles_in_order: tuple[Literal["core", "mid", "support"], ...]
    emblems_per_role: Literal[3]
    shared_offer_size: Literal[3]
    remaining_rolls_min: Literal[1]
    remaining_rolls_max: Literal[40]
    operation_selection: str
    observed_results_must_be_manually_confirmed: Literal[True]

    @model_validator(mode="after")
    def canonical_roles(self) -> AdvisorInputPolicy:
        if self.roles_in_order != ("core", "mid", "support"):
            raise ValueError("P7 requires the canonical Core/Mid/Support input order")
        return self


class AdvisorQuickAnalysisPolicy(StrictModel):
    rate_agnostic_action_interval: Literal[True]
    one_step_exact_mutation_and_group_performance: Literal[True]
    future_offer_value_included: Literal[False]
    future_roll_reachability_included: Literal[False]
    models: tuple[str, ...]
    mean_retention_epsilons: tuple[float, ...]
    cvar_alpha: float = Field(gt=0.0, le=1.0)
    show_model_sensitivity: Literal[True]
    show_current_best_team_matching: Literal[True]

    @model_validator(mode="after")
    def validate_frontier(self) -> AdvisorQuickAnalysisPolicy:
        if self.models != (
            "client-weight-primary-v1",
            "flattened-weights-v1",
            "sharpened-weights-v1",
        ):
            raise ValueError("P7 transition-model sensitivity set drifted")
        if self.mean_retention_epsilons != (0.0, 0.01, 0.02, 0.05):
            raise ValueError("P7 epsilon frontier drifted")
        return self


class AdvisorOptionalSolverPolicy(StrictModel):
    enabled_on_explicit_user_action_only: Literal[True]
    solver_policy_id: str
    display_effectiveness_status: Literal["failed-escalation-review-required"]
    display_unresolved_and_executed_fallback: Literal[True]
    claim_global_optimality: Literal[False]


class AdvisorSessionPolicy(StrictModel):
    locked_baseline_fields: tuple[str, ...]
    observed_state_replanning: Literal[True]
    in_session_rate_learning: Literal[False]
    saved_replay_schema_version: Literal[1]


class AdvisorBoundaryPolicy(StrictModel):
    listen_address: Literal["127.0.0.1"]
    dota_client_control: Literal[False]
    automatic_filling: Literal[False]
    unconfirmed_ocr_action: Literal[False]
    main_execution: Literal["fail_closed"]


class AdvisorPerformancePolicy(StrictModel):
    context_load: float = Field(gt=0.0)
    quick_analysis: float = Field(gt=0.0)
    cached_repeat: float = Field(gt=0.0)
    optional_solver: float = Field(gt=0.0)


class InteractiveAdvisorPolicy(StrictModel):
    schema_version: Literal[1]
    policy_id: str
    period: Literal["group"]
    as_of: str
    seed: int
    source_p3_evidence_sha256: str
    source_p4_evidence_sha256: str
    source_p5_evidence_sha256: str
    source_p6_evidence_sha256: str
    playbook_sha256: dict[str, str]
    scenario: AdvisorScenarioPolicy
    input: AdvisorInputPolicy
    quick_analysis: AdvisorQuickAnalysisPolicy
    optional_solver: AdvisorOptionalSolverPolicy
    session: AdvisorSessionPolicy
    boundaries: AdvisorBoundaryPolicy
    performance_targets_seconds: AdvisorPerformancePolicy
    functional_gate: tuple[str, ...]

    @model_validator(mode="after")
    def validate_locked_contract(self) -> InteractiveAdvisorPolicy:
        if set(self.playbook_sha256) != {"rate-agnostic", "primary-model"}:
            raise ValueError("P7 requires exactly two independent playbook editions")
        required_fields = {
            "as_of",
            "data_snapshot_sha256",
            "rule_snapshot_sha256",
            "scenario_sha256",
            "playbook_sha256",
            "transition_models",
            "seeds",
        }
        if set(self.session.locked_baseline_fields) != required_fields:
            raise ValueError("P7 locked baseline field set drifted")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


def load_advisor_policy(path: Path) -> InteractiveAdvisorPolicy:
    return InteractiveAdvisorPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def emblem_payload(emblem: EmblemState) -> dict[str, Any]:
    return {
        "stat_id": emblem.stat_id,
        "quality_tier": emblem.quality_tier,
        "trait_id": emblem.trait_id,
    }


def banner_payload(banner: BannerState) -> dict[str, Any]:
    return {
        "role": banner.role,
        "emblems": [emblem_payload(emblem) for emblem in banner.emblems],
    }


def state_payload(state: GroupRollState) -> dict[str, Any]:
    return {
        "period": state.period,
        "slot_count": state.slot_count,
        "remaining_rolls": state.remaining_rolls,
        "offer": list(state.offer.operation_ids),
        "banners": [banner_payload(banner) for banner in state.banners],
    }


def state_sha256(state: GroupRollState) -> str:
    return sha256_json(state_payload(state))


def _exact_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise AdvisorSessionError(
            f"{label} fields differ: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdvisorSessionError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AdvisorSessionError(f"{label} must be an array")
    return value


def emblem_from_payload(value: Any) -> EmblemState:
    payload = _mapping(value, "Emblem")
    _exact_keys(payload, {"stat_id", "quality_tier", "trait_id"}, "Emblem")
    quality = payload["quality_tier"]
    if not isinstance(quality, int) or isinstance(quality, bool):
        raise AdvisorSessionError("Emblem quality_tier must be an integer")
    return EmblemState(
        stat_id=str(payload["stat_id"]),
        quality_tier=quality,
        trait_id=str(payload["trait_id"]),
    )


def banner_from_payload(value: Any) -> BannerState:
    payload = _mapping(value, "Banner")
    _exact_keys(payload, {"role", "emblems"}, "Banner")
    return BannerState(
        role=str(payload["role"]),
        emblems=tuple(emblem_from_payload(item) for item in _sequence(payload["emblems"], "emblems")),
    )


def state_from_payload(value: Any) -> GroupRollState:
    payload = _mapping(value, "Group state")
    _exact_keys(
        payload,
        {"period", "slot_count", "remaining_rolls", "offer", "banners"},
        "Group state",
    )
    slot_count = payload["slot_count"]
    remaining = payload["remaining_rolls"]
    if not isinstance(slot_count, int) or isinstance(slot_count, bool):
        raise AdvisorSessionError("slot_count must be an integer")
    if not isinstance(remaining, int) or isinstance(remaining, bool):
        raise AdvisorSessionError("remaining_rolls must be an integer")
    offer = _sequence(payload["offer"], "offer")
    if any(not isinstance(item, int) or isinstance(item, bool) for item in offer):
        raise AdvisorSessionError("offer operation IDs must be integers")
    return GroupRollState(
        banners=tuple(banner_from_payload(item) for item in _sequence(payload["banners"], "banners")),
        offer=RollOffer(tuple(offer)),
        remaining_rolls=remaining,
        period=str(payload["period"]),
        slot_count=slot_count,
    )


@dataclass(frozen=True)
class AdvisorBaseline:
    as_of: str
    data_snapshot_sha256: str
    rule_snapshot_sha256: str
    scenario_sha256: str
    playbook_sha256: tuple[tuple[str, str], ...]
    transition_models: tuple[str, ...]
    seeds: tuple[tuple[str, int], ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "data_snapshot_sha256": self.data_snapshot_sha256,
            "rule_snapshot_sha256": self.rule_snapshot_sha256,
            "scenario_sha256": self.scenario_sha256,
            "playbook_sha256": dict(self.playbook_sha256),
            "transition_models": list(self.transition_models),
            "seeds": dict(self.seeds),
        }

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.as_payload())

    @classmethod
    def from_payload(cls, value: Any) -> AdvisorBaseline:
        payload = _mapping(value, "baseline")
        expected = {
            "as_of",
            "data_snapshot_sha256",
            "rule_snapshot_sha256",
            "scenario_sha256",
            "playbook_sha256",
            "transition_models",
            "seeds",
        }
        _exact_keys(payload, expected, "baseline")
        playbooks = _mapping(payload["playbook_sha256"], "baseline.playbook_sha256")
        seeds = _mapping(payload["seeds"], "baseline.seeds")
        if any(not isinstance(item, int) or isinstance(item, bool) for item in seeds.values()):
            raise AdvisorSessionError("baseline seeds must be integers")
        models = _sequence(payload["transition_models"], "baseline.transition_models")
        return cls(
            as_of=str(payload["as_of"]),
            data_snapshot_sha256=str(payload["data_snapshot_sha256"]),
            rule_snapshot_sha256=str(payload["rule_snapshot_sha256"]),
            scenario_sha256=str(payload["scenario_sha256"]),
            playbook_sha256=tuple(sorted((str(key), str(item)) for key, item in playbooks.items())),
            transition_models=tuple(str(item) for item in models),
            seeds=tuple(sorted((str(key), int(item)) for key, item in seeds.items())),
        )


@dataclass(frozen=True)
class AdvisorEvent:
    event_type: Literal["apply", "refresh"]
    banner_role: str | None
    operation_id: int | None
    realized_banner: BannerState | None
    replacement_offer: RollOffer
    before_state_sha256: str
    after_state_sha256: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "banner_role": self.banner_role,
            "operation_id": self.operation_id,
            "realized_banner": (
                None if self.realized_banner is None else banner_payload(self.realized_banner)
            ),
            "replacement_offer": list(self.replacement_offer.operation_ids),
            "before_state_sha256": self.before_state_sha256,
            "after_state_sha256": self.after_state_sha256,
        }

    @classmethod
    def from_payload(cls, value: Any) -> AdvisorEvent:
        payload = _mapping(value, "event")
        expected = {
            "event_type",
            "banner_role",
            "operation_id",
            "realized_banner",
            "replacement_offer",
            "before_state_sha256",
            "after_state_sha256",
        }
        _exact_keys(payload, expected, "event")
        event_type = payload["event_type"]
        if event_type not in {"apply", "refresh"}:
            raise AdvisorSessionError("event_type must be apply or refresh")
        operation_id = payload["operation_id"]
        if operation_id is not None and (
            not isinstance(operation_id, int) or isinstance(operation_id, bool)
        ):
            raise AdvisorSessionError("event operation_id must be an integer or null")
        offer = _sequence(payload["replacement_offer"], "event.replacement_offer")
        if any(not isinstance(item, int) or isinstance(item, bool) for item in offer):
            raise AdvisorSessionError("replacement offer IDs must be integers")
        realized = payload["realized_banner"]
        return cls(
            event_type=event_type,
            banner_role=None if payload["banner_role"] is None else str(payload["banner_role"]),
            operation_id=operation_id,
            realized_banner=None if realized is None else banner_from_payload(realized),
            replacement_offer=RollOffer(tuple(offer)),
            before_state_sha256=str(payload["before_state_sha256"]),
            after_state_sha256=str(payload["after_state_sha256"]),
        )


def _apply_event(state: GroupRollState, event: AdvisorEvent, rules: RollRuleSet) -> GroupRollState:
    if state_sha256(state) != event.before_state_sha256:
        raise AdvisorSessionError("event before_state_sha256 does not match replay state")
    try:
        if event.event_type == "refresh":
            if (
                event.banner_role is not None
                or event.operation_id is not None
                or event.realized_banner is not None
            ):
                raise AdvisorSessionError("refresh event must not contain apply-only fields")
            next_state = refresh_transition(state, event.replacement_offer, rules)
        else:
            if event.banner_role is None or event.operation_id is None or event.realized_banner is None:
                raise AdvisorSessionError("apply event is missing its confirmed result")
            next_state = apply_realized_transition(
                state,
                ApplyRollAction(event.banner_role, event.operation_id),
                event.realized_banner,
                event.replacement_offer,
                rules,
            )
    except (RollActionError, ValueError) as error:
        raise AdvisorSessionError(f"event is not a legal observed transition: {error}") from error
    if state_sha256(next_state) != event.after_state_sha256:
        raise AdvisorSessionError("event after_state_sha256 does not match replay result")
    return next_state


@dataclass(frozen=True)
class AdvisorSession:
    baseline: AdvisorBaseline
    initial_state: GroupRollState
    events: tuple[AdvisorEvent, ...] = ()

    @classmethod
    def create(
        cls,
        baseline: AdvisorBaseline,
        initial_state: GroupRollState,
        rules: RollRuleSet,
    ) -> AdvisorSession:
        validate_group_state(initial_state, rules)
        if initial_state.remaining_rolls < 1:
            raise AdvisorSessionError("an interactive session requires at least one remaining Roll")
        return cls(baseline=baseline, initial_state=initial_state)

    def current_state(self, rules: RollRuleSet) -> GroupRollState:
        state = self.initial_state
        for event in self.events:
            state = _apply_event(state, event, rules)
        return state

    def apply_observed(
        self,
        action: ApplyRollAction,
        realized_banner: BannerState,
        replacement_offer: RollOffer,
        rules: RollRuleSet,
    ) -> AdvisorSession:
        state = self.current_state(rules)
        next_state = apply_realized_transition(
            state,
            action,
            realized_banner,
            replacement_offer,
            rules,
        )
        event = AdvisorEvent(
            event_type="apply",
            banner_role=action.banner_role,
            operation_id=action.operation_id,
            realized_banner=realized_banner,
            replacement_offer=replacement_offer,
            before_state_sha256=state_sha256(state),
            after_state_sha256=state_sha256(next_state),
        )
        return AdvisorSession(self.baseline, self.initial_state, (*self.events, event))

    def refresh_observed(
        self,
        replacement_offer: RollOffer,
        rules: RollRuleSet,
    ) -> AdvisorSession:
        state = self.current_state(rules)
        next_state = refresh_transition(state, replacement_offer, rules)
        event = AdvisorEvent(
            event_type="refresh",
            banner_role=None,
            operation_id=None,
            realized_banner=None,
            replacement_offer=replacement_offer,
            before_state_sha256=state_sha256(state),
            after_state_sha256=state_sha256(next_state),
        )
        return AdvisorSession(self.baseline, self.initial_state, (*self.events, event))

    def as_payload(self, rules: RollRuleSet) -> dict[str, Any]:
        current = self.current_state(rules)
        body = {
            "schema_version": 1,
            "baseline": self.baseline.as_payload(),
            "initial_state": state_payload(self.initial_state),
            "events": [event.as_payload() for event in self.events],
            "final_state_sha256": state_sha256(current),
        }
        return {**body, "session_sha256": sha256_json(body)}

    def as_json(self, rules: RollRuleSet) -> str:
        return json.dumps(self.as_payload(rules), ensure_ascii=False, indent=2)

    @classmethod
    def from_payload(
        cls,
        value: Any,
        rules: RollRuleSet,
        *,
        expected_baseline: AdvisorBaseline | None = None,
    ) -> AdvisorSession:
        payload = _mapping(value, "session")
        expected = {
            "schema_version",
            "baseline",
            "initial_state",
            "events",
            "final_state_sha256",
            "session_sha256",
        }
        _exact_keys(payload, expected, "session")
        if payload["schema_version"] != 1:
            raise AdvisorSessionError("unsupported advisor replay schema_version")
        body = {key: payload[key] for key in expected if key != "session_sha256"}
        if sha256_json(body) != payload["session_sha256"]:
            raise AdvisorSessionError("session_sha256 does not match the saved payload")
        baseline = AdvisorBaseline.from_payload(payload["baseline"])
        if expected_baseline is not None and baseline != expected_baseline:
            raise AdvisorSessionError("saved session baseline differs from the locked local context")
        initial_state = state_from_payload(payload["initial_state"])
        validate_group_state(initial_state, rules)
        events = tuple(
            AdvisorEvent.from_payload(item) for item in _sequence(payload["events"], "events")
        )
        session = cls(baseline=baseline, initial_state=initial_state, events=events)
        if state_sha256(session.current_state(rules)) != payload["final_state_sha256"]:
            raise AdvisorSessionError("saved final_state_sha256 differs from deterministic replay")
        return session

    @classmethod
    def from_json(
        cls,
        value: str | bytes,
        rules: RollRuleSet,
        *,
        expected_baseline: AdvisorBaseline | None = None,
    ) -> AdvisorSession:
        try:
            payload = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise AdvisorSessionError(f"saved session is not valid JSON: {error}") from error
        return cls.from_payload(payload, rules, expected_baseline=expected_baseline)


_MUTATION_LABELS = {
    ROLL_QUALITY: "重随品质",
    ROLL_TRAIT: "重随 Trait",
    ROLL_STAT: "重随 Stat",
    INCREASE_ONE_QUALITY: "随机一格升一级",
    INCREASE_TWO_DECREASE_ONE: "两格升一级、一格降一级",
}
_COLOR_LABELS = {"red": "红", "blue": "蓝", "green": "绿"}
_SELECTOR_LABELS = {
    TARGET_ALL_COLOR: "同色全部",
    TARGET_ONE_COLOR: "同色随机一格",
    TARGET_FIRST_COLOR: "同色第一格",
    TARGET_LAST_COLOR: "同色最后一格",
}
_ROLE_LABELS = {"core": "Carry", "mid": "Mid", "support": "Support"}


def operation_label(operation_id: int, rules: RollRuleSet) -> str:
    operation = rules.operation(operation_id)
    mutation = _MUTATION_LABELS.get(operation.mutation, operation.mutation)
    targets = set(operation.targets)
    if targets == {TARGET_ALL}:
        target = "整面战旗"
    else:
        color = next((color for flag, color in COLOR_TARGETS.items() if flag in targets), None)
        selector = next((flag for flag in _SELECTOR_LABELS if flag in targets), None)
        target = " / ".join(
            part
            for part in (
                None if color is None else f"{_COLOR_LABELS[color]}色",
                None if selector is None else _SELECTOR_LABELS[selector],
            )
            if part is not None
        )
    return f"#{operation_id} · {mutation} · {target}"


def action_identity(action: RollAction) -> str:
    if isinstance(action, RefreshRollAction):
        return "refresh"
    return f"{action.banner_role}:{action.operation_id}"


def action_label(action: RollAction, rules: RollRuleSet) -> str:
    if isinstance(action, RefreshRollAction):
        return "刷新三个选项（战旗不变）"
    role = _ROLE_LABELS.get(action.banner_role, action.banner_role)
    return f"{role} · {operation_label(action.operation_id, rules)}"


def action_from_identity(identity: str, state: GroupRollState, rules: RollRuleSet) -> RollAction:
    candidates = {action_identity(action): action for action in legal_actions(state, rules)}
    try:
        return candidates[identity]
    except KeyError as error:
        raise AdvisorSessionError(f"action {identity!r} is not legal in the current state") from error


def mutation_outcome_label(current: BannerState, outcome: BannerState) -> str:
    changes = []
    for index, (before, after) in enumerate(zip(current.emblems, outcome.emblems, strict=True), start=1):
        parts = []
        if before.stat_id != after.stat_id:
            parts.append(f"Stat {before.stat_id}→{after.stat_id}")
        if before.quality_tier != after.quality_tier:
            parts.append(f"T{before.quality_tier}→T{after.quality_tier}")
        if before.trait_id != after.trait_id:
            parts.append(f"Trait {before.trait_id}→{after.trait_id}")
        if parts:
            changes.append(f"第{index}格 " + "，".join(parts))
    return "；".join(changes) if changes else "数值封顶，画面无变化"


def legal_realized_banners(
    state: GroupRollState,
    action: ApplyRollAction,
    rules: RollRuleSet,
) -> tuple[BannerState, ...]:
    banner = next(item for item in state.banners if item.role == action.banner_role)
    return enumerate_mutation_outcomes(banner, action.operation_id, rules)
