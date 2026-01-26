# Income & Expense Backend Guide (Configuration + Workflows)

This document describes the Income/Expense + Budget backend currently implemented, including:
- Configuration and how it drives validation and approvals
- Employer vs Employee workflows
- Endpoints and payloads
- Budget control behavior
- Treasury integration hooks
- Notifications and status definitions

All endpoints require authentication (JWT). Most administrative actions require an **employer** user.

---

## 1) Response format and errors

Most action endpoints return a consistent payload via `api_response`:

```
{
  "success": true|false,
  "message": "human readable message",
  "data": {...} | [] ,
  "errors": [] | { ... }
}
```

Validation and permission errors return human-readable messages. Errors are surfaced either through `api_response` or the DRF exception handler (`accounts.utils.custom_exception_handler`).

List endpoints (standard ViewSet list actions) return **DRF paginated responses**:

```
{
  "count": 123,
  "next": "http://.../api/income-expense/expenses/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Pagination uses `PageNumberPagination` with `page` query param and default `PAGE_SIZE = 20`.

---

## 2) Tenancy and storage

- **All Income/Expense tables live in the tenant DB**.
- Configuration is tenant-scoped and stored in the tenant database.
- The configuration has a FK to `EmployerProfile` (`institution`), but DB constraints are disabled because `accounts` lives in the default DB.

Tables (tenant DB):
- `income_expense_configuration`
- `expense_category`
- `income_category`
- `budget_plan`
- `budget_line`
- `expense_claim`
- `income_record`

---

## 3) Roles and access

Simple role model used by backend:

- **Employee**: can create their own expenses, submit them, and see status.
- **Employer/Admin**: can configure, approve/reject, manage budgets, and create income records.

Access enforcement highlights:
- Expenses: employee can create for themselves; list is filtered to own expenses.
- Income: only employer/admin can create or act on income.
- Budgets and categories: employer-only.

---

## 4) Configuration (single authoritative table)

### Model
`IncomeExpenseConfiguration` (`income_expense_configuration` table)

Key rules:
- **One active config per institution** (service enforces this)
- **Auto-created on first GET**
- **No deletes** (update in place)

### Configuration endpoint
Base path: `/api/income-expense/`

- `GET /api/income-expense/config/`
  - Returns current config (auto-creates if missing)
- `PUT /api/income-expense/config/`
  - Updates current config (employer only)

### How configuration affects operations

**General toggles**
- `enable_income`, `enable_expenses`, `enable_budgets`
  - Disable CRUD/workflow entry points when false

**Expense submission rules**
- `expense_require_attachment`
- `expense_require_notes`
- `expense_allow_backdate`
- `expense_max_backdate_days`

These are enforced at **create** and **submit**.

**Expense approval rules**
- `expense_approval_required`
- `expense_approval_threshold_amount`
- `expense_allow_self_approval`
- `expense_cancel_requires_approval`
- `expense_allow_edit_after_approval`

**Income rules**
- `income_allow_manual_entry`
- `income_require_attachment`
- `income_require_notes`
- `income_approval_required`
- `income_approval_threshold_amount`

**Budgeting rules**
- `budget_control_mode`: `OFF | WARN | BLOCK`
- `budget_periodicity`: `MONTHLY | QUARTERLY | YEARLY`
- `budget_scope`: `COMPANY | BRANCH | DEPARTMENT`
- `budget_enforce_on_submit`
- `budget_enforce_on_approval`
- `budget_allow_override`
- `budget_override_requires_reason`

**Treasury integration**
- `push_approved_expenses_to_treasury`
- `auto_mark_paid_from_treasury`

---

## 5) Status definitions (use these values)

**Expense statuses**
- `DRAFT`
- `APPROVAL_PENDING`
- `APPROVED`
- `REJECTED`
- `CANCELLED`
- `PAID`

**Income statuses**
- `DRAFT`
- `APPROVAL_PENDING`
- `APPROVED`
- `REJECTED`
- `CANCELLED`
- `RECEIVED`

---

## 6) Endpoints

Base path: `/api/income-expense/`

### 6.1 Categories (Employer only)

**Expense categories**
- `GET /api/income-expense/expense-categories/`
- `POST /api/income-expense/expense-categories/`
- `GET /api/income-expense/expense-categories/{id}/`
- `PUT/PATCH /api/income-expense/expense-categories/{id}/`
- `DELETE /api/income-expense/expense-categories/{id}/` (soft delete)

**Income categories**
- `GET /api/income-expense/income-categories/`
- `POST /api/income-expense/income-categories/`
- `GET /api/income-expense/income-categories/{id}/`
- `PUT/PATCH /api/income-expense/income-categories/{id}/`
- `DELETE /api/income-expense/income-categories/{id}/` (soft delete)

### 6.2 Budgets (Employer only)

**Budget plans**
- `GET /api/income-expense/budgets/`
- `POST /api/income-expense/budgets/`
- `GET /api/income-expense/budgets/{id}/`
- `PUT/PATCH /api/income-expense/budgets/{id}/`
- `DELETE /api/income-expense/budgets/{id}/` (soft delete)

**Summary**
- `GET /api/income-expense/budgets/{id}/summary/`
  - Returns totals per currency (allocated/consumed/reserved/remaining)

**Activate plan**
- `POST /api/income-expense/budgets/{id}/activate/`
  - Rules:
    - Plan must have at least one line
    - Prevents conflicts with existing ACTIVE plans that overlap date range, periodicity, scope, category, and currency

**Budget lines**
- `GET /api/income-expense/budget-lines/`
- `POST /api/income-expense/budget-lines/`
- `GET /api/income-expense/budget-lines/{id}/`
- `PUT/PATCH /api/income-expense/budget-lines/{id}/`
- `DELETE /api/income-expense/budget-lines/{id}/` (soft delete)

### 6.3 Expenses (Employee + Employer)

**CRUD**
- `GET /api/income-expense/expenses/`
  - Filters: `status`, `employee_id` (employer only), `from`, `to`
- `POST /api/income-expense/expenses/`
- `GET /api/income-expense/expenses/{id}/`
- `PUT/PATCH /api/income-expense/expenses/{id}/`
- `DELETE /api/income-expense/expenses/{id}/` (soft delete)

**Actions**
- `POST /api/income-expense/expenses/{id}/submit/`
- `POST /api/income-expense/expenses/{id}/approve/`
- `POST /api/income-expense/expenses/{id}/reject/`
- `POST /api/income-expense/expenses/{id}/cancel/`
- `POST /api/income-expense/expenses/{id}/mark-paid/`

### 6.4 Income (Employer only)

**CRUD**
- `GET /api/income-expense/income/`
  - Filters: `status`, `from`, `to`
- `POST /api/income-expense/income/`
- `GET /api/income-expense/income/{id}/`
- `PUT/PATCH /api/income-expense/income/{id}/`
- `DELETE /api/income-expense/income/{id}/` (soft delete)

**Actions**
- `POST /api/income-expense/income/{id}/submit/`
- `POST /api/income-expense/income/{id}/approve/`
- `POST /api/income-expense/income/{id}/reject/`
- `POST /api/income-expense/income/{id}/mark-received/`

### 6.5 Treasury payment update (internal)

- `POST /api/income-expense/treasury/payment-update/`
  - Body:
    ```
    {
      "expense_id": "uuid",
      "treasury_payment_line_id": "optional uuid",
      "status": "PAID" | "FAILED",
      "paid_at": "optional datetime",
      "external_reference": "optional string"
    }
    ```

---

## 7) Expense workflow (Employee vs Employer)

### 7.1 Employee side: create expense (draft)

**Endpoint**: `POST /api/income-expense/expenses/`

Employee provides:
- `expense_category`
- `title`
- `expense_date`
- `amount`
- `currency` (default from config if omitted)
- `notes` (if required)
- `attachment` (if required)

Backend sets automatically:
- `employee` from session
- `institution_id` from tenant
- `status = DRAFT`
- `created_by_id`

**Config enforcement at create**
- `expense_require_notes` => notes required
- `expense_require_attachment` => attachment required
- `expense_allow_backdate` and `expense_max_backdate_days` enforced

### 7.2 Employee side: submit

**Endpoint**: `POST /api/income-expense/expenses/{id}/submit/`

Rules:
- Employee must own the expense
- Required fields validated again

Approval routing:
- If `expense_approval_required = False` => auto `APPROVED`
- If `expense_approval_required = True` and amount >= threshold => `APPROVAL_PENDING`
- Otherwise => `APPROVAL_PENDING` (current behavior)

Budget enforcement:
- If `budget_enforce_on_submit = True`, a budget check runs
- If `budget_enforce_on_approval = True` and auto-approval happens on submit, a budget check runs
- Results:
  - `OFF` => no warnings
  - `WARN` => allowed; response includes `budget_warning` and `budget_remaining`
  - `BLOCK` => requires override if allowed (otherwise error)

### 7.3 Employer side: approve

**Endpoint**: `POST /api/income-expense/expenses/{id}/approve/`

Checks:
- Employer/admin only
- Status must be `APPROVAL_PENDING`
- If `expense_allow_self_approval = False`, approver cannot be `created_by_id`

Budget:
- If `budget_enforce_on_approval = True`, budget is re-checked
- `BLOCK` requires override if allowed
- `WARN` is allowed and returns warning fields

On success:
- Status -> `APPROVED`
- `approved_by_id`, `approved_at` set
- Budget consumption applied

Treasury integration:
- If `push_approved_expenses_to_treasury = True`, backend calls a stub integration hook and can store `treasury_payment_line_id`.

### 7.4 Employer side: reject

**Endpoint**: `POST /api/income-expense/expenses/{id}/reject/`

Rules:
- Status must be `APPROVAL_PENDING`
- `rejected_reason` is required
- Releases budget reservation if applicable

### 7.5 Cancel

**Endpoint**: `POST /api/income-expense/expenses/{id}/cancel/`

Rules:
- Allowed from `DRAFT`, `APPROVAL_PENDING`, `APPROVED`
- If `expense_cancel_requires_approval = True`, only employer can cancel when status is pending/approved
- If `APPROVED` and `expense_allow_edit_after_approval = False`, cancellation is blocked
- If `APPROVED` and `treasury_payment_line_id` exists, cancellation is blocked

### 7.6 Mark paid (manual)

**Endpoint**: `POST /api/income-expense/expenses/{id}/mark-paid/`

Rules:
- Employer/admin only
- `auto_mark_paid_from_treasury` must be True
- Status must be `APPROVED` or `PAID`
- Sets `status = PAID`, `paid_at`, and optional `treasury_payment_line_id`

### 7.7 Treasury payment update (callback)

**Endpoint**: `POST /api/income-expense/treasury/payment-update/`

Rules:
- Only applies if `auto_mark_paid_from_treasury = True`

Behavior:
- `PAID` => `status = PAID`, clears `payment_failed`
- `FAILED` => status stays `APPROVED`, sets `payment_failed = True` and reason
- Optional `treasury_payment_line_id` and `external_reference` saved

---

## 8) Income workflow (Employer/Finance)

### 8.1 Create income

**Endpoint**: `POST /api/income-expense/income/`

Rules:
- Employer/admin only
- `income_allow_manual_entry` must be True
- `income_require_notes` / `income_require_attachment` enforced
- Status = `DRAFT`

### 8.2 Submit income

**Endpoint**: `POST /api/income-expense/income/{id}/submit/`

Approval routing:
- If `income_approval_required = False` => `APPROVED`
- If required and threshold met => `APPROVAL_PENDING`
- Otherwise => `APPROVAL_PENDING` (current behavior)

Budget enforcement:
- Uses same WARN/BLOCK behavior as expenses

### 8.3 Approve / Reject

- `POST /api/income-expense/income/{id}/approve/`
- `POST /api/income-expense/income/{id}/reject/`

Rules:
- Status must be `APPROVAL_PENDING`
- `rejected_reason` required on reject
- Budget consumption applied on approve

### 8.4 Mark received

**Endpoint**: `POST /api/income-expense/income/{id}/mark-received/`

Rules:
- Allowed from `APPROVED` or `RECEIVED`
- Sets `received_at` and optional `bank_statement_line_id`

---

## 9) Budget workflow (Employer only)

### 9.1 Budget setup

**Create plan**
- `POST /api/income-expense/budgets/`
- Uses config default `budget_periodicity` if not supplied

**Add lines**
- `POST /api/income-expense/budget-lines/`

Rules:
- Must match config `budget_scope` (COMPANY/BRANCH/DEPARTMENT)
- `COMPANY` => `scope_id` must be null
- `BRANCH` / `DEPARTMENT` => `scope_id` required
- `category_type` controls which category FK is required

**Activate**
- `POST /api/income-expense/budgets/{id}/activate/`
- Prevents overlapping active plans for the same scope/category/currency

### 9.2 Budget consumption

Budget check resolves a line by:
- ACTIVE plan with matching periodicity and date window
- Matching scope (company/branch/department)
- Matching category (expense or income)

Remaining is computed as:
```
remaining = allocated - consumed - reserved
```

Control mode:
- `OFF` => no warning or blocking
- `WARN` => allowed; response includes warning
- `BLOCK` => requires override if allowed (otherwise error)

Reservation/consumption rules:
- If `budget_enforce_on_submit = True`, submit reserves amount
- If `budget_enforce_on_approval = True`, approval consumes amount
- When consuming, reserved amount is reduced if it was reserved
- Reject or cancel releases reserved amount (when applicable)

---

## 10) Editing rules

**Expenses**
- If `expense_allow_edit_after_approval = False`, updates are blocked when status is:
  - `APPROVAL_PENDING`, `APPROVED`, `PAID`, `CANCELLED`

**Income**
- Updates are blocked when status is:
  - `APPROVED`, `RECEIVED`, `CANCELLED`

---

## 11) Notifications sent to frontend

Notifications are created using `accounts.notifications.create_notification` and appear in:
- `GET /api/notifications/`

Events emitted:
- Expense submitted (employee + employer)
- Expense approved/rejected/cancelled/paid (employee)
- Income submitted/approved/rejected/received (employer)

Each notification includes a `type` (`INFO`, `ACTION`, `ALERT`) and a `data` payload with IDs/status.

---

## 12) Model fields (frontend form reference)

Use these fields for UI forms; read-only fields should be displayed but not editable.

### 12.1 IncomeExpenseConfiguration (read-only: `id`, `institution`, `is_active`, `created_at`, `updated_at`)
- `default_currency`, `enable_income`, `enable_expenses`, `enable_budgets`
- `expense_require_attachment`, `expense_require_notes`, `expense_allow_backdate`, `expense_max_backdate_days`
- `expense_approval_required`, `expense_approval_threshold_amount`, `expense_allow_self_approval`, `expense_cancel_requires_approval`, `expense_allow_edit_after_approval`
- `income_allow_manual_entry`, `income_require_attachment`, `income_require_notes`, `income_approval_required`, `income_approval_threshold_amount`
- `budget_control_mode`, `budget_periodicity`, `budget_scope`, `budget_enforce_on_submit`, `budget_enforce_on_approval`, `budget_allow_override`, `budget_override_requires_reason`
- `push_approved_expenses_to_treasury`, `push_approved_vendor_bills_to_treasury`, `auto_mark_paid_from_treasury`

### 12.2 ExpenseCategory / IncomeCategory (read-only: `id`, `institution_id`, `created_at`, `updated_at`, delete fields)
- `code`, `name`, `is_active`

### 12.3 BudgetPlan (read-only: `id`, `institution_id`, `created_at`, `updated_at`, delete fields)
- `name`, `periodicity`, `start_date`, `end_date`, `status`

### 12.4 BudgetLine (read-only: `id`, `created_at`, `updated_at`, delete fields)
- `budget_plan`, `scope_type`, `scope_id`, `category_type`
- `expense_category` or `income_category`
- `currency`, `allocated_amount`, `consumed_amount`, `reserved_amount`, `is_active`

### 12.5 ExpenseClaim (read-only: `id`, `institution_id`, `status`, timestamps, treasury/payment fields)
- `employee`, `expense_category`, `title`, `notes`, `expense_date`, `amount`, `currency`, `attachment`
- `submitted_at`, `approved_by_id`, `approved_at`, `rejected_reason`
- `treasury_payment_line_id`, `treasury_external_reference`, `paid_at`
- `payment_failed`, `payment_failed_reason`
- `budget_line`, `budget_override_used`, `budget_override_reason`

### 12.6 IncomeRecord (read-only: `id`, `institution_id`, `status`, timestamps)
- `income_category`, `title`, `notes`, `income_date`, `amount`, `currency`, `attachment`
- `submitted_at`, `approved_by_id`, `approved_at`, `rejected_reason`
- `bank_statement_line_id`, `received_at`
- `budget_line`, `budget_override_used`, `budget_override_reason`

---

## 13) Frontend flow suggestion

1) Load config via `GET /api/income-expense/config/` and drive UI toggles/validation.
2) Employer sets categories and budgets if enabled.
3) Employee creates expense drafts, then submits.
4) Employer approves/rejects, then treasury handles payment; payment updates flow back.
5) Employer creates income and marks received after confirmation.
6) Use `/api/notifications/` to show action outcomes.

---

## 14) Enum values

**IncomeExpenseConfiguration**
- `budget_control_mode`: `OFF`, `WARN`, `BLOCK`
- `budget_periodicity`: `MONTHLY`, `QUARTERLY`, `YEARLY`
- `budget_scope`: `COMPANY`, `BRANCH`, `DEPARTMENT`

**BudgetPlan**
- `status`: `DRAFT`, `ACTIVE`, `CLOSED`

**BudgetLine**
- `scope_type`: `COMPANY`, `BRANCH`, `DEPARTMENT`
- `category_type`: `EXPENSE`, `INCOME`

**ExpenseClaim**
- `status`: `DRAFT`, `APPROVAL_PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`, `PAID`

**IncomeRecord**
- `status`: `DRAFT`, `APPROVAL_PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`, `RECEIVED`
