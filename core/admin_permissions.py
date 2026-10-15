
"""Blue Moon Apartments — explicit administrator permission policy.

Definitions alone grant no access. Service-layer enforcement is added in
Sprint 11A.2, after assigning roles to existing administrators.
"""

ROLES = (
    "super_admin",
    "property_manager",
    "leasing_agent",
    "maintenance_manager",
    "finance_manager",
    "auditor",
)

ROLE_LABELS = {
    "super_admin": "Super Admin",
    "property_manager": "Property Manager",
    "leasing_agent": "Leasing Agent",
    "maintenance_manager": "Maintenance Manager",
    "finance_manager": "Finance Manager",
    "auditor": "Auditor",
}

ALL_PERMISSIONS = frozenset({
    "overview.read",
    "tenants.read", "tenants.create", "tenants.update", "tenants.archive",
    "leases.read", "leases.renew", "leases.terminate", "transfers.execute",
    "apartments.read", "apartments.create", "apartments.update",
    "inspections.read", "inspections.record", "inspections.approve",
    "payments.read",
    "deposits.read", "deposits.edit", "deposits.approve", "refunds.record",
    "maintenance.read", "maintenance.update",
    "announcements.read", "announcements.manage",
    "news.read", "news.manage",
    "history.read",
    "admins.read", "admins.manage",
})

READ_ONLY = frozenset({
    "overview.read", "tenants.read", "leases.read", "apartments.read",
    "inspections.read", "payments.read", "deposits.read",
    "maintenance.read", "announcements.read", "news.read",
    "history.read",
})

ROLE_PERMISSIONS = {
    "super_admin": ALL_PERMISSIONS,

    "property_manager": READ_ONLY | {
        "tenants.create", "tenants.update", "tenants.archive",
        "leases.renew", "leases.terminate", "transfers.execute",
        "apartments.create", "apartments.update",
        "inspections.record", "inspections.approve",
        "maintenance.update", "announcements.manage", "news.manage",
    },

    "leasing_agent": frozenset({
        "overview.read", "tenants.read", "tenants.create", "tenants.update",
        "leases.read", "leases.renew", "apartments.read", "history.read",
    }),

    "maintenance_manager": frozenset({
        "overview.read", "apartments.read", "maintenance.read",
        "maintenance.update", "inspections.read", "inspections.record",
    }),

    "finance_manager": frozenset({
        "overview.read", "tenants.read", "leases.read", "payments.read",
        "deposits.read", "deposits.edit", "deposits.approve",
        "refunds.record", "history.read", "inspections.read",
    }),

    "auditor": READ_ONLY,
}


def permissions_for(role: str | None) -> frozenset[str]:
    """Unknown or unassigned roles get no permissions."""
    return frozenset(ROLE_PERMISSIONS.get(role, frozenset()))


def valid_role(role: str) -> bool:
    return role in ROLES
