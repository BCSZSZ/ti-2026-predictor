from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_roll import MainRollState, build_main_roll_rules
from ti_predictor.fantasy.main_roll_research_contract import load_main_roll_research_manifest
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import (
    StopRollAction,
    TerminalEvaluation,
)
from ti_predictor.fantasy.main_roll_research_strategies import (
    BoundedConfigurationTargetGenerator,
    GreedyImmediatePolicy,
    HorizonHybridPolicy,
    TargetSeekingPolicy,
    weighted_lower_tail_cvar,
)
from ti_predictor.fantasy.roll import BannerState, EmblemState, RollOffer
from ti_predictor.rules import _inspect_fantasy_crafting


class _QualityTerminal:
    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        value = float(sum(emblem.quality_tier for banner in banners for emblem in banner.emblems))
        return TerminalEvaluation(
            np.asarray([value - 2.0, value, value + 2.0]),
            (101, 102, 103),
        )


class _TraitShapeTerminal:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        value = 100.0
        support = next(banner for banner in banners if banner.role == "support")
        traits = tuple(emblem.trait_id for emblem in support.emblems)
        if self.mode == "friendly":
            value += 50.0 if traits.count("friendly") >= 3 else 0.0
        else:
            desired = ("friendly", "benevolent", "friendly", "benevolent", "friendly")
            value += sum(20.0 for actual, target in zip(traits, desired, strict=True) if actual == target)
        return TerminalEvaluation(np.asarray([value, value + 1.0]), (101, 102, 103))


@pytest.fixture(scope="module")
def manifest():
    path = Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-simulator-v1.json"
    return load_main_roll_research_manifest(path)


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def _state(rules, *, remaining: int = 3, quality: int = 3) -> MainRollState:
    banners = tuple(
        BannerState(
            role,
            tuple(
                EmblemState(rules.stats_for(color)[0], quality, "fractal")
                for color in rules.colors_for(role)[:5]
            ),
        )
        for role in rules.roles
    )
    return MainRollState(banners, RollOffer((23, 14, 31)), remaining)


def _provider(rules, manifest):
    return MainRollProbabilityProvider(
        rules,
        manifest.probability_model("client-weight-primary-v1"),
    )


def test_weighted_cvar_handles_fractional_probability_boundary() -> None:
    values = np.asarray([0.0, 10.0, 20.0])
    weights = np.asarray([0.05, 0.10, 0.85])

    assert weighted_lower_tail_cvar(values, weights, 0.1) == pytest.approx(5.0)


def test_greedy_policy_selects_positive_immediate_quality_gain(main_rules, manifest) -> None:
    policy = GreedyImmediatePolicy(
        main_rules,
        _QualityTerminal(),
        _provider(main_rules, manifest),
        manifest.strategies.greedy,
    )

    decision = policy.choose_action(_state(main_rules))

    assert decision.diagnostics["mode"] == "greedy-immediate"
    assert getattr(decision.action, "operation_id", None) == 23


def test_greedy_policy_stops_on_last_roll_without_immediate_gain(main_rules, manifest) -> None:
    state = _state(main_rules, remaining=1, quality=5)
    state = MainRollState(state.banners, RollOffer((14, 31, 17)), 1)
    policy = GreedyImmediatePolicy(
        main_rules,
        _QualityTerminal(),
        _provider(main_rules, manifest),
        manifest.strategies.greedy,
    )

    decision = policy.choose_action(state)

    assert isinstance(decision.action, StopRollAction)


def test_target_generator_has_no_context_free_best_trait_shape(main_rules, manifest) -> None:
    state = _state(main_rules)
    friendly = BoundedConfigurationTargetGenerator(
        main_rules,
        _TraitShapeTerminal("friendly"),
        manifest.strategies.target,
    ).generate(state)
    positional = BoundedConfigurationTargetGenerator(
        main_rules,
        _TraitShapeTerminal("positional"),
        manifest.strategies.target,
    ).generate(state)

    assert friendly
    assert positional
    assert friendly[0].traits != positional[0].traits
    assert friendly[0].traits.count("friendly") >= 3
    assert positional[0].traits == (
        "friendly",
        "benevolent",
        "friendly",
        "benevolent",
        "friendly",
    )


def test_target_and_hybrid_policies_are_deterministic(main_rules, manifest) -> None:
    provider = _provider(main_rules, manifest)
    terminal = _QualityTerminal()
    greedy = GreedyImmediatePolicy(
        main_rules,
        terminal,
        provider,
        manifest.strategies.greedy,
    )
    target = TargetSeekingPolicy(
        main_rules,
        terminal,
        provider,
        manifest.strategies.target,
        manifest.strategies.greedy,
    )
    hybrid = HorizonHybridPolicy(greedy, target, manifest.strategies.hybrid)
    state = _state(main_rules)

    first_target = target.choose_action(state)
    second_target = target.choose_action(state)
    first_hybrid = hybrid.choose_action(state)
    second_hybrid = hybrid.choose_action(state)

    assert first_target == second_target
    assert first_hybrid == second_hybrid
    assert first_hybrid.diagnostics["mode"] in {"hybrid-target", "hybrid-greedy"}
