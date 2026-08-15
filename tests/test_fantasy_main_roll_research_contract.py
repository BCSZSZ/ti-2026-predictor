from __future__ import annotations

import json
from pathlib import Path

import pytest

from ti_predictor.fantasy.main_roll_research_contract import (
    MainRollResearchManifest,
    load_main_roll_research_manifest,
)


def _manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "research" / "fantasy-main-roll-simulator-v1.json"


def test_research_manifest_freezes_non_production_boundary() -> None:
    manifest = load_main_roll_research_manifest(_manifest_path())

    assert manifest.period == "main"
    assert manifest.research_only is True
    assert manifest.web_integration is False
    assert manifest.runtime_pointer_writes is False
    assert manifest.dota_client_control is False
    assert manifest.as_of.endswith("Z")
    assert manifest.source.eligibility_mode == "projected"
    assert len(manifest.semantic_hash) == 64


def test_research_manifest_separates_probability_axes_and_seed_splits() -> None:
    manifest = load_main_roll_research_manifest(_manifest_path())

    primary = manifest.probability_model(manifest.primary_probability_model)
    flattened = manifest.probability_model("flattened-weights-v1")
    repeat_suppressed = manifest.probability_model("repeat-suppressed-v1")
    correlated = manifest.probability_model("correlated-multi-target-v1")

    assert primary.offer_weight_power == primary.quality_weight_power == 1.0
    assert flattened.offer_weight_power == flattened.quality_weight_power == 0.5
    assert repeat_suppressed.repeat_current_factor == 0.01
    assert correlated.multi_target_correlation == 0.25
    assert not (set(manifest.splits.tuning.values) & set(manifest.splits.confirmation.values))
    roster = manifest.projected_roster_validation
    assert set(roster.tuning_folds).isdisjoint(roster.confirmation_folds)
    assert set(roster.tuning_folds) | set(roster.confirmation_folds) == set(range(roster.fold_count))
    assert roster.inner_scenarios_per_phase in roster.convergence_inner_scenario_counts


def test_research_manifest_rejects_web_integration_and_noncanonical_time() -> None:
    payload = json.loads(_manifest_path().read_text(encoding="utf-8"))
    payload["web_integration"] = True
    payload["as_of"] = "2026-08-13T22:23:17+09:00"

    with pytest.raises(ValueError):
        MainRollResearchManifest.model_validate_json(json.dumps(payload))


def test_research_manifest_requires_disjoint_seed_ranges() -> None:
    payload = json.loads(_manifest_path().read_text(encoding="utf-8"))
    payload["splits"]["confirmation"] = payload["splits"]["tuning"]

    with pytest.raises(ValueError, match="disjoint"):
        MainRollResearchManifest.model_validate_json(json.dumps(payload))


def test_research_manifest_rejects_projected_actual_or_fold_mixing() -> None:
    payload = json.loads(_manifest_path().read_text(encoding="utf-8"))
    payload["source"]["eligibility_mode"] = "actual"
    payload["projected_roster_validation"]["confirmation_folds"] = [3, 4, 5, 6, 7]

    with pytest.raises(ValueError):
        MainRollResearchManifest.model_validate_json(json.dumps(payload))
