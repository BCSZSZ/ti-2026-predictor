from __future__ import annotations

import json
from pathlib import Path

import pytest

from ti_predictor.fantasy.main_roll_bounded_challenger_contract import (
    MainRollBoundedChallengerManifest,
    load_main_roll_bounded_challenger_manifest,
)
from ti_predictor.fantasy.main_roll_research_states import (
    episode_seed,
    load_starting_state_coverage_manifest,
)


def _path() -> Path:
    return (
        Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-bounded-challengers-v1.json"
    )


def _v2_path() -> Path:
    return (
        Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-bounded-challengers-v2.json"
    )


def test_bounded_manifest_freezes_fresh_research_only_design() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = load_main_roll_bounded_challenger_manifest(_path())
    prior = load_starting_state_coverage_manifest(
        root / "config/research/fantasy-main-starting-state-coverage-v1.json"
    )

    assert manifest.research_only is True
    assert manifest.web_integration is False
    assert manifest.runtime_pointer_writes is False
    assert manifest.dota_client_control is False
    assert manifest.generator.master_seed != prior.generator.master_seed
    assert manifest.splits.development.count == 100
    assert manifest.splits.confirmation.count == 900
    assert manifest.runtime_gate.ideal_confirmation_seconds_per_candidate == 3600
    assert manifest.runtime_gate.maximum_confirmation_seconds_per_candidate == 7200
    assert len(manifest.strategies.candidate_policy_ids) == 3
    assert len(manifest.semantic_hash) == 64


def test_bounded_manifest_rejects_production_and_runtime_expansion() -> None:
    payload = json.loads(_path().read_text(encoding="utf-8"))
    payload["web_integration"] = True
    payload["runtime_gate"]["maximum_confirmation_seconds_per_candidate"] = 7201

    with pytest.raises(ValueError):
        MainRollBoundedChallengerManifest.model_validate(payload)


def test_bounded_manifest_rejects_development_confirmation_overlap() -> None:
    payload = json.loads(_path().read_text(encoding="utf-8"))
    payload["splits"]["confirmation"] = payload["splits"]["development"]

    with pytest.raises(ValueError, match="disjoint"):
        MainRollBoundedChallengerManifest.model_validate(payload)


def test_v2_freezes_user_selected_trigger_budget_without_reusing_confirmation() -> None:
    v1 = load_main_roll_bounded_challenger_manifest(_path())
    v2 = load_main_roll_bounded_challenger_manifest(_v2_path())

    assert v2.parent_bounded_challenger_manifest is not None
    assert v2.parent_bounded_challenger_manifest.semantic_sha256 == v1.semantic_hash
    assert v2.roll_tape_namespace_semantic_sha256 == v1.semantic_hash
    assert v2.generator == v1.generator
    assert v2.splits == v1.splits
    assert v2.strategies.selective_two_step.policy_id.endswith("-v2")
    assert v2.strategies.selective_two_step.ambiguity_fraction == 0.001
    assert v2.strategies.selective_two_step.max_triggers_per_episode == 5
    assert v2.semantic_hash != v1.semantic_hash
    model_id = v2.primary_probability_model
    assert episode_seed(v1, 0, model_id) == episode_seed(
        v2,
        0,
        model_id,
        namespace_sha256=v2.roll_tape_namespace_semantic_sha256,
    )


def test_v2_rejects_mixed_experiment_and_policy_versions() -> None:
    payload = json.loads(_v2_path().read_text(encoding="utf-8"))
    payload["strategies"]["selective_two_step"]["policy_id"] = "main-greedy-selective-two-step-v1"

    with pytest.raises(ValueError, match="versions must match"):
        MainRollBoundedChallengerManifest.model_validate_json(json.dumps(payload))
