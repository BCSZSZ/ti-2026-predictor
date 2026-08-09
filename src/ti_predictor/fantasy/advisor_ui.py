"""Streamlit UI for the local current-screen Group Roll advisor."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.fantasy.advisor import operation_label
from ti_predictor.fantasy.current_advisor import (
    CurrentAdvisorContext,
    analyze_current_screen,
    load_current_advisor_policy,
    load_current_advisor_roll_rules,
    prepare_current_advisor_context,
)
from ti_predictor.fantasy.live_ocr import (
    LiveRollMonitor,
    live_capture_supported,
    load_live_ocr_profile,
    observation_widget_updates,
)
from ti_predictor.fantasy.roll import BannerState, EmblemState, GroupRollState, RollOffer
from ti_predictor.paths import PATHS

_ROLE_LABELS = {"core": "核心位", "mid": "中单", "support": "辅助位"}
_COLOR_LABELS = {"red": "红", "blue": "蓝", "green": "绿"}
_TRAIT_LABELS = {
    "fractal": "Fractal（品质两两不同才生效）",
    "benevolent": "Benevolent（相邻格 +20%）",
    "vampiric": "Vampiric（自身 +50%，相邻格 -10%）",
    "unique": "Unique（整面仅有一个该 Trait 才生效）",
    "friendly": "Friendly（三格全是 Friendly 才生效）",
}
_RISK_LABELS = {
    "balanced": "平衡（推荐）",
    "mean-first": "最高平均分",
    "downside-first": "更看重低迷时表现",
}
_GRADE_LABELS = {
    "clear": "可以选择",
    "conditional": "有条件选择",
    "refresh": "建议刷新",
    "complete": "Roll 已完成",
}
_MODEL_LABELS = {
    "client-weight-primary-v1": "当前最佳出率估计",
    "flattened-weights-v1": "出率更平均",
    "sharpened-weights-v1": "高权重结果更集中",
}
_TITLE_LABEL_OVERRIDES = {
    "clutch": "BO3 打到第 3 局时，在第 3 局触发",
}


@st.cache_resource(show_spinner=False)
def _cached_roll_rules():
    return load_current_advisor_roll_rules()


@st.cache_resource(show_spinner=False)
def _cached_context(as_of: str) -> CurrentAdvisorContext:
    return prepare_current_advisor_context(as_of=as_of)


def _policy():
    return load_current_advisor_policy(
        PATHS.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )


@st.cache_resource(show_spinner=False)
def _cached_live_monitor() -> LiveRollMonitor:
    return LiveRollMonitor(
        profile=load_live_ocr_profile(),
        rules=_cached_roll_rules(),
    )


def _stat_labels() -> dict[str, str]:
    stats = load_rules()["fantasy"]["stats"]
    return {stat_id: str(row["label"]) for stat_id, row in stats.items()}


def _public_operation_label(operation_id: int, rules) -> str:
    return operation_label(operation_id, rules).replace(f"#{operation_id} · ", "").replace(" / ", " · ")


def _team_options() -> tuple[tuple[int, str], ...]:
    manifest = load_tournament_manifest(PATHS.tournament)
    return tuple((int(team.team_id), team.name) for team in manifest.teams)


def _clear_result() -> None:
    st.session_state.pop("current_advisor_result", None)


def _field_label(field_id: str) -> str:
    parts = field_id.split(".")
    if len(parts) == 4 and parts[0] == "banner":
        role = _ROLE_LABELS.get(parts[1], parts[1])
        attribute = {"stat": "Stat", "quality": "品质", "trait": "Trait"}.get(
            parts[3], parts[3]
        )
        return f"{role}第 {int(parts[2]) + 1} 格 {attribute}"
    if len(parts) == 2 and parts[0] == "offer":
        return f"选项 {int(parts[1]) + 1}"
    if field_id == "remaining_rolls":
        return "剩余 Roll 次数"
    return field_id


def _consume_pending_observation(rules) -> None:
    observation = st.session_state.pop("current_advisor_pending_observation", None)
    if observation is None:
        return
    for key, value in observation_widget_updates(observation, rules).items():
        st.session_state[key] = value
    st.session_state["current_advisor_last_observation"] = observation
    st.session_state.pop("current_advisor_result", None)
    if observation.get("status") == "confirmed":
        st.session_state["current_advisor_autocalculate"] = True


@st.fragment(run_every=1.0)
def _render_live_monitor_status() -> None:
    monitor = _cached_live_monitor()
    snapshot = monitor.snapshot()
    stage = snapshot.stage
    if stage == "error":
        st.error(snapshot.message)
    elif stage == "incomplete":
        st.warning(snapshot.message)
    elif stage == "confirmed":
        st.success(snapshot.message)
    else:
        st.caption(snapshot.message)

    observation = snapshot.observation
    last_generation = int(st.session_state.get("current_advisor_monitor_generation", -1))
    if observation is None or snapshot.generation <= last_generation:
        return
    st.session_state["current_advisor_monitor_generation"] = snapshot.generation
    if observation.get("status") not in {"incomplete", "confirmed"}:
        return
    st.session_state["current_advisor_pending_observation"] = observation
    st.rerun()


def _render_live_controls() -> None:
    st.subheader("自动读取游戏画面")
    st.caption(
        "点击后切回 Dota；程序读取下一张稳定的完整页面一次，然后自动停止。"
        "英文优先，同时支持简体中文。"
    )
    monitor = _cached_live_monitor()
    snapshot = monitor.snapshot()
    if snapshot.running:
        if st.button("取消本次识别", use_container_width=True):
            monitor.stop()
            st.rerun()
    elif st.button(
        "识别下一次稳定的 Dota 画面",
        type="primary",
        use_container_width=True,
        help=(
            "单屏时点击后用 Alt+Tab 切回 Dota；双屏时可以直接点击。"
            "只读取一次，不控制游戏。"
        ),
    ):
        monitor.start_once()
        st.rerun()
    _render_live_monitor_status()
    observation = st.session_state.get("current_advisor_last_observation")
    if observation is None:
        st.caption("等待期间可切回 Dota；识别完成后回到本页查看，也可以始终使用下方手填。")
        return
    captured_at = str(observation.get("captured_at", ""))
    fingerprint = str(observation.get("image_sha256", ""))[:12]
    if observation.get("status") == "incomplete":
        missing = [_field_label(item) for item in observation.get("missing_field_ids", [])]
        st.warning(
            "已自动填入可信字段；以下字段没有覆盖原值，也没有自动计算："
            + "、".join(missing)
        )
    else:
        st.caption("完整观测已自动写入表单；无需再点计算按钮。")
    st.caption(f"画面时间：{captured_at} · 图像指纹：{fingerprint}")


def _input_form(
    rules,
    *,
    manual_team_mode: bool,
    auto_calculate: bool = False,
) -> tuple[GroupRollState | None, Any, str, bool]:
    stat_labels = _stat_labels()
    team_options = _team_options()
    team_names = dict(team_options)
    positive_ids = tuple(item.operation_id for item in rules.offered_operations)
    with st.form("current_advisor_form"):
        st.subheader("1. 录入当前三面战旗")
        st.caption("每格只需选择 Stat、品质和 Trait。颜色与位置固定，页面会自动限制可选 Stat。")
        banners = []
        for role in rules.group_roles:
            with st.expander(_ROLE_LABELS[role], expanded=True):
                columns = st.columns(3)
                emblems = []
                for index, (column, color) in enumerate(
                    zip(columns, rules.colors_for(role)[:3], strict=True)
                ):
                    with column:
                        st.markdown(f"**第 {index + 1} 格 · {_COLOR_LABELS[color]}色**")
                        stat_key = f"current_advisor_{role}_{index}_stat"
                        stat_id = st.selectbox(
                            "Stat",
                            rules.stats_for(color),
                            index=None if stat_key in st.session_state else 0,
                            key=stat_key,
                            format_func=lambda item, labels=stat_labels: labels.get(item, item),
                        )
                        quality_key = f"current_advisor_{role}_{index}_quality"
                        quality = st.selectbox(
                            "品质",
                            (1, 2, 3, 4, 5),
                            index=None if quality_key in st.session_state else 0,
                            key=quality_key,
                            format_func=lambda item: f"Tier {item}",
                        )
                        trait_key = f"current_advisor_{role}_{index}_trait"
                        trait = st.selectbox(
                            "Trait",
                            rules.traits,
                            index=None if trait_key in st.session_state else 0,
                            key=trait_key,
                            format_func=lambda item: _TRAIT_LABELS.get(item, item),
                        )
                        emblems.append(EmblemState(stat_id, quality, trait))
                banners.append(BannerState(role, tuple(emblems)))

        st.subheader("2. 录入这一次看到的三个选项")
        st.caption("三个选项来自同一屏幕。系统不会猜下一轮；你操作后把这里改成游戏实际出现的新选项。")
        offer_columns = st.columns(3)
        offer_ids = []
        for index, column in enumerate(offer_columns):
            with column:
                offer_key = f"current_advisor_offer_{index}"
                offer_ids.append(
                    st.selectbox(
                        f"选项 {index + 1}",
                        positive_ids,
                        index=None if offer_key in st.session_state else index,
                        key=offer_key,
                        format_func=lambda item: _public_operation_label(item, rules),
                    )
                )
        remaining_key = "current_advisor_remaining"
        remaining = int(
            st.number_input(
                "剩余 Roll 次数",
                min_value=0,
                max_value=40,
                value=None if remaining_key in st.session_state else 40,
                step=1,
                key=remaining_key,
            )
        )

        selected_team_ids = None
        if manual_team_mode:
            st.subheader("3. 指定准备使用的队伍组合")
            st.caption("三个位置可来自不同队伍；历史样本始终跟随该位置的稳定选手 ID。")
            team_columns = st.columns(3)
            selected = []
            for role, column in zip(rules.group_roles, team_columns, strict=True):
                with column:
                    selected.append(
                        st.selectbox(
                            _ROLE_LABELS[role],
                            tuple(team_names),
                            key=f"current_advisor_team_{role}",
                            format_func=lambda item, names=team_names: names[item],
                        )
                    )
            selected_team_ids = tuple(selected)

        with st.expander("高级设置"):
            risk_profile = st.selectbox(
                "取舍方式",
                tuple(_RISK_LABELS),
                index=0,
                format_func=lambda item: _RISK_LABELS[item],
                key="current_advisor_risk",
            )
            st.caption("平衡模式允许牺牲最多 1% 的理论最高均值，换取更好的低迷情景表现。")
        submitted = st.form_submit_button("计算现在应该怎么选", type="primary", use_container_width=True)

    if len(set(offer_ids)) != 3:
        if submitted:
            st.error("三个 Roll 选项必须互不重复；请按游戏画面重新选择。")
        return None, selected_team_ids, risk_profile, False
    state = GroupRollState(
        banners=tuple(banners),
        offer=RollOffer(tuple(offer_ids)),
        remaining_rolls=remaining,
    )
    return state, selected_team_ids, risk_profile, submitted or auto_calculate


def _render_recommendation(result: dict[str, Any]) -> None:
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

    metrics = st.columns(4)
    metrics[0].metric("预计平均分变化", f"{recommendation['mean_delta']:+,.0f}")
    metrics[1].metric("低迷情景变化", f"{recommendation['cvar10_delta']:+,.0f}")
    metrics[2].metric("最差合法结果", f"{recommendation['support_lower']:+,.0f}")
    metrics[3].metric("最好合法结果", f"{recommendation['support_upper']:+,.0f}")
    st.caption("低迷情景是把所有可能结果放在一起，只看最差 10% 的平均表现。")
    if grade == "conditional":
        st.caption("这不是说一定会变差，而是这个选项的合法结果中仍含有回撤，或不同出率假设没有完全同意。")
    if grade == "refresh":
        st.caption("刷新只消耗一次 Roll 并换掉三个选项。下一屏出现什么不在计算内。")

    rows = []
    for index, row in enumerate(result["primary_action_values"], start=1):
        rows.append(
            {
                "建议顺序": index,
                "当前可执行动作": row["action_label"],
                "平均变化": round(float(row["mean_delta"])),
                "低迷情景变化": round(float(row["cvar10_delta"])),
                "最差～最好合法结果": (
                    f"{float(row['support_lower']):+,.0f} ～ {float(row['support_upper']):+,.0f}"
                ),
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _render_lineup_and_title(result: dict[str, Any]) -> None:
    st.subheader("当前队伍组合")
    current = result["current"]
    columns = st.columns(3)
    for column, role, team in zip(
        columns, ("core", "mid", "support"), current["selected_teams"], strict=True
    ):
        column.metric(_ROLE_LABELS[role], team)
    mode = "系统自动匹配" if result["team_mode"] == "auto" else "按你指定的组合"
    st.caption(f"{mode}。每个位置只计算该队对应位置的选手池，不按全队五人混算。")

    title = result["title"]
    prefix = title["recommended_prefix"]
    suffix = title["recommended_suffix"]
    st.subheader("自动 Title 建议")
    st.success(
        f"**{prefix['name']} + {suffix['name']}**\n\n"
        f"当前阵容下的纸面平均加成约 **+{title['estimated_pair_bonus_percent']:.2f}%**。"
    )
    title_columns = st.columns(2)
    with title_columns[0]:
        st.markdown("**Prefix 前三**")
        for row in title["prefixes"]:
            st.markdown(
                f"**{row['rank']}. {row['name']} · +{row['paper_bonus_percent']:.2f}%**  \n"
                f"{_TITLE_LABEL_OVERRIDES.get(row['id'], row['label'])} · "
                f"预计触发 {row['trigger_rate']:.1%}"
            )
    with title_columns[1]:
        st.markdown("**Suffix 前三**")
        for row in title["suffixes"]:
            st.markdown(
                f"**{row['rank']}. {row['name']} · +{row['paper_bonus_percent']:.2f}%**  \n"
                f"{_TITLE_LABEL_OVERRIDES.get(row['id'], row['label'])} · "
                f"预计触发 {row['trigger_rate']:.1%}"
            )
    st.caption(f"{title['method']} {title['limitation']}")


def _render_details(result: dict[str, Any], context: CurrentAdvisorContext) -> None:
    with st.expander("模型分歧与计算边界"):
        model_rows = []
        action_labels = {
            row["action_id"]: row["action_label"] for row in result["primary_action_values"]
        }
        for row in result["preferred_by_model"]:
            model_rows.append(
                {
                    "出率假设": _MODEL_LABELS.get(row["model_id"], row["model_id"]),
                    "首选动作": action_labels.get(row["action_id"], row["action_id"]),
                }
            )
        if model_rows:
            st.dataframe(pd.DataFrame(model_rows), hide_index=True, width="stretch")
        for limitation in result["limitations"]:
            st.warning(limitation)
        for warning in context.warnings:
            st.caption(warning)
        st.caption(f"数据截止：{result['as_of']} · 分析指纹：{result['analysis_sha256'][:12]}")


def render_advisor_page() -> None:
    st.title("Group Roll 实时顾问")
    st.write("本机可自动读取完整 Roll 页面，也可以继续手填；页面只推荐这一步怎么做。")
    st.caption("本地只读辅助：不控制 Dota、不猜下一轮选项。仅支持 Group 三格战旗。")

    try:
        rules = _cached_roll_rules()
        policy = _policy()
    except (OSError, ValueError) as error:
        st.error(f"当前客户端规则不可用：{error}")
        return

    if live_capture_supported():
        _consume_pending_observation(rules)
        _render_live_controls()
        st.divider()

    manual_team_mode = st.radio(
        "队伍组合",
        (False, True),
        format_func=lambda value: "系统自动选择" if not value else "我自己指定",
        horizontal=True,
        key="current_advisor_manual_team_mode",
        on_change=_clear_result,
    )
    auto_calculate = bool(st.session_state.pop("current_advisor_autocalculate", False))
    state, selected_team_ids, risk_profile, submitted = _input_form(
        rules,
        manual_team_mode=manual_team_mode,
        auto_calculate=auto_calculate,
    )
    if submitted and state is not None:
        try:
            with st.spinner("载入当前证据并计算所有可执行选择…首次打开约需十几秒。"):
                context = _cached_context(policy.as_of)
                result = analyze_current_screen(
                    context,
                    state,
                    risk_profile=risk_profile,
                    selected_team_ids=selected_team_ids,
                )
            st.session_state["current_advisor_result"] = result
        except (OSError, ValueError) as error:
            st.error(f"本次结果被阻断：{error}")
            st.session_state.pop("current_advisor_result", None)

    result = st.session_state.get("current_advisor_result")
    if result is None:
        st.info("完成输入后点击“计算现在应该怎么选”。")
        return
    try:
        context = _cached_context(policy.as_of)
    except (OSError, ValueError) as error:
        st.error(f"结果来源已经不可用：{error}")
        return
    st.divider()
    st.subheader("现在的结论")
    _render_recommendation(result)
    _render_lineup_and_title(result)
    _render_details(result, context)
    st.info(
        "在游戏里完成操作后，再点击一次“识别下一次稳定的 Dota 画面”并切回游戏；"
        "也可以手动修改实际发生变化的字段后重新计算。"
    )
