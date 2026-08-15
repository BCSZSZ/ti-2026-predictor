from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_roll import MainRollState, build_main_roll_rules
from ti_predictor.fantasy.main_roll_bounded_challenger_contract import (
    load_main_roll_bounded_challenger_manifest,
)
from ti_predictor.fantasy.main_roll_bounded_challenger_strategies import (
    GreedyLocalConfigurationTieBreakPolicy,
    GreedySafeBandPolicy,
    GreedySelectiveTwoStepPolicy,
    local_configuration_score,
)
from ti_predictor.fantasy.main_roll_research_contract import (
    load_main_roll_research_manifest,
)
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import TerminalEvaluation
from ti_predictor.fantasy.roll import BannerState, EmblemState, RollOffer
from ti_predictor.rules import _inspect_fantasy_crafting


class _OffsetQualityTerminal:
    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        quality = float(sum(emblem.quality_tier for banner in banners for emblem in banner.emblems))
        value = 1000.0 + quality
        return TerminalEvaluation(
            np.asarray([value - 2.0, value, value + 2.0]),
            (101, 102, 103),
        )


@pytest.fixture(scope="module")
def manifests():
    root = Path(__file__).resolve().parents[1]
    return (
        load_main_roll_research_manifest(root / "config/research/fantasy-main-roll-simulator-v1.json"),
        load_main_roll_bounded_challenger_manifest(
            root / "config/research/fantasy-main-roll-bounded-challengers-v1.json"
        ),
    )


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def _state(rules, *, remaining: int = 5) -> MainRollState:
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


def _provider(rules, base_manifest):
    return MainRollProbabilityProvider(
        rules,
        base_manifest.probability_model("client-weight-primary-v1"),
    )


def test_local_configuration_score_rewards_conditional_progress(main_rules) -> None:
    state = _state(main_rules)
    low = local_configuration_score(state.banners)
    improved_banner = BannerState(
        "core",
        tuple(
            EmblemState(emblem.stat_id, quality, "fractal")
            for emblem, quality in zip(
                state.banners[0].emblems,
                (1, 2, 3, 4, 5),
                strict=True,
            )
        ),
    )
    improved = (improved_banner, *state.banners[1:])

    assert local_configuration_score(improved) > low


def test_bounded_policies_are_deterministic_and_keep_frozen_ids(
    main_rules,
    manifests,
) -> None:
    base, bounded = manifests
    terminal = _OffsetQualityTerminal()
    state = _state(main_rules)

    def policies():
        provider = _provider(main_rules, base)
        return (
            GreedySafeBandPolicy(
                main_rules,
                terminal,
                provider,
                bounded.strategies.safe_band,
                bounded.strategies.baseline,
            ),
            GreedyLocalConfigurationTieBreakPolicy(
                main_rules,
                terminal,
                provider,
                bounded.strategies.local_tie,
                bounded.strategies.baseline,
            ),
            GreedySelectiveTwoStepPolicy(
                main_rules,
                terminal,
                provider,
                bounded.strategies.selective_two_step.model_copy(update={"ambiguity_fraction": 0.01}),
                bounded.strategies.baseline,
            ),
        )

    first = tuple(policy.choose_action(state) for policy in policies())
    second = tuple(policy.choose_action(state) for policy in policies())

    assert first == second
    assert tuple(policy.policy_id for policy in policies()) == bounded.strategies.candidate_policy_ids
    assert first[0].diagnostics["mode"] == "greedy-safe-band"
    assert first[1].diagnostics["mode"].startswith("greedy-local")
    assert first[2].diagnostics["mode"] == "greedy-selective-two-step"


def test_two_step_policy_obeys_per_episode_trigger_cap(main_rules, manifests) -> None:
    base, bounded = manifests
    provider = _provider(main_rules, base)
    specification = bounded.strategies.selective_two_step.model_copy(
        update={"ambiguity_fraction": 0.01, "max_triggers_per_episode": 2}
    )
    policy = GreedySelectiveTwoStepPolicy(
        main_rules,
        _OffsetQualityTerminal(),
        provider,
        specification,
        bounded.strategies.baseline,
    )
    state = _state(main_rules)

    modes = [policy.choose_action(state).diagnostics["mode"] for _ in range(4)]

    assert modes[:2] == ["greedy-selective-two-step"] * 2
    assert modes[2:] == ["selective-two-step-budgeted-greedy"] * 2
