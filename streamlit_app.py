"""Public manual-only Streamlit entrypoint."""

import streamlit as st

from ti_predictor.fantasy.advisor_ui import render_advisor_page
from ti_predictor.fantasy.manual_release import default_manual_release_path

st.set_page_config(
    page_title="TI 2026 Group Roll 手动求解器",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_advisor_page(
    manual_only=True,
    release_bundle_path=default_manual_release_path(),
)
