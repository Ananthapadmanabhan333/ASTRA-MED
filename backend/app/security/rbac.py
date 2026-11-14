"""Roles and permissions.

Access is granted by permission, never by role name, so the matrix below is the single place that
decides who may do what. The administrator role manages accounts, the audit log and models but is
deliberately *not* given access to crew health records (separation of duties).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    FLIGHT_SURGEON = "flight_surgeon"
    MISSION_OPERATOR = "mission_operator"
    ANALYST = "analyst"
    ADMIN = "admin"


PERMISSIONS: dict[str, str] = {
    "health:read": "View crew health records: vitals, sleep, dose, alerts, digital twin and AI outputs",
    "space:read": "View NASA space-environment data",
    "alerts:manage": "Acknowledge and resolve alerts",
    "simulation:control": "Start and cancel simulated test scenarios and emergency runs",
    "reports:read": "Read incident reports",
    "reports:write": "Create and export incident reports",
    "reports:review": "Record the medical review status of incident reports",
    "assistant:use": "Ask the medical data assistant",
    "space:sync": "Trigger NASA data synchronisation",
    "models:manage": "Reload AI model versions",
    "system:maintain": "Run database consistency repairs",
    "audit:read": "Read the audit log",
    "users:manage": "Create, change and deactivate user accounts",
}

ROLE_LABELS: dict[Role, str] = {
    Role.FLIGHT_SURGEON: "Flight surgeon",
    Role.MISSION_OPERATOR: "Mission operator",
    Role.ANALYST: "Analyst",
    Role.ADMIN: "Administrator",
}

ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.FLIGHT_SURGEON: "Medical lead: full health-record access and sign-off of incident report reviews.",
    Role.MISSION_OPERATOR: "Runs monitoring and simulations, handles alerts and drafts incident reports.",
    Role.ANALYST: "Read-only access to health data and the assistant; no reports, no actions.",
    Role.ADMIN: "Accounts, audit log, models and data sync. No access to crew health records.",
}

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.FLIGHT_SURGEON: frozenset({
        "health:read", "space:read", "alerts:manage", "reports:read", "reports:write",
        "reports:review", "assistant:use",
    }),
    Role.MISSION_OPERATOR: frozenset({
        "health:read", "space:read", "alerts:manage", "simulation:control", "reports:read",
        "reports:write", "assistant:use", "space:sync", "system:maintain",
    }),
    Role.ANALYST: frozenset({"health:read", "space:read", "assistant:use"}),
    Role.ADMIN: frozenset({"space:read", "space:sync", "models:manage", "audit:read", "users:manage",
                           "system:maintain"}),
}

assert all(p in PERMISSIONS for perms in ROLE_PERMISSIONS.values() for p in perms)


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    display_name: str
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    method: str = "session"  # session (cookie) | bearer | disabled
    session_id: str | None = None
    csrf_token: str | None = None

    def can(self, permission: str) -> bool:
        return permission in self.permissions


# Used only when authentication is switched off (tests, isolated local development).
AUTH_DISABLED = Principal(
    user_id="auth-disabled",
    username="auth-disabled",
    display_name="Authentication disabled",
    role="auth_disabled",
    permissions=frozenset(PERMISSIONS),
    method="disabled",
)


def permissions_for(role: str) -> frozenset[str]:
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()
