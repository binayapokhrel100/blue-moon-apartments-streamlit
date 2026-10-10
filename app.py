import streamlit as st

from core.config import APP_NAME


st.set_page_config(
    page_title=APP_NAME,
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    st.title("🌙 Blue Moon Apartments")

    st.subheader("Resident Portal")

    st.info(
        "Blue Moon Apartments project foundation is running successfully."
    )

    st.write(
        "This application will provide resident payments, maintenance, "
        "notifications, lease management, security, community news, "
        "and administrative services."
    )


if __name__ == "__main__":
    main()