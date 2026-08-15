from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from ti_predictor.fantasy.main_roll import build_main_roll_rules, validate_main_state
from ti_predictor.fantasy.main_roll_research_states import (
    build_starting_state_records,
    episode_seed,
    generate_starting_state,
    load_base_research_manifest,
    load_starting_state_coverage_manifest,
    sensitivity_state_indices,
    state_index_semantic_hash,
)
from ti_predictor.rules import _inspect_fantasy_crafting


@pytest.fixture(scope="module")
def coverage_manifest():
    return load_starting_state_coverage_manifest(
        Path(__file__).resolve().parents[1] / "config/research/fantasy-main-starting-state-coverage-v1.json"
    )


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def test_coverage_manifest_pins_base_manifest(coverage_manifest) -> None:
    root = Path(__file__).resolve().parents[1]

    path, base = load_base_research_manifest(coverage_manifest, repository_root=root)

    assert path == (root / "config/research/fantasy-main-roll-simulator-v1.json").resolve()
    assert base.semantic_hash == coverage_manifest.base_research_manifest.semantic_sha256
    assert coverage_manifest.splits.development.count == 100
    assert coverage_manifest.splits.confirmation.count == 900


def test_generator_is_deterministic_legal_and_index_keyed(
    coverage_manifest,
    main_rules,
) -> None:
    first = generate_starting_state(coverage_manifest, main_rules, 137)
    repeated = generate_starting_state(coverage_manifest, main_rules, 137)
    other = generate_starting_state(coverage_manifest, main_rules, 138)

    validate_main_state(first, main_rules)
    assert first == repeated
    assert first != other
    assert first.remaining_rolls == 30
    assert len(first.banners) == 3
    assert all(len(banner.emblems) == 5 for banner in first.banners)
    assert len(set(first.offer.operation_ids)) == 3


def test_frozen_suite_contains_1000_unique_states_and_100_sensitivity_states(
    coverage_manifest,
    main_rules,
) -> None:
    records = build_starting_state_records(coverage_manifest, main_rules)

    assert len(records) == 1_000
    assert len({record["state_sha256"] for record in records}) == 1_000
    assert Counter(record["split"] for record in records) == {
        "development": 100,
        "confirmation": 900,
    }
    assert sum(bool(record["sensitivity_selected"]) for record in records) == 100
    assert state_index_semantic_hash(records) == (
        "48346486905dc51d398b0d9ad6312b8cbfc441efb27579c3b59afaa2c4b04278"
    )


def test_sensitivity_selection_and_paired_episode_seed_are_outcome_blind(
    coverage_manifest,
) -> None:
    selected = sensitivity_state_indices(coverage_manifest)
    primary = episode_seed(coverage_manifest, selected[0], "client-weight-primary-v1")

    assert len(selected) == 100
    assert selected == tuple(sorted(selected))
    assert all(index >= 100 for index in selected)
    assert primary == episode_seed(
        coverage_manifest,
        selected[0],
        "client-weight-primary-v1",
    )
    assert primary != episode_seed(
        coverage_manifest,
        selected[0],
        "flattened-weights-v1",
    )


def test_manifest_rejects_a_non_100_900_split(coverage_manifest) -> None:
    payload = coverage_manifest.model_dump(mode="python")
    payload["splits"]["development"]["count"] = 99
    payload["splits"]["confirmation"]["start"] = 99
    payload["splits"]["confirmation"]["count"] = 901

    with pytest.raises(ValidationError, match="100 development / 900 confirmation"):
        type(coverage_manifest).model_validate(payload)
