"""Streamlit surface for the experimental, local-only Group Roll advisor."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ti_predictor.config import load_rules
from ti_predictor.fantasy.advisor import (
    AdvisorSession,
    AdvisorSessionError,
    action_identity,
    action_label,
    legal_realized_banners,
    load_advisor_policy,
    mutation_outcome_label,
    operation_label,
    state_sha256,
)
from ti_predictor.fantasy.advisor_analysis import (
    AdvisorContext,
    analyze_advisor_state,
    load_advisor_roll_rules,
    prepare_advisor_context,
    run_optional_solver,
)
from ti_predictor.fantasy.roll import (
    ApplyRollAction,
    BannerState,
    EmblemState,
    GroupRollState,
    RefreshRollAction,
    RollOffer,
    legal_actions,
    validate_group_state,
)
from ti_predictor.paths import PATHS

_ROLE_LABELS = {"core": "Carry", "mid": "Mid", "support": "Support"}
_COLOR_LABELS = {"red": "红", "blue": "蓝", "green": "绿"}
_TRAIT_LABELS = {
    "fractal": "Fractal（品质互异）",
    "benevolent": "Benevolent（友爱/邻格 +20%）",
    "vampiric": "Vampiric（吸血/自身 +50%，邻格 -10%）",
    "unique": "Unique（全旗唯一）",
    "friendly": "Friendly（三格同款）",
}
_RISK_LABELS = {
    "mean-first": "均值优先",
    "default-knee": "默认折点",
    "downside-first": "下行优先",
}
_EDITION_LABELS = {
    "rate-agnostic": "无关出率版",
    "primary-model": "最佳猜测出率版",
}


@st.cache_resource(show_spinner=False)
def _cached_roll_rules():
    return load_advisor_roll_rules()


@st.cache_resource(show_spinner=False)
def _cached_context(as_of: str) -> AdvisorContext:
    return prepare_advisor_context(as_of=as_of)


def _policy():
    return load_advisor_policy(
        PATHS.config / "models" / "fantasy-group-interactive-advisor-v1.json"
    )


def _stat_labels() -> dict[str, str]:
    stats = load_rules()["fantasy"]["stats"]
    return {
        stat_id: f"{row['label']} · {stat_id}"
        for stat_id, row in stats.items()
    }


def _clear_computed_results() -> None:
    for key in (
        "group_advisor_analysis_key",
        "group_advisor_analysis",
        "group_advisor_solver_key",
        "group_advisor_solver",
    ):
        st.session_state.pop(key, None)


def _initial_state_form(rules) -> GroupRollState | None:
    stat_labels = _stat_labels()
    st.subheader("1. 手工确认当前 Group 状态")
    st.caption("按 Carry → Mid → Support、每面从左到右录入。九格、三个选项缺一不可。")
    banners = []
    for role in rules.group_roles:
        with st.expander(_ROLE_LABELS[role], expanded=True):
            columns = st.columns(3)
            emblems = []
            for index, (column, color) in enumerate(
                zip(columns, rules.colors_for(role)[:3], strict=True)
            ):
                with column:
                    st.markdown(f"{index + 1}. {_COLOR_LABELS[color]}色")
                    stats = rules.stats_for(color)
                    stat_id = st.selectbox(
                        "Stat",
                        stats,
                        key=f"advisor_initial_{role}_{index}_stat",
                        format_func=lambda item, labels=stat_labels: labels.get(item, item),
                    )
                    quality = st.selectbox(
                        "品质",
                        (1, 2, 3, 4, 5),
                        key=f"advisor_initial_{role}_{index}_quality",
                        format_func=lambda item: f"T{item}",
                    )
                    trait = st.selectbox(
                        "Trait",
                        rules.traits,
                        key=f"advisor_initial_{role}_{index}_trait",
                        format_func=lambda item: _TRAIT_LABELS.get(item, item),
                    )
                    emblems.append(EmblemState(stat_id, quality, trait))
            banners.append(BannerState(role, tuple(emblems)))

    positive_ids = tuple(item.operation_id for item in rules.offered_operations)
    offer = st.multiselect(
        "当前共享的三个 Roll 选项",
        positive_ids,
        default=positive_ids[:3],
        max_selections=3,
        key="advisor_initial_offer",
        format_func=lambda item: operation_label(item, rules),
    )
    remaining = int(
        st.number_input(
            "剩余 Roll",
            min_value=1,
            max_value=40,
            value=40,
            step=1,
            key="advisor_initial_remaining",
        )
    )
    if len(offer) != 3:
        st.warning("必须确认恰好三个不同的正权重选项。")
        return None
    return GroupRollState(
        banners=tuple(banners),
        offer=RollOffer(tuple(offer)),
        remaining_rolls=remaining,
    )


def _state_rows(state: GroupRollState, rules) -> list[dict[str, Any]]:
    stat_labels = _stat_labels()
    rows = []
    for banner in state.banners:
        for index, (emblem, color) in enumerate(
            zip(banner.emblems, rules.colors_for(banner.role)[:3], strict=True),
            start=1,
        ):
            rows.append(
                {
                    "位置": _ROLE_LABELS[banner.role],
                    "格": index,
                    "颜色": _COLOR_LABELS[color],
                    "Stat": stat_labels.get(emblem.stat_id, emblem.stat_id),
                    "品质": f"T{emblem.quality_tier}",
                    "Trait": _TRAIT_LABELS.get(emblem.trait_id, emblem.trait_id),
                }
            )
    return rows


def _session_loader(rules, context: AdvisorContext | None) -> None:
    with st.expander("加载并重放已保存会话"):
        uploaded = st.file_uploader(
            "会话 JSON",
            type=("json",),
            key="group_advisor_session_upload",
        )
        if st.button("校验并重放", disabled=uploaded is None, key="group_advisor_replay"):
            try:
                expected = None if context is None else context.baseline
                replayed = AdvisorSession.from_json(
                    uploaded.getvalue(),
                    rules,
                    expected_baseline=expected,
                )
                st.session_state["group_advisor_session_json"] = replayed.as_json(rules)
                _clear_computed_results()
                st.rerun()
            except (AdvisorSessionError, ValueError) as error:
                st.error(f"会话拒绝加载：{error}")


def _load_current_session(context: AdvisorContext, rules) -> AdvisorSession:
    saved = st.session_state["group_advisor_session_json"]
    return AdvisorSession.from_json(saved, rules, expected_baseline=context.baseline)


def _analysis_for(
    context: AdvisorContext,
    session: AdvisorSession,
    rules,
    *,
    edition: str,
    risk_preference: str,
) -> dict[str, Any]:
    state = session.current_state(rules)
    key = (
        state_sha256(state),
        context.baseline.semantic_hash,
        edition,
        risk_preference,
    )
    if st.session_state.get("group_advisor_analysis_key") != key:
        with st.spinner("计算一步精确分布（不含未来 offer 价值）…"):
            st.session_state["group_advisor_analysis"] = analyze_advisor_state(
                context,
                state,
                edition=edition,
                risk_preference=risk_preference,
            )
        st.session_state["group_advisor_analysis_key"] = key
    return st.session_state["group_advisor_analysis"]


def _render_diagnostic(
    context: AdvisorContext,
    state: GroupRollState,
    analysis: dict[str, Any],
    *,
    selected_model: str,
    selected_epsilon: float,
) -> None:
    manual = analysis["manual"]
    st.subheader("2. 人工手册结论（第一优先）")
    st.warning(
        f"{_EDITION_LABELS[manual['edition']]}仍是 {manual['status']}；"
        "这是冻结人工规则的当前分支，不是全局最优证明。"
    )
    st.info(f"建议：{manual['action_label']}\n\n依据：{manual['explanation']}")

    st.subheader("3. 一步诊断（第二意见）")
    st.caption(
        "下面精确枚举本次 mutation 与 128 个留出比赛情景；不估计下一组 offer 的期权价值，"
        "也不计算剩余 Roll 的未来可达性。刷新 delta=0 只表示这层没有给未来 offer 定价。"
    )
    selected_rows = [
        row
        for row in analysis["action_values"]
        if row["model_id"] == selected_model and row["epsilon"] == selected_epsilon
    ]
    preferred = next(
        (
            row
            for row in analysis["preferred_actions"]
            if row["model_id"] == selected_model and row["epsilon"] == selected_epsilon
        ),
        None,
    )
    table = []
    for row in selected_rows:
        table.append(
            {
                "动作": row["action_label"],
                "手册": row["action_id"] == manual["action_id"],
                "一步首选": preferred is not None and row["action_id"] == preferred["action_id"],
                "期望总分": round(row["mean"], 2),
                "期望变化": round(row["mean_delta"], 2),
                "CVaR10": round(row["cvar10"], 2),
                "CVaR10 变化": round(row["cvar10_delta"], 2),
                "无关出率下界": round(row["rate_agnostic_lower"], 2),
                "无关出率上界": round(row["rate_agnostic_upper"], 2),
            }
        )
    if table:
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
        st.caption(
            f"当前选择：{selected_model} · epsilon={selected_epsilon:.0%} · "
            f"完整计算 {analysis['runtime_seconds']['total']:.2f}s"
        )
    else:
        st.info("Roll 已用完，没有可执行动作。")

    matching = next(
        row for row in analysis["current_matching"] if row["epsilon"] == selected_epsilon
    )
    st.subheader("4. 当前战旗的最终队伍匹配")
    team_columns = st.columns(3)
    for column, role, team_name, team_id in zip(
        team_columns,
        ("core", "mid", "support"),
        matching["selected_teams"],
        matching["selected_team_ids"],
        strict=True,
    ):
        column.metric(_ROLE_LABELS[role], team_name, help=f"stable team_id={team_id}")
    st.caption(
        f"Group 总分期望 {matching['mean']:.2f}；CVaR10 {matching['cvar10']:.2f}；"
        "三个位置可分别匹配战队。"
    )

    with st.expander("模型分歧、证据状态与限制"):
        st.dataframe(pd.DataFrame(analysis["model_sensitivity"]), hide_index=True)
        st.json(analysis["source_status"])
        for limitation in analysis["limitations"]:
            st.warning(limitation)
        st.caption(f"state_sha256: {state_sha256(state)}")


def _observed_transition_panel(
    session: AdvisorSession,
    context: AdvisorContext,
    rules,
) -> None:
    state = session.current_state(rules)
    st.subheader("5. 实际 Roll 后更新 Observed state")
    st.caption("这里不控制客户端。先在游戏里操作，再回来确认画面实际出现的结果。")
    if state.remaining_rolls == 0:
        st.success("40 次中的可用 Roll 已耗尽；保留当前战旗并使用上面的队伍匹配。")
        return
    actions = legal_actions(state, rules)
    action_ids = tuple(action_identity(action) for action in actions)
    action_by_id = {action_identity(action): action for action in actions}
    selected_id = st.selectbox(
        "你在游戏里实际选择的动作",
        action_ids,
        key="group_advisor_observed_action",
        format_func=lambda item: action_label(action_by_id[item], rules),
    )
    selected_action = action_by_id[selected_id]
    realized = None
    if isinstance(selected_action, ApplyRollAction):
        current_banner = next(
            banner for banner in state.banners if banner.role == selected_action.banner_role
        )
        outcomes = legal_realized_banners(state, selected_action, rules)
        outcome_indexes = tuple(range(len(outcomes)))
        selected_outcome = st.selectbox(
            "画面实际实现的战旗结果",
            outcome_indexes,
            key=f"group_advisor_outcome_{selected_id}",
            format_func=lambda index: mutation_outcome_label(current_banner, outcomes[index]),
        )
        realized = outcomes[selected_outcome]
    else:
        st.info("刷新只更换三个选项，九格战旗必须保持不变。")

    positive_ids = tuple(item.operation_id for item in rules.offered_operations)
    replacement = st.multiselect(
        "本次消耗后画面显示的新三个共享选项",
        positive_ids,
        default=list(state.offer.operation_ids),
        max_selections=3,
        key=f"group_advisor_replacement_{state_sha256(state)}_{selected_id}",
        format_func=lambda item: operation_label(item, rules),
    )
    confirmed = st.checkbox(
        "我已逐项核对动作、实现结果和新三个选项",
        key=f"group_advisor_confirm_{state_sha256(state)}_{selected_id}",
    )
    if st.button(
        "记录这次已观察结果并重新规划",
        type="primary",
        disabled=not confirmed or len(replacement) != 3,
        key=f"group_advisor_apply_event_{state_sha256(state)}_{selected_id}",
    ):
        try:
            offer = RollOffer(tuple(replacement))
            if isinstance(selected_action, RefreshRollAction):
                updated = session.refresh_observed(offer, rules)
            else:
                if realized is None:
                    raise AdvisorSessionError("apply action lacks a manually confirmed result")
                updated = session.apply_observed(selected_action, realized, offer, rules)
            if updated.baseline != context.baseline:
                raise AdvisorSessionError("locked baseline changed during an observed transition")
            st.session_state["group_advisor_session_json"] = updated.as_json(rules)
            _clear_computed_results()
            st.rerun()
        except (AdvisorSessionError, ValueError) as error:
            st.error(f"状态没有更新：{error}")


def _optional_solver_panel(
    context: AdvisorContext,
    state: GroupRollState,
    *,
    selected_model: str,
    selected_epsilon: float,
) -> None:
    with st.expander("按需运行 P5 简化求解器（次要、失败门禁）"):
        st.error(
            "P5 effectiveness = failed-escalation-review-required。结果近似且不保证全局最优；"
            "未决时实际动作是无关出率 fallback。"
        )
        if state.remaining_rolls == 0:
            st.info("没有剩余 Roll，求解器不再提供动作。")
            return
        if state.remaining_rolls > 1:
            st.warning(
                "当前只开放最后 1 次 Roll 的按需求解：实测约 9 秒。P5 长视野历史中位数约 "
                "749 秒，超过本地交互的 60 秒目标；较早阶段请使用人工手册与一步诊断。"
            )
            return
        key = (state_sha256(state), selected_model, selected_epsilon)
        if st.button("我理解限制，运行一次求解器", key="group_advisor_run_solver"):
            with st.spinner("运行分支截断求解器…"):
                st.session_state["group_advisor_solver"] = run_optional_solver(
                    context,
                    state,
                    model_id=selected_model,
                    epsilon=selected_epsilon,
                )
                st.session_state["group_advisor_solver_key"] = key
        if st.session_state.get("group_advisor_solver_key") == key:
            result = st.session_state["group_advisor_solver"]
            if result["resolved"]:
                st.warning("本次内部确认已分离候选，但 P5 总体失败门禁仍然有效。")
            else:
                st.error("本次候选未决；必须看 executed fallback，不能把 preferred 当成确定答案。")
            st.write(f"preferred：{result['preferred_action_label']}")
            st.write(f"executed：{result['executed_action_label']}")
            st.caption(
                f"screen={result['screening_paths_per_action']}/action；"
                f"confirm={result['confirmation_paths_per_finalist']}/finalist；"
                f"runtime={result['runtime_seconds']:.2f}s"
            )
            st.json(result)


def render_advisor_page() -> None:
    st.title("Group 40-Roll 顾问（实验）")
    st.error(
        "人工手册仍为 draft；P5 求解器 effectiveness 失败；P6 仅 partial-draft。"
        "本页是本地辅助记录器，不是自动操作器或最优性证明。"
    )
    st.caption("仅 Group 40 次 Roll；Main 接口预留但执行层 fail closed。")
    period = st.radio("阶段", ("Group", "Main（预留）"), horizontal=True, key="advisor_period")
    if period != "Group":
        st.error("Main 的五格规则尚未冻结，本页拒绝创建、加载或推进 Main 状态。")
        return

    try:
        rules = _cached_roll_rules()
        policy = _policy()
    except (OSError, ValueError) as error:
        st.error(f"冻结规则不可用：{error}")
        return

    saved = st.session_state.get("group_advisor_session_json")
    if saved is None:
        _session_loader(rules, None)
        initial_state = _initial_state_form(rules)
        if st.button(
            "确认录入并创建 Locked baseline",
            type="primary",
            disabled=initial_state is None,
            key="group_advisor_create",
        ):
            try:
                if initial_state is None:
                    raise AdvisorSessionError("initial state is incomplete")
                validate_group_state(initial_state, rules)
                with st.spinner("验证 P3–P6 冻结证据并加载 128 个留出情景…"):
                    context = _cached_context(policy.as_of)
                session = AdvisorSession.create(context.baseline, initial_state, rules)
                st.session_state["group_advisor_session_json"] = session.as_json(rules)
                _clear_computed_results()
                st.rerun()
            except (OSError, ValueError) as error:
                st.error(f"会话没有创建：{error}")
        return

    try:
        with st.spinner("校验 Locked baseline 与会话重放…"):
            context = _cached_context(policy.as_of)
            session = _load_current_session(context, rules)
        state = session.current_state(rules)
    except (OSError, ValueError) as error:
        st.error(f"当前会话被阻断：{error}")
        if st.button("丢弃本页会话并重新录入", key="group_advisor_discard_blocked"):
            st.session_state.pop("group_advisor_session_json", None)
            _clear_computed_results()
            st.rerun()
        return

    header = st.columns(4)
    header[0].metric("剩余 Roll", state.remaining_rolls)
    header[1].metric("已确认事件", len(session.events))
    header[2].metric("上下文加载", f"{context.context_load_seconds:.2f}s")
    header[3].metric("P6", context.p6_status)
    st.dataframe(pd.DataFrame(_state_rows(state, rules)), hide_index=True, width="stretch")
    st.write("当前三个选项：")
    for operation_id in state.offer.operation_ids:
        st.write(f"- {operation_label(operation_id, rules)}")

    controls = st.columns(4)
    with controls[0]:
        edition = st.selectbox(
            "人工手册",
            tuple(context.manuals),
            format_func=lambda item: _EDITION_LABELS[item],
            key="group_advisor_edition",
        )
    with controls[1]:
        risk_preference = st.selectbox(
            "手册风险偏好",
            tuple(_RISK_LABELS),
            index=1,
            format_func=lambda item: _RISK_LABELS[item],
            key="group_advisor_risk",
        )
    with controls[2]:
        selected_model = st.selectbox(
            "一步出率模型",
            context.policy.quick_analysis.models,
            key="group_advisor_model",
        )
    with controls[3]:
        selected_epsilon = st.selectbox(
            "期望损失阀门",
            context.policy.quick_analysis.mean_retention_epsilons,
            index=1,
            format_func=lambda item: f"{item:.0%}",
            key="group_advisor_epsilon",
        )

    analysis = _analysis_for(
        context,
        session,
        rules,
        edition=edition,
        risk_preference=risk_preference,
    )
    _render_diagnostic(
        context,
        state,
        analysis,
        selected_model=selected_model,
        selected_epsilon=selected_epsilon,
    )
    _observed_transition_panel(session, context, rules)
    _optional_solver_panel(
        context,
        state,
        selected_model=selected_model,
        selected_epsilon=selected_epsilon,
    )

    st.subheader("会话保存与边界")
    st.download_button(
        "下载可重放会话 JSON",
        session.as_json(rules),
        file_name="ti2026-group-roll-session.json",
        mime="application/json",
        key="group_advisor_download",
    )
    _session_loader(rules, context)
    if st.button("结束并清除本页会话", key="group_advisor_discard"):
        st.session_state.pop("group_advisor_session_json", None)
        _clear_computed_results()
        st.rerun()
    st.caption(
        "服务仅监听 127.0.0.1；不保存 Steam 凭据，不控制 Dota 客户端，不自动填写，"
        "本局观测不会修改出率权重。"
    )
