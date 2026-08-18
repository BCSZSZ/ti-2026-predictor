from __future__ import annotations

from pathlib import Path

import pytest

from ti_predictor.fantasy.main_roll import (
    MAIN_PERIOD,
    MAIN_ROLL_COUNT,
    MAIN_SLOT_COUNT,
    MainRollState,
    build_main_roll_rules,
    enumerate_mutation_outcomes,
    legal_actions,
    mutation_distribution,
    validate_main_state,
)
from ti_predictor.fantasy.roll import (
    REFRESH,
    BannerState,
    EmblemState,
    GroupRollState,
    RollOffer,
    RollStateError,
    validate_group_state,
)
from ti_predictor.rules import _inspect_fantasy_crafting


@pytest.fixture(scope="module")
def client_roll() -> dict:
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8"))


@pytest.fixture
def main_rules(rules_payload, client_roll):
    return build_main_roll_rules(rules_payload, client_roll)


def _banner(role: str, rules, *, slots: int = MAIN_SLOT_COUNT) -> BannerState:
    colors = rules.colors_for(role)[:slots]
    return BannerState(
        role=role,
        emblems=tuple(
            EmblemState(
                stat_id=rules.stats_for(color)[index % len(rules.stats_for(color))],
                quality_tier=3,
                trait_id=rules.traits[index % len(rules.traits)],
            )
            for index, color in enumerate(colors)
        ),
    )


def _state(rules, *, remaining: int = MAIN_ROLL_COUNT) -> MainRollState:
    return MainRollState(
        banners=tuple(_banner(role, rules) for role in rules.roles),
        offer=RollOffer((14, 12, 31)),
        remaining_rolls=remaining,
    )


def test_main_state_has_its_own_fixed_five_slot_contract(main_rules) -> None:
    state = _state(main_rules)

    validate_main_state(state, main_rules)

    assert state.period == MAIN_PERIOD
    assert state.slot_count == MAIN_SLOT_COUNT
    assert main_rules.main_rolls == MAIN_ROLL_COUNT
    assert [len(banner.emblems) for banner in state.banners] == [5, 5, 5]


def test_group_and_main_states_cannot_cross_period_stacks(main_rules) -> None:
    main = _state(main_rules)
    with pytest.raises(RollStateError, match="Group"):
        validate_group_state(
            GroupRollState(
                banners=main.banners,
                offer=main.offer,
                remaining_rolls=30,
                period="main",
                slot_count=5,
            ),
            main_rules,
        )

    with pytest.raises(RollStateError, match="five"):
        validate_main_state(
            MainRollState(
                banners=tuple(_banner(role, main_rules, slots=3) for role in main_rules.roles),
                offer=main.offer,
                remaining_rolls=30,
            ),
            main_rules,
        )


def test_main_operation_24_selects_exactly_two_increases_and_one_distinct_decrease(main_rules) -> None:
    banner = _banner("core", main_rules)

    outcomes = enumerate_mutation_outcomes(banner, 24, main_rules)
    distribution = mutation_distribution(banner, 24, main_rules, "client-weight-primary-v1")

    assert len(outcomes) == 30
    assert {item.banner for item in distribution} == set(outcomes)
    assert all(item.probability == pytest.approx(1 / 30) for item in distribution)
    for outcome in outcomes:
        deltas = [
            after.quality_tier - before.quality_tier
            for before, after in zip(banner.emblems, outcome.emblems, strict=True)
        ]
        assert deltas.count(1) == 2
        assert deltas.count(-1) == 1
        assert deltas.count(0) == 2


def test_main_operation_24_merges_clamped_duplicate_targets_without_losing_probability(
    main_rules,
) -> None:
    source = _banner("core", main_rules)
    banner = BannerState(
        source.role,
        tuple(EmblemState(emblem.stat_id, 5, emblem.trait_id) for emblem in source.emblems),
    )

    distribution = mutation_distribution(banner, 24, main_rules, "client-weight-primary-v1")

    assert len(distribution) == 5
    assert sum(item.probability for item in distribution) == pytest.approx(1.0)
    assert all(item.probability == pytest.approx(0.2) for item in distribution)


def test_main_legal_actions_use_five_slot_rules_and_zero_rolls_finish(main_rules) -> None:
    state = _state(main_rules)

    actions = legal_actions(state, main_rules)

    assert actions[0] == REFRESH
    assert any(getattr(action, "banner_role", None) == "core" for action in actions)
    assert legal_actions(_state(main_rules, remaining=0), main_rules) == ()


def test_main_terminal_state_does_not_require_disappeared_offer(main_rules) -> None:
    source = _state(main_rules)
    terminal = MainRollState(source.banners, None, 0)

    validate_main_state(terminal, main_rules)

    assert legal_actions(terminal, main_rules) == ()


def test_active_main_state_still_requires_three_visible_options(main_rules) -> None:
    source = _state(main_rules)

    with pytest.raises(RollStateError, match="three visible options"):
        validate_main_state(MainRollState(source.banners, None, 1), main_rules)
