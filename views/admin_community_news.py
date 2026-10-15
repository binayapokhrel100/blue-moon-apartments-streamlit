
"""Sprint 09: create, edit, and manage community news visibility."""

import logging

import streamlit as st

from core.session import get_current_user
from services.admin_content_service import (
    create_admin_community_news,
    get_admin_community_news,
    update_admin_community_news,
)


logger = logging.getLogger(__name__)


# ==================================================
# SAVE HANDLER
# ==================================================

def _save(
    action,
    success: str,
    revision_key: str,
) -> None:

    try:
        action()

    except (ValueError, PermissionError) as exc:
        st.error(str(exc))

    except Exception:
        logger.exception(
            "Cannot save community news"
        )
        st.error(
            "Could not save community news. "
            "Please try again."
        )

    else:
        st.session_state[
            revision_key
        ] = (
            st.session_state.get(
                revision_key, 0
            ) + 1
        )

        st.session_state[
            "bm_admin_news_flash"
        ] = success

        st.rerun()


# ==================================================
# ADMIN COMMUNITY NEWS PAGE
# ==================================================

def render_admin_community_news() -> None:

    session = get_current_user() or {}

    if (
        str(session.get("role", ""))
        .strip().lower() != "admin"
    ):
        st.error(
            "Administrator access required."
        )
        st.stop()

    admin_id = int(
        session["id"]
    )

    st.title(
        "Community News Management"
    )

    st.caption(
        "Create and manage neighborhood updates "
        "for the resident portal."
    )

    # ------------------------------------------
    # SUCCESS MESSAGE
    # ------------------------------------------

    flash = st.session_state.pop(
        "bm_admin_news_flash",
        None,
    )

    if flash:
        st.success(flash)

    # ------------------------------------------
    # LOAD NEWS
    # ------------------------------------------

    try:
        records = get_admin_community_news(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        st.stop()

    except Exception:
        logger.exception(
            "Cannot load community news"
        )
        st.error(
            "Could not load community news."
        )
        return

    # ------------------------------------------
    # SUMMARY METRICS
    # ------------------------------------------

    a, b, c = st.columns(3)

    a.metric(
        "News Records",
        len(records),
    )

    b.metric(
        "Active News",
        sum(
            x["active"]
            for x in records
        ),
    )

    c.metric(
        "Hidden News",
        sum(
            not x["active"]
            for x in records
        ),
    )

    # ------------------------------------------
    # TABS
    # ------------------------------------------

    directory_tab, new_tab, edit_tab = st.tabs(
        [
            "News Directory",
            "Create News",
            "Edit / Visibility",
        ]
    )

    # ==================================================
    # TAB 1 — NEWS DIRECTORY
    # ==================================================

    with directory_tab:

        search_col, status_col = st.columns(
            [2, 1]
        )

        with search_col:

            query = st.text_input(
                "Search community news",
                placeholder=(
                    "Headline, category, or source"
                ),
                key="bm_news_search",
            ).strip().casefold()

        with status_col:

            status = st.selectbox(
                "Visibility",
                [
                    "All",
                    "Active",
                    "Hidden",
                ],
                key="bm_news_filter",
            )

        # --------------------------------------
        # APPLY FILTERS
        # --------------------------------------

        filtered = [
            item
            for item in records
            if (
                not query
                or query in " ".join(
                    str(item[field])
                    for field in (
                        "title",
                        "summary",
                        "category",
                        "source_name",
                    )
                ).casefold()
            )
            and (
                status == "All"
                or (
                    item["active"]
                    if status == "Active"
                    else not item["active"]
                )
            )
        ]

        st.caption(
            f"Showing {len(filtered)} of "
            f"{len(records)} recent news records "
            "(maximum 500)."
        )

        # --------------------------------------
        # DATA TABLE
        # --------------------------------------

        st.dataframe(
            [
                {
                    "Headline": x["title"],
                    "Category": x["category"],
                    "Source": (
                        x["source_name"] or "—"
                    ),
                    "Visibility": (
                        "Active"
                        if x["active"]
                        else "Hidden"
                    ),
                    "Published (UTC)": (
                        x["published_at"].strftime(
                            "%b %d, %Y"
                        )
                        if x["published_at"]
                        else "—"
                    ),
                }
                for x in filtered
            ],
            hide_index=True,
            use_container_width=True,
        )

    # ==================================================
    # TAB 2 — CREATE COMMUNITY NEWS
    # ==================================================

    with new_tab:

        st.subheader(
            "Create Community News"
        )

        st.caption(
            "Use original or properly attributed "
            "content. Hide until ready if necessary."
        )

        revision = st.session_state.get(
            "bm_news_create_revision",
            0,
        )

        with st.form(
            f"bm_news_create_form_{revision}"
        ):

            title = st.text_input(
                "Headline *",
                max_chars=255,
            )

            summary = st.text_area(
                "Summary *",
                max_chars=10000,
                height=160,
            )

            category = st.text_input(
                "Category *",
                value="Community",
                max_chars=100,
            )

            source_name = st.text_input(
                "Source name (optional)",
                max_chars=150,
            )

            source_url = st.text_input(
                "Source URL (optional)",
                placeholder=(
                    "https://example.org/story"
                ),
                max_chars=1000,
            )

            active = st.checkbox(
                "Show in resident Community News",
                value=True,
            )

            submitted = st.form_submit_button(
                "Save Community News",
                type="primary",
            )

        # --------------------------------------
        # SAVE NEWS
        # --------------------------------------

        if submitted:

            _save(
                lambda: create_admin_community_news(
                    admin_id,
                    title=title,
                    summary=summary,
                    category=category,
                    source_name=source_name,
                    source_url=source_url,
                    active=active,
                ),
                "Community news created successfully.",
                "bm_news_create_revision",
            )

    # ==================================================
    # TAB 3 — EDIT COMMUNITY NEWS
    # ==================================================

    with edit_tab:

        if not records:

            st.info(
                "Create a community news item first."
            )

        else:

            by_id = {
                item["id"]: item
                for item in records
            }

            selected_id = st.selectbox(
                "Choose news item",
                list(by_id),
                format_func=lambda item_id: (
                    f"{by_id[item_id]['title']} · "
                    f"{'Active' if by_id[item_id]['active'] else 'Hidden'}"
                ),
                key="bm_news_selected",
            )

            item = by_id[
                selected_id
            ]

            revision = st.session_state.get(
                "bm_news_edit_revision",
                0,
            )

            with st.form(
                f"bm_news_edit_form_"
                f"{selected_id}_{revision}"
            ):

                title = st.text_input(
                    "Headline *",
                    value=item["title"],
                    max_chars=255,
                )

                summary = st.text_area(
                    "Summary *",
                    value=item["summary"],
                    height=160,
                    max_chars=10000,
                )

                category = st.text_input(
                    "Category *",
                    value=item["category"],
                    max_chars=100,
                )

                source_name = st.text_input(
                    "Source name (optional)",
                    value=item["source_name"],
                    max_chars=150,
                )

                source_url = st.text_input(
                    "Source URL (optional)",
                    value=item["source_url"],
                    max_chars=1000,
                )

                active = st.checkbox(
                    "Visible to residents",
                    value=item["active"],
                )

                submitted = st.form_submit_button(
                    "Save Changes",
                    type="primary",
                )

            # ----------------------------------
            # SAVE CHANGES
            # ----------------------------------

            if submitted:

                _save(
                    lambda: update_admin_community_news(
                        admin_id,
                        selected_id,
                        title=title,
                        summary=summary,
                        category=category,
                        source_name=source_name,
                        source_url=source_url,
                        active=active,
                    ),
                    "Community news updated successfully.",
                    "bm_news_edit_revision",
                )

            st.caption(
                "Uncheck Visible to residents and save "
                "to hide this item without deleting it."
            )
