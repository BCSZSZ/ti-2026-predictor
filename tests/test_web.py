from __future__ import annotations

import logging
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

_GROUP_TAB = "小组赛（历史 · 三格）"


def _run_group_tab(app: AppTest, *, timeout: int = 20) -> AppTest:
    app.session_state["fantasy_advisor_period_tab"] = _GROUP_TAB
    return app.run(timeout=timeout)


def _open_roll_page(app: AppTest, *, period: str = "main") -> AppTest:
    app.sidebar.radio[0].set_value("Fantasy Roll 实时顾问").run(timeout=20)
    if period != "main":
        _run_group_tab(app)
    return app


def test_streamlit_default_page_has_no_runtime_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    assert not app.exception
    assert any(metric.label == "Fantasy 表现样本" for metric in app.metric)


def test_streamlit_group_advisor_input_page_has_no_runtime_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)

    _open_roll_page(app, period="group")

    assert not app.exception
    assert any(title.value == "Fantasy Roll 实时顾问" for title in app.title)
    capture_buttons = [button for button in app.button if button.label == "识别下一次稳定的 Dota 画面"]
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
    _open_roll_page(app, period="group")

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="streamlit.elements.lib.policies"):
        app.session_state["current_advisor_offer_1"] = 23
        _run_group_tab(app)

    assert not app.exception
    assert not any("created with a default value" in record.getMessage() for record in caplog.records)


def test_streamlit_group_advisor_manual_lineup_uses_three_team_dropdowns() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=20)
    _open_roll_page(app, period="group")

    mode = next(radio for radio in app.radio if radio.label == "队伍组合")
    mode.set_value(True)
    _run_group_tab(app)

    assert not app.exception
    role_selects = {
        select.label: select for select in app.selectbox if select.label in {"核心位", "中单", "辅助位"}
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
    _open_roll_page(app, period="group")

    calculate = next(button for button in app.button if button.label == "计算现在应该怎么选")
    # The first click covers the declared 45 s frozen-context target plus the 10 s analysis target.
    calculate.click()
    _run_group_tab(app, timeout=60)

    assert not app.exception
    assert any(subheader.value == "现在的结论" for subheader in app.subheader)
    assert any(subheader.value == "自动 Title 建议" for subheader in app.subheader)
    assert any("在游戏里完成操作后" in info.value for info in app.info)


def test_streamlit_main_tab_uses_five_slots_and_calculates_with_projected_entrants() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = _open_roll_page(AppTest.from_file(str(app_path)).run(timeout=20))

    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Main（当前 · 五格）", "小组赛（历史 · 三格）"]
    assert app.session_state["fantasy_advisor_period_tab"] == "Main（当前 · 五格）"
    assert sum(select.label == "Stat" for select in app.selectbox) == 15
    assert sum(select.label == "品质" for select in app.selectbox) == 15
    assert sum(select.label == "Trait" for select in app.selectbox) == 15
    remaining = next(item for item in app.number_input if item.label == "Main 剩余 Roll 次数")
    assert remaining.value == 30
    assert remaining.max == 30
    strategy = next(radio for radio in app.radio if radio.label == "Main 计算策略")
    assert strategy.value == "main-greedy-immediate-v1"
    assert strategy.options == [
        "G（默认 · 眼前最优）",
        "G-Lite（可选 · 有限二步）",
    ]
    calculate = next(button for button in app.button if button.label.startswith("计算 Main"))
    assert not calculate.disabled
    assert any("当前 16 队" in warning.value for warning in app.warning)

    calculate.click()
    app.run(timeout=20)

    assert any(subheader.value == "Main 现在的结论" for subheader in app.subheader)
    assert any(subheader.value == "Main 当前队伍组合" for subheader in app.subheader)
    assert not app.error


def test_streamlit_main_strategy_can_switch_to_g_lite_without_exposing_failed_variant() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = _open_roll_page(AppTest.from_file(str(app_path)).run(timeout=20))

    strategy = next(radio for radio in app.radio if radio.label == "Main 计算策略")
    strategy.set_value("main-greedy-selective-two-step-v1")
    app.run(timeout=20)

    assert not app.exception
    assert any("尚未通过独立 confirmation" in warning.value for warning in app.warning)
    assert any(button.label == "重置本局预算" for button in app.button)
    assert not any("0.10%" in str(element.value) for element in (*app.caption, *app.warning))

    calculate = next(button for button in app.button if button.label.startswith("计算 Main"))
    calculate.click()
    app.run(timeout=30)

    result = app.session_state["main_advisor_result"]
    assert result["strategy"]["strategy_id"] == "main-greedy-selective-two-step-v1"
    assert any("本次策略：G-Lite" in caption.value for caption in app.caption)
    assert not app.error


def test_streamlit_projected_main_manual_lineup_exposes_current_sixteen_candidates() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src/ti_predictor/web_app.py"
    app = _open_roll_page(AppTest.from_file(str(app_path)).run(timeout=20))

    mode = next(radio for radio in app.radio if radio.label == "Main 队伍组合")
    mode.set_value(True)
    app.run(timeout=20)

    role_selects = {
        select.label: select for select in app.selectbox if select.label in {"核心位", "中单", "辅助位"}
    }
    assert len(role_selects["核心位"].options) == 16
    assert len(role_selects["中单"].options) == 15
    assert len(role_selects["辅助位"].options) == 16
    assert "LGD Gaming" in role_selects["核心位"].options
    assert "LGD Gaming" not in role_selects["中单"].options
    assert not app.error
