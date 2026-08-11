from __future__ import annotations

import logging
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_default_page_has_no_runtime_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    assert not app.exception
    assert any(metric.label == "Fantasy 表现样本" for metric in app.metric)


def test_streamlit_group_advisor_input_page_has_no_runtime_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)

    app.sidebar.radio[0].set_value("Group Roll 实时顾问").run(timeout=20)

    assert not app.exception
    assert any(title.value == "Group Roll 实时顾问" for title in app.title)
    capture_buttons = [
        button for button in app.button if button.label == "识别下一次稳定的 Dota 画面"
    ]
    if sys.platform == "win32":
        assert len(capture_buttons) == 1
    else:
        assert not capture_buttons
    assert not any(toggle.label == "实时监视 Dota 2 的 Group Roll 页面" for toggle in app.toggle)
    assert any(button.label == "计算现在应该怎么选" for button in app.button)
    assert sum(select.label.startswith("选项 ") for select in app.selectbox) == 3
    assert not app.error


def test_streamlit_ocr_widget_update_has_no_duplicate_default_warning(caplog) -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    app.sidebar.radio[0].set_value("Group Roll 实时顾问").run(timeout=20)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="streamlit.elements.lib.policies"):
        app.session_state["current_advisor_offer_1"] = 23
        app.run(timeout=20)

    assert not app.exception
    assert not any(
        "created with a default value" in record.getMessage()
        for record in caplog.records
    )


def test_streamlit_group_advisor_manual_lineup_uses_three_team_dropdowns() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    app.sidebar.radio[0].set_value("Group Roll 实时顾问").run(timeout=20)

    mode = next(radio for radio in app.radio if radio.label == "队伍组合")
    mode.set_value(True).run(timeout=20)

    assert not app.exception
    role_selects = {
        select.label: select
        for select in app.selectbox
        if select.label in {"核心位", "中单", "辅助位"}
    }
    labels = set(role_selects)
    assert {"核心位", "中单", "辅助位"} <= labels
    assert "LGD Gaming" in role_selects["核心位"].options
    assert "LGD Gaming" not in role_selects["中单"].options
    assert "LGD Gaming" in role_selects["辅助位"].options
    assert not app.error


def test_streamlit_group_advisor_default_input_calculates_recommendation_and_title() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    app.sidebar.radio[0].set_value("Group Roll 实时顾问").run(timeout=20)

    calculate = next(button for button in app.button if button.label == "计算现在应该怎么选")
    # The first click covers the declared 45 s fail-closed context target plus the 10 s analysis target.
    calculate.click().run(timeout=60)

    assert not app.exception
    assert any(subheader.value == "现在的结论" for subheader in app.subheader)
    assert any(subheader.value == "自动 Title 建议" for subheader in app.subheader)
    assert any("在游戏里完成操作后" in info.value for info in app.info)
