from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import zstandard as zstd
from streamlit.testing.v1 import AppTest

from ti_predictor.fantasy.current_advisor import analyze_current_screen
from ti_predictor.fantasy.roll import BannerState, EmblemState, GroupRollState, RollOffer
from ti_predictor.fantasy.solver_release import (
    default_solver_release_path,
    default_solver_release_pointer_path,
    load_solver_release_context,
    solver_release_team_options,
)

_GROUP_TAB = "小组赛（历史 · 三格）"


def _run_group_tab(app: AppTest, *, timeout: int = 20) -> AppTest:
    app.session_state["fantasy_advisor_period_tab"] = _GROUP_TAB
    return app.run(timeout=timeout)


def test_solver_release_bundle_is_content_addressed_and_loadable() -> None:
    path = default_solver_release_path()
    pointer = json.loads(default_solver_release_pointer_path().read_text(encoding="utf-8"))
    expected_hash, expected_name = (
        path.with_name(path.name + ".sha256").read_text(encoding="utf-8").strip().split("  ", maxsplit=1)
    )
    assert expected_name == path.name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    assert pointer["file_sha256"] == expected_hash
    assert pointer["bytes"] == path.stat().st_size
    assert pointer["release_schema_version"] == 3

    context = load_solver_release_context()
    assert context.policy.as_of == "2026-08-10T13:45:12Z"
    assert len(context.pool_result.pools) == 47
    assert len(context.scenarios.scenario_ids) == 256
    assert {role: len(options) for role, options in solver_release_team_options(context).items()} == {
        "core": 16,
        "mid": 15,
        "support": 16,
    }


def test_solver_release_payload_has_shared_consumer_runtime_contract() -> None:
    path = default_solver_release_path()
    payload = json.loads(zstd.ZstdDecompressor().decompress(path.read_bytes()))
    assert payload["runtime_contract"] == {
        "accepted_input": "confirmed-group-roll-state-v1",
        "contains_data_sync": False,
        "contains_dota_client_control": False,
        "contains_ocr": False,
        "contains_processed_data": False,
        "contains_raw_data": False,
        "contains_run_artifacts": False,
        "contains_screen_capture": False,
        "future_offer_generation": False,
    }
    assert path.stat().st_size < 1024 * 1024
    assert "ocr_profile" not in payload
    assert "screenshots" not in payload
    assert "raw_responses" not in payload
    assert "processed_tables" not in payload
    assert "run_artifacts" not in payload
    assert payload["policy"]["boundaries"]["period_stack"] == "group"
    assert payload["canonical_rules"]["fantasy"]["roll"]["supported_periods"] == [
        "group",
        "main",
    ]


def test_v3_self_contained_release_preserves_the_frozen_v2_group_result() -> None:
    root = Path(__file__).resolve().parents[1]
    legacy_path = root / "deploy/runtime/releases/group-roll-20260810T134512Z-9d3b7851fae0.json.zst"
    contexts = (load_solver_release_context(legacy_path), load_solver_release_context())
    hashes = []
    recommendations = []
    for context in contexts:
        banners = tuple(
            BannerState(
                role,
                tuple(
                    EmblemState(
                        context.roll_rules.stats_for(color)[0],
                        1,
                        context.roll_rules.traits[0],
                    )
                    for color in context.roll_rules.colors_for(role)[:3]
                ),
            )
            for role in context.roll_rules.roles
        )
        offer = RollOffer(
            tuple(operation.operation_id for operation in context.roll_rules.offered_operations[:3])
        )
        result = analyze_current_screen(context, GroupRollState(banners, offer, 40))
        hashes.append(result["analysis_sha256"])
        recommendations.append(result["recommendation"])

    assert len(set(hashes)) == 1
    assert recommendations[0] == recommendations[1]


def test_public_streamlit_entrypoint_is_manual_only_and_calculates() -> None:
    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)

    assert not app.exception
    assert any(title.value == "Fantasy Roll 手动求解器" for title in app.title)
    assert [tab.label for tab in app.tabs] == ["Main（当前 · 五格）", "小组赛（历史 · 三格）"]
    assert app.session_state["fantasy_advisor_period_tab"] == "Main（当前 · 五格）"
    assert sum(select.label == "Stat" for select in app.selectbox) == 15
    strategy = next(radio for radio in app.radio if radio.label == "Main 计算策略")
    assert strategy.value == "main-greedy-immediate-v1"
    assert strategy.options == [
        "G（默认 · 眼前最优）",
        "G-Lite（可选 · 有限二步）",
    ]
    main_calculate = next(button for button in app.button if button.label.startswith("计算 Main"))
    assert not main_calculate.disabled
    assert not any("识别" in button.label for button in app.button)

    main_calculate.click()
    app.run(timeout=20)
    assert any(subheader.value == "Main 现在的结论" for subheader in app.subheader)

    _run_group_tab(app)
    assert any(button.label == "计算现在应该怎么选" for button in app.button)
    assert sum(select.label == "Stat" for select in app.selectbox) == 9
    assert sum(select.label.startswith("选项 ") for select in app.selectbox) == 3

    calculate = next(button for button in app.button if button.label == "计算现在应该怎么选")
    calculate.click()
    _run_group_tab(app, timeout=30)

    assert not app.exception
    assert not app.error
    assert any(subheader.value == "现在的结论" for subheader in app.subheader)
    assert any("实际出现的新状态" in info.value for info in app.info)


def test_manual_and_local_ocr_entrypoints_share_the_same_solver_result() -> None:
    root = Path(__file__).resolve().parents[1]
    manual = AppTest.from_file(str(root / "streamlit_app.py")).run(timeout=20)
    local = AppTest.from_file(str(root / "local_ocr_app.py")).run(timeout=20)

    assert not any("识别" in button.label for button in manual.button)
    if sys.platform == "win32":
        assert any(button.label == "识别下一次稳定的 Main 画面" for button in local.button)

    for app in (manual, local):
        _run_group_tab(app)
        calculate = next(button for button in app.button if button.label == "计算现在应该怎么选")
        calculate.click()
        _run_group_tab(app, timeout=30)
        assert not app.exception
        assert not app.error

    manual_result = manual.session_state["current_advisor_result"]
    local_result = local.session_state["current_advisor_result"]
    assert manual_result["analysis_sha256"] == local_result["analysis_sha256"]
    assert manual_result["recommendation"] == local_result["recommendation"]
