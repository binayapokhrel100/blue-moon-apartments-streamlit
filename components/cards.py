
import html
from textwrap import dedent

import streamlit as st


def metric_card(
    title: str,
    value: str,
    subtitle: str = "",
):
    safe_title = html.escape(str(title))
    safe_value = html.escape(str(value))
    safe_subtitle = html.escape(str(subtitle))

    card_html = dedent(f"""
    <div class="metric-card">
        <div class="metric-title">{safe_title}</div>
        <div class="metric-value">{safe_value}</div>
        <div class="metric-subtitle">{safe_subtitle}</div>
    </div>
    """).strip()

    st.markdown(
        card_html,
        unsafe_allow_html=True,
    )
