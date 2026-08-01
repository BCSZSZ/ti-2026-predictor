from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ti_predictor.audit import audit_run
from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.hashing import sha256_bytes
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
    issues = validate_rules(rules)
    blocking = [item for item in issues if item.severity == "blocking"]
    _status_badge("blocked" if blocking else ("warning" if issues else "publishable"))
    left, right = st.columns(2)
    with left:
        st.subheader("规则")
        st.metric("Fantasy 统计", len(rules["fantasy"]["stats"]))
        st.metric("小组预测槽位", sum(item["count"] for item in rules["prediction"]["group"]["slots"]))
        st.dataframe(pd.DataFrame([item.model_dump() for item in issues]), hide_index=True, width="stretch")
    with right:
        st.subheader("本地数据")
        for filename, label in (
            ("matches.parquet", "比赛"),
            ("fantasy_observations.parquet", "玩家逐局"),
            ("roster_intervals.parquet", "阵容区间"),
        ):
            frame = read_parquet_if_exists(PATHS.processed / filename)
            st.metric(label, len(frame))
        snapshots = sorted((PATHS.raw / "rules").glob("*/rule_snapshot.json"), reverse=True)
        if snapshots:
            snapshot = json.loads(snapshots[0].read_text(encoding="utf-8"))
            st.caption(f"最新客户端规则快照：{snapshot['snapshot_id']} · build {snapshot.get('steam_build')}")
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
page = st.sidebar.radio("页面", ("数据与规则状态", "预测", "Fantasy", "审计"))
if page == "数据与规则状态":
    data_page()
elif page == "预测":
    recommendation_page("prediction")
elif page == "Fantasy":
    recommendation_page("fantasy")
else:
    audit_page()
