
"""Unit tests for Blue Moon Assistant."""

import pytest

from services import assistant_service


@pytest.fixture
def resident_context():
    return {
        "resident": {
            "first_name": "Sarah",
            "unit_number": "4B",
        },
        "lease": {
            "start_date": "2026-06-01",
            "end_date": "2027-05-31",
            "monthly_rent": "1250.00",
            "security_deposit": "1250.00",
            "status": "active",
        },
        "payments": [
            {
                "amount": "1250.00",
                "payment_month": "2026-09-01",
                "status": "confirmed",
                "paid_at": "2026-09-01",
            }
        ],
        "maintenance": [
            {
                "request_number": "MR-2026-0142",
                "category": "Plumbing",
                "status": "In Progress",
            }
        ],
        "announcements": [
            {
                "title": "Fire Alarm Inspection",
                "message": "Inspections take place October 15.",
            }
        ],
        "community_news": [
            {
                "title": "Bike Share",
                "summary": "A station opened nearby.",
            }
        ],
    }


def test_monthly_rent(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "What is my monthly rent?",
        resident_context,
    )
    assert "$1,250.00" in answer
    assert "4B" in answer


def test_lease_end_date(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "When does my lease end?",
        resident_context,
    )
    assert "May 31, 2027" in answer


def test_due_date_is_not_invented(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "When is my rent due?",
        resident_context,
    )
    assert "cannot confirm" in answer


def test_balance_is_not_invented(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "How much do I owe?",
        resident_context,
    )
    assert "cannot confirm" in answer


def test_latest_payment(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "Show my latest payment",
        resident_context,
    )
    assert "confirmed" in answer
    assert "$1,250.00" in answer


def test_maintenance_status(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "What's my maintenance status?",
        resident_context,
    )
    assert "MR-2026-0142" in answer
    assert "In Progress" in answer


def test_announcements(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "Any announcements?",
        resident_context,
    )
    assert "Fire Alarm Inspection" in answer


def test_community_news(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "Any community news?",
        resident_context,
    )
    assert "Bike Share" in answer


def test_no_lease(resident_context):
    resident_context["lease"] = None
    answer = assistant_service.generate_assistant_reply(
        "My lease",
        resident_context,
    )
    assert "could not find an active lease" in answer


def test_no_payment(resident_context):
    resident_context["payments"] = []
    answer = assistant_service.generate_assistant_reply(
        "My latest payment",
        resident_context,
    )
    assert "could not find any recorded payments" in answer


def test_no_maintenance(resident_context):
    resident_context["maintenance"] = []
    answer = assistant_service.generate_assistant_reply(
        "Maintenance status",
        resident_context,
    )
    assert "no recorded maintenance" in answer


def test_payment_is_not_processed(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "Pay my rent",
        resident_context,
    )
    assert "cannot process payments" in answer


def test_unknown_question(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "What is the weather on Jupiter?",
        resident_context,
    )
    assert "don't have a rule" in answer


def test_missing_question(resident_context):
    answer = assistant_service.generate_assistant_reply(
        "   ",
        resident_context,
    )
    assert "Please type a question" in answer


def test_bridge_passes_identity_only_from_caller(
    monkeypatch,
    resident_context,
):
    captured = []

    def fake_context(user_id):
        captured.append(user_id)
        return resident_context

    monkeypatch.setattr(
        assistant_service,
        "build_assistant_context",
        fake_context,
    )

    result = assistant_service.ask_resident_assistant(
        7,
        "Show my latest payment",
    )

    assert captured == [7]
    assert "confirmed" in result
