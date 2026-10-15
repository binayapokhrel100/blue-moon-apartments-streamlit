
"""Blue Moon Apartments — Admin Apartment Transfer interface."""

import logging
from datetime import date

import streamlit as st
from sqlalchemy.exc import IntegrityError

from services.admin_apartment_transfer_service import (
    get_apartment_transfer_history,
    get_transfer_candidates,
    get_transfer_destinations,
    transfer_resident,
)


logger = logging.getLogger(__name__)


# ==========================================================
# ADMIN APARTMENT TRANSFER
# ==========================================================

def render_admin_apartment_transfer(admin_id: int) -> None:

    st.subheader("Apartment Transfer")

    st.caption(
        "Transfer a resident with an active lease "
        "to another vacant apartment."
    )

    flash = st.session_state.pop(
        "bm_transfer_flash",
        None,
    )

    if flash:
        st.success(flash)

    st.info(
        "This workflow transfers the resident today. "
        "The previous lease and payment history remain "
        "in the database. The new lease keeps the "
        "current rent, security deposit, and expiration date."
    )

    # ------------------------------------------
    # LOAD AVAILABLE DATA
    # ------------------------------------------

    try:
        candidates = get_transfer_candidates(
            admin_id
        )

        destinations = get_transfer_destinations(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Failed to load apartment transfer data"
        )

        st.error(
            "Unable to load resident and apartment data."
        )
        return

    # ==================================================
    # TRANSFER FORM
    # ==========================================================

    if not candidates:

        st.warning(
            "No eligible active leases were found."
        )

    elif not destinations:

        st.warning(
            "No vacant apartments are available for "
            "transfer. Add a vacant apartment or "
            "resolve an existing assignment first."
        )

    else:

        candidate_by_lease = {
            row["lease_id"]: row
            for row in candidates
        }

        destination_by_id = {
            row["id"]: row
            for row in destinations
        }

        # --------------------------------------
        # SELECT RESIDENT / LEASE
        # --------------------------------------

        st.markdown("#### Current Resident")

        lease_id = st.selectbox(
            "Select resident to transfer",
            list(candidate_by_lease),
            format_func=lambda value: (
                f"{candidate_by_lease[value]['resident_name']} "
                f"· Unit {candidate_by_lease[value]['unit']}"
            ),
            key="bm_transfer_resident_select",
        )

        selected = candidate_by_lease[
            lease_id
        ]

        with st.container(border=True):

            st.write(
                "**Resident:** "
                f"{selected['resident_name']}"
            )

            st.write(
                "**Email:** "
                f"{selected['email']}"
            )

            st.write(
                "**Current apartment:** "
                f"Unit {selected['unit']}"
            )

            st.write(
                "**Lease start:** "
                f"{selected['lease_start']:%b %d, %Y}"
            )

            st.write(
                "**Current lease expiration:** "
                f"{selected['lease_end']:%b %d, %Y}"
            )

            st.write(
                "**Current monthly rent:** "
                f"${selected['monthly_rent']:,.2f}"
            )

            st.write(
                "**Recorded security deposit:** "
                f"${selected['security_deposit']:,.2f}"
            )

        # --------------------------------------
        # SELECT VACANT DESTINATION
        # --------------------------------------

        st.markdown("#### New Apartment")

        new_apartment_id = st.selectbox(
            "Assign new vacant apartment *",
            list(destination_by_id),
            format_func=lambda value: (
                f"Unit {destination_by_id[value]['unit']} "
                f"· "
                f"${destination_by_id[value]['listed_rent']:,.2f}"
                "/month listed rent"
            ),
            key="bm_transfer_destination_select",
        )

        destination = destination_by_id[
            new_apartment_id
        ]

        with st.container(border=True):

            st.write(
                "**New apartment:** "
                f"Unit {destination['unit']}"
            )

            st.write(
                "**Floor:** "
                f"{destination['floor'] if destination['floor'] is not None else 'N/A'}"
            )

            st.write(
                "**Bedrooms:** "
                f"{destination['bedrooms']}"
            )

            st.write(
                "**Bathrooms:** "
                f"{destination['bathrooms']:g}"
            )

            st.write(
                "**Listed apartment rent:** "
                f"${destination['listed_rent']:,.2f}"
            )

        if (
            destination["listed_rent"]
            != selected["monthly_rent"]
        ):

            st.warning(
                "The new apartment's listed rent differs "
                "from the resident's current lease. "
                "This transfer will KEEP the existing "
                f"rent of ${selected['monthly_rent']:,.2f}. "
                "Rent changes are not included in "
                "this workflow."
            )

        # --------------------------------------
        # TRANSFER SUMMARY
        # --------------------------------------

        st.markdown("#### Transfer Summary")

        st.write(
            f"**From:** Unit {selected['unit']}"
        )

        st.write(
            f"**To:** Unit {destination['unit']}"
        )

        st.write(
            f"**Effective date:** {date.today():%B %d, %Y}"
        )

        st.write(
            "**New lease expiration:** "
            f"{selected['lease_end']:%B %d, %Y}"
        )

        # --------------------------------------
        # CONFIRMATION FORM
        # --------------------------------------

        revision = st.session_state.get(
            "bm_transfer_form_revision",
            0,
        )

        with st.form(
            f"bm_transfer_form_"
            f"{lease_id}_{new_apartment_id}_{revision}"
        ):

            reason = st.text_area(
                "Reason for apartment transfer *",
                placeholder=(
                    "Example: Resident requested a "
                    "transfer due to a maintenance "
                    "issue. Apartment assignment "
                    "approved by management."
                ),
                height=120,
                max_chars=2000,
                key=(
                    f"bm_transfer_reason_"
                    f"{lease_id}_{new_apartment_id}_{revision}"
                ),
            )

            confirmed = st.checkbox(
                "I confirm the transfer is authorized, "
                "effective today, and the existing "
                "rent and deposit will carry forward.",
                key=(
                    f"bm_transfer_confirm_"
                    f"{lease_id}_{new_apartment_id}_{revision}"
                ),
            )

            submitted = st.form_submit_button(
                "Confirm Apartment Transfer",
                type="primary",
            )

        if submitted:

            if not confirmed:

                st.error(
                    "Please confirm the transfer "
                    "before continuing."
                )

            else:

                try:

                    transfer_resident(
                        admin_id,
                        lease_id,
                        expected_apartment_id=(
                            selected["apartment_id"]
                        ),
                        expected_end_date=(
                            selected["lease_end"]
                        ),
                        new_apartment_id=new_apartment_id,
                        reason=reason,
                    )

                except (
                    ValueError,
                    PermissionError,
                ) as exc:

                    st.error(str(exc))

                except IntegrityError:

                    st.error(
                        "The database rejected the transfer. "
                        "Refresh and try again."
                    )

                except Exception:

                    logger.exception(
                        "Apartment transfer failed"
                    )

                    st.error(
                        "Unable to complete the apartment transfer."
                    )

                else:

                    st.session_state[
                        "bm_transfer_form_revision"
                    ] = revision + 1

                    st.session_state[
                        "bm_transfer_flash"
                    ] = (
                        "Apartment transfer completed. "
                        "Both apartment occupancy records "
                        "have been updated and the resident "
                        "has been notified."
                    )

                    st.rerun()

    # ==================================================
    # TRANSFER HISTORY
    # ==========================================================

    st.divider()

    st.subheader(
        "Apartment Transfer History"
    )

    try:

        history = get_apartment_transfer_history(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:

        logger.exception(
            "Unable to load transfer history"
        )

        st.error(
            "Unable to load apartment transfer history."
        )
        return

    if not history:

        st.caption(
            "No apartment transfers have been "
            "recorded yet."
        )
        return

    st.dataframe(
        [
            {
                "Resident": row["resident"],
                "Previous Unit": row["old_unit"],
                "New Unit": row["new_unit"],
                "Effective Date": row["effective_date"],
                "Lease End": row["contract_end"],
                "Monthly Rent": row["monthly_rent"],
                "Reason": row["reason"],
                "Admin ID": row["admin_id"],
                "Recorded At": row["created_at"],
            }
            for row in history
        ],
        hide_index=True,
        use_container_width=True,
    )
