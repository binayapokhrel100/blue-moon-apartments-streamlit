
"""Offline Blue Moon Assistant user interface.

Chat history exists only in the current Streamlit session.
"""

import logging

import streamlit as st

from components.header import render_header
from core.session import get_current_user
from services.assistant_service import (
    SUGGESTED_QUESTIONS,
    ask_resident_assistant,
)


logger = logging.getLogger(__name__)


# ==========================================
# WELCOME MESSAGE
# ==========================================

def _welcome(first_name: str) -> str:

    return (
        f"Hello, {first_name}! "
        "I'm Blue Moon Assistant. "
        "I can help with lease details, "
        "recorded payments, maintenance requests, "
        "announcements, and community news. "
        "What would you like to know?"
    )


# ==========================================
# MAIN ASSISTANT PAGE
# ==========================================

def render_assistant() -> None:

    # ======================================
    # AUTHENTICATED RESIDENT
    # ======================================

    user = get_current_user() or {}

    user_id = user.get("id")

    if (
        user_id is None
        or user.get("role") != "resident"
    ):

        st.error(
            "Blue Moon Assistant is available "
            "to signed-in residents only."
        )

        return

    first_name = str(
        user.get("first_name") or "Resident"
    )

    # ======================================
    # INITIALIZE CHAT HISTORY
    # ======================================

    # Reset conversation if a different
    # resident signs in to this session.

    if (
        st.session_state.get("assistant_user_id")
        != user_id
    ):

        st.session_state.assistant_user_id = (
            user_id
        )

        st.session_state.assistant_messages = [
            {
                "role": "assistant",
                "content": _welcome(first_name),
            }
        ]

    # ======================================
    # PAGE HEADER
    # ======================================

    render_header("Blue Moon Assistant")

    st.html(
        """
        <h1 class="page-title">
            Blue Moon Assistant
        </h1>

        <p class="page-description">
            Ask about your apartment, lease,
            payments, maintenance, and community.
            Answers come from your recorded information.
        </p>
        """
    )

    # ======================================
    # STATUS AND CLEAR CHAT BUTTON
    # ======================================

    header_col, clear_col = st.columns(
        [5, 1]
    )

    with header_col:

        st.caption(
            "Offline · Read-only · "
            "Resident-specific information"
        )

    with clear_col:

        clear_clicked = st.button(
            "Clear chat",
            use_container_width=True,
        )

        if clear_clicked:

            st.session_state.assistant_messages = [
                {
                    "role": "assistant",
                    "content": _welcome(first_name),
                }
            ]

            st.rerun()

    # ======================================
    # SUGGESTED QUESTIONS
    # ======================================

    st.markdown(
        "**Try a question**"
    )

    cols = st.columns(2)

    suggested_question = None

    for i, suggestion in enumerate(
        SUGGESTED_QUESTIONS
    ):

        with cols[i % 2]:

            if st.button(
                suggestion,
                key=f"assistant_suggestion_{i}",
                use_container_width=True,
            ):

                suggested_question = suggestion

    st.divider()

    # ======================================
    # DISPLAY CHAT HISTORY
    # ======================================

    for message in (
        st.session_state.assistant_messages
    ):

        role = message["role"]

        with st.chat_message(
            role,
            avatar=(
                "🌙"
                if role == "assistant"
                else None
            ),
        ):

            if role == "assistant":

                st.markdown(
                    message["content"]
                )

            else:

                st.write(
                    message["content"]
                )

    # ======================================
    # CHAT INPUT
    # ======================================

    typed_question = st.chat_input(
        "Ask about your lease, payments, maintenance...",
        max_chars=500,
    )

    question = (
        typed_question
        or suggested_question
    )

    if not question:
        return

    # ======================================
    # SAVE USER MESSAGE
    # ======================================

    st.session_state.assistant_messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    with st.chat_message("user"):

        st.write(
            question
        )

    # ======================================
    # GENERATE ASSISTANT RESPONSE
    # ======================================

    with st.chat_message(
        "assistant",
        avatar="🌙",
    ):

        with st.spinner(
            "Checking your Blue Moon records..."
        ):

            try:

                answer = ask_resident_assistant(
                    user_id,
                    question,
                )

            except (
                ValueError,
                PermissionError,
            ) as error:

                logger.warning(
                    "Assistant request rejected: %s",
                    error,
                )

                answer = (
                    "I couldn't access your resident "
                    "information. Please sign in again."
                )

            except Exception:

                logger.exception(
                    "Unexpected Blue Moon Assistant error."
                )

                answer = (
                    "Something went wrong. "
                    "Please try again later."
                )

        st.markdown(
            answer
        )

    # ======================================
    # SAVE ASSISTANT RESPONSE
    # ======================================

    st.session_state.assistant_messages.append(
        {
            "role": "assistant",
            "content": answer,
        }
    )

    # ======================================
    # LIMIT STORED CHAT HISTORY
    # ======================================

    # Keep the welcome message plus the
    # most recent 40 conversation messages.

    st.session_state.assistant_messages = (
        st.session_state.assistant_messages[:1]
        + st.session_state.assistant_messages[1:][-40:]
    )
