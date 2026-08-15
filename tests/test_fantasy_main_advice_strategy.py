from __future__ import annotations

import json
from pathlib import Path

import pytest

from ti_predictor.fantasy.main_advice_strategy import (
    G_LITE_MAIN_STRATEGY_ID,
    GREEDY_MAIN_STRATEGY_ID,
    MainAdviceStrategyCatalog,
    load_main_advice_strategy_catalog,
)


def _path() -> Path:
    return Path(__file__).resolve().parents[1] / "config/models/fantasy-main-advice-strategies-v1.json"


def test_main_strategy_catalog_freezes_g_default_and_only_g_lite_v1() -> None:
    catalog = load_main_advice_strategy_catalog(_path())

    assert catalog.default_strategy_id == GREEDY_MAIN_STRATEGY_ID
    assert catalog.strategies.ids == (GREEDY_MAIN_STRATEGY_ID, G_LITE_MAIN_STRATEGY_ID)
    assert catalog.default_risk_profile == "mean-first"
    assert catalog.strategies.g_lite.ambiguity_fraction == 0.0005
    assert catalog.strategies.g_lite.max_triggers_per_episode == 4
    assert catalog.strategies.g_lite.research_evidence.evidence_status.endswith("not-confirmed")
    assert "selective-two-step-v2" not in _path().read_text(encoding="utf-8")
    assert len(catalog.semantic_hash) == 64


def test_main_strategy_catalog_rejects_nonpositive_g_lite_evidence() -> None:
    payload = json.loads(_path().read_text(encoding="utf-8"))
    payload["strategies"]["g_lite"]["research_evidence"]["relative_mean_gain"] = 0.0

    with pytest.raises(ValueError, match="positive point estimate"):
        MainAdviceStrategyCatalog.model_validate_json(json.dumps(payload))
