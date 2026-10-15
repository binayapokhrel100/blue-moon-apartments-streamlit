
"""Sprint 09: manage property announcements, drafts, and publication."""

import logging

import streamlit as st

from core.session import get_current_user
from services.admin_content_service import (
    PRIORITIES,
    create_admin_announcement,
    get_admin_announcements,
    update_admin_announcement,
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
            "Cannot save admin announcement"
        )
        st.error(
            "Could not save the announcement. "
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
            "bm_admin_announcement_flash"
        ] = success

        st.rerun()


# ==================================================
# ADMIN ANNOUNCEMENTS PAGE
# ==================================================

def render_admin_announcements() -> None:

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
        "Announcement Management"
    )

    st.caption(
        "Create, edit, publish or unpublish "
        "property announcements."
    )

    # ------------------------------------------
    # SUCCESS MESSAGE
    # ------------------------------------------

    flash = st.session_state.pop(
        "bm_admin_announcement_flash",
        None,
    )

    if flash:
        st.success(flash)

    # ------------------------------------------
    # LOAD ANNOUNCEMENTS
    # ------------------------------------------

    try:
        records = get_admin_announcements(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        st.stop()

    except Exception:
        logger.exception(
            "Unable to load announcements"
        )
        st.error(
            "Could not load announcements."
        )
        return

    # ------------------------------------------
    # SUMMARY METRICS
    # ------------------------------------------

    a, b, c = st.columns(3)

    a.metric(
        "All Announcements",
        len(records),
    )

    b.metric(
        "Published Now",
        sum(
            x["visibility"] == "Published"
            for x in records
        ),
    )

    c.metric(
        "Drafts",
        sum(
            x["visibility"] == "Draft"
            for x in records
        ),
    )

    # ------------------------------------------
    # TABS
    # ------------------------------------------

    directory_tab, new_tab, edit_tab = st.tabs(
        [
            "Announcement Directory",
            "Create Announcement",
            "Edit / Publish",
        ]
    )

    # ==================================================
    # TAB 1 — DIRECTORY
    # ==================================================

    with directory_tab:

        col_search, col_visibility = st.columns(
            [2, 1]
        )

        with col_search:

            query = st.text_input(
                "Search announcements",
                placeholder=(
                    "Title, category, or message"
                ),
                key="bm_announcement_search",
            ).strip().casefold()

        with col_visibility:

            visibility = st.selectbox(
                "Visibility",
                [
                    "All",
                    "Published",
                    "Draft",
                    "Expired",
                    "Scheduled",
                ],
                key="bm_announcement_visibility",
            )

        # --------------------------------------
        # FILTER RECORDS
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
                        "category",
                        "message",
                    )
                ).casefold()
            )
            and (
                visibility == "All"
                or item["visibility"] == visibility
            )
        ]

        st.caption(
            f"Showing {len(filtered)} of "
            f"{len(records)} recent announcements "
            "(maximum 500)."
        )

        # --------------------------------------
        # DATA TABLE
        # --------------------------------------

        st.dataframe(
            [
                {
                    "Title": x["title"],
                    "Category": x["category"],
                    "Priority": x["priority"],
                    "Visibility": x["visibility"],
                    "Published (UTC)": (
                        x["published_at"].strftime(
                            "%b %d, %Y"
                        )
                        if x["published_at"]
                        else "—"
                    ),
                    "Expires (UTC)": (
                        x["expires_at"].strftime(
                            "%Y-%m-%d"
                        )
                        if x["expires_at"]
                        else "Never"
                    ),
                }
                for x in filtered
            ],
            hide_index=True,
            use_container_width=True,
        )

    # ==================================================
    # TAB 2 — CREATE ANNOUNCEMENT
    # ==================================================

    with new_tab:

        st.subheader(
            "New Announcement"
        )

        st.caption(
            "Leave Publish immediately unchecked "
            "to save a draft. Expiration is optional "
            "and uses a UTC date."
        )

        revision = st.session_state.get(
            "bm_announcement_create_revision",
            0,
        )

        with st.form(
            f"bm_announcement_create_form_{revision}"
        ):

            title = st.text_input(
                "Title *",
                max_chars=255,
            )

            message = st.text_area(
                "Message *",
                height=155,
                max_chars=10000,
            )

            col_category, col_priority = st.columns(2)

            with col_category:

                category = st.text_input(
                    "Category *",
                    value="General",
                    max_chars=100,
                )

            with col_priority:

                priority = st.selectbox(
                    "Priority",
                    PRIORITIES,
                )

            expires_on = st.text_input(
                "Expiration date (YYYY-MM-DD, optional)",
                placeholder="2026-11-30",
            )

            published = st.checkbox(
                "Publish immediately",
                value=True,
            )

            submitted = st.form_submit_button(
                "Save Announcement",
                type="primary",
            )

        # --------------------------------------
        # CREATE RECORD
        # --------------------------------------

        if submitted:

            _save(
                lambda: create_admin_announcement(
                    admin_id,
                    title=title,
                    message=message,
                    category=category,
                    priority=priority,
                    expires_on=expires_on,
                    published=published,
                ),
                "Announcement saved successfully.",
                "bm_announcement_create_revision",
            )

    # ==================================================
    # TAB 3 — EDIT / PUBLISH
    # ==================================================

    with edit_tab:

        if not records:

            st.info(
                "Create an announcement first."
            )

        else:

            by_id = {
                item["id"]: item
                for item in records
            }

            selected_id = st.selectbox(
                "Choose announcement",
                list(by_id),
                format_func=lambda item_id: (
                    f"{by_id[item_id]['title']} "
                    f"· {by_id[item_id]['visibility']}"
                ),
                key="bm_announcement_selected",
            )

            item = by_id[
                selected_id
            ]

            revision = st.session_state.get(
                "bm_announcement_edit_revision",
                0,
            )

            # ----------------------------------
            # EDIT FORM
            # ----------------------------------

            with st.form(
                f"bm_announcement_edit_form_"
                f"{selected_id}_{revision}"
            ):

                title = st.text_input(
                    "Title *",
                    value=item["title"],
                    max_chars=255,
                )

                message = st.text_area(
                    "Message *",
                    value=item["message"],
                    height=155,
                    max_chars=10000,
                )

                col_category, col_priority = (
                    st.columns(2)
                )

                with col_category:

                    category = st.text_input(
                        "Category *",
                        value=item["category"],
                        max_chars=100,
                    )

                with col_priority:

                    choices = list(
                        PRIORITIES
                    )

                    if (
                        item["priority"]
                        not in choices
                    ):
                        choices.append(
                            item["priority"]
                        )

                    priority = st.selectbox(
                        "Priority",
                        choices,
                        index=choices.index(
                            item["priority"]
                        ),
                    )

                expires_on = st.text_input(
                    "Expiration date (YYYY-MM-DD, optional)",
                    value=(
                        item["expires_at"].strftime(
                            "%Y-%m-%d"
                        )
                        if item["expires_at"]
                        else ""
                    ),
                )

                published = st.checkbox(
                    "Published — visible to residents",
                    value=item["published"],
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
                    lambda: update_admin_announcement(
                        admin_id,
                        selected_id,
                        title=title,
                        message=message,
                        category=category,
                        priority=priority,
                        expires_on=expires_on,
                        published=published,
                    ),
                    "Announcement updated successfully.",
                    "bm_announcement_edit_revision",
                )

            st.caption(
                "Uncheck Published and save to unpublish. "
                "Recheck and save to republish."
            )
