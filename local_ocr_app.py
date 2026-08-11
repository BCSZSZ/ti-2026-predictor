"""Windows-local OCR Streamlit entrypoint backed by the Frozen Solver Release."""

import streamlit as st

from ti_predictor.fantasy.advisor_ui import render_advisor_page
from ti_predictor.fantasy.solver_release import default_solver_release_path

st.set_page_config(
    page_title="TI 2026 Group Roll 本地 OCR 顾问",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_advisor_page(
    manual_only=False,
    release_bundle_path=default_solver_release_path(),
)
