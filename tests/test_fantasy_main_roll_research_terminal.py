from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ti_predictor.fantasy.main_roll_research_contract import load_main_roll_research_manifest
from ti_predictor.fantasy.main_roll_research_experiment import load_frozen_main_research_context
from ti_predictor.fantasy.main_roll_research_simulator import state_from_payload
from ti_predictor.fantasy.main_roll_research_terminal import VectorizedMainResearchTerminal
from ti_predictor.fantasy.solver_release import load_solver_release_context


def test_vectorized_research_terminal_matches_frozen_production_arithmetic() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = load_main_roll_research_manifest(root / "config/research/fantasy-main-roll-simulator-v1.json")
    group = load_solver_release_context()
    main = load_frozen_main_research_context(group, manifest)
    state_path = root / "config/research/states/ti2026-main-reference-screen-20260814.json"
    state = state_from_payload(
        json.loads(state_path.read_text(encoding="utf-8")),
        main.roll_rules,
    )
    fast = VectorizedMainResearchTerminal(
        main.terminal.pool_result,
        main.terminal.scenario_set,
        main.terminal.canonical_rules,
    )

    for banner in state.banners:
        expected = main.terminal.banner(banner)
        actual = fast.banner(banner)
        assert actual.team_ids == expected.team_ids
        assert actual.role == expected.role
        assert actual.scenario_sha256 == expected.scenario_sha256
        np.testing.assert_allclose(actual.outcomes, expected.outcomes, rtol=1e-12, atol=1e-12)
        assert fast.banner(banner) is actual
