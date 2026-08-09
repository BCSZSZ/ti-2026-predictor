from __future__ import annotations

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
    live_toggles = [
        toggle for toggle in app.toggle if toggle.label == "实时监视 Dota 2 的 Group Roll 页面"
    ]
    if sys.platform == "win32":
        assert len(live_toggles) == 1 and not live_toggles[0].value
    else:
        assert not live_toggles
    assert any(button.label == "计算现在应该怎么选" for button in app.button)
    assert sum(select.label.startswith("选项 ") for select in app.selectbox) == 3
    assert not app.error


def test_streamlit_group_advisor_manual_lineup_uses_three_team_dropdowns() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    app.sidebar.radio[0].set_value("Group Roll 实时顾问").run(timeout=20)

    mode = next(radio for radio in app.radio if radio.label == "队伍组合")
    mode.set_value(True).run(timeout=20)

    assert not app.exception
    labels = {select.label for select in app.selectbox}
    assert {"核心位", "中单", "辅助位"} <= labels
    assert not app.error


def test_streamlit_group_advisor_default_input_calculates_recommendation_and_title() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    app.sidebar.radio[0].set_value("Group Roll 实时顾问").run(timeout=20)

    calculate = next(button for button in app.button if button.label == "计算现在应该怎么选")
    calculate.click().run(timeout=40)

    assert not app.exception
    assert any(subheader.value == "现在的结论" for subheader in app.subheader)
    assert any(subheader.value == "自动 Title 建议" for subheader in app.subheader)
    assert any("在游戏里完成操作后" in info.value for info in app.info)
