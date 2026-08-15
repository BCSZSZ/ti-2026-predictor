"""Streamlit UI for the independent five-slot Main Fantasy advisor stack."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from ti_predictor.config import load_rules
from ti_predictor.fantasy.advisor import operation_label
from ti_predictor.fantasy.live_ocr import (
    LiveRollMonitor,
    live_capture_supported,
    load_live_ocr_profile,
    observation_widget_updates,
)
from ti_predictor.fantasy.main_advice_policy import main_state_sha256
from ti_predictor.fantasy.main_advice_strategy import G_LITE_MAIN_STRATEGY_ID
from ti_predictor.fantasy.main_current_advisor import analyze_main_current_screen
from ti_predictor.fantasy.main_roll import MainRollState
from ti_predictor.fantasy.main_solver_release import (
    MainSolverReleaseError,
    MainSolverReleasePending,
    load_main_solver_release_context,
    main_solver_readiness,
    main_solver_team_options,
)
from ti_predictor.fantasy.roll import BannerState, EmblemState, RollOffer
from ti_predictor.fantasy.solver_release import load_solver_release_context
from ti_predictor.paths import PATHS

_ROLE_LABELS = {"core": "核心位", "mid": "中单", "support": "辅助位"}
_COLOR_LABELS = {"red": "红", "blue": "蓝", "green": "绿"}
_TRAIT_LABELS = {
    "fractal": "Fractal（品质两两不同才生效）",
    "benevolent": "Benevolent（相邻格 +20%）",
    "vampiric": "Vampiric（自身 +50%，相邻格 -10%）",
    "unique": "Unique（整面仅有一个该 Trait 才生效）",
    "friendly": "Friendly（整面至少三格 Friendly 才生效）",
}
_RISK_LABELS = {
    "mean-first": "最高平均分（G / G-Lite 默认）",
    "balanced": "平衡",
    "downside-first": "更看重低迷时表现",
}
_GRADE_LABELS = {
    "clear": "可以选择",
    "conditional": "有条件选择",
    "refresh": "建议刷新",
    "complete": "Roll 已完成",
}


@st.cache_resource(show_spinner=False)
def _cached_group_context(path: str):
    return load_solver_release_context(Path(path))


@st.cache_resource(show_spinner=False)
def _cached_main_monitor(group_release_path: str) -> LiveRollMonitor:
    group_context = _cached_group_context(group_release_path)
    return LiveRollMonitor(
        profile=load_live_ocr_profile(PATHS.config / "ocr" / "fantasy-main-roll-screen-v1.json"),
        rules=group_context.roll_rules,
    )


def _stat_labels() -> dict[str, str]:
    return {stat_id: str(row["label"]) for stat_id, row in load_rules()["fantasy"]["stats"].items()}


def _public_operation_label(operation_id: int, rules) -> str:
    return operation_label(operation_id, rules).replace(f"#{operation_id} · ", "").replace(" / ", " · ")


def _clear_main_result() -> None:
    st.session_state.pop("main_advisor_result", None)


def _reset_g_lite_budget() -> None:
    st.session_state.pop("main_advisor_g_lite_triggered_states", None)
    _clear_main_result()


def _field_label(field_id: str) -> str:
    parts = field_id.split(".")
    if len(parts) == 4 and parts[0] == "banner":
        role = _ROLE_LABELS.get(parts[1], parts[1])
        attribute = {"stat": "Stat", "quality": "品质", "trait": "Trait"}.get(parts[3], parts[3])
        return f"{role}第 {int(parts[2]) + 1} 格 {attribute}"
    if len(parts) == 2 and parts[0] == "offer":
        return f"选项 {int(parts[1]) + 1}"
    if field_id == "remaining_rolls":
        return "剩余 Roll 次数"
    return field_id


def _consume_pending_observation(rules) -> None:
    observation = st.session_state.pop("main_advisor_pending_observation", None)
    if observation is None:
        return
    updates = observation_widget_updates(
        observation,
        rules,
        period="main",
        key_prefix="main_advisor",
    )
    for key, value in updates.items():
        st.session_state[key] = value
    st.session_state["main_advisor_last_observation"] = observation
    st.session_state.pop("main_advisor_result", None)
    if observation.get("status") == "confirmed":
        st.session_state["main_advisor_autocalculate"] = True


@st.fragment(run_every=1.0)
def _render_live_monitor_status(group_release_path: str) -> None:
    monitor = _cached_main_monitor(group_release_path)
    snapshot = monitor.snapshot()
    renderer = {
        "error": st.error,
        "incomplete": st.warning,
        "confirmed": st.success,
    }.get(snapshot.stage, st.caption)
    renderer(snapshot.message)
    observation = snapshot.observation
    last_generation = int(st.session_state.get("main_advisor_monitor_generation", -1))
    if observation is None or snapshot.generation <= last_generation:
        return
    st.session_state["main_advisor_monitor_generation"] = snapshot.generation
    if observation.get("status") not in {"incomplete", "confirmed"}:
        return
    st.session_state["main_advisor_pending_observation"] = observation
    st.rerun()


def _render_live_controls(group_release_path: str) -> None:
    st.subheader("自动读取 Main 画面")
    st.caption("读取三面战旗的全部 15 枚 Emblem、三个选项与剩余 Roll；不会截成 Group 九格。")
    monitor = _cached_main_monitor(group_release_path)
    snapshot = monitor.snapshot()
    if snapshot.running:
        if st.button("取消本次 Main 识别", use_container_width=True):
            monitor.stop()
            st.rerun()
    elif st.button(
        "识别下一次稳定的 Main 画面",
        type="primary",
        use_container_width=True,
        help="点击后切回 Dota；只读取一次，不控制游戏。",
    ):
        monitor.start_once()
        st.rerun()
    _render_live_monitor_status(group_release_path)
    observation = st.session_state.get("main_advisor_last_observation")
    if observation is None:
        st.caption("等待期间可切回 Dota；也可以始终使用下方五槽手填。")
        return
    captured_at = str(observation.get("captured_at", ""))
    fingerprint = str(observation.get("image_sha256", ""))[:12]
    if observation.get("status") == "incomplete":
        missing = [_field_label(item) for item in observation.get("missing_field_ids", [])]
        st.warning("未自动计算；仍未确认：" + "、".join(missing))
    else:
        st.caption("完整 15 槽观测已写入 Main 表单。")
    st.caption(f"画面时间：{captured_at} · 图像指纹：{fingerprint}")


def _input_form(
    rules,
    *,
    team_options: dict[str, tuple[tuple[int, str], ...]] | None,
    manual_team_mode: bool,
    solver_ready: bool,
    auto_calculate: bool,
    default_risk_profile: str,
) -> tuple[MainRollState | None, Any, str, bool]:
    stat_labels = _stat_labels()
    operation_ids = tuple(operation.operation_id for operation in rules.offered_operations)
    with st.form("main_advisor_form"):
        st.subheader("1. 录入 Main 三面战旗（每面五格）")
        st.caption("五格颜色与位置固定；每格分别选择 Stat、品质和 Trait。")
        banners = []
        for role in rules.roles:
            with st.expander(_ROLE_LABELS[role], expanded=True):
                columns = st.columns(5)
                emblems = []
                for index, (column, color) in enumerate(
                    zip(columns, rules.colors_for(role)[:5], strict=True)
                ):
                    with column:
                        st.markdown(f"**{index + 1} · {_COLOR_LABELS[color]}**")
                        stat_key = f"main_advisor_{role}_{index}_stat"
                        stat_id = st.selectbox(
                            "Stat",
                            rules.stats_for(color),
                            index=None if stat_key in st.session_state else 0,
                            key=stat_key,
                            format_func=lambda item, labels=stat_labels: labels.get(item, item),
                        )
                        quality_key = f"main_advisor_{role}_{index}_quality"
                        quality = st.selectbox(
                            "品质",
                            (1, 2, 3, 4, 5),
                            index=None if quality_key in st.session_state else 0,
                            key=quality_key,
                            format_func=lambda item: f"Tier {item}",
                        )
                        trait_key = f"main_advisor_{role}_{index}_trait"
                        trait = st.selectbox(
                            "Trait",
                            rules.traits,
                            index=None if trait_key in st.session_state else 0,
                            key=trait_key,
                            format_func=lambda item: _TRAIT_LABELS.get(item, item),
                        )
                        emblems.append(EmblemState(stat_id, quality, trait))
                banners.append(BannerState(role, tuple(emblems)))

        st.subheader("2. 录入当前三个 Main 选项")
        offer_ids = []
        for index, column in enumerate(st.columns(3)):
            with column:
                key = f"main_advisor_offer_{index}"
                offer_ids.append(
                    st.selectbox(
                        f"Main 选项 {index + 1}",
                        operation_ids,
                        index=None if key in st.session_state else index,
                        key=key,
                        format_func=lambda item: _public_operation_label(item, rules),
                    )
                )
        remaining_key = "main_advisor_remaining"
        remaining = int(
            st.number_input(
                "Main 剩余 Roll 次数",
                min_value=0,
                max_value=30,
                value=None if remaining_key in st.session_state else 30,
                step=1,
                key=remaining_key,
            )
        )

        selected_team_ids = None
        if manual_team_mode and team_options is not None:
            st.subheader("3. 指定 Main 队伍组合")
            selected = []
            for role, column in zip(rules.roles, st.columns(3), strict=True):
                names = dict(team_options[role])
                with column:
                    selected.append(
                        st.selectbox(
                            _ROLE_LABELS[role],
                            tuple(names),
                            key=f"main_advisor_team_{role}",
                            format_func=lambda item, labels=names: labels[item],
                        )
                    )
            selected_team_ids = tuple(selected)

        with st.expander("Main 高级设置"):
            risk_profile = st.selectbox(
                "取舍方式",
                tuple(_RISK_LABELS),
                index=tuple(_RISK_LABELS).index(default_risk_profile),
                format_func=lambda item: _RISK_LABELS[item],
                key="main_advisor_risk",
            )
        submitted = st.form_submit_button(
            "计算 Main 现在应该怎么选",
            type="primary",
            use_container_width=True,
            disabled=not solver_ready,
        )

    if len(set(offer_ids)) != 3:
        if submitted:
            st.error("三个 Main Roll 选项必须互不重复。")
        return None, selected_team_ids, risk_profile, False
    state = MainRollState(
        banners=tuple(banners),
        offer=RollOffer(tuple(offer_ids)),
        remaining_rolls=remaining,
    )
    return state, selected_team_ids, risk_profile, submitted or (auto_calculate and solver_ready)


def _render_result(result: dict[str, Any]) -> None:
    st.divider()
    st.subheader("Main 现在的结论")
    recommendation = result["recommendation"]
    grade = str(recommendation["grade"])
    heading = f"{_GRADE_LABELS[grade]}：{recommendation['action_label']}"
    renderer = {
        "clear": st.success,
        "conditional": st.warning,
        "refresh": st.info,
        "complete": st.success,
    }[grade]
    renderer(f"**{heading}**\n\n{recommendation['reason']}")
    strategy = result["strategy"]
    st.caption(f"本次策略：{strategy['strategy_label']}")
    if strategy["strategy_id"] == G_LITE_MAIN_STRATEGY_ID:
        if strategy["g_lite_triggered"]:
            st.info(
                "本次已触发 G-Lite 有限二步比较；这次触发计入每局 4 次预算，重复计算同一个画面不会重复计数。"
            )
        else:
            st.caption("本次未触发有限二步比较，结果等同 G。")
    metrics = st.columns(4)
    metrics[0].metric("当前一步平均变化", f"{recommendation['mean_delta']:+,.0f}")
    metrics[1].metric("当前一步低迷变化", f"{recommendation['cvar10_delta']:+,.0f}")
    metrics[2].metric("最差合法结果", f"{recommendation['support_lower']:+,.0f}")
    metrics[3].metric("最好合法结果", f"{recommendation['support_upper']:+,.0f}")
    rows = [
        {
            "建议顺序": index,
            "当前可执行动作": row["action_label"],
            "平均变化": round(float(row["mean_delta"])),
            "低迷情景变化": round(float(row["cvar10_delta"])),
            "合法结果数": int(row["support_count"]),
        }
        for index, row in enumerate(result["primary_action_values"], start=1)
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.subheader("Main 当前队伍组合")
    for column, role, team in zip(
        st.columns(3),
        ("core", "mid", "support"),
        result["current"]["selected_teams"],
        strict=True,
    ):
        column.metric(_ROLE_LABELS[role], team)
    with st.expander("Main 计算边界"):
        for limitation in result["limitations"]:
            st.warning(limitation)
        st.caption(f"数据截止：{result['as_of']} · 分析指纹：{result['analysis_sha256'][:12]}")


def render_main_advisor(
    *,
    manual_only: bool,
    group_release_path: Path,
) -> None:
    st.subheader("Main（当前）")
    st.caption(
        "独立 Main 栈：三面战旗 × 每面五格、30 次 Roll；正式名单前用 16 队预测晋级情景，"
        "名单形成后自动缩为实际 8 队。"
    )
    try:
        group_context = _cached_group_context(str(group_release_path.resolve()))
        rules = group_context.roll_rules
    except (OSError, ValueError) as error:
        st.error(f"共享客户端规则与历史样本包不可用：{error}")
        return

    try:
        main_context = load_main_solver_release_context(group_context)
        readiness = main_solver_readiness()
        team_options = main_solver_team_options(main_context)
        solver_ready = True
        st.caption(
            f"服务已自动加载当前 Main 求解包：{readiness.eligibility_mode} · "
            f"数据截止 {main_context.as_of}。玩家无需运行发布命令。"
        )
        if readiness.status == "provisional":
            st.warning(readiness.reason)
            st.caption(
                f"当前可选 {readiness.candidate_team_count} 队；每个计算情景仍只有 "
                f"{readiness.entrant_team_count} 队进入 Main。后台形成新的 actual 发布包后，"
                "服务会自动缩减候选队。"
            )
        else:
            st.success(readiness.reason)
    except MainSolverReleasePending:
        main_context = None
        team_options = None
        solver_ready = False
        st.error("当前安装缺少可用的 Main 求解包；请更新项目文件后重新启动服务。")
    except (OSError, MainSolverReleaseError) as error:
        main_context = None
        team_options = None
        solver_ready = False
        st.error(f"Main 冻结求解上下文不可用：{error}")

    if not manual_only and live_capture_supported():
        _consume_pending_observation(rules)
        _render_live_controls(str(group_release_path.resolve()))
        st.divider()

    manual_team_mode = False
    strategy_id = None
    if solver_ready:
        strategy_id = st.radio(
            "Main 计算策略",
            main_context.strategy_catalog.strategies.ids,
            index=main_context.strategy_catalog.strategies.ids.index(
                main_context.strategy_catalog.default_strategy_id
            ),
            format_func=main_context.strategy_catalog.label,
            horizontal=True,
            key="main_advisor_strategy",
            on_change=_clear_main_result,
        )
        if strategy_id == G_LITE_MAIN_STRATEGY_ID:
            specification = main_context.strategy_catalog.strategies.g_lite
            triggered_states = set(st.session_state.get("main_advisor_g_lite_triggered_states", ()))
            st.warning(
                "G-Lite 是用户主动选择的开发阶段策略：只在近似平手时做固定 4 样本有限二步"
                "比较，尚未通过独立 confirmation。"
            )
            budget, reset = st.columns([3, 1])
            budget.caption(
                f"本局 G-Lite 触发预算：已使用 {len(triggered_states)} / "
                f"{specification.max_triggers_per_episode}"
            )
            reset.button(
                "重置本局预算",
                key="main_advisor_reset_g_lite_budget",
                on_click=_reset_g_lite_budget,
                use_container_width=True,
            )
        else:
            st.caption("默认 G：每次只比较当前可见动作的一步期望价值，不猜下一轮选项。")
        manual_team_mode = st.radio(
            "Main 队伍组合",
            (False, True),
            format_func=lambda value: "系统自动选择" if not value else "我自己指定",
            horizontal=True,
            key="main_advisor_manual_team_mode",
            on_change=_clear_main_result,
        )
    auto_calculate = bool(st.session_state.pop("main_advisor_autocalculate", False))
    state, selected_team_ids, risk_profile, submitted = _input_form(
        rules,
        team_options=team_options,
        manual_team_mode=manual_team_mode,
        solver_ready=solver_ready,
        auto_calculate=auto_calculate,
        default_risk_profile=(
            main_context.strategy_catalog.default_risk_profile if main_context is not None else "mean-first"
        ),
    )
    if submitted and state is not None and main_context is not None:
        try:
            with st.spinner("使用独立 Main 五槽求解器评估全部合法结果…"):
                triggered_states = set(st.session_state.get("main_advisor_g_lite_triggered_states", ()))
                state_sha256 = main_state_sha256(state)
                previously_counted = state_sha256 in triggered_states
                triggers_used = len(triggered_states) - int(previously_counted)
                result = analyze_main_current_screen(
                    main_context,
                    state,
                    risk_profile=risk_profile,
                    selected_team_ids=selected_team_ids,
                    strategy_id=strategy_id,
                    g_lite_triggers_used=triggers_used,
                )
                if strategy_id == G_LITE_MAIN_STRATEGY_ID and result["strategy"]["g_lite_triggered"]:
                    triggered_states.add(state_sha256)
                    st.session_state["main_advisor_g_lite_triggered_states"] = sorted(triggered_states)
            st.session_state["main_advisor_result"] = result
        except (OSError, ValueError) as error:
            st.error(f"本次 Main 结果被阻断：{error}")
            st.session_state.pop("main_advisor_result", None)
    result = st.session_state.get("main_advisor_result")
    if result is not None:
        _render_result(result)
    elif solver_ready:
        st.info("完成 Main 输入后点击“计算 Main 现在应该怎么选”。")


__all__ = ["render_main_advisor"]
