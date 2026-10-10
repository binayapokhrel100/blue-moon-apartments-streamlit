import streamlit as st


def render_header(title: str):
    st.markdown(
        f"""
        <div class="page-header">
            <div class="breadcrumb">
                ⌂ &nbsp; Blue Moon Apartments
                &nbsp; › &nbsp;
                <strong>{title}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )