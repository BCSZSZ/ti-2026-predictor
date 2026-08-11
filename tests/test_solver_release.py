from __future__ import annotations

import hashlib
import json
from pathlib import Path

import zstandard as zstd
from streamlit.testing.v1 import AppTest

from ti_predictor.fantasy.solver_release import (
    default_solver_release_path,
    default_solver_release_pointer_path,
    load_solver_release_context,
    solver_release_team_options,
)


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


def test_public_streamlit_entrypoint_is_manual_only_and_calculates() -> None:
    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)

    assert not app.exception
    assert any(title.value == "Group Roll 手动求解器" for title in app.title)
    assert any(button.label == "计算现在应该怎么选" for button in app.button)
    assert not any("识别" in button.label for button in app.button)
    assert sum(select.label.startswith("选项 ") for select in app.selectbox) == 3

    calculate = next(button for button in app.button if button.label == "计算现在应该怎么选")
    calculate.click().run(timeout=30)

    assert not app.exception
    assert not app.error
    assert any(subheader.value == "现在的结论" for subheader in app.subheader)
    assert any("实际出现的新状态" in info.value for info in app.info)


def test_manual_and_local_ocr_entrypoints_share_the_same_solver_result() -> None:
    root = Path(__file__).resolve().parents[1]
    manual = AppTest.from_file(str(root / "streamlit_app.py")).run(timeout=20)
    local = AppTest.from_file(str(root / "local_ocr_app.py")).run(timeout=20)

    for app in (manual, local):
        calculate = next(button for button in app.button if button.label == "计算现在应该怎么选")
        calculate.click().run(timeout=30)
        assert not app.exception
        assert not app.error

    manual_result = manual.session_state["current_advisor_result"]
    local_result = local.session_state["current_advisor_result"]
    assert manual_result["analysis_sha256"] == local_result["analysis_sha256"]
    assert manual_result["recommendation"] == local_result["recommendation"]
