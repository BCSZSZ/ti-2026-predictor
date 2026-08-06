from __future__ import annotations

import copy
import random
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ti_predictor.fantasy.roll import (
    REFRESH,
    ApplyRollAction,
    BannerState,
    EmblemState,
    GroupRollState,
    RefreshRollAction,
    RollActionError,
    RollOffer,
    RollRuleError,
    RollStateError,
    apply_realized_transition,
    build_group_roll_rules,
    draw_roll_offer,
    enumerate_mutation_outcomes,
    legal_actions,
    mutation_distribution,
    operation_applies,
    rank_rate_agnostic_actions,
    refresh_transition,
    sample_apply_transition,
    sample_mutation,
    sample_refresh_transition,
    validate_banner,
    validate_group_state,
)
from ti_predictor.rules import _inspect_fantasy_crafting

MODEL_IDS = (
    "client-weight-primary-v1",
    "flattened-weights-v1",
    "sharpened-weights-v1",
)


@pytest.fixture(scope="module")
def client_roll() -> dict:
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8"))


@pytest.fixture
def roll_rules(rules_payload, client_roll):
    return build_group_roll_rules(rules_payload, client_roll)


def _banner(
    role: str,
    rules,
    *,
    qualities: tuple[int, int, int] = (1, 2, 3),
    trait_offsets: tuple[int, int, int] = (0, 1, 2),
    stat_offsets: tuple[int, int, int] = (0, 1, 2),
) -> BannerState:
    colors = rules.colors_for(role)[:3]
    return BannerState(
        role=role,
        emblems=tuple(
            EmblemState(
                stat_id=rules.stats_for(color)[stat_offsets[index] % len(rules.stats_for(color))],
                quality_tier=qualities[index],
                trait_id=rules.traits[trait_offsets[index] % len(rules.traits)],
            )
            for index, color in enumerate(colors)
        ),
    )


def _state(rules, offer: tuple[int, int, int] = (9, 23, 28), remaining: int = 40) -> GroupRollState:
    return GroupRollState(
        banners=tuple(_banner(role, rules) for role in rules.group_roles),
        offer=RollOffer(offer),
        remaining_rolls=remaining,
    )


def test_rule_set_round_trips_current_client_contract(roll_rules) -> None:
    assert len(roll_rules.operations) == 28
    assert len(roll_rules.offered_operations) == 20
    assert tuple(item.operation_id for item in roll_rules.offered_operations) == (
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
    )
    assert sum(item.roll_weight for item in roll_rules.offered_operations) == 168
    assert roll_rules.group_rolls == 40
    assert roll_rules.offer_size == 3
    with pytest.raises(RollRuleError, match="zero-weight"):
        roll_rules.operation(1)


def test_state_is_immutable_and_main_fails_closed(roll_rules) -> None:
    state = _state(roll_rules)
    validate_group_state(state, roll_rules)
    with pytest.raises(FrozenInstanceError):
        state.remaining_rolls = 39  # type: ignore[misc]
    main = GroupRollState(
        banners=state.banners,
        offer=state.offer,
        remaining_rolls=30,
        period="main",
        slot_count=5,
    )
    with pytest.raises(RollStateError, match="Main"):
        validate_group_state(main, roll_rules)


def test_offers_are_complete_unique_positive_and_known(roll_rules) -> None:
    with pytest.raises(RollStateError, match="exactly three"):
        RollOffer((9, 10))
    with pytest.raises(RollStateError, match="unique"):
        RollOffer((9, 9, 10))
    for offer in (RollOffer((1, 9, 10)), RollOffer((9, 10, 999))):
        state = GroupRollState(
            banners=tuple(_banner(role, roll_rules) for role in roll_rules.group_roles),
            offer=offer,
            remaining_rolls=40,
        )
        with pytest.raises(RollStateError):
            validate_group_state(state, roll_rules)


def test_legal_actions_filter_operations_by_banner_color(roll_rules) -> None:
    state = _state(roll_rules, offer=(9, 12, 15))
    actions = legal_actions(state, roll_rules)
    assert actions[0] == REFRESH
    applies = {(item.banner_role, item.operation_id) for item in actions if isinstance(item, ApplyRollAction)}
    assert applies == {
        ("core", 9),
        ("core", 15),
        ("mid", 9),
        ("mid", 12),
        ("mid", 15),
        ("support", 12),
        ("support", 15),
    }
    assert legal_actions(_state(roll_rules, remaining=0), roll_rules) == ()


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    qualities=st.lists(st.integers(min_value=1, max_value=5), min_size=9, max_size=9),
    traits=st.lists(st.integers(min_value=0, max_value=4), min_size=9, max_size=9),
    stats=st.lists(st.integers(min_value=0, max_value=5), min_size=9, max_size=9),
)
def test_every_positive_operation_has_legal_model_invariant_support(
    roll_rules, qualities: list[int], traits: list[int], stats: list[int]
) -> None:
    banners = []
    for role_index, role in enumerate(roll_rules.group_roles):
        start = role_index * 3
        banners.append(
            _banner(
                role,
                roll_rules,
                qualities=tuple(qualities[start : start + 3]),
                trait_offsets=tuple(traits[start : start + 3]),
                stat_offsets=tuple(stats[start : start + 3]),
            )
        )
    covered: set[tuple[int, str]] = set()
    for operation in roll_rules.offered_operations:
        for banner in banners:
            support = enumerate_mutation_outcomes(banner, operation.operation_id, roll_rules)
            if not operation_applies(banner, operation, roll_rules):
                assert support == ()
                continue
            covered.add((operation.operation_id, banner.role))
            assert support
            assert len(support) == len(set(support))
            for outcome in support:
                validate_banner(outcome, roll_rules)
                assert outcome.role == banner.role
                assert len(outcome.emblems) == 3
            for model_id in MODEL_IDS:
                distribution = mutation_distribution(banner, operation.operation_id, roll_rules, model_id)
                assert {item.banner for item in distribution} == set(support)
                assert sum(item.probability for item in distribution) == pytest.approx(1.0)
                assert all(item.probability > 0 for item in distribution)
                sampled = sample_mutation(
                    banner,
                    operation.operation_id,
                    roll_rules,
                    model_id,
                    random.Random(42),
                )
                assert sampled in support
    for operation in roll_rules.offered_operations:
        assert any(operation.operation_id == operation_id for operation_id, _ in covered)


def test_one_first_and_last_color_have_distinct_target_support(roll_rules) -> None:
    core = _banner("core", roll_rules)
    one = enumerate_mutation_outcomes(core, 25, roll_rules)
    first = enumerate_mutation_outcomes(core, 26, roll_rules)
    last = enumerate_mutation_outcomes(core, 27, roll_rules)
    assert len(one) == 9
    assert len(first) == 5
    assert len(last) == 5
    assert all(outcome.emblems[2] == core.emblems[2] for outcome in first)
    assert all(outcome.emblems[0] == core.emblems[0] for outcome in last)


def test_apply_and_refresh_consume_one_and_replace_all_options(roll_rules) -> None:
    state = _state(roll_rules, offer=(9, 23, 28), remaining=17)
    action = ApplyRollAction("core", 23)
    realized = enumerate_mutation_outcomes(state.banners[0], 23, roll_rules)[-1]
    replacement = RollOffer((10, 13, 16))
    applied = apply_realized_transition(state, action, realized, replacement, roll_rules)
    assert applied.remaining_rolls == 16
    assert applied.offer == replacement
    assert applied.banners[0] == realized
    assert applied.banners[1:] == state.banners[1:]
    refreshed = refresh_transition(state, replacement, roll_rules)
    assert refreshed.remaining_rolls == 16
    assert refreshed.offer == replacement
    assert refreshed.banners == state.banners

    with pytest.raises(RollActionError, match="not legal"):
        apply_realized_transition(
            state,
            ApplyRollAction("support", 9),
            state.banners[2],
            replacement,
            roll_rules,
        )
    with pytest.raises(RollActionError, match="outside"):
        apply_realized_transition(state, action, state.banners[1], replacement, roll_rules)
    with pytest.raises(RollActionError, match="no Roll"):
        sample_refresh_transition(
            _state(roll_rules, remaining=0),
            roll_rules,
            "client-weight-primary-v1",
            random.Random(1),
        )


@pytest.mark.parametrize("model_id", MODEL_IDS)
def test_fixed_seed_reproduces_offers_and_transitions_without_zero_templates(
    roll_rules, model_id: str
) -> None:
    first_rng = random.Random(20260806)
    second_rng = random.Random(20260806)
    first_offers = [draw_roll_offer(roll_rules, model_id, first_rng) for _ in range(100)]
    second_offers = [draw_roll_offer(roll_rules, model_id, second_rng) for _ in range(100)]
    assert first_offers == second_offers
    assert all(len(set(offer.operation_ids)) == 3 for offer in first_offers)
    assert not (
        {operation_id for offer in first_offers for operation_id in offer.operation_ids} & set(range(1, 9))
    )

    state = _state(roll_rules, offer=(9, 23, 28), remaining=40)
    action = ApplyRollAction("core", 23)
    assert sample_apply_transition(
        state, action, roll_rules, model_id, random.Random(99)
    ) == sample_apply_transition(state, action, roll_rules, model_id, random.Random(99))


def test_rate_agnostic_intervals_use_full_support_and_refresh_wins_zero_ties(roll_rules) -> None:
    zero_tie_state = _state(roll_rules, offer=(10, 13, 16))
    ranked = rank_rate_agnostic_actions(
        zero_tie_state,
        roll_rules,
        lambda banner: sum(emblem.quality_tier for emblem in banner.emblems),
    )
    assert isinstance(ranked[0].action, RefreshRollAction)
    assert all((item.lower, item.upper) == (0.0, 0.0) for item in ranked)

    state = _state(roll_rules, offer=(24, 10, 13))

    def value(banner: BannerState) -> float:
        return float(sum(emblem.quality_tier for emblem in banner.emblems))

    ranked = rank_rate_agnostic_actions(state, roll_rules, value)
    core_interval = next(
        item for item in ranked if item.action == ApplyRollAction(banner_role="core", operation_id=24)
    )
    current = value(state.banners[0])
    exact_deltas = [
        value(outcome) - current for outcome in enumerate_mutation_outcomes(state.banners[0], 24, roll_rules)
    ]
    assert core_interval.lower == min(exact_deltas)
    assert core_interval.upper == max(exact_deltas)


def test_unknown_or_malformed_positive_client_mutation_fails_closed(rules_payload, client_roll) -> None:
    malformed = copy.deepcopy(client_roll)
    operation = next(item for item in malformed["operations"] if item["operation_id"] == 9)
    operation["mutations"][0]["operation"] = "k_eFantasyMutationOperation_Unknown"
    with pytest.raises(RollRuleError, match="unsupported mutation"):
        build_group_roll_rules(rules_payload, malformed)

    ambiguous = copy.deepcopy(client_roll)
    operation = next(item for item in ambiguous["operations"] if item["operation_id"] == 9)
    operation["mutations"][0]["targets"].append("k_eFantasyMutationTarget_FirstColor")
    with pytest.raises(RollRuleError, match="ambiguous"):
        build_group_roll_rules(rules_payload, ambiguous)

    wrong_quality = copy.deepcopy(client_roll)
    wrong_quality["qualities"][0]["bonus_percent"] = 999
    with pytest.raises(RollRuleError, match="Quality definitions"):
        build_group_roll_rules(rules_payload, wrong_quality)

    wrong_assumption = copy.deepcopy(rules_payload)
    wrong_assumption["fantasy"]["roll"]["outcome_assumptions"]["reroll_may_repeat_current"] = False
    with pytest.raises(RollRuleError, match="outcome assumptions"):
        build_group_roll_rules(wrong_assumption, client_roll)
