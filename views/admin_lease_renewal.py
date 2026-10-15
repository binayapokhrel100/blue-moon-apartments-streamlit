
"""Streamlit admin interface for lease extensions."""

import logging
from datetime import timedelta

import streamlit as st
from sqlalchemy.exc import IntegrityError

from services.admin_lease_renewal_service import (
    get_lease_renewal_history,
    get_renewable_leases,
    renew_lease,
)


logger = logging.getLogger(__name__)


# ==========================================================
# LEASE RENEWAL PAGE
# ==========================================================

def render_admin_lease_renewal(admin_id: int) -> None:

    st.subheader("Lease Renewal")

    st.caption(
        "Extend an active resident lease while preserving "
        "the previous expiration date and renewal history."
    )

    flash = st.session_state.pop(
        "bm_lease_renewal_flash",
        None,
    )

    if flash:
        st.success(flash)

    st.info(
        "This workflow extends the current lease. "
        "Monthly rent and the original lease start date "
        "remain unchanged. It records the extension but "
        "does not generate or sign a legal lease document."
    )

    # ==================================================
    # AVAILABLE ACTIVE LEASES
    # ==================================================

    try:
        leases = get_renewable_leases(admin_id)

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Failed to load renewable leases"
        )
        st.error(
            "Unable to load active leases."
        )
        return

    if not leases:

        st.warning(
            "No eligible active leases were found. "
            "Only active leases with a matching apartment "
            "assignment can be extended."
        )

    else:

        lease_by_id = {
            item["lease_id"]: item
            for item in leases
        }

        selected_id = st.selectbox(
            "Select an active lease",
            list(lease_by_id),
            format_func=lambda value: (
                f"{lease_by_id[value]['resident_name']} "
                f"· Unit {lease_by_id[value]['unit']} "
                f"· Ends "
                f"{lease_by_id[value]['end_date']:%b %d, %Y}"
            ),
            key="bm_lease_renewal_selected",
        )

        selected = lease_by_id[selected_id]

        # ------------------------------------------
        # CURRENT LEASE SUMMARY
        # ------------------------------------------

        st.markdown("#### Current Lease Details")

        with st.container(border=True):

            st.write(
                f"**Resident:** "
                f"{selected['resident_name']}"
            )

            st.write(
                f"**Email:** "
                f"{selected['email']}"
            )

            st.write(
                f"**Apartment:** "
                f"Unit {selected['unit']}"
            )

            st.write(
                "**Lease start:** "
                f"{selected['start_date']:%B %d, %Y}"
            )

            st.write(
                "**Current expiration:** "
                f"{selected['end_date']:%B %d, %Y}"
            )

            st.write(
                "**Monthly rent:** "
                f"${selected['monthly_rent']:,.2f}"
            )

            st.write(
                "**Recorded security deposit:** "
                f"${selected['security_deposit']:,.2f}"
            )

        # ------------------------------------------
        # RENEWAL FORM
        # ------------------------------------------

        st.markdown("#### Extend Lease")

        current_end = selected["end_date"]

        revision = st.session_state.get(
            "bm_renewal_form_revision",
            0,
        )

        form_key = (
            f"bm_renewal_form_{selected_id}_{revision}"
        )

        with st.form(form_key):

            new_end_date = st.date_input(
                "New lease expiration date *",
                value=current_end + timedelta(days=365),
                min_value=current_end + timedelta(days=1),
                key=(
                    f"bm_renewal_new_end_"
                    f"{selected_id}_{revision}"
                ),
                help=(
                    "The new expiration must be later "
                    "than the current expiration."
                ),
            )

            notes = st.text_area(
                "Renewal notes / agreement reference *",
                placeholder=(
                    "Example: Resident agreed to extend "
                    "the existing lease for another "
                    "12 months. Agreement reviewed "
                    "by property management."
                ),
                height=120,
                max_chars=2000,
                key=(
                    f"bm_renewal_notes_"
                    f"{selected_id}_{revision}"
                ),
            )

            st.caption(
                "The original rent and security deposit "
                "will remain unchanged. The new "
                "expiration date will be recorded "
                "in renewal history."
            )

            confirmed = st.checkbox(
                "I confirm the renewal has been agreed "
                "to by the appropriate parties and "
                "the new expiration date is correct.",
                key=(
                    f"bm_renewal_confirm_"
                    f"{selected_id}_{revision}"
                ),
            )

            submitted = st.form_submit_button(
                "Confirm Lease Renewal",
                type="primary",
            )

        # ------------------------------------------
        # SAVE RENEWAL
        # ------------------------------------------

        if submitted:

            if not confirmed:

                st.error(
                    "Please confirm the renewal "
                    "before continuing."
                )

            else:

                try:

                    renew_lease(
                        admin_id,
                        selected_id,
                        expected_end_date=current_end,
                        new_end_date=new_end_date,
                        notes=notes,
                    )

                except (
                    ValueError,
                    PermissionError,
                ) as exc:

                    st.error(str(exc))

                except IntegrityError:

                    st.error(
                        "The database rejected this "
                        "renewal. Refresh and try again."
                    )

                except Exception:

                    logger.exception(
                        "Lease renewal failed"
                    )

                    st.error(
                        "Unable to complete this renewal."
                    )

                else:

                    st.session_state[
                        "bm_renewal_form_revision"
                    ] = revision + 1

                    st.session_state[
                        "bm_lease_renewal_flash"
                    ] = (
                        "Lease extended successfully. "
                        "The resident has been notified "
                        "and renewal history was saved."
                    )

                    st.rerun()

    # ==================================================
    # RENEWAL HISTORY
    # ==================================================

    st.divider()

    st.subheader("Lease Renewal History")

    try:

        history = get_lease_renewal_history(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:

        logger.exception(
            "Failed to load renewal history"
        )

        st.error(
            "Unable to load lease renewal history."
        )

        return

    if not history:

        st.caption(
            "No lease renewals have been recorded yet."
        )

    else:

        st.dataframe(
            [
                {
                    "Resident": row["resident"],
                    "Apartment": row["unit"],
                    "Previous End Date": row["previous_end"],
                    "New End Date": row["new_end"],
                    "Monthly Rent": row["monthly_rent"],
                    "Renewal Notes": row["notes"],
                    "Admin ID": row["admin_id"],
                    "Recorded At": row["recorded_at"],
                }
                for row in history
            ],
            hide_index=True,
            use_container_width=True,
        )
