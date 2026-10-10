
from textwrap import dedent

import streamlit as st

from components.cards import metric_card
from components.header import render_header


def render_dashboard():
    render_header("Dashboard")

    st.markdown(
        '<h1 class="page-title">Welcome back, Sarah</h1>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="page-description">'
        'Here is what is happening with your apartment.'
        '</p>',
        unsafe_allow_html=True,
    )

    # Dashboard metric cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        metric_card(
            "Apartment",
            "4B",
            "Blue Moon Apartments",
        )

    with col2:
        metric_card(
            "Monthly Rent",
            "$1,250",
            "Due October 1",
        )

    with col3:
        metric_card(
            "Current Balance",
            "$0.00",
            "Paid",
        )

    with col4:
        metric_card(
            "Lease Status",
            "Active",
            "Expires May 31, 2027",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    left, right = st.columns([2, 1])

    # Recent Activity
    
    
    # Recent Activity
    with left:
        activity_html = (
            '<div class="content-card">'
            '<h3>Recent Activity</h3>'
            '<div class="activity-row">'
            '<strong>Payment Confirmed</strong>'
            '<p>September rent payment of $1,250 was received.</p>'
            '<span>Sep 1, 2026</span>'
            '</div>'
            '<div class="activity-row">'
            '<strong>Maintenance Request</strong>'
            '<p>Leaking faucet request is currently In Progress.</p>'
            '<span>Sep 8, 2026</span>'
            '</div>'
            '</div>'
        )

        st.html(activity_html)
