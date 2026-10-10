
from pathlib import Path

import streamlit as st


def load_css() -> None:
    """Load the application theme and sidebar overrides."""

    styles_dir = Path(__file__).resolve().parent.parent / "styles"

    for filename in ("main.css", "sidebar.css"):
        css_file = styles_dir / filename

        if css_file.is_file():
            css = css_file.read_text(encoding="utf-8")

            st.markdown(
                f"<style>{css}</style>",
                unsafe_allow_html=True,
            )
