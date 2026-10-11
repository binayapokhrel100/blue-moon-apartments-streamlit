
import html
from textwrap import dedent

import streamlit as st

from components.header import render_header
from services.community_news_service import (
    get_active_community_news,
)


# ==========================================
# COMMUNITY NEWS CATEGORY ICONS
# ==========================================

CATEGORY_ICONS = {
    "Community": "⌂",
    "Transportation": "↔",
    "Events": "☆",
    "Safety": "◇",
    "Lifestyle": "♡",
    "Local Services": "▣",
}


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _safe_text(value) -> str:
    """
    Escape dynamic content before
    inserting it into HTML.
    """

    if value is None:
        return ""

    return html.escape(
        str(value),
        quote=True,
    )


def _format_date(value) -> str:
    """
    Format the publication date.
    """

    if value is None:
        return "Date unavailable"

    return value.strftime(
        "%b %d, %Y"
    ).replace(
        " 0",
        " ",
    )


# ==========================================
# COMMUNITY NEWS CARD
# ==========================================

def _render_community_news_card(
    item: dict,
) -> None:
    """
    Render a community news card using
    the existing Blue Moon CSS classes.
    """

    # --------------------------------------
    # News title
    # --------------------------------------

    title = _safe_text(
        item.get("title", "")
    )

    # --------------------------------------
    # News summary
    # --------------------------------------

    summary = _safe_text(
        item.get("summary", "")
    )

    # --------------------------------------
    # News category
    # --------------------------------------

    category_value = (
        item.get("category")
        or "Community"
    )

    category = _safe_text(
        category_value
    )

    # --------------------------------------
    # News source
    # --------------------------------------

    source_name = _safe_text(
        item.get("source_name")
        or "Blue Moon Community"
    )

    # --------------------------------------
    # Category icon
    # --------------------------------------

    icon = CATEGORY_ICONS.get(
        category_value,
        "●",
    )

    # --------------------------------------
    # Publication date
    # --------------------------------------

    date_text = _safe_text(
        _format_date(
            item.get("published_at")
        )
    )

    # ======================================
    # COMMUNITY NEWS HTML
    # ======================================

    news_html = dedent(
        f"""
        <div class="community-news-card">

            <div class="community-news-icon">
                {icon}
            </div>

            <div class="community-news-content">

                <div class="community-news-meta-top">

                    <span>
                        {category}
                    </span>

                    <span>
                        {date_text}
                    </span>

                </div>

                <h3>
                    {title}
                </h3>

                <p>
                    {summary}
                </p>

                <div class="community-news-source">
                    Source: {source_name}
                </div>

            </div>

        </div>
        """
    ).strip()

    # IMPORTANT:
    # st.html() renders HTML directly.
    # This prevents raw HTML from
    # appearing as text in Streamlit.

    st.html(
        news_html
    )


# ==========================================
# MAIN COMMUNITY NEWS PAGE
# ==========================================

def render_community_news() -> None:
    """
    Render the complete Community News
    page for Blue Moon Apartments.
    """

    # ======================================
    # PAGE HEADER
    # ======================================

    render_header(
        "Community News"
    )

    header_html = dedent(
        """
        <h1 class="page-title">
            Community News
        </h1>

        <p class="page-description">
            Local updates, events and useful
            information for Blue Moon residents.
        </p>
        """
    ).strip()

    st.html(
        header_html
    )

    # ======================================
    # FETCH ACTIVE COMMUNITY NEWS
    # ======================================

    news_items = (
        get_active_community_news()
    )

    # ======================================
    # EMPTY STATE
    # ======================================

    if not news_items:

        st.info(
            "No community news is "
            "available right now."
        )

        return

    # ======================================
    # CATEGORY FILTER
    # ======================================

    categories = sorted(
        {
            item.get("category") or "Community"
            for item in news_items
        }
    )

    selected_category = st.selectbox(
        "Filter news",
        [
            "All",
            *categories,
        ],
        key="community_news_category_filter",
    )

    # ======================================
    # FILTER NEWS ITEMS
    # ======================================

    if selected_category != "All":

        news_items = [
            item
            for item in news_items
            if (
                item.get("category")
                or "Community"
            ) == selected_category
        ]

    # ======================================
    # SPACING
    # ======================================

    st.html(
        '<div style="height: 12px;"></div>'
    )

    # ======================================
    # DISPLAY COMMUNITY NEWS
    # ======================================

    if not news_items:

        st.info(
            "No community news found "
            "for the selected category."
        )

        return

    for item in news_items:

        _render_community_news_card(
            item
        )
