import streamlit as st

from components.header import render_header


def render_placeholder(title: str):
    render_header(title)

    st.markdown(
        f'<h1 class="page-title">{title}</h1>',
        unsafe_allow_html=True,
    )

    st.info(
        f"The {title} module will be implemented "
        "in an upcoming sprint."
    )