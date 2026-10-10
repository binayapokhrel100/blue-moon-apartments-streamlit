from pathlib import Path

import streamlit as st


def load_css():
    css_file = Path(__file__).parent.parent / "styles" / "main.css"

    if css_file.exists():
        with open(css_file, "r", encoding="utf-8") as file:
            st.markdown(
                f"<style>{file.read()}</style>",
                unsafe_allow_html=True,
            )