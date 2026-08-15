from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_advice_strategy import (
    G_LITE_MAIN_STRATEGY_ID,
    GREEDY_MAIN_STRATEGY_ID,
    load_main_advice_strategy_catalog,
)
from ti_predictor.fantasy.main_current_advisor import (
    MainCurrentAdvisorContext,
    analyze_main_current_screen,
)
from ti_predictor.fantasy.main_roll import MainRollState, build_main_roll_rules
from ti_predictor.fantasy.roll import BannerState, EmblemState, RollOffer
from ti_predictor.fantasy.valuation import TeamOutcomeMatrix
from ti_predictor.rules import _inspect_fantasy_crafting


class _FakeMainTerminal:
    team_ids = tuple(range(101, 109))
    scenario_count = 4

    def banner(self, banner: BannerState) -> TeamOutcomeMatrix:
        role_offset = {"core": 100.0, "mid": 200.0, "support": 300.0}[banner.role]
        banner_value = sum(
            emblem.quality_tier * 10.0 + len(emblem.stat_id) + len(emblem.trait_id)
            for emblem in banner.emblems
        )
        outcomes = np.asarray(
            [
                [role_offset + banner_value + team_index + scenario for scenario in range(4)]
                for team_index in range(8)
            ],
            dtype=float,
        )
        return TeamOutcomeMatrix(
            kind="main-test-banner",
            item_id=f"{banner.role}:{banner_value}",
            role=banner.role,
            scenario_sha256="a" * 64,
            team_ids=self.team_ids,
            outcomes=outcomes,
        )


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    client_roll = _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8"))
    return build_main_roll_rules(rules_payload, client_roll)


def _state(rules) -> MainRollState:
    banners = []
    for role in rules.roles:
        emblems = []
        for index, color in enumerate(rules.colors_for(role)[:5]):
            emblems.append(
                EmblemState(
                    stat_id=rules.stats_for(color)[0],
                    quality_tier=3,
                    trait_id=rules.traits[index % len(rules.traits)],
                )
            )
        banners.append(BannerState(role=role, emblems=tuple(emblems)))
    return MainRollState(
        banners=tuple(banners),
        offer=RollOffer((23, 24, 31)),
        remaining_rolls=30,
    )


def _context(main_rules) -> MainCurrentAdvisorContext:
    terminal = _FakeMainTerminal()
    root = Path(__file__).resolve().parents[1]
    return MainCurrentAdvisorContext(
        as_of="2026-08-13T13:23:17Z",
        roll_rules=main_rules,
        terminal=terminal,
        scenario_count=terminal.scenario_count,
        team_names={team_id: f"Main Team {team_id}" for team_id in terminal.team_ids},
        strategy_catalog=load_main_advice_strategy_catalog(
            root / "config/models/fantasy-main-advice-strategies-v1.json"
        ),
    )


def test_main_current_screen_evaluates_all_five_slot_mutations(main_rules) -> None:
    payload = analyze_main_current_screen(_context(main_rules), _state(main_rules))

    assert payload["period"] == "main"
    assert payload["analysis_type"] == "main_current_screen_exact_one_step_no_future_offer_value"
    assert payload["strategy"]["strategy_id"] == GREEDY_MAIN_STRATEGY_ID
    assert len(payload["current"]["selected_team_ids"]) == 3
    operation_24_rows = [row for row in payload["primary_action_values"] if ":24" in row["action_id"]]
    assert len(operation_24_rows) == 3
    assert {row["support_count"] for row in operation_24_rows} == {30}
    assert len(payload["preferred_by_model"]) == 3


def test_main_current_screen_is_deterministic(main_rules) -> None:
    first = analyze_main_current_screen(_context(main_rules), _state(main_rules))
    second = analyze_main_current_screen(_context(main_rules), _state(main_rules))

    assert first == second
    assert first["analysis_sha256"] == second["analysis_sha256"]


def test_main_current_screen_exposes_deterministic_opt_in_g_lite(main_rules) -> None:
    context = _context(main_rules)
    state = _state(main_rules)

    first = analyze_main_current_screen(
        context,
        state,
        strategy_id=G_LITE_MAIN_STRATEGY_ID,
    )
    second = analyze_main_current_screen(
        context,
        state,
        strategy_id=G_LITE_MAIN_STRATEGY_ID,
    )

    assert first == second
    assert first["analysis_type"] == ("main_current_screen_selective_two_step_sampled_future_offer_value")
    assert first["strategy"]["strategy_id"] == G_LITE_MAIN_STRATEGY_ID
    assert first["strategy"]["evidence_status"] == ("development-positive-user-opt-in-not-confirmed")


def test_main_current_screen_rejects_group_sized_banner(main_rules) -> None:
    state = _state(main_rules)
    broken = MainRollState(
        banners=(
            BannerState(role="core", emblems=state.banners[0].emblems[:3]),
            *state.banners[1:],
        ),
        offer=state.offer,
        remaining_rolls=state.remaining_rolls,
    )

    with pytest.raises(ValueError, match="five"):
        analyze_main_current_screen(_context(main_rules), broken)
