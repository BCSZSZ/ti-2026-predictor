from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_roll import MainRollState, build_main_roll_rules
from ti_predictor.fantasy.main_roll_research_contract import load_main_roll_research_manifest
from ti_predictor.fantasy.main_roll_research_probability import (
    MainRollProbabilityProvider,
    OfferOutcome,
)
from ti_predictor.fantasy.main_roll_research_simulator import TerminalEvaluation
from ti_predictor.fantasy.main_roll_research_strategies import GreedyImmediatePolicy
from ti_predictor.fantasy.main_roll_research_validation import (
    MainResearchValidationError,
    exact_policy_terminal_mean,
)
from ti_predictor.fantasy.roll import BannerState, EmblemState, RollOffer
from ti_predictor.rules import _inspect_fantasy_crafting


class _QualityTerminal:
    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        value = float(sum(emblem.quality_tier for banner in banners for emblem in banner.emblems))
        return TerminalEvaluation(np.asarray([value]), (101, 102, 103))


class _TwoOfferProvider(MainRollProbabilityProvider):
    def __init__(self, rules, specification) -> None:
        super().__init__(rules, specification)
        self._offers = (
            OfferOutcome(RollOffer((23, 14, 31)), 0.5),
            OfferOutcome(RollOffer((24, 14, 31)), 0.5),
        )

    def offer_distribution(self) -> tuple[OfferOutcome, ...]:
        return self._offers

    def draw_offer(self, rng: random.Random) -> RollOffer:
        return self._offers[0].offer if rng.random() < 0.5 else self._offers[1].offer


@pytest.fixture(scope="module")
def manifest():
    return load_main_roll_research_manifest(
        Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-simulator-v1.json"
    )


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def _state(rules, remaining: int) -> MainRollState:
    banners = tuple(
        BannerState(
            role,
            tuple(
                EmblemState(rules.stats_for(color)[0], 3, "fractal") for color in rules.colors_for(role)[:5]
            ),
        )
        for role in rules.roles
    )
    return MainRollState(banners, RollOffer((23, 14, 31)), remaining)


@pytest.mark.parametrize("horizon", [1, 2, 3])
def test_exact_short_horizon_integrates_non_fixed_future_offers(
    main_rules,
    manifest,
    horizon,
) -> None:
    terminal = _QualityTerminal()
    provider = _TwoOfferProvider(
        main_rules,
        manifest.probability_model("client-weight-primary-v1"),
    )
    policy = GreedyImmediatePolicy(
        main_rules,
        terminal,
        provider,
        manifest.strategies.greedy,
    )

    result = exact_policy_terminal_mean(
        _state(main_rules, horizon),
        policy,
        provider,
        terminal,
        main_rules,
        horizon=horizon,
        maximum_evaluated_states=50_000,
    )

    assert result.expected_terminal_mean >= 46.0
    assert result.evaluated_states >= horizon


def test_exact_short_horizon_fails_instead_of_truncating_state_space(main_rules, manifest) -> None:
    terminal = _QualityTerminal()
    provider = _TwoOfferProvider(
        main_rules,
        manifest.probability_model("client-weight-primary-v1"),
    )
    policy = GreedyImmediatePolicy(
        main_rules,
        terminal,
        provider,
        manifest.strategies.greedy,
    )

    with pytest.raises(MainResearchValidationError, match="no branches were truncated"):
        exact_policy_terminal_mean(
            _state(main_rules, 3),
            policy,
            provider,
            terminal,
            main_rules,
            horizon=3,
            maximum_evaluated_states=1,
        )
