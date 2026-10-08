"""
The catalogue of granular permissions that can be granted to internal employees.

Single source of truth: the admin UI reads it from GET /admin/employees/permissions and
employee updates are validated against it. "areas" lists what each permission unlocks in the UI.
Only manage_blogs, manage_support, manage_employees and manage_finance are also enforced by the API today.

Super admins, admins and the CEO implicitly hold every permission
(see common.auth_dependencies.missing_permissions).
"""

EMPLOYEE_PERMISSIONS: list[dict] = [
    {"id": "view_overview", "label": "View Overview & Performance",
     "areas": ["Admin overview", "Platform performance"]},
    {"id": "manage_users", "label": "Manage Users", "areas": ["User accounts", "Waitlist & whitelist"]},
    {"id": "manage_finance", "label": "Manage Finance", "areas": ["Finance dashboard", "Subscription plans"]},
    {"id": "manage_communications", "label": "Manage Communications", "areas": ["Broadcasts & email templates"]},
    {"id": "manage_blogs", "label": "Manage Blogs", "areas": ["Blog posts & comments"]},
    {"id": "manage_support", "label": "Manage Support", "areas": ["Support tickets", "User feedback"]},
    # Granted historically but no screen or endpoint checks it yet (feedback is gated by manage_support).
    {"id": "manage_feedback", "label": "Manage User Feedback", "areas": []},
    {"id": "manage_employees", "label": "Manage Employees",
     "areas": ["Employee directory & profiles", "Meetings & attendance"]},
    # Granted historically but no screen or endpoint checks it yet.
    {"id": "manage_performance", "label": "Manage Employee Performance", "areas": []},
    {"id": "manage_approvals", "label": "Manage Approvals Queue", "areas": ["Approvals queue"]},
    {"id": "manage_ai", "label": "Manage AI Governance", "areas": ["AI parser governance"]},
    {"id": "view_audit_logs", "label": "View Audit Logs", "areas": ["System audit logs"]},
    {"id": "manage_settings", "label": "Manage Settings", "areas": ["Platform settings"]},
]

PERMISSION_IDS: frozenset[str] = frozenset(p["id"] for p in EMPLOYEE_PERMISSIONS)
