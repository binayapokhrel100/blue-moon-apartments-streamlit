
"""Offline rule-based Blue Moon Assistant.

No LLM, external API, or database write operations.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from services.assistant_context_service import (
    build_assistant_context,
)


SUGGESTED_QUESTIONS = (
    "What is my monthly rent?",
    "When does my lease end?",
    "Show my latest payment",
    "What's my maintenance status?",
    "Any community announcements?",
)


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _has(text: str, *phrases: str) -> bool:
    """Match whole words or phrases in normalized text."""

    return any(
        re.search(
            rf"(?<!\w){re.escape(phrase)}(?!\w)",
            text,
        )
        is not None
        for phrase in phrases
    )


def _money(amount) -> str:
    if amount is None:
        return "not available"

    try:
        return f"${Decimal(str(amount)):,.2f}"

    except (InvalidOperation, ValueError):
        return "not available"


def _date(value) -> str:
    if not value:
        return "not recorded"

    try:
        return date.fromisoformat(
            str(value)[:10]
        ).strftime("%b %d, %Y")

    except ValueError:
        return "not recorded"


# ==========================================
# RULE-BASED RESPONSE ENGINE
# ==========================================

def generate_assistant_reply(
    question: str,
    context: dict,
) -> str:
    """Generate a deterministic answer from resident data."""

    if not isinstance(question, str) or not question.strip():
        return (
            "Please type a question about your "
            "Blue Moon account."
        )

    if len(question) > 500:
        return (
            "Please shorten your question "
            "to 500 characters or fewer."
        )

    q = " ".join(
        question.casefold().split()
    )

    resident = context.get("resident") or {}
    lease = context.get("lease")
    payments = context.get("payments") or []
    maintenance = context.get("maintenance") or []
    announcements = context.get("announcements") or []
    news = context.get("community_news") or []

    # ======================================
    # HELP
    # ======================================

    if _has(
        q,
        "help",
        "what can you do",
        "what can i ask",
    ):
        return (
            "I can check your monthly rent, lease dates, "
            "recorded payments, maintenance requests, "
            "announcements, and community news. "
            "I cannot make payments or change your account."
        )

    # ======================================
    # GREETINGS
    # ======================================

    if _has(
        q,
        "hello",
        "hi",
        "hey",
        "good morning",
        "good evening",
    ):
        name = resident.get("first_name") or "there"

        return (
            f"Hello, {name}! Ask me about your lease, "
            "rent, payments, maintenance, or community updates."
        )

    # ======================================
    # SECURITY QUESTIONS
    # ======================================

    if _has(
        q,
        "password",
        "sign in",
        "login",
        "log in",
        "security settings",
    ):
        return (
            "For passwords and login activity, "
            "open the Security page. "
            "I cannot see or disclose passwords."
        )

    # ======================================
    # PAYMENT ACTIONS (NOT ALLOWED)
    # ======================================

    if (
        _has(
            q,
            "pay rent",
            "make a payment",
            "submit a payment",
            "pay my rent",
            "how do i pay",
            "can i pay rent",
        )
        and not _has(
            q,
            "did i pay",
            "have i paid",
        )
    ):
        return (
            "I cannot process payments. "
            "Open the Payments page to review "
            "available payment options."
        )

    # ======================================
    # MAINTENANCE SUBMISSION
    # ======================================

    if _has(
        q,
        "submit maintenance",
        "create maintenance",
        "new maintenance request",
        "report a repair",
    ):
        return (
            "To submit a maintenance request, "
            "open the Maintenance page. "
            "I can also check existing requests."
        )

    # ======================================
    # CURRENT BALANCE / DUE DATE
    # ======================================

    if _has(
        q,
        "balance",
        "owe",
        "overdue",
        "late fee",
        "due date",
        "rent due",
        "when is rent due",
        "when is my rent due",
    ):

        rent_info = (
            " Your active lease lists monthly rent as "
            f"{_money(lease.get('monthly_rent'))}."
            if lease
            else ""
        )

        return (
            "I cannot confirm your current outstanding "
            "balance, late fees, or exact rent due date "
            "from the available records."
            + rent_info
            + " Check the Payments page or contact "
            "property management for an authoritative "
            "amount and due date."
        )

    # ======================================
    # PAYMENTS
    # ======================================

    if _has(
        q,
        "payment",
        "payments",
        "paid",
        "receipt",
        "transaction",
        "did i pay",
        "have i paid",
        "pay rent last month",
    ):

        if not payments:
            return (
                "I could not find any recorded payments "
                "for your account. Check the Payments "
                "page for details."
            )

        latest = payments[0]

        return (
            "Your latest recorded payment is "
            f"{_money(latest.get('amount'))} "
            f"for {_date(latest.get('payment_month'))}. "
            "Its recorded status is "
            f"{latest.get('status') or 'not recorded'}, "
            "with payment date "
            f"{_date(latest.get('paid_at'))}. "
            "For the full history, open Payments."
        )

    # ======================================
    # LEASE / RENT
    # ======================================

    if _has(
        q,
        "lease",
        "rent",
        "monthly rent",
        "security deposit",
        "deposit",
        "apartment",
        "unit",
    ):

        if not lease:
            return (
                "I could not find an active lease "
                "for your account. "
                "Please contact property management."
            )

        unit = (
            resident.get("unit_number")
            or "not recorded"
        )

        return (
            f"Your active lease for apartment {unit} "
            f"runs from {_date(lease.get('start_date'))} "
            f"to {_date(lease.get('end_date'))}. "
            "Monthly rent is "
            f"{_money(lease.get('monthly_rent'))}, "
            "and the recorded security deposit is "
            f"{_money(lease.get('security_deposit'))}. "
            "Open My Lease for more details."
        )

    # ======================================
    # MAINTENANCE STATUS
    # ======================================

    if _has(
        q,
        "maintenance",
        "repair",
        "request status",
        "technician",
        "fix",
        "plumbing",
        "broken",
        "work order",
    ):

        if not maintenance:
            return (
                "You have no recorded maintenance "
                "requests in the available history."
            )

        lines = [
            (
                f"{item.get('request_number') or 'Request'}: "
                f"{item.get('category') or 'Maintenance'} — "
                f"{item.get('status') or 'Unknown'}"
            )
            for item in maintenance[:3]
        ]

        return (
            "Your most recent maintenance requests are:\n\n"
            + "\n".join(
                "- " + line
                for line in lines
            )
        )

    # ======================================
    # ANNOUNCEMENTS
    # ======================================

    if _has(
        q,
        "announcement",
        "announcements",
        "notice",
        "notices",
        "community update",
    ):

        if not announcements:
            return (
                "There are no current published "
                "announcements to show."
            )

        lines = [
            (
                f"{item.get('title') or 'Announcement'}: "
                f"{item.get('message') or 'No details available.'}"
            )
            for item in announcements[:3]
        ]

        return (
            "Current announcements:\n\n"
            + "\n".join(
                "- " + line
                for line in lines
            )
        )

    # ======================================
    # COMMUNITY NEWS
    # ======================================

    if _has(
        q,
        "news",
        "community",
        "neighborhood",
        "event",
        "events",
    ):

        if not news:
            return (
                "There are no active community "
                "news items to show."
            )

        lines = [
            (
                f"{item.get('title') or 'Community update'}: "
                f"{item.get('summary') or 'No details available.'}"
            )
            for item in news[:3]
        ]

        return (
            "Community news:\n\n"
            + "\n".join(
                "- " + line
                for line in lines
            )
        )

    # ======================================
    # UNKNOWN QUESTION
    # ======================================

    return (
        "I don't have a rule for that question yet. "
        "Try asking about rent, your lease, payments, "
        "maintenance, announcements, or community news."
    )


# ==========================================
# PUBLIC SERVICE FUNCTION
# ==========================================

def ask_resident_assistant(
    user_id: int,
    question: str,
) -> str:
    """Answer a question for one authenticated resident.

    The UI must obtain user_id from the active session,
    never from text typed into the chat.
    """

    if not isinstance(question, str) or not question.strip():
        return (
            "Please type a question about your "
            "Blue Moon account."
        )

    if len(question) > 500:
        return (
            "Please shorten your question "
            "to 500 characters or fewer."
        )

    context = build_assistant_context(user_id)

    return generate_assistant_reply(
        question,
        context,
    )
