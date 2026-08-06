"""Frozen, human-readable Group Roll playbook execution.

This module evaluates rules that were derived from governed Stat evidence and exact
Quality/Trait arithmetic.  It deliberately contains no look-ahead search or Reference Roll
solver dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ti_predictor.fantasy.roll import (
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
    GroupRollState,
    RefreshRollAction,
    RollAction,
    RollOperation,
    RollRuleSet,
    enumerate_mutation_outcomes,
    legal_actions,
    mutation_distribution,
)
from ti_predictor.fantasy.scoring import Emblem, emblem_multipliers
from ti_predictor.hashing import sha256_json

ROLE_ORDER = ("core", "mid", "support")
GRADE_ORDER = {
    "priority-repair": 0,
    "conditional-reroll": 1,
    "keep": 2,
    "hard-protect": 3,
}
APPROVED_TRAIT_RECIPES = {
    ("friendly", "friendly", "friendly"),
    ("fractal", "fractal", "fractal"),
    ("vampiric", "benevolent", "vampiric"),
    ("benevolent", "vampiric", "benevolent"),
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlaybookPhase(StrictModel):
    id: Literal["early", "middle", "late"]
    remaining_min: int = Field(ge=1, le=40)
    remaining_max: int = Field(ge=1, le=40)


class PlaybookRule(StrictModel):
    rule_id: str = Field(min_length=1)
    handler: str = Field(min_length=1)
    title: str = Field(min_length=1)
    visible_conditions: tuple[str, ...]
    parameters: dict[str, Any]

    @model_validator(mode="after")
    def validate_complexity(self) -> PlaybookRule:
        if len(self.visible_conditions) > 3:
            raise ValueError(f"{self.rule_id} exceeds three visible conditions")
        if len(set(self.visible_conditions)) != len(self.visible_conditions):
            raise ValueError(f"{self.rule_id} repeats a visible condition")
        return self


class PlaybookFallback(StrictModel):
    action: Literal["refresh"]
    instruction: str = Field(min_length=1)


class PlaybookDefinition(StrictModel):
    schema_version: Literal[1]
    playbook_id: str
    edition: Literal["rate-agnostic", "primary-model"]
    status: Literal["candidate-frozen", "baseline-reliable", "strict-reliable", "draft", "inapplicable"]
    period: Literal["group"]
    roll_count: Literal[40]
    as_of: str
    origin: Literal["independent-stat-quality-trait-derivation-before-reference-solver"]
    source_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_models: tuple[str, ...] | None = None
    transition_model: str | None = None
    sensitivity_models: tuple[str, ...] | None = None
    phases: tuple[PlaybookPhase, ...]
    stat_grade_thresholds: dict[str, float]
    published_rule_count: Literal[12]
    candidate_rule_counts: tuple[Literal[8, 12, 16], ...]
    risk_overlays: dict[str, dict[str, Any]]
    rules: tuple[PlaybookRule, ...]
    fallback: PlaybookFallback

    @model_validator(mode="after")
    def validate_contract(self) -> PlaybookDefinition:
        if self.candidate_rule_counts != (8, 12, 16):
            raise ValueError("playbook candidates must be the nested 8/12/16 frontier")
        if len(self.rules) != 16 or len({rule.rule_id for rule in self.rules}) != 16:
            raise ValueError("a frozen playbook must contain sixteen unique ordered candidate rules")
        if tuple(phase.id for phase in self.phases) != ("early", "middle", "late"):
            raise ValueError("playbook phases must be early, middle, late")
        covered = [0] * 41
        for phase in self.phases:
            if phase.remaining_min > phase.remaining_max:
                raise ValueError("playbook phase bounds are reversed")
            if phase.remaining_min % 5 not in (0, 1) or phase.remaining_max % 5 not in (0, 4):
                raise ValueError("playbook phase boundaries must be between multiples of five")
            for remaining in range(phase.remaining_min, phase.remaining_max + 1):
                covered[remaining] += 1
        if any(covered[remaining] != 1 for remaining in range(1, 41)):
            raise ValueError("playbook phases must partition all forty remaining-Roll states")
        if set(self.risk_overlays) != {"mean-first", "default-knee", "downside-first"}:
            raise ValueError("playbook must expose exactly three risk overlays")
        if self.edition == "rate-agnostic":
            if self.transition_model is not None or self.sensitivity_models is not None:
                raise ValueError("Rate-agnostic playbook cannot declare a decision transition model")
            if not self.validation_models or len(self.validation_models) != 3:
                raise ValueError("Rate-agnostic playbook must declare all three validation models")
        else:
            if not self.transition_model or not self.sensitivity_models:
                raise ValueError("Primary-model playbook must declare its model and sensitivities")
            if self.validation_models is not None:
                raise ValueError("Primary-model playbook uses transition_model, not validation_models")
        return self

    @property
    def semantic_hash(self) -> str:
        return sha256_json(self.model_dump(mode="json"))

    def phase_for(self, remaining_rolls: int) -> str:
        for phase in self.phases:
            if phase.remaining_min <= remaining_rolls <= phase.remaining_max:
                return phase.id
        raise ValueError(f"remaining Rolls outside playbook contract: {remaining_rolls}")


@dataclass(frozen=True)
class StatPriority:
    role: str
    color: str
    stat_id: str
    relative_to_best: float
    best_team_mean: float
    runner_up_mean: float
    all_team_mean: float
    grade: str
    boundary: bool
    provenance: str
    coverage: float


@dataclass(frozen=True)
class ActionMetrics:
    minimum_delta: float
    maximum_delta: float
    expected_delta: float | None
    current_value: float

    @property
    def expected_relative_gain(self) -> float | None:
        if self.expected_delta is None:
            return None
        return self.expected_delta / max(abs(self.current_value), 1e-12)


@dataclass(frozen=True)
class PlaybookDecision:
    action: RollAction
    rule_id: str | None
    rule_title: str | None
    explanation: str
    metrics: ActionMetrics | None


def load_playbook(path: Path) -> PlaybookDefinition:
    return PlaybookDefinition.model_validate_json(path.read_text(encoding="utf-8"))


def build_stat_priorities(
    stat_forecasts: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
) -> tuple[StatPriority, ...]:
    """Apply the accepted point-grade rules; bootstrap remains an independent marker."""

    boundary = {
        (str(row["role"]), str(row["color"]), str(row["stat_id"])): bool(row["boundary"])
        for row in bootstrap.get("rows", ())
    }
    source_rows = stat_forecasts.get("rows", ())
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in source_rows:
        grouped.setdefault((str(row["role"]), str(row["color"])), []).append(row)
    expected_groups = {
        ("core", "red"),
        ("core", "green"),
        ("mid", "red"),
        ("mid", "blue"),
        ("mid", "green"),
        ("support", "blue"),
        ("support", "green"),
    }
    if set(grouped) != expected_groups or any(len(rows) != 6 for rows in grouped.values()):
        raise ValueError("P4 requires exactly seven role/color groups of six Stats")

    result: list[StatPriority] = []
    for (role, color), rows in grouped.items():
        best = max(rows, key=lambda row: float(row["relative_to_best"]))
        best_is_hard = float(best["runner_up_mean"]) < 0.44 * float(best["best_team_mean"])
        for row in rows:
            relative = float(row["relative_to_best"])
            if row is best and best_is_hard:
                grade = "hard-protect"
            elif relative >= 0.846:
                grade = "keep"
            elif relative >= 0.44:
                grade = "conditional-reroll"
            else:
                grade = "priority-repair"
            key = (role, color, str(row["stat_id"]))
            coverage = min(
                float(row["eligible_row_provenance_coverage"]),
                float(row["complete_block_provenance_coverage"]),
            )
            provenance = str(row["provenance"])
            if provenance not in {"exact", "derived"}:
                raise ValueError("Playbook Stats require exact or accepted derived provenance")
            if coverage != 1.0:
                raise ValueError("Playbook Stats require complete provenance coverage")
            result.append(
                StatPriority(
                    role=role,
                    color=color,
                    stat_id=key[2],
                    relative_to_best=relative,
                    best_team_mean=float(row["best_team_mean"]),
                    runner_up_mean=float(row["runner_up_mean"]),
                    all_team_mean=float(row["all_team_mean"]),
                    grade=grade,
                    boundary=boundary.get(key, False),
                    provenance=provenance,
                    coverage=coverage,
                )
            )
    result.sort(key=lambda row: (ROLE_ORDER.index(row.role), row.color, -row.relative_to_best, row.stat_id))
    return tuple(result)


class PlaybookPolicy:
    """Execute one frozen human rule list without any look-ahead search."""

    def __init__(
        self,
        definition: PlaybookDefinition,
        rules: RollRuleSet,
        canonical_rules: Mapping[str, Any],
        stat_priorities: Sequence[StatPriority],
    ) -> None:
        self.definition = definition
        self.rules = rules
        self.canonical_rules = canonical_rules
        self.priority = {(row.role, row.stat_id): row for row in stat_priorities}
        expected = {
            (role, stat_id)
            for role in rules.group_roles
            for color in set(rules.colors_for(role)[:3])
            for stat_id in rules.stats_for(color)
        }
        if set(self.priority) != expected:
            raise ValueError("Stat priorities do not cover every legal Group role/color Stat")

    def banner_value(self, banner: BannerState) -> float:
        emblems = [
            Emblem(
                stat_id=state.stat_id,
                color=self.rules.color_for_stat(state.stat_id),
                quality_tier=state.quality_tier,
                trait=state.trait_id,
            )
            for state in banner.emblems
        ]
        multipliers = emblem_multipliers(emblems, dict(self.canonical_rules))
        return float(
            sum(
                self.priority[(banner.role, state.stat_id)].best_team_mean * multiplier
                for state, multiplier in zip(banner.emblems, multipliers, strict=True)
            )
        )

    def base_contributions(self, banner: BannerState) -> tuple[float, ...]:
        quality_bonus = {
            int(row["tier"]): float(row["bonus_percent"]) / 100.0
            for row in self.canonical_rules["fantasy"]["qualities"]
        }
        return tuple(
            self.priority[(banner.role, emblem.stat_id)].best_team_mean
            * (1.0 + quality_bonus[emblem.quality_tier])
            for emblem in banner.emblems
        )

    def action_metrics(
        self,
        state: GroupRollState,
        action: ApplyRollAction,
        *,
        model_id: str | None,
    ) -> ActionMetrics:
        banner = self._banner(state, action.banner_role)
        current = self.banner_value(banner)
        support_values = tuple(
            self.banner_value(outcome)
            for outcome in enumerate_mutation_outcomes(banner, action.operation_id, self.rules)
        )
        if not support_values:
            raise ValueError("playbook action has no legal mutation support")
        expected: float | None = None
        if model_id is not None:
            expected = (
                sum(
                    outcome.probability * self.banner_value(outcome.banner)
                    for outcome in mutation_distribution(
                        banner,
                        action.operation_id,
                        self.rules,
                        model_id,
                    )
                )
                - current
            )
        return ActionMetrics(
            minimum_delta=min(support_values) - current,
            maximum_delta=max(support_values) - current,
            expected_delta=expected,
            current_value=current,
        )

    def decide(
        self,
        state: GroupRollState,
        *,
        candidate_rule_count: Literal[8, 12, 16] = 12,
        risk_preference: Literal["mean-first", "default-knee", "downside-first"] = "default-knee",
        omit_rule_id: str | None = None,
    ) -> PlaybookDecision:
        if candidate_rule_count not in self.definition.candidate_rule_counts:
            raise ValueError("candidate rule count must be one of the frozen 8/12/16 frontier")
        if risk_preference not in self.definition.risk_overlays:
            raise ValueError(f"unknown risk overlay: {risk_preference}")
        if state.remaining_rolls == 0:
            raise ValueError("no playbook decision exists after all Rolls are spent")
        actions = tuple(
            action for action in legal_actions(state, self.rules) if isinstance(action, ApplyRollAction)
        )
        model_id = self.definition.transition_model if self.definition.edition == "primary-model" else None
        metrics = {action: self.action_metrics(state, action, model_id=model_id) for action in actions}
        for rule in self.definition.rules[:candidate_rule_count]:
            if rule.rule_id == omit_rule_id:
                continue
            candidates = self._apply_handler(
                rule,
                state,
                actions,
                metrics,
                risk_preference=risk_preference,
            )
            if candidates:
                action = self._best_action(candidates, metrics)
                return PlaybookDecision(
                    action=action,
                    rule_id=rule.rule_id,
                    rule_title=rule.title,
                    explanation=f"{rule.rule_id}: {rule.title}",
                    metrics=metrics[action],
                )
        refresh = next(
            action for action in legal_actions(state, self.rules) if isinstance(action, RefreshRollAction)
        )
        return PlaybookDecision(
            action=refresh,
            rule_id=None,
            rule_title=None,
            explanation=self.definition.fallback.instruction,
            metrics=None,
        )

    def _apply_handler(
        self,
        rule: PlaybookRule,
        state: GroupRollState,
        actions: Sequence[ApplyRollAction],
        metrics: Mapping[ApplyRollAction, ActionMetrics],
        *,
        risk_preference: str,
    ) -> tuple[ApplyRollAction, ...]:
        handler = getattr(self, f"_handle_{rule.handler}", None)
        if handler is None:
            raise ValueError(f"unknown frozen playbook handler: {rule.handler}")
        return tuple(handler(rule, state, actions, metrics, risk_preference))

    def _best_action(
        self,
        actions: Sequence[ApplyRollAction],
        metrics: Mapping[ApplyRollAction, ActionMetrics],
    ) -> ApplyRollAction:
        def rank(action: ApplyRollAction) -> tuple[Any, ...]:
            metric = metrics[action]
            primary = metric.expected_delta if metric.expected_delta is not None else metric.minimum_delta
            return (
                -float(primary),
                -metric.maximum_delta,
                ROLE_ORDER.index(action.banner_role),
                action.operation_id,
            )

        return min(actions, key=rank)

    def _banner(self, state: GroupRollState, role: str) -> BannerState:
        return next(banner for banner in state.banners if banner.role == role)

    def _operation(self, action: ApplyRollAction) -> RollOperation:
        return self.rules.operation(action.operation_id)

    def _target_indices(self, banner: BannerState, operation: RollOperation) -> tuple[int, ...]:
        targets = set(operation.targets)
        if targets == {TARGET_ALL}:
            return tuple(range(3))
        color = next(
            color
            for color in ("red", "blue", "green")
            if any(
                flag.endswith({"red": "Rubies", "blue": "Sapphires", "green": "Emeralds"}[color])
                for flag in targets
            )
        )
        matching = tuple(
            index for index, actual in enumerate(self.rules.colors_for(banner.role)[:3]) if actual == color
        )
        if TARGET_FIRST_COLOR in targets:
            return matching[:1]
        if TARGET_LAST_COLOR in targets:
            return matching[-1:]
        if TARGET_ALL_COLOR in targets or TARGET_ONE_COLOR in targets:
            return matching
        raise ValueError(f"unsupported playbook operation target: {operation.targets}")

    def _grades(self, banner: BannerState, indices: Sequence[int]) -> tuple[str, ...]:
        return tuple(self.priority[(banner.role, banner.emblems[index].stat_id)].grade for index in indices)

    def _boundaries(self, banner: BannerState, indices: Sequence[int]) -> tuple[bool, ...]:
        return tuple(
            self.priority[(banner.role, banner.emblems[index].stat_id)].boundary for index in indices
        )

    def _active_triple_fractal(self, banner: BannerState) -> bool:
        return (
            tuple(emblem.trait_id for emblem in banner.emblems) == ("fractal",) * 3
            and len({emblem.quality_tier for emblem in banner.emblems}) == 3
        )

    def _is_approved_recipe(self, banner: BannerState) -> bool:
        traits = tuple(emblem.trait_id for emblem in banner.emblems)
        if traits == ("fractal",) * 3:
            return len({emblem.quality_tier for emblem in banner.emblems}) == 3
        if traits == ("friendly",) * 3:
            return True
        if traits == ("vampiric", "benevolent", "vampiric"):
            base = self.base_contributions(banner)
            return base[0] + base[2] > 3.5 * base[1]
        if traits == ("benevolent", "vampiric", "benevolent"):
            base = self.base_contributions(banner)
            return base[1] > 1.5 * (base[0] + base[2])
        return False

    def _trait_dead(self, banner: BannerState, index: int) -> bool:
        trait = banner.emblems[index].trait_id
        traits = tuple(emblem.trait_id for emblem in banner.emblems)
        if trait == "friendly":
            return traits.count("friendly") < 3
        if trait == "fractal":
            return len({emblem.quality_tier for emblem in banner.emblems}) != 3
        if trait == "unique":
            return traits.count("unique") != 1
        return False

    def _one_away_from_recipe(self, banner: BannerState, indices: Sequence[int]) -> bool:
        if len(indices) != 1 or self._is_approved_recipe(banner):
            return False
        index = indices[0]
        current = list(emblem.trait_id for emblem in banner.emblems)
        for recipe in APPROVED_TRAIT_RECIPES:
            differing = [
                offset
                for offset, (actual, wanted) in enumerate(zip(current, recipe, strict=True))
                if actual != wanted
            ]
            if differing == [index]:
                if recipe == ("fractal",) * 3 and len({item.quality_tier for item in banner.emblems}) != 3:
                    continue
                return True
        return False

    def _does_not_break_protection(self, banner: BannerState, operation: RollOperation) -> bool:
        indices = self._target_indices(banner, operation)
        if operation.mutation == ROLL_STAT:
            return all(
                self.priority[(banner.role, banner.emblems[index].stat_id)].grade
                not in {"keep", "hard-protect"}
                for index in indices
            )
        if operation.mutation in {ROLL_QUALITY, ROLL_TRAIT}:
            return not self._is_approved_recipe(banner)
        return True

    def _filter_mutation(
        self, actions: Sequence[ApplyRollAction], mutation: str
    ) -> tuple[ApplyRollAction, ...]:
        return tuple(action for action in actions if self._operation(action).mutation == mutation)

    # Frozen rule handlers.  Each one maps directly to one human-visible rule.
    def _handle_increase_one_quality(self, rule, state, actions, metrics, risk):
        for action in actions:
            banner = self._banner(state, action.banner_role)
            if self._operation(action).mutation == INCREASE_ONE_QUALITY and any(
                emblem.quality_tier < 5 for emblem in banner.emblems
            ):
                yield action

    def _handle_targeted_green_priority_repair(self, rule, state, actions, metrics, risk):
        yield from self._targeted_green_by_grade(state, actions, {"priority-repair"}, boundary=None)

    def _handle_targeted_green_stable_priority_repair(self, rule, state, actions, metrics, risk):
        yield from self._targeted_green_by_grade(state, actions, {"priority-repair"}, boundary=False)

    def _handle_mid_singleton_priority_repair(self, rule, state, actions, metrics, risk):
        for action in self._filter_mutation(actions, ROLL_STAT):
            if action.banner_role != "mid":
                continue
            banner = self._banner(state, "mid")
            indices = self._target_indices(banner, self._operation(action))
            if len(indices) == 1 and self._grades(banner, indices) == ("priority-repair",):
                yield action

    def _handle_duplicate_color_priority_repair(self, rule, state, actions, metrics, risk):
        for action in self._filter_mutation(actions, ROLL_STAT):
            if action.banner_role not in {"core", "support"}:
                continue
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if len(indices) == 2 and set(self._grades(banner, indices)) == {"priority-repair"}:
                yield action

    def _handle_precise_t1_quality(self, rule, state, actions, metrics, risk):
        yield from self._quality_targets_at_most(state, actions, 1, targeted_only=True)

    def _handle_precise_t1_quality_before_late(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 11:
            yield from self._quality_targets_at_most(state, actions, 1, targeted_only=True)

    def _handle_broad_all_t1_quality(self, rule, state, actions, metrics, risk):
        yield from self._quality_targets_at_most(state, actions, 1, broad_only=True)

    def _handle_broad_all_t1_quality_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 26:
            yield from self._quality_targets_at_most(state, actions, 1, broad_only=True)

    def _handle_precise_dead_blue_trait(self, rule, state, actions, metrics, risk):
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            operation = self._operation(action)
            if not set(operation.targets) & {TARGET_ONE_COLOR, TARGET_FIRST_COLOR, TARGET_LAST_COLOR}:
                continue
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, operation)
            if (
                not indices
                or self._is_approved_recipe(banner)
                or not all(self._trait_dead(banner, index) for index in indices)
            ):
                continue
            base = self.base_contributions(banner)
            if all(
                base[index]
                >= 0.2
                * max(
                    (base[adjacent] for adjacent in (index - 1, index + 1) if 0 <= adjacent < 3), default=0.0
                )
                for index in indices
            ):
                yield action

    def _handle_precise_dead_blue_trait_before_late(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 11:
            yield from self._handle_precise_dead_blue_trait(rule, state, actions, metrics, risk)

    def _handle_late_nonnegative_support(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls <= 10:
            yield from (action for action in actions if metrics[action].minimum_delta >= -1e-9)

    def _handle_nonnegative_stat_before_late(self, rule, state, actions, metrics, risk):
        yield from self._nonnegative_mutation_before_late(state, actions, metrics, ROLL_STAT)

    def _handle_nonnegative_quality_before_late(self, rule, state, actions, metrics, risk):
        yield from self._nonnegative_mutation_before_late(state, actions, metrics, ROLL_QUALITY)

    def _handle_nonnegative_trait_before_late(self, rule, state, actions, metrics, risk):
        yield from self._nonnegative_mutation_before_late(state, actions, metrics, ROLL_TRAIT)

    def _handle_targeted_green_conditional_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 11:
            yield from self._targeted_green_by_grade(state, actions, {"conditional-reroll"}, boundary=False)

    def _handle_precise_t2_quality_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 11:
            yield from self._quality_targets_at_most(
                state,
                actions,
                2,
                minimum=2,
                targeted_only=True,
                preserve_fractal=True,
            )

    def _handle_one_away_blue_trait_recipe(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            operation = self._operation(action)
            if not set(operation.targets) & {TARGET_ONE_COLOR, TARGET_FIRST_COLOR, TARGET_LAST_COLOR}:
                continue
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, operation)
            if self._one_away_from_recipe(banner, indices):
                yield action

    def _handle_balanced_two_up_one_down_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 26 and self._allow_balanced_trade(risk):
            yield from self._balanced_trade_candidates(state, actions, maximum_tier=3, metrics=metrics)

    def _handle_targeted_green_boundary_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 26 and risk == "mean-first":
            yield from self._targeted_green_by_grade(state, actions, {"conditional-reroll"}, boundary=True)

    def _handle_broad_all_t2_quality_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls >= 26 and risk == "mean-first":
            yield from self._quality_targets_at_most(state, actions, 2, broad_only=True)

    def _handle_broad_trait_floor_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 26:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            indices = self._target_indices(banner, operation)
            if (
                TARGET_ALL_COLOR in operation.targets
                and not self._is_approved_recipe(banner)
                and all(self._trait_dead(banner, index) for index in indices)
            ):
                yield action

    def _handle_balanced_two_up_one_down_middle(self, rule, state, actions, metrics, risk):
        if 11 <= state.remaining_rolls <= 25 and risk == "mean-first":
            yield from self._balanced_trade_candidates(state, actions, maximum_tier=2, metrics=metrics)

    def _handle_singleton_positive_stat_mean(self, rule, state, actions, metrics, risk):
        threshold = (
            float(rule.parameters.get("late_minimum_relative_gain", 0.05))
            if state.remaining_rolls <= 10
            else 0.0
        )
        for action in self._filter_mutation(actions, ROLL_STAT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            gain = metrics[action].expected_relative_gain
            if len(indices) == 1 and gain is not None and gain > threshold:
                yield action

    def _handle_singleton_positive_stat_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_STAT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if len(indices) == 1 and self._meets_expected_gain_floor(action, metrics, risk):
                yield action

    def _handle_duplicate_positive_stat_mean(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_STAT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if len(indices) == 2 and "hard-protect" not in self._grades(banner, indices):
                if (metrics[action].expected_delta or 0.0) > 0.0:
                    yield action

    def _handle_duplicate_positive_stat_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_STAT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if (
                len(indices) == 2
                and "hard-protect" not in self._grades(banner, indices)
                and self._meets_expected_gain_floor(action, metrics, risk)
            ):
                yield action

    def _handle_precise_quality_positive_mean(self, rule, state, actions, metrics, risk):
        maximum = int(rule.parameters.get("maximum_quality_tier", 2))
        yield from self._quality_targets_at_most(
            state, actions, maximum, targeted_only=True, preserve_fractal=True
        )

    def _handle_broad_quality_positive_mean(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_QUALITY):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            if TARGET_ALL_COLOR in operation.targets and not self._active_triple_fractal(banner):
                if (metrics[action].expected_delta or 0.0) > 0.0:
                    yield action

    def _handle_broad_quality_positive_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_QUALITY):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            if (
                TARGET_ALL_COLOR in operation.targets
                and not self._active_triple_fractal(banner)
                and self._meets_expected_gain_floor(action, metrics, risk)
            ):
                yield action

    def _handle_precise_blue_trait_positive_mean(self, rule, state, actions, metrics, risk):
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            if set(operation.targets) & {TARGET_ONE_COLOR, TARGET_FIRST_COLOR, TARGET_LAST_COLOR}:
                if not self._is_approved_recipe(banner) and (metrics[action].expected_delta or 0.0) > 0.0:
                    yield action

    def _handle_precise_blue_trait_positive_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            if (
                set(operation.targets) & {TARGET_ONE_COLOR, TARGET_FIRST_COLOR, TARGET_LAST_COLOR}
                and not self._is_approved_recipe(banner)
                and self._meets_expected_gain_floor(action, metrics, risk)
            ):
                yield action

    def _handle_singleton_trait_positive_mean(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if len(indices) == 1 and not self._is_approved_recipe(banner):
                if (metrics[action].expected_delta or 0.0) > 0.0:
                    yield action

    def _handle_singleton_trait_positive_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if (
                len(indices) == 1
                and not self._is_approved_recipe(banner)
                and self._meets_expected_gain_floor(action, metrics, risk)
            ):
                yield action

    def _handle_targeted_green_stable_positive_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        candidates = self._targeted_green_by_grade(
            state,
            actions,
            {"priority-repair"},
            boundary=False,
        )
        yield from (action for action in candidates if self._meets_expected_gain_floor(action, metrics, risk))

    def _handle_one_away_blue_trait_positive_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            operation = self._operation(action)
            if not set(operation.targets) & {TARGET_ONE_COLOR, TARGET_FIRST_COLOR, TARGET_LAST_COLOR}:
                continue
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, operation)
            if self._one_away_from_recipe(banner, indices) and self._meets_expected_gain_floor(
                action,
                metrics,
                risk,
            ):
                yield action

    def _handle_targeted_green_conditional_mean(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 11:
            return
        candidates = self._targeted_green_by_grade(state, actions, {"conditional-reroll"}, boundary=None)
        yield from (action for action in candidates if (metrics[action].expected_delta or 0.0) > 0.0)

    def _handle_late_positive_mean(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls > 10:
            return
        overlay = self.definition.risk_overlays[risk]
        threshold = float(overlay.get("minimum_expected_delta", 0.0))
        for action in actions:
            banner = self._banner(state, action.banner_role)
            gain = metrics[action].expected_relative_gain
            if (
                gain is not None
                and gain > threshold
                and self._does_not_break_protection(banner, self._operation(action))
            ):
                yield action

    def _handle_broad_trait_positive_mean_early(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 26:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            if TARGET_ALL_COLOR in operation.targets and not self._is_approved_recipe(banner):
                if (metrics[action].expected_delta or 0.0) > 0.0:
                    yield action

    def _handle_broad_trait_positive_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 26:
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            if (
                TARGET_ALL_COLOR in operation.targets
                and not self._is_approved_recipe(banner)
                and self._meets_expected_gain_floor(action, metrics, risk)
            ):
                yield action

    def _handle_balanced_two_up_one_down_threshold(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 26 or not self._allow_balanced_trade(risk):
            return
        candidates = self._balanced_trade_candidates(state, actions, maximum_tier=2, metrics=metrics)
        yield from (action for action in candidates if self._meets_expected_gain_floor(action, metrics, risk))

    def _handle_conditional_stat_boundary_mean_first(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls < 26 or risk != "mean-first":
            return
        for action in self._filter_mutation(actions, ROLL_STAT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if any(self._boundaries(banner, indices)) and (metrics[action].expected_delta or 0.0) > 0.0:
                yield action

    def _handle_precise_trait_mean_first_late(self, rule, state, actions, metrics, risk):
        if state.remaining_rolls > 10 or risk != "mean-first":
            return
        for action in self._filter_mutation(actions, ROLL_TRAIT):
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, self._operation(action))
            if len(indices) == 1 and not self._is_approved_recipe(banner):
                if (metrics[action].expected_delta or 0.0) > 0.0:
                    yield action

    def _targeted_green_by_grade(self, state, actions, grades, boundary):
        for action in self._filter_mutation(actions, ROLL_STAT):
            operation = self._operation(action)
            if not set(operation.targets) & {TARGET_ONE_COLOR, TARGET_FIRST_COLOR, TARGET_LAST_COLOR}:
                continue
            banner = self._banner(state, action.banner_role)
            indices = self._target_indices(banner, operation)
            if len(indices) != 1 or self.rules.color_for_stat(banner.emblems[indices[0]].stat_id) != "green":
                continue
            row = self.priority[(banner.role, banner.emblems[indices[0]].stat_id)]
            if row.grade in grades and (boundary is None or row.boundary is boundary):
                yield action

    def _quality_targets_at_most(
        self,
        state,
        actions,
        maximum,
        *,
        minimum=1,
        targeted_only=False,
        broad_only=False,
        preserve_fractal=False,
    ):
        for action in self._filter_mutation(actions, ROLL_QUALITY):
            banner = self._banner(state, action.banner_role)
            operation = self._operation(action)
            is_broad = TARGET_ALL_COLOR in operation.targets
            if targeted_only and is_broad:
                continue
            if broad_only and not is_broad:
                continue
            indices = self._target_indices(banner, operation)
            if preserve_fractal and self._active_triple_fractal(banner):
                continue
            if indices and all(minimum <= banner.emblems[index].quality_tier <= maximum for index in indices):
                yield action

    def _allow_balanced_trade(self, risk: str) -> bool:
        return bool(self.definition.risk_overlays[risk].get("allow_balanced_trade", False))

    def _meets_expected_gain_floor(self, action, metrics, risk) -> bool:
        gain = metrics[action].expected_relative_gain
        threshold = float(self.definition.risk_overlays[risk].get("minimum_expected_delta", 0.0))
        return gain is not None and gain > threshold

    def _nonnegative_mutation_before_late(self, state, actions, metrics, mutation):
        if state.remaining_rolls < 11:
            return
        yield from (
            action
            for action in self._filter_mutation(actions, mutation)
            if metrics[action].minimum_delta >= -1e-9
        )

    def _balanced_trade_candidates(self, state, actions, *, maximum_tier, metrics):
        for action in actions:
            if self._operation(action).mutation != INCREASE_TWO_DECREASE_ONE:
                continue
            banner = self._banner(state, action.banner_role)
            base = self.base_contributions(banner)
            total = sum(base)
            if (
                all(emblem.quality_tier <= maximum_tier for emblem in banner.emblems)
                and total > 0
                and max(base) / total <= 0.45
            ):
                if (
                    self.definition.edition == "rate-agnostic"
                    or (metrics[action].expected_delta or 0.0) > 0.0
                ):
                    yield action


def playbook_snapshot(
    definition: PlaybookDefinition,
    priorities: Sequence[StatPriority],
) -> dict[str, Any]:
    """Return the small immutable policy/evidence identity used by P4/P7 artifacts."""

    priority_rows = [
        {
            "role": row.role,
            "color": row.color,
            "stat_id": row.stat_id,
            "relative_to_best": row.relative_to_best,
            "grade": row.grade,
            "boundary": row.boundary,
            "provenance": row.provenance,
            "coverage": row.coverage,
        }
        for row in priorities
    ]
    payload = {
        "playbook_id": definition.playbook_id,
        "playbook_sha256": definition.semantic_hash,
        "source_evidence_sha256": definition.source_evidence_sha256,
        "priorities": priority_rows,
    }
    payload["snapshot_sha256"] = sha256_json(payload)
    return payload
