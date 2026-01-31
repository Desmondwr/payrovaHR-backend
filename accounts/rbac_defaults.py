"""Default RBAC permission catalog for employer modules."""
from .models import Permission


DEFAULT_PERMISSIONS = [
    {
        "code": "employer.dashboard.view",
        "module": "employer",
        "resource": "dashboard",
        "action": "view",
        "scope": "COMPANY",
        "description": "View employer dashboard.",
    },
    {
        "code": "employer.config.manage",
        "module": "employer",
        "resource": "configuration",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage employer configuration (branches, departments, policies).",
    },
    {
        "code": "employees.manage",
        "module": "employees",
        "resource": "employee",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage employees and profiles.",
    },
    {
        "code": "employees.configure",
        "module": "employees",
        "resource": "configuration",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage employee setup, branches, and departments.",
    },
    {
        "code": "contracts.manage",
        "module": "contracts",
        "resource": "contract",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage contracts.",
    },
    {
        "code": "timeoff.manage",
        "module": "timeoff",
        "resource": "timeoff",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage time-off requests and configuration.",
    },
    {
        "code": "attendance.manage",
        "module": "attendance",
        "resource": "attendance",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage attendance settings and records.",
    },
    {
        "code": "income_expense.manage",
        "module": "income_expense",
        "resource": "income_expense",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage income and expense workflows.",
    },
    {
        "code": "treasury.manage",
        "module": "treasury",
        "resource": "treasury",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage treasury operations.",
    },
    {
        "code": "fleets.manage",
        "module": "fleets",
        "resource": "fleet",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage fleet operations.",
    },
    {
        "code": "frontdesk.manage",
        "module": "frontdesk",
        "resource": "frontdesk",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Manage frontdesk operations.",
    },
    {
        "code": "reports.view",
        "module": "reports",
        "resource": "reports",
        "action": "view",
        "scope": "COMPANY",
        "description": "View employer reports.",
    },
    {
        "code": "payroll.manage",
        "module": "payroll",
        "resource": "payroll",
        "action": "manage",
        "scope": "COMPANY",
        "description": "Run payroll and manage payroll workflows.",
    },
]


def ensure_default_permissions():
    """Create any missing permissions from the default catalog."""
    created = 0
    for entry in DEFAULT_PERMISSIONS:
        code = entry["code"]
        _, was_created = Permission.objects.get_or_create(code=code, defaults=entry)
        if was_created:
            created += 1
    return created

