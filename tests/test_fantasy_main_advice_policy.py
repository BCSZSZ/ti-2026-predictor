from __future__ import annotations

import hashlib
import random
from pathlib import Path

import pytest

from ti_predictor.fantasy.main_advice_policy import (
    MainImmediateActionValue,
    choose_main_strategy_action,
    main_state_sha256,
    sample_g_lite_transition,
)
from ti_predictor.fantasy.main_advice_strategy import (
    G_LITE_MAIN_STRATEGY_ID,
    GREEDY_MAIN_STRATEGY_ID,
    load_main_advice_strategy_catalog,
)
from ti_predictor.fantasy.main_roll import (
    MainRollState,
    apply_realized_transition,
    build_main_roll_rules,
)
from ti_predictor.fantasy.main_roll_research_contract import load_main_roll_research_manifest
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import state_sha256
from ti_predictor.fantasy.roll import ApplyRollAction, BannerState, EmblemState, RollOffer
from ti_predictor.rules import _inspect_fantasy_crafting


@pytest.fixture(scope="module")
def catalog():
    root = Path(__file__).resolve().parents[1]
    return load_main_advice_strategy_catalog(root / "config/models/fantasy-main-advice-strategies-v1.json")


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def _state(rules) -> MainRollState:
    banners = tuple(
        BannerState(
            role,
            tuple(
                EmblemState(rules.stats_for(color)[0], 3, "fractal") for color in rules.colors_for(role)[:5]
            ),
        )
        for role in rules.roles
    )
    return MainRollState(banners, RollOffer((23, 14, 31)), 30)


def _rows():
    return (
        MainImmediateActionValue(ApplyRollAction("core", 23), 1001.0, 901.0, 1.0, -1.0),
        MainImmediateActionValue(ApplyRollAction("mid", 23), 1000.6, 902.0, 0.6, -2.0),
    )


def test_g_is_default_and_g_lite_obeys_trigger_budget(catalog) -> None:
    state = MainRollState((), RollOffer((23, 14, 31)), 30)
    continuation = lambda action, index: (  # noqa: E731
        (1100.0, 900.0) if getattr(action, "banner_role", "") == "mid" else (1000.0, 900.0)
    )

    greedy = choose_main_strategy_action(
        catalog,
        GREEDY_MAIN_STRATEGY_ID,
        state,
        1000.0,
        _rows(),
        mean_retention_epsilon=0.0,
        g_lite_triggers_used=0,
        continuation_value=continuation,
    )
    g_lite = choose_main_strategy_action(
        catalog,
        G_LITE_MAIN_STRATEGY_ID,
        state,
        1000.0,
        _rows(),
        mean_retention_epsilon=0.0,
        g_lite_triggers_used=0,
        continuation_value=continuation,
    )
    capped = choose_main_strategy_action(
        catalog,
        G_LITE_MAIN_STRATEGY_ID,
        state,
        1000.0,
        _rows(),
        mean_retention_epsilon=0.0,
        g_lite_triggers_used=4,
        continuation_value=continuation,
    )

    assert greedy.action == ApplyRollAction("core", 23)
    assert g_lite.action == ApplyRollAction("mid", 23)
    assert g_lite.triggered is True
    assert capped.action == greedy.action
    assert capped.triggered is False


def test_production_g_lite_sampling_matches_research_v1(main_rules) -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = load_main_roll_research_manifest(root / "config/research/fantasy-main-roll-simulator-v1.json")
    provider = MainRollProbabilityProvider(
        main_rules,
        manifest.probability_model("client-weight-primary-v1"),
    )
    state = _state(main_rules)
    action = ApplyRollAction("core", 23)
    sample_index = 2
    seed = 2026081504

    assert main_state_sha256(state) == state_sha256(state)

    def rng(kind: str) -> random.Random:
        digest = hashlib.sha256(
            f"main-bounded-two-step:{seed}:{state_sha256(state)}:{sample_index}:{kind}".encode()
        ).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    replacement = provider.draw_offer(rng("replacement-offer"))
    banner = next(item for item in state.banners if item.role == action.banner_role)
    realized = provider.sample_mutation(banner, action.operation_id, rng("mutation-uniform"))
    expected = apply_realized_transition(state, action, realized, replacement, main_rules)

    assert (
        sample_g_lite_transition(
            state,
            action,
            sample_index,
            rules=main_rules,
            model_id="client-weight-primary-v1",
            decision_seed=seed,
        )
        == expected
    )
