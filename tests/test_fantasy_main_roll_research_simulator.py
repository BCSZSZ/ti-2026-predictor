from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_advice_strategy import load_main_advice_strategy_catalog
from ti_predictor.fantasy.main_current_advisor import MainCurrentAdvisorContext
from ti_predictor.fantasy.main_roll import MainRollState, build_main_roll_rules, legal_actions
from ti_predictor.fantasy.main_roll_research_contract import load_main_roll_research_manifest
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.main_roll_research_simulator import (
    STOP,
    FrozenMainTerminalAdapter,
    MainRollResearchSimulator,
    PolicyDecision,
    TerminalEvaluation,
    state_from_payload,
    state_payload,
)
from ti_predictor.fantasy.roll import BannerState, EmblemState, RefreshRollAction, RollOffer
from ti_predictor.fantasy.valuation import TeamOutcomeMatrix
from ti_predictor.rules import _inspect_fantasy_crafting


class _ScalarTerminal:
    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        value = float(sum(emblem.quality_tier for banner in banners for emblem in banner.emblems))
        return TerminalEvaluation(
            outcomes=np.asarray([value - 1.0, value, value + 1.0]),
            selected_team_ids=(101, 102, 103),
        )


class _FrozenBannerTerminal:
    team_ids = tuple(range(101, 109))

    def banner(self, banner: BannerState) -> TeamOutcomeMatrix:
        role_offset = {"core": 100.0, "mid": 200.0, "support": 300.0}[banner.role]
        banner_value = sum(emblem.quality_tier for emblem in banner.emblems)
        outcomes = np.asarray(
            [
                [role_offset + banner_value + team_index + scenario for scenario in range(3)]
                for team_index in range(8)
            ],
            dtype=float,
        )
        return TeamOutcomeMatrix(
            kind="main-research-test",
            item_id=f"{banner.role}:{banner_value}",
            role=banner.role,
            scenario_sha256="b" * 64,
            team_ids=self.team_ids,
            outcomes=outcomes,
        )


class _FirstApplyThenStop:
    policy_id = "test-first-apply-then-stop"

    def choose_action(self, state: MainRollState) -> PolicyDecision:
        if state.remaining_rolls < 2:
            return PolicyDecision(STOP, "test stop")
        action = next(
            action for action in legal_actions(state, self.rules) if not isinstance(action, RefreshRollAction)
        )
        return PolicyDecision(action, "test apply")

    def __init__(self, rules) -> None:
        self.rules = rules


@pytest.fixture(scope="module")
def research_manifest():
    path = Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-simulator-v1.json"
    return load_main_roll_research_manifest(path)


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    client_roll = _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8"))
    return build_main_roll_rules(rules_payload, client_roll)


def _state(rules, *, remaining: int = 2) -> MainRollState:
    banners = []
    for role in rules.roles:
        banners.append(
            BannerState(
                role,
                tuple(
                    EmblemState(rules.stats_for(color)[0], 3, rules.traits[0])
                    for color in rules.colors_for(role)[:5]
                ),
            )
        )
    return MainRollState(tuple(banners), RollOffer((23, 24, 31)), remaining)


def test_state_payload_round_trip_is_exact(main_rules) -> None:
    state = _state(main_rules)

    assert state_from_payload(state_payload(state), main_rules) == state


def test_forward_episode_is_deterministic_and_stop_preserves_unspent_roll(
    main_rules,
    research_manifest,
) -> None:
    provider = MainRollProbabilityProvider(
        main_rules,
        research_manifest.probability_model("client-weight-primary-v1"),
    )
    simulator = MainRollResearchSimulator(
        research_manifest,
        main_rules,
        _ScalarTerminal(),
        source_version="test-source",
    )
    policy = _FirstApplyThenStop(main_rules)

    first = simulator.run_episode(_state(main_rules), policy, provider, episode_seed=7)
    second = simulator.run_episode(_state(main_rules), policy, provider, episode_seed=7)

    assert first.trace == second.trace
    assert first.trace["spent_rolls"] == 1
    assert first.trace["unspent_rolls"] == 1
    assert first.trace["stop_reason"] == "policy-stop"
    assert first.trace["steps"][-1]["decision"]["action_id"] == "stop"
    assert first.trace["research_only"] is True
    assert first.trace["web_integration"] is False


def test_simulator_rejects_probability_provider_from_another_rule_object(
    main_rules,
    research_manifest,
) -> None:
    provider = MainRollProbabilityProvider(
        main_rules,
        research_manifest.probability_model("client-weight-primary-v1"),
    )
    simulator = MainRollResearchSimulator(
        research_manifest,
        main_rules,
        _ScalarTerminal(),
        source_version="test-source",
    )
    copied_rules = build_main_roll_rules(
        json.loads(
            (Path(__file__).resolve().parents[1] / "config/rules/ti2026.json").read_text(encoding="utf-8")
        ),
        _inspect_fantasy_crafting(
            (Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata").read_text(encoding="utf-8")
        ),
    )
    foreign_provider = MainRollProbabilityProvider(copied_rules, provider.specification)

    with pytest.raises(ValueError, match="different Rule set"):
        simulator.run_episode(
            _state(main_rules),
            _FirstApplyThenStop(main_rules),
            foreign_provider,
            episode_seed=7,
        )


def test_frozen_main_terminal_adapter_matches_all_three_roles(main_rules, research_manifest) -> None:
    terminal = _FrozenBannerTerminal()
    context = MainCurrentAdvisorContext(
        as_of=research_manifest.as_of,
        roll_rules=main_rules,
        terminal=terminal,
        scenario_count=3,
        team_names={team_id: f"Team {team_id}" for team_id in terminal.team_ids},
        strategy_catalog=load_main_advice_strategy_catalog(
            Path(__file__).resolve().parents[1] / "config/models/fantasy-main-advice-strategies-v1.json"
        ),
    )
    adapter = FrozenMainTerminalAdapter(context)
    state = _state(main_rules)

    first = adapter.evaluate(state.banners)
    second = adapter.evaluate(state.banners)

    assert first is second
    assert first.selected_team_ids == (108, 108, 108)
    assert len(first.outcomes) == 3
