from __future__ import annotations

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

    app.sidebar.radio[0].set_value("Group Roll 顾问（实验）").run(timeout=20)

    assert not app.exception
    assert any(title.value == "Group 40-Roll 顾问（实验）" for title in app.title)
    assert any(button.label == "确认录入并创建 Locked baseline" for button in app.button)
    assert any("P5 求解器 effectiveness 失败" in error.value for error in app.error)


def test_streamlit_group_advisor_main_fails_closed() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    app.sidebar.radio[0].set_value("Group Roll 顾问（实验）").run(timeout=20)

    stage = next(radio for radio in app.radio if radio.label == "阶段")
    stage.set_value("Main（预留）").run(timeout=20)

    assert not app.exception
    assert any("Main 的五格规则尚未冻结" in error.value for error in app.error)
    assert not any(button.label == "确认录入并创建 Locked baseline" for button in app.button)
