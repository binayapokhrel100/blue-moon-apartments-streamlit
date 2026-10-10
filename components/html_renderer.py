
"""Shared HTML renderer for Blue Moon Apartments."""

from textwrap import dedent

import streamlit as st


def render_html(markup: str) -> None:
    """
    Render trusted HTML without Markdown treating
    indented HTML as a code block.
    """
    cleaned = "\n".join(
        line.lstrip()
        for line in dedent(markup).strip().splitlines()
    )

    st.markdown(
        cleaned,
        unsafe_allow_html=True,
    )
