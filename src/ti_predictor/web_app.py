from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from ti_predictor.audit import audit_run
from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.fantasy.advisor_ui import render_advisor_page
from ti_predictor.fantasy.solver_release import default_solver_release_path
from ti_predictor.hashing import sha256_bytes
from ti_predictor.match_catalog import filter_match_catalog, utc_year_bounds
from ti_predictor.ocr import inspect_screenshot
from ti_predictor.paths import PATHS
from ti_predictor.reporting import discover_runs, filling_checklist
from ti_predictor.rules import validate_rules
from ti_predictor.storage import read_parquet_if_exists

st.set_page_config(page_title="TI 2026 决策台", page_icon="🏆", layout="wide")


def _runs(kind: str | None = None) -> list[dict]:
    return discover_runs(PATHS.artifacts, kind)


def _status_badge(status: str) -> None:
    if status == "publishable":
        st.success("可发布")
    elif status == "warning":
        st.warning("可审阅，但有警告")
    else:
        st.error("不可发布")


def _load_recommendations(run: dict) -> list[dict]:
    path = Path(run["_folder"]) / "recommendations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def data_page() -> None:
    st.title("数据与规则状态")
    rules = load_rules()
    tournament = load_tournament_manifest()
    issues = validate_rules(rules)
    blocking = [item for item in issues if item.severity == "blocking"]
    _status_badge("blocked" if blocking else ("warning" if issues else "publishable"))
    matches = read_parquet_if_exists(PATHS.processed / "matches.parquet")
    fantasy_samples = read_parquet_if_exists(PATHS.processed / "fantasy_performance_samples.parquet")
    rosters = read_parquet_if_exists(PATHS.processed / "roster_intervals.parquet")
    catalog_year = tournament.group_lock_at.year
    year_start, year_end = utc_year_bounds(catalog_year)
    year_catalog = filter_match_catalog(
        matches,
        start_at=year_start,
        end_before=year_end,
        pro_only=True,
    )
    detailed_games = (
        int(fantasy_samples["match_id"].nunique())
        if not fantasy_samples.empty and "match_id" in fantasy_samples
        else 0
    )

    st.subheader("本地数据")
    data_columns = st.columns(4)
    data_columns[0].metric(f"{catalog_year} 职业比赛目录", len(year_catalog))
    data_columns[1].metric("Fantasy 表现样本", len(fantasy_samples))
    data_columns[2].metric("已解析比赛详情", detailed_games)
    data_columns[3].metric("TI 审核阵容", len(rosters))
    st.caption(
        "Fantasy 表现样本 = 一名玩家在一局已结束比赛中的统计；它是模型输入，"
        "不是 Fantasy 预测。三位置卡片、徽标和教练选择请看 Fantasy 推荐页。"
    )

    st.subheader("比赛数据浏览器")
    if year_catalog.empty:
        st.warning(
            f"尚无 {catalog_year} 全年职业比赛目录。请运行 "
            f"`uv run ti data sync --as-of {catalog_year}-08-01T23:59:59Z --year {catalog_year}`。"
        )
    else:
        minimum_day = year_catalog["start_time"].min().date()
        maximum_day = year_catalog["start_time"].max().date()
        filter_columns = st.columns(3)
        with filter_columns[0]:
            selected_days = st.date_input(
                "时间（UTC）",
                value=(minimum_day, maximum_day),
                min_value=minimum_day,
                max_value=maximum_day,
            )
        patch_options = sorted(year_catalog["patch_name"].dropna().astype(str).unique())
        with filter_columns[1]:
            selected_patches = st.multiselect("游戏版本", patch_options, default=patch_options)
        tier_options = sorted(year_catalog["league_tier"].fillna("unknown").astype(str).unique())
        with filter_columns[2]:
            selected_tiers = st.multiselect("赛事级别", tier_options, default=tier_options)

        if isinstance(selected_days, (tuple, list)) and len(selected_days) == 2:
            selected_start = datetime.combine(selected_days[0], datetime.min.time(), tzinfo=UTC)
            selected_end = datetime.combine(
                selected_days[1] + timedelta(days=1), datetime.min.time(), tzinfo=UTC
            )
        else:
            selected_start, selected_end = year_start, year_end
        filtered = filter_match_catalog(
            year_catalog,
            start_at=selected_start,
            end_before=selected_end,
            patch_names=set(selected_patches),
            league_tiers=set(selected_tiers),
            pro_only=True,
        )
        st.caption(
            "赛事级别沿用 OpenDota 的 premium / professional / amateur / excluded / unknown，"
            "不擅自换算为社区 Tier 1/2/3。"
        )
        st.metric("筛选后比赛", len(filtered))
        display = filtered.copy()
        if "duration" in display:
            display["duration_minutes"] = (display["duration"] / 60).round(1)
        columns = [
            "start_time",
            "patch_name",
            "league_tier",
            "league_name",
            "radiant_team_name",
            "dire_team_name",
            "radiant_score",
            "dire_score",
            "radiant_win",
            "duration_minutes",
            "series_id",
            "match_id",
        ]
        st.dataframe(display[[column for column in columns if column in display]], hide_index=True)

    left, right = st.columns(2)
    with left:
        st.subheader("规则")
        st.metric("Fantasy 统计项", len(rules["fantasy"]["stats"]))
        st.metric("小组预测槽位", sum(item["count"] for item in rules["prediction"]["group"]["slots"]))
        st.dataframe(pd.DataFrame([item.model_dump() for item in issues]), hide_index=True)
    with right:
        st.subheader("客户端规则快照")
        snapshots = sorted((PATHS.raw / "rules").glob("*/rule_snapshot.json"), reverse=True)
        if snapshots:
            snapshot = json.loads(snapshots[0].read_text(encoding="utf-8"))
            st.caption(f"最新快照：{snapshot['snapshot_id']} · build {snapshot.get('steam_build')}")
        else:
            st.error("尚无本机客户端规则快照；请先运行 `uv run ti rules snapshot`。")


def recommendation_page(kind: str) -> None:
    title = "小组与主赛事预测" if kind == "prediction" else "Fantasy"
    st.title(title)
    available = _runs() if kind == "prediction" else _runs("fantasy")
    if kind == "prediction":
        available = [item for item in available if item["kind"] in {"group", "bracket"}]
    if not available:
        st.info("尚无运行产物。请先使用 CLI 同步数据并生成推荐。")
        return
    labels = [f"{item['run_id']} · {item['status']}" for item in available]
    selected = available[st.selectbox("运行", range(len(labels)), format_func=labels.__getitem__)]
    _status_badge(selected["status"])
    recommendations = _load_recommendations(selected)
    profile_names = [item["profile"] for item in recommendations]
    profile = st.radio("策略", profile_names, horizontal=True)
    recommendation = next(item for item in recommendations if item["profile"] == profile)
    if recommendation.get("warnings"):
        for warning in recommendation["warnings"]:
            st.warning(warning)
    checklist = filling_checklist(recommendation)
    st.subheader("按游戏界面顺序填写")
    st.dataframe(pd.DataFrame(checklist), hide_index=True, width="stretch")
    st.download_button(
        "导出填写清单 JSON",
        json.dumps(checklist, ensure_ascii=False, indent=2),
        file_name=f"{selected['run_id']}-{profile}-checklist.json",
        mime="application/json",
    )
    with st.expander("完整推荐与置信信息"):
        st.json(recommendation)
    if kind == "fantasy":
        ocr_panel()


def ocr_panel() -> None:
    st.subheader("个人战旗截图（可选第二阶段）")
    st.caption("只处理你主动上传的图片；OCR 草稿必须人工确认，不会控制 Steam。")
    uploaded = st.file_uploader("上传 Fantasy 截图", type=("png", "jpg", "jpeg", "webp"))
    if uploaded is None:
        return
    content = uploaded.getvalue()
    st.image(content, caption=uploaded.name)
    if st.button("在本机运行 OCR"):
        suffix = Path(uploaded.name).suffix.lower() or ".png"
        cache = PATHS.data / "cache" / "ocr"
        cache.mkdir(parents=True, exist_ok=True)
        image_path = cache / f"{sha256_bytes(content)[:16]}{suffix}"
        image_path.write_bytes(content)
        try:
            st.session_state["ocr_draft"] = inspect_screenshot(image_path)
        except RuntimeError as error:
            st.error(str(error))
    draft = st.session_state.get("ocr_draft")
    if draft:
        edited = st.data_editor(pd.DataFrame(draft["lines"]), width="stretch")
        confirmed = st.checkbox("我已逐项确认词条、品质和百分比")
        if confirmed:
            st.success("已确认本次 OCR 草稿；后续有限期重选模拟可以安全使用这些值。")
            st.json(edited.to_dict(orient="records"))


def audit_page() -> None:
    st.title("审计")
    available = _runs()
    if not available:
        st.info("尚无可审计运行。")
        return
    labels = [item["run_id"] for item in available]
    selected = st.selectbox("运行", labels)
    report = audit_run(selected, write=False)
    _status_badge(report["status"])
    st.metric("可发布", "是" if report["publishable"] else "否")
    st.dataframe(pd.DataFrame(report["issues"]), hide_index=True, width="stretch")
    st.json(report["output_sha256"])


manifest = load_tournament_manifest()
st.sidebar.title("TI 2026")
st.sidebar.caption(f"{manifest.display_name} · 仅监听 localhost")
page = st.sidebar.radio(
    "页面",
    ("数据与规则状态", "预测", "Fantasy", "Group Roll 实时顾问", "审计"),
)
if page == "数据与规则状态":
    data_page()
elif page == "预测":
    recommendation_page("prediction")
elif page == "Fantasy":
    recommendation_page("fantasy")
elif page == "Group Roll 实时顾问":
    render_advisor_page(release_bundle_path=default_solver_release_path())
else:
    audit_page()
