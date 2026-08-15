from __future__ import annotations

import random
from pathlib import Path

import pytest

from ti_predictor.fantasy.main_roll import (
    build_main_roll_rules,
    enumerate_mutation_outcomes,
    mutation_distribution,
)
from ti_predictor.fantasy.main_roll_research_contract import (
    load_main_roll_research_manifest,
)
from ti_predictor.fantasy.main_roll_research_probability import MainRollProbabilityProvider
from ti_predictor.fantasy.roll import BannerState, EmblemState
from ti_predictor.rules import _inspect_fantasy_crafting


@pytest.fixture(scope="module")
def research_manifest():
    path = Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-simulator-v1.json"
    return load_main_roll_research_manifest(path)


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    client_roll = _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8"))
    return build_main_roll_rules(rules_payload, client_roll)


def _banner(rules, role: str = "core") -> BannerState:
    return BannerState(
        role=role,
        emblems=tuple(
            EmblemState(
                stat_id=rules.stats_for(color)[index % len(rules.stats_for(color))],
                quality_tier=index + 1,
                trait_id=rules.traits[index % len(rules.traits)],
            )
            for index, color in enumerate(rules.colors_for(role)[:5])
        ),
    )


def test_primary_probability_provider_matches_existing_mutation_distribution(
    main_rules,
    research_manifest,
) -> None:
    banner = _banner(main_rules)
    provider = MainRollProbabilityProvider(
        main_rules,
        research_manifest.probability_model("client-weight-primary-v1"),
    )

    for operation in main_rules.offered_operations:
        expected = {
            outcome.banner: outcome.probability
            for outcome in mutation_distribution(
                banner,
                operation.operation_id,
                main_rules,
                "client-weight-primary-v1",
            )
        }
        actual = {
            outcome.banner: outcome.probability
            for outcome in provider.mutation_distribution(banner, operation.operation_id)
        }
        assert actual == pytest.approx(expected)


def test_sensitivity_models_keep_the_same_client_legal_support(
    main_rules,
    research_manifest,
) -> None:
    banner = _banner(main_rules)
    for operation in main_rules.offered_operations:
        support = set(enumerate_mutation_outcomes(banner, operation.operation_id, main_rules))
        for specification in research_manifest.probability_models:
            provider = MainRollProbabilityProvider(main_rules, specification)
            distribution = provider.mutation_distribution(banner, operation.operation_id)
            assert {outcome.banner for outcome in distribution} == support
            if support:
                assert sum(outcome.probability for outcome in distribution) == pytest.approx(1.0)
                assert all(outcome.probability > 0.0 for outcome in distribution)


def test_offer_distribution_is_exact_and_sampling_is_reproducible(
    main_rules,
    research_manifest,
) -> None:
    provider = MainRollProbabilityProvider(
        main_rules,
        research_manifest.probability_model("client-weight-primary-v1"),
    )

    distribution = provider.offer_distribution()
    first = provider.draw_offer(random.Random(42))
    second = provider.draw_offer(random.Random(42))

    assert len(distribution) == 20 * 19 * 18
    assert sum(outcome.probability for outcome in distribution) == pytest.approx(1.0)
    assert first == second
    assert len(set(first.operation_ids)) == 3
