# Comprehensive Employee Management Implementation Plan

This document serves as the master blueprint for building a complete, professional **Employee Management Infrastructure** for the Super Admin in KapuLetu. The system relies exclusively on internal, self-hosted services and enforces strict Role-Based Access Control (RBAC), dedicated workspaces, and approval workflows for high-risk operations.

---

## 1. Employee Roles, Dedicated Workspaces, & User Management

To ensure security, the platform is divided into specific **Workspaces**. Employees will only be able to see and access the modules relevant to their assigned role. 

Crucially, **User Management** (handling the platform's external users, i.e., Treasurers and group members) is segmented based on the sensitivity of the action.

### A. Customer Support Agent (`SUPPORT_AGENT`)
* **Focus:** Handling user inquiries, tickets, and basic User Management.
* **Accessible Workspaces & Modules:**
  * **Inbox & Communications:** Manage contact messages and direct user inquiries.
  * **Basic User Management (`/admin/users/support`):** View user profiles to assist with issues, trigger password reset emails, and help users navigate the platform.
  * **Help Center Management:** Update FAQs and guide documentation.
* **Restricted From:** Financial data, deleting users, suspending accounts, and employee HR management.

### B. Marketing & Content Manager (`CONTENT_MANAGER`)
* **Focus:** Managing the public-facing image, blogs, and marketing campaigns.
* **Accessible Workspaces & Modules:**
  * **Blog Management:** Full access to create, edit, publish, and delete blog posts.
  * **Marketing Campaigns:** Access to promotional campaigns.
  * **Landing Page Management:** Update features and hero sections on the main public site.
* **Restricted From:** Direct user data (PII), financial data, and system configurations.

### C. Financial & Accounts Manager (`FINANCE_MANAGER`)
* **Focus:** Platform economics, billing, and transactions.
* **Accessible Workspaces & Modules:**
  * **Financial Dashboards:** Platform-wide revenue, subscription models, and transaction analytics.
  * **Advanced Account Management (`/admin/users/accounts`):** Oversee group financial limits, billing issues, and account upgrades.
* **Restricted From:** Content creation, employee HR management, and bypassing approval workflows for refunds.

### D. Super Admin / Management (`SUPER_ADMIN`)
* **Focus:** Complete infrastructure control and final authorizations.
* **Accessible Workspaces & Modules:**
  * **Unrestricted Access:** Access to all of the above workspaces.
  * **Employee Management Hub:** Full CRUD operations for all internal staff.
  * **Approvals Queue:** Review and authorize sensitive actions initiated by lower-tier employees.
  * **Global Activity Logs:** Monitor every action taken by every employee.

---

## 2. Handling Sensitive Actions (Maker-Checker / Approvals Workflow)

For security and accountability, sensitive operations cannot be unilaterally executed by standard employees. We will implement a **Maker-Checker (Approvals) Workflow**.

* **Sensitive Actions include:**
  * Issuing financial refunds or adjusting billing.
  * Permanently deleting or suspending a user/group account.
  * Changing global platform configurations (fees, limits).
  * Promoting an employee to a higher role.
* **How it works:**
  1. **Initiation (The Maker):** A `FINANCE_MANAGER` attempts to issue a refund. Instead of executing immediately, the system creates a `Pending Action Request`.
  2. **The Approvals Queue (`/admin/approvals`):** This request is routed to the Super Admin's approval queue. The request contains the action details, the initiating employee, and a justification note.
  3. **Authorization (The Checker):** The `SUPER_ADMIN` reviews the request and clicks "Approve" (executing the action) or "Reject".
  4. **Audit Trail:** The entire lifecycle (who requested it, who approved it, and when) is permanently recorded in the `employee_audit_logs`.

---

## 3. Onboarding Workflow (Self-Hosted)

The process of bringing a new employee onto the KapuLetu platform:

1. **Invitation Generation:** The Super Admin enters the employee's details and selects their `Role` in `/admin/employees`.
2. **Internal Email Dispatch:** The backend uses the self-hosted KapuLetu SMTP service to send a secure magic link: `https://kapuletu.co.ke/employee-setup?token=xyz...`
3. **Password Configuration:** The employee clicks the link, enters a secure password, and their account is activated in the `users` table.

---

## 4. Database Schema & Architecture

To support this infrastructure, we need the following database modifications in Python/SQLAlchemy:

* **Extend `UserRole` Enum:** `CONTENT_MANAGER`, `SUPPORT_AGENT`, `FINANCE_MANAGER`, `SUPER_ADMIN`.
* **Create `user_invites` Table:** `id`, `email`, `role`, `token`, `expires_at`, `is_used`.
* **Create `approval_requests` Table:** `id`, `requested_by`, `action_type`, `payload` (JSON), `status` (PENDING, APPROVED, REJECTED), `resolved_by`, `timestamp`.
* **Create `employee_audit_logs` Table:** `log_id`, `employee_id`, `action_type`, `resource_id`, `details` (JSON), `timestamp`, `ip_address`.

---

## 5. Phased Execution Plan

1. **Phase 1: Database & Backend Foundation.** Implement the new enums, SQLAlchemy models (`user_invites`, `employee_audit_logs`, `approval_requests`), and the SMTP email integration.
2. **Phase 2: The Core API Endpoints.** Build the invite generation, password setup, and Employee CRUD endpoints for the Super Admin.
3. **Phase 3: Employee UI & Onboarding.** Build the `/employee-setup` page and the Super Admin `/admin/employees` directory.
4. **Phase 4: Workspaces & RBAC.** Refactor the frontend sidebar and backend routers to strictly enforce role-based access to specific modules (Content, Support, Finance).
5. **Phase 5: Approvals Workflow & Audit Logs.** Build the Maker-Checker engine for sensitive actions and the global activity feed for the Super Admin.
