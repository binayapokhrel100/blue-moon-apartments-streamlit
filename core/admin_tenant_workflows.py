
"""Blue Moon Apartments — Tenant Management workflow permissions.

One selected workflow runs per Streamlit rerun.

Tenant history remains Super Admin-only temporarily until
its backend reporting service receives full RBAC enforcement.
"""

TENANT_WORKFLOW_RULES = (
    (
        "directory",
        "Resident Directory",
        {"tenants.read", "apartments.read"},
    ),
    (
        "create",
        "Add Resident",
        {"tenants.create", "apartments.read"},
    ),
    (
        "edit",
        "Edit Resident / Assignment",
        {"tenants.update", "apartments.read"},
    ),
    (
        "lease",
        "Lease & Move-Out",
        {"leases.read", "leases.terminate"},
    ),
    (
        "archive",
        "Remove / Archive Tenant",
        {"tenants.read", "tenants.archive", "history.read"},
    ),
    (
        "renewal",
        "Lease Renewal",
        {"leases.read", "leases.renew", "history.read"},
    ),
    (
        "transfer",
        "Apartment Transfer",
        {
            "leases.read",
            "apartments.read",
            "transfers.execute",
            "history.read",
        },
    ),
    (
        "inspection",
        "Move-Out Inspection",
        {"inspections.read"},
    ),
    (
        "deposit",
        "Security Deposit Settlement",
        {"deposits.read"},
    ),
    (
        "history",
        "Tenant History",
        {"admins.manage"},
    ),
)


def get_tenant_workflows(
    permissions: set[str] | frozenset[str],
) -> list[tuple[str, str]]:
    """Return ordered, permitted Tenant Management workflows."""

    granted = set(permissions or [])

    return [
        (workflow_id, label)
        for workflow_id, label, required
        in TENANT_WORKFLOW_RULES
        if required.issubset(granted)
    ]
