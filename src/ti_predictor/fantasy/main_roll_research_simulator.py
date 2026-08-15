"""Pure forward simulator for isolated TI 2026 Main Roll research."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import numpy as np

from ti_predictor.fantasy.main_current_advisor import MainCurrentAdvisorContext
from ti_predictor.fantasy.main_roll import (
    MainRollState,
    apply_realized_transition,
    legal_actions,
    refresh_transition,
    validate_main_state,
)
from ti_predictor.fantasy.main_roll_research_contract import MainRollResearchManifest
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.roll import (
    ApplyRollAction,
    BannerState,
    EmblemState,
    RefreshRollAction,
    RollOffer,
    RollRuleSet,
)
from ti_predictor.fantasy.scenarios import ROLE_IDS
from ti_predictor.fantasy.valuation import (
    RiskConfiguration,
    distribution_summary,
    match_group_roles,
)
from ti_predictor.hashing import sha256_bytes, sha256_json


class MainResearchSimulationError(ValueError):
    """An offline Main research episode violates its frozen contract."""


@dataclass(frozen=True, order=True)
class StopRollAction:
    """Analysis-only choice to retain the current Banners and stop spending tokens."""


STOP = StopRollAction()
type ResearchAction = ApplyRollAction | RefreshRollAction | StopRollAction


def action_identity(action: ResearchAction) -> str:
    if isinstance(action, StopRollAction):
        return "stop"
    if isinstance(action, RefreshRollAction):
        return "refresh"
    return f"{action.banner_role}:{action.operation_id}"


def action_payload(action: ResearchAction) -> dict[str, Any]:
    if isinstance(action, StopRollAction):
        return {"kind": "stop"}
    if isinstance(action, RefreshRollAction):
        return {"kind": "refresh"}
    return {
        "kind": "apply",
        "banner_role": action.banner_role,
        "operation_id": action.operation_id,
    }


def banner_payload(banner: BannerState) -> dict[str, Any]:
    return {
        "role": banner.role,
        "emblems": [
            {
                "stat_id": emblem.stat_id,
                "quality_tier": emblem.quality_tier,
                "trait_id": emblem.trait_id,
            }
            for emblem in banner.emblems
        ],
    }


def state_payload(state: MainRollState) -> dict[str, Any]:
    return {
        "period": state.period,
        "slot_count": state.slot_count,
        "remaining_rolls": state.remaining_rolls,
        "banners": [banner_payload(banner) for banner in state.banners],
        "offer": {"operation_ids": list(state.offer.operation_ids)},
    }


def state_from_payload(payload: Mapping[str, Any], rules: RollRuleSet) -> MainRollState:
    try:
        banners = tuple(
            BannerState(
                role=str(banner["role"]),
                emblems=tuple(
                    EmblemState(
                        stat_id=str(emblem["stat_id"]),
                        quality_tier=int(emblem["quality_tier"]),
                        trait_id=str(emblem["trait_id"]),
                    )
                    for emblem in banner["emblems"]
                ),
            )
            for banner in payload["banners"]
        )
        offer_payload = payload["offer"]
        state = MainRollState(
            banners=banners,
            offer=RollOffer(tuple(int(value) for value in offer_payload["operation_ids"])),
            remaining_rolls=int(payload["remaining_rolls"]),
            period=str(payload.get("period", "main")),
            slot_count=int(payload.get("slot_count", 5)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise MainResearchSimulationError("Main research state payload is malformed") from error
    validate_main_state(state, rules)
    return state


def state_sha256(state: MainRollState) -> str:
    return sha256_json(state_payload(state))


@dataclass(frozen=True)
class TerminalEvaluation:
    outcomes: np.ndarray = field(repr=False, compare=False)
    selected_team_ids: tuple[int, ...]
    selection_mode: Literal["fixed-across-scenarios", "projected-roster-conditional"] = (
        "fixed-across-scenarios"
    )
    selection_plan_sha256: str | None = None
    cohort_ids: tuple[int, ...] = field(default=(), repr=False)
    roster_ids: tuple[int, ...] = field(default=(), repr=False)
    mean: float = field(init=False)
    cvar10: float = field(init=False)
    p10: float = field(init=False)
    p50: float = field(init=False)
    p90: float = field(init=False)
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        outcomes = np.ascontiguousarray(self.outcomes, dtype="<f8")
        if outcomes.ndim != 1 or not len(outcomes) or not np.isfinite(outcomes).all():
            raise MainResearchSimulationError("terminal outcomes must be a finite non-empty vector")
        selected = tuple(int(team_id) for team_id in self.selected_team_ids)
        object.__setattr__(self, "selected_team_ids", selected)
        if self.selection_mode == "fixed-across-scenarios":
            if len(selected) != 3:
                raise MainResearchSimulationError("fixed terminal evaluation requires one Team per Main role")
            selection_plan_sha256 = self.selection_plan_sha256 or sha256_json(
                {"selection_mode": self.selection_mode, "selected_team_ids": selected}
            )
        else:
            if selected:
                raise MainResearchSimulationError(
                    "roster-conditional terminal evaluation cannot claim one fixed Team lineup"
                )
            selection_plan_sha256 = self.selection_plan_sha256
        if (
            selection_plan_sha256 is None
            or len(selection_plan_sha256) != 64
            or any(character not in "0123456789abcdef" for character in selection_plan_sha256)
        ):
            raise MainResearchSimulationError("terminal Team-selection plan requires a SHA-256")
        cohort_ids = tuple(int(value) for value in self.cohort_ids)
        roster_ids = tuple(int(value) for value in self.roster_ids)
        if cohort_ids and len(cohort_ids) != len(outcomes):
            raise MainResearchSimulationError("terminal cohort IDs must align with outcomes")
        if roster_ids and len(roster_ids) != len(outcomes):
            raise MainResearchSimulationError("terminal roster IDs must align with outcomes")
        object.__setattr__(self, "selection_plan_sha256", selection_plan_sha256)
        object.__setattr__(self, "cohort_ids", cohort_ids)
        object.__setattr__(self, "roster_ids", roster_ids)
        outcomes.setflags(write=False)
        summary = distribution_summary(outcomes, cvar_alpha=0.1)
        object.__setattr__(self, "outcomes", outcomes)
        object.__setattr__(self, "mean", float(summary["mean"]))
        object.__setattr__(self, "cvar10", float(summary["cvar"]))
        object.__setattr__(self, "p10", float(summary["p10"]))
        object.__setattr__(self, "p50", float(summary["p50"]))
        object.__setattr__(self, "p90", float(summary["p90"]))
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "selection_mode": self.selection_mode,
                    "selected_team_ids": self.selected_team_ids,
                    "selection_plan_sha256": selection_plan_sha256,
                    "cohort_ids_sha256": sha256_json(cohort_ids),
                    "roster_ids_sha256": sha256_json(roster_ids),
                    "outcomes_sha256": sha256_bytes(outcomes.tobytes(order="C")),
                }
            ),
        )

    def summary_payload(self) -> dict[str, Any]:
        return {
            "selection_mode": self.selection_mode,
            "selected_team_ids": list(self.selected_team_ids),
            "selection_plan_sha256": self.selection_plan_sha256,
            "cohort_count": len(set(self.cohort_ids)) if self.cohort_ids else 0,
            "roster_count": len(set(self.roster_ids)) if self.roster_ids else 0,
            "mean": self.mean,
            "cvar10": self.cvar10,
            "p10": self.p10,
            "p50": self.p50,
            "p90": self.p90,
            "semantic_hash": self.semantic_hash,
        }


class MainResearchTerminal(Protocol):
    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation: ...


class FrozenMainTerminalAdapter:
    """Read-only adapter over the currently frozen Main release evaluator."""

    def __init__(
        self,
        context: MainCurrentAdvisorContext,
        *,
        mean_retention_epsilon: float = 0.0,
        cvar_alpha: float = 0.1,
    ) -> None:
        self.context = context
        self.risk = RiskConfiguration(
            mean_retention_epsilon=mean_retention_epsilon,
            cvar_alpha=cvar_alpha,
        )
        self._cache: dict[tuple[BannerState, ...], TerminalEvaluation] = {}

    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        banners = tuple(banners)
        if banners in self._cache:
            return self._cache[banners]
        banner_by_role = {banner.role: banner for banner in banners}
        if tuple(banner_by_role) != ROLE_IDS:
            raise MainResearchSimulationError("terminal Banners must follow canonical Main roles")
        matrices = {role: self.context.terminal.banner(banner_by_role[role]) for role in ROLE_IDS}
        if any(matrix.outcomes.shape[1] != self.context.scenario_count for matrix in matrices.values()):
            raise MainResearchSimulationError("terminal matrices do not align with Main Scenarios")
        matched = match_group_roles(matrices, self.risk)
        selected = tuple(int(team_id) for team_id in matched.selected_team_ids)
        result = TerminalEvaluation(
            outcomes=matched.outcomes,
            selected_team_ids=selected,  # type: ignore[arg-type]
        )
        self._cache[banners] = result
        return result


@dataclass(frozen=True)
class PolicyDecision:
    action: ResearchAction
    reason: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class MainResearchPolicy(Protocol):
    policy_id: str

    def choose_action(self, state: MainRollState) -> PolicyDecision: ...


@dataclass(frozen=True)
class EpisodeResult:
    trace: dict[str, Any]
    initial_terminal: TerminalEvaluation
    final_terminal: TerminalEvaluation


def _keyed_rng(episode_seed: int, step: int, draw_kind: str) -> tuple[random.Random, str]:
    key = f"main-roll-research:{episode_seed}:{step}:{draw_kind}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return random.Random(int(digest[:16], 16)), digest


class MainRollResearchSimulator:
    """Run deterministic, read-only episodes without touching Web or runtime pointers."""

    def __init__(
        self,
        manifest: MainRollResearchManifest,
        rules: RollRuleSet,
        terminal: MainResearchTerminal,
        *,
        source_version: str,
    ) -> None:
        if not source_version:
            raise MainResearchSimulationError("research runs require a source version")
        self.manifest = manifest
        self.rules = rules
        self.terminal = terminal
        self.source_version = source_version

    def run_episode(
        self,
        state: MainRollState,
        policy: MainResearchPolicy,
        provider: MainRollProbabilityProvider,
        *,
        episode_seed: int,
    ) -> EpisodeResult:
        validate_main_state(state, self.rules)
        if provider.rules is not self.rules:
            raise MainResearchSimulationError("probability provider uses a different Rule set")
        self.manifest.probability_model(provider.model_id)
        initial_state = state
        initial_terminal = self.terminal.evaluate(state.banners)
        steps: list[dict[str, Any]] = []
        spent_rolls = 0
        while True:
            if state.remaining_rolls == 0:
                stop_reason = "roll-budget-exhausted"
                break
            decision = policy.choose_action(state)
            legal = legal_actions(state, self.rules)
            if not isinstance(decision.action, StopRollAction) and decision.action not in legal:
                raise MainResearchSimulationError(
                    f"policy {policy.policy_id} selected an illegal action: "
                    f"{action_identity(decision.action)}"
                )
            before = state
            action = decision.action
            draw_keys: dict[str, str] = {}
            if isinstance(action, StopRollAction):
                after = state
                stop_reason = "policy-stop"
            else:
                offer_rng, offer_key = _keyed_rng(episode_seed, spent_rolls, "replacement-offer")
                replacement_offer = provider.draw_offer(offer_rng)
                draw_keys["replacement_offer"] = offer_key
                if isinstance(action, RefreshRollAction):
                    after = refresh_transition(state, replacement_offer, self.rules)
                else:
                    mutation_rng, mutation_key = _keyed_rng(
                        episode_seed,
                        spent_rolls,
                        "mutation",
                    )
                    current_banner = next(
                        banner for banner in state.banners if banner.role == action.banner_role
                    )
                    realized = provider.sample_mutation(
                        current_banner,
                        action.operation_id,
                        mutation_rng,
                    )
                    draw_keys["mutation"] = mutation_key
                    after = apply_realized_transition(
                        state,
                        action,
                        realized,
                        replacement_offer,
                        self.rules,
                    )
                spent_rolls += 1
                stop_reason = "continue"
            steps.append(
                {
                    "step": len(steps),
                    "remaining_before": before.remaining_rolls,
                    "state_before": state_payload(before),
                    "state_before_sha256": state_sha256(before),
                    "decision": {
                        "action": action_payload(action),
                        "action_id": action_identity(action),
                        "reason": decision.reason,
                        "diagnostics": dict(decision.diagnostics),
                    },
                    "draw_keys": draw_keys,
                    "state_after": state_payload(after),
                    "state_after_sha256": state_sha256(after),
                    "remaining_after": after.remaining_rolls,
                }
            )
            state = after
            if isinstance(action, StopRollAction):
                break
            if len(steps) > initial_state.remaining_rolls:
                raise MainResearchSimulationError("episode exceeded its frozen Roll budget")

        final_terminal = self.terminal.evaluate(state.banners)
        body = {
            "schema_version": 1,
            "analysis_type": "main-roll-strategy-research-episode",
            "research_only": True,
            "web_integration": False,
            "as_of": self.manifest.as_of,
            "source_version": self.source_version,
            "manifest_sha256": self.manifest.semantic_hash,
            "rule_snapshot_sha256": self.manifest.source.rule_snapshot_sha256,
            "main_release_sha256": self.manifest.source.main_release_sha256,
            "eligibility_mode": self.manifest.source.eligibility_mode,
            "probability_model": provider.model_id,
            "policy_id": policy.policy_id,
            "episode_seed": episode_seed,
            "initial_state_sha256": state_sha256(initial_state),
            "final_state_sha256": state_sha256(state),
            "spent_rolls": spent_rolls,
            "unspent_rolls": state.remaining_rolls,
            "stop_reason": stop_reason,
            "initial_terminal": initial_terminal.summary_payload(),
            "final_terminal": final_terminal.summary_payload(),
            "steps": steps,
        }
        trace = {**body, "trace_sha256": sha256_json(body)}
        if not math.isfinite(final_terminal.mean):
            raise MainResearchSimulationError("episode produced a non-finite terminal value")
        return EpisodeResult(trace, initial_terminal, final_terminal)


__all__ = [
    "EpisodeResult",
    "FrozenMainTerminalAdapter",
    "MainResearchPolicy",
    "MainResearchSimulationError",
    "MainResearchTerminal",
    "MainRollResearchSimulator",
    "PolicyDecision",
    "STOP",
    "StopRollAction",
    "TerminalEvaluation",
    "action_identity",
    "state_from_payload",
    "state_payload",
    "state_sha256",
]
