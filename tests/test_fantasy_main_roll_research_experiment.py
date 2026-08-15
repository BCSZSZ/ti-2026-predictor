from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ti_predictor.fantasy.main_roll import MainRollState, build_main_roll_rules
from ti_predictor.fantasy.main_roll_research_contract import load_main_roll_research_manifest
from ti_predictor.fantasy.main_roll_research_experiment import (
    MainResearchExperimentError,
    run_paired_experiment,
    write_research_experiment_bundle,
)
from ti_predictor.fantasy.main_roll_research_simulator import TerminalEvaluation
from ti_predictor.fantasy.roll import BannerState, EmblemState, RollOffer
from ti_predictor.rules import _inspect_fantasy_crafting


class _QualityTerminal:
    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        value = float(sum(emblem.quality_tier for banner in banners for emblem in banner.emblems))
        return TerminalEvaluation(np.asarray([value - 1.0, value, value + 1.0]), (101, 102, 103))


@pytest.fixture(scope="module")
def manifest():
    return load_main_roll_research_manifest(
        Path(__file__).resolve().parents[1] / "config/research/fantasy-main-roll-simulator-v1.json"
    )


@pytest.fixture
def main_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    return build_main_roll_rules(
        rules_payload,
        _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8")),
    )


def _state(rules) -> MainRollState:
    banners = tuple(
        BannerState(
            role,
            tuple(
                EmblemState(rules.stats_for(color)[0], 5, "fractal") for color in rules.colors_for(role)[:5]
            ),
        )
        for role in rules.roles
    )
    return MainRollState(banners, RollOffer((14, 31, 17)), 1)


def test_smoke_experiment_is_paired_deterministic_and_release_ineligible(
    main_rules,
    manifest,
) -> None:
    arguments = dict(
        source_version_id="test-source",
        mode="smoke",
        smoke_count=2,
        model_ids=("client-weight-primary-v1",),
    )

    first = run_paired_experiment(
        manifest,
        main_rules,
        _QualityTerminal(),
        _state(main_rules),
        **arguments,
    )
    second = run_paired_experiment(
        manifest,
        main_rules,
        _QualityTerminal(),
        _state(main_rules),
        **arguments,
    )

    assert first.report == second.report
    assert len(first.episodes) == 2 * 3
    assert first.report["release_eligible"] is False
    assert first.report["web_integration"] is False
    assert all(gate["status"] == "not-evaluated" for gate in first.report["research_gates"].values())


def test_research_bundle_is_confined_and_reproducible(tmp_path, main_rules, manifest) -> None:
    result = run_paired_experiment(
        manifest,
        main_rules,
        _QualityTerminal(),
        _state(main_rules),
        source_version_id="test-source",
        mode="smoke",
        smoke_count=2,
        model_ids=("client-weight-primary-v1",),
    )
    allowed = tmp_path / "artifacts/research/main-roll-simulator"

    destination = write_research_experiment_bundle(
        result,
        manifest,
        output_root=allowed,
        allowed_root=allowed,
    )
    repeated = write_research_experiment_bundle(
        result,
        manifest,
        output_root=allowed,
        allowed_root=allowed,
    )

    assert destination == repeated
    assert (destination / "report.json").is_file()
    assert (destination / "checksums.json").is_file()
    assert len(tuple((destination / "episodes").rglob("*.json"))) == 6
    with pytest.raises(MainResearchExperimentError, match="allowed artifact root"):
        write_research_experiment_bundle(
            result,
            manifest,
            output_root=tmp_path / "outside",
            allowed_root=allowed,
        )


def test_confirmation_refuses_partial_probability_family(main_rules, manifest) -> None:
    with pytest.raises(MainResearchExperimentError, match="every frozen"):
        run_paired_experiment(
            manifest,
            main_rules,
            _QualityTerminal(),
            _state(main_rules),
            source_version_id="test-source",
            mode="confirmation",
            model_ids=("client-weight-primary-v1",),
        )


def test_tuning_validation_can_retain_greedy_without_spending_confirmation(
    main_rules,
    manifest,
) -> None:
    result = run_paired_experiment(
        manifest,
        main_rules,
        _QualityTerminal(),
        _state(main_rules),
        source_version_id="test-source",
        mode="tuning",
        model_ids=("client-weight-primary-v1",),
    )

    assert result.report["strategy_selection"] == {
        "status": "tuning-futility-fallback",
        "selected_policy_id": manifest.strategies.greedy.policy_id,
        "advancing_policy_ids": [],
        "reason": (
            "No challenger passed the independent tuning-validation screen; "
            "confirmation is unnecessary for retaining the safety baseline."
        ),
    }
    assert all(
        row["status"] == "stop-for-futility" for row in result.report["tuning_candidate_screen"].values()
    )
