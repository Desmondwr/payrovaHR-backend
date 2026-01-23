# Treasury Backend Guide (Configuration + Operations)

This document describes the treasury backend that is currently implemented, including:
- The configuration model and how it affects operations
- The REST endpoints and payloads
- Notification behavior and response format

All endpoints require authentication (JWT). Most treasury operations require an **employer** user.

---

## 1) Response format and errors

Most endpoints return a consistent payload using `api_response`:

```
{
  "success": true|false,
  "message": "human readable message",
  "data": {...} | [] ,
  "errors": [] | { ... }
}
```

Validation and permission errors use human-readable messages. Errors are surfaced either through `api_response` or through the DRF exception handler (`accounts.utils.custom_exception_handler`).

List endpoints (the standard ViewSet list actions) return **DRF paginated responses**:

```
{
  "count": 123,
  "next": "http://.../api/treasury/batches/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Pagination uses `PageNumberPagination` with `page` query param and a default `PAGE_SIZE = 20`.

---

## 2) Tenancy and storage

- **Each employer has their own treasury tables in their tenant DB**.
- The configuration table is **tenant-scoped** and stored in the tenant database.
- The configuration has a FK to `EmployerProfile` (`institution`), but the FK constraint is disabled in DB because the `accounts` tables live in default DB.

Tables used (tenant DB):
- `treasury_configuration`
- `treasury_bank_accounts`
- `treasury_cash_desks`
- `treasury_cashdesk_sessions`
- `treasury_payment_batches`
- `treasury_payment_lines`
- `treasury_transactions`
- `treasury_bank_statements`
- `treasury_bank_statement_lines`
- `treasury_reconciliation_matches`

---

## 3) Treasury Configuration (single authoritative table)

### Model
`TreasuryConfiguration` (`treasury_configuration` table)

Key rules:
- **One active config per institution** (enforced in service layer)
- **Defaults auto-create on first access**
- **No deletes** (update in place)

### Configuration endpoints
Base path: `/api/config/treasury/`

- `GET /api/config/treasury/`
  - Returns the current config (auto-creates if missing)
- `PUT /api/config/treasury/`
  - Updates current config
- `GET /api/config/treasury/preview-reference/?type=batch|trx|cash&branch=BRANCH_CODE`
  - Returns a preview of formatted reference numbers

### How configuration affects operations
Below is a field-by-field summary of effects used today:

**Global toggles**
- `enable_bank_accounts`
  - Blocks bank account CRUD and bank-sourced batches
  - Blocks transfer from cash desk to bank and bank->cash withdrawals
- `enable_cash_desks`
  - Blocks cash desk CRUD
  - Blocks cash operations and any cash-sourced batches
- `enable_mobile_money` / `enable_cheques`
  - Controls allowed `payment_method` for batches
- `enable_reconciliation`
  - Blocks statement import and reconciliation endpoints

**Numbering / references**
- `batch_reference_format`, `transaction_reference_format`, `cash_voucher_format`
  - Used only by **preview endpoint** for now
  - No auto-generation is done yet during batch execution

**Approval rules**
- `batch_approval_required` + `batch_approval_threshold_amount`
  - On submit: if total >= threshold, status -> `APPROVAL_PENDING`; otherwise -> `APPROVED`
- `allow_self_approval`
  - Prevents approver from approving their own batch
- `cancellation_requires_approval`
  - Disallows cancellation when a batch is in `APPROVAL_PENDING`
- `line_approval_required` + `line_approval_threshold_amount`
  - On line create/update, sets `requires_approval` and `approved=False`
- `allow_edit_after_approval`
  - Blocks edits to batches/lines once a batch is approved/executed/reconciled

**Execution rules**
- `default_*_payment_method`
  - Stored, but **not yet auto-applied** in the API
- `require_beneficiary_details_for_non_cash`
  - Blocks executing a batch unless payee name/id is present on each line when payment method is not cash
- `execution_proof_required`
  - `execute` endpoint requires `proof_reference`

**Cash desk policy**
- `require_open_session`
  - All cash desk operations require an open session
- `allow_negative_cash_balance`
  - Prevents going below zero on cash-out or transfer
- `max_cash_desk_balance`
  - Prevents balance from exceeding configured limit
- `cash_out_approval_threshold`
  - Blocks cash-out above threshold (must be approved elsewhere)
- `cash_out_requires_reason`
  - Blocks cash-out without notes
- `adjustments_require_approval`
  - Blocks cash-in/out category = `ADJUSTMENT`
- `discrepancy_tolerance_amount` + `auto_lock_cash_desk_on_discrepancy`
  - On close session, if discrepancy exceeds tolerance, cash desk is auto-disabled

**Reconciliation rules**
- `auto_match_enabled`
  - Enables auto-match endpoint
- `match_window_days`
  - Date window used to match statement lines
- `auto_confirm_confidence_threshold`
  - Auto-confirms matches above this score
- Auto-match logic (current):
  - First tries reference matching using statement `reference_raw`/`external_id`
    - Matches `PaymentLine.external_reference` (confidence 98)
    - Matches `TreasuryTransaction.reference` or `TreasuryTransaction.notes` (confidence 96)
  - If no reference match, falls back to amount+currency+date window:
    - PaymentLine: amount + currency + batch planned_date within window (confidence 90)
    - TreasuryTransaction: amount + currency + direction + transaction_date within window (confidence 85)
- `matching_strictness` / `lock_batch_until_reconciled`
  - Stored for future use (not enforced by endpoints yet)

---

## 4) Treasury Operations API

Base path for operations: `/api/treasury/`

### 4.1 Bank Accounts
- `GET /api/treasury/bank-accounts/`
- `POST /api/treasury/bank-accounts/`
- `GET /api/treasury/bank-accounts/{id}/`
- `PUT/PATCH /api/treasury/bank-accounts/{id}/`
- `DELETE /api/treasury/bank-accounts/{id}/`

**Withdraw to cash desk**
- `POST /api/treasury/bank-accounts/{id}/withdraw-to-cashdesk/`
  - Body:
    ```
    {
      "cashdesk_id": "uuid",
      "amount": 1000.00,
      "reference": "optional",
      "notes": "optional"
    }
    ```
  - Rules: requires bank + cash desk enabled, open cash desk session, sufficient bank balance

### 4.2 Cash Desks
- `GET /api/treasury/cash-desks/`
- `POST /api/treasury/cash-desks/`
- `GET /api/treasury/cash-desks/{id}/`
- `PUT/PATCH /api/treasury/cash-desks/{id}/`
- `DELETE /api/treasury/cash-desks/{id}/`

**Open session**
- `POST /api/treasury/cash-desks/{id}/open-session/`
  - Body: `{ "opening_count_amount": 1000.00 }`

**Close session**
- `POST /api/treasury/cash-desks/{id}/close-session/`
  - Body:
    ```
    {
      "closing_count_amount": 950.00,
      "discrepancy_note": "optional"
    }
    ```

**Cash in**
- `POST /api/treasury/cash-desks/{id}/cash-in/`
  - Body:
    ```
    {
      "amount": 500.00,
      "category": "DEPOSIT",
      "notes": "optional"
    }
    ```

**Cash out**
- `POST /api/treasury/cash-desks/{id}/cash-out/`
  - Body:
    ```
    {
      "amount": 300.00,
      "category": "WITHDRAWAL",
      "notes": "optional"
    }
    ```

**Transfer to bank**
- `POST /api/treasury/cash-desks/{id}/transfer-to-bank/`
  - Body:
    ```
    {
      "amount": 200.00,
      "bank_account_id": "uuid",
      "reference": "optional",
      "notes": "optional"
    }
    ```

### 4.3 Payment Batches
- `GET /api/treasury/batches/`
- `POST /api/treasury/batches/`
- `GET /api/treasury/batches/{id}/`
- `PUT/PATCH /api/treasury/batches/{id}/`
- `DELETE /api/treasury/batches/{id}/`

**Submit for approval**
- `POST /api/treasury/batches/{id}/submit-approval/`

**Approve**
- `POST /api/treasury/batches/{id}/approve/`

**Execute**
- `POST /api/treasury/batches/{id}/execute/`
  - Body (if required): `{ "proof_reference": "string", "notes": "optional" }`
  - Rules:
    - Batch must be `APPROVED`
    - All lines must be approved if they require approval
    - Payment method must be allowed by config
    - Source account/cash desk must be enabled and have sufficient funds
  - Behavior:
    - On successful execution, all `PENDING` payment lines in the batch are auto-marked as `PAID`
    - If `proof_reference` is provided, it is copied to `external_reference` for any line where it is empty

**Cancel**
- `POST /api/treasury/batches/{id}/cancel/`

### 4.4 Payment Lines
- `GET /api/treasury/lines/`
- `POST /api/treasury/lines/`
- `GET /api/treasury/lines/{id}/`
- `PUT/PATCH /api/treasury/lines/{id}/`
- `DELETE /api/treasury/lines/{id}/`

**Mark paid**
- `POST /api/treasury/lines/{id}/mark-paid/`
  - Body: `{ "external_reference": "optional", "notes": "optional" }`

**Mark failed**
- `POST /api/treasury/lines/{id}/fail/`
  - Body: `{ "external_reference": "optional", "notes": "optional" }`

### 4.5 Bank Statements
- `GET /api/treasury/statements/`
- `POST /api/treasury/statements/`
- `GET /api/treasury/statements/{id}/`
- `PUT/PATCH /api/treasury/statements/{id}/`
- `DELETE /api/treasury/statements/{id}/`

**Import statement**
- `POST /api/treasury/statements/import/`
  - Body:
    ```
    {
      "bank_account_id": "uuid",
      "period_start": "YYYY-MM-DD",
      "period_end": "YYYY-MM-DD",
      "lines": [
        {
          "txn_date": "YYYY-MM-DD",
          "description": "optional",
          "amount_signed": -500.00,
          "currency": "XAF",
          "reference_raw": "optional",
          "external_id": "optional"
        }
      ]
    }
    ```

**Statement lines**
- `GET /api/treasury/statements/{id}/lines/`

### 4.6 Reconciliation
- `GET /api/treasury/reconcile/auto-match/{statement_id}/`
- `POST /api/treasury/reconcile/auto-match/{statement_id}/`
- `POST /api/treasury/reconcile/confirm/`
  - Body: `{ "match_id": "uuid" }`
- `POST /api/treasury/reconcile/reject/`
  - Body: `{ "match_id": "uuid", "rejected_reason": "optional" }`

---

## 5) Notifications sent to frontend

Treasury actions emit notifications using `accounts.notifications.create_notification`, visible on:
- `GET /api/notifications/`

Examples of actions that send notifications:
- Cash desk session opened/closed
- Cash in/out
- Bank withdrawal to cash desk
- Cash desk transfer to bank
- Batch submitted/approved/executed/cancelled
- Payment line marked paid/failed
- Bank statement imported
- Reconciliation auto-match / confirm / reject

Each notification includes `type` (`INFO`, `ACTION`, `ALERT`) and a data payload (ids, status).

---

## 6) Important notes / current limits

- Reference formats are only used by the preview endpoint; batch/transaction numbers are not auto-generated yet.
- `matching_strictness` and `lock_batch_until_reconciled` are stored but not enforced yet by endpoints.
- Config is auto-created on access; if multiple active configs exist, the service deactivates older ones.

---

## 7) Suggested frontend flow

1) Load config via `GET /api/config/treasury/` to drive UI toggles.
2) Create bank accounts / cash desks as needed.
3) Create a batch, add lines, submit for approval, approve, then execute.
4) Import bank statements and reconcile as needed.
5) Use `/api/notifications/` to show action feedback to users.

---

## 8) Enum values (use these in selects)

**TreasuryConfiguration**
- `sequence_reset_policy`: `MONTHLY`, `YEARLY`, `NEVER`
- `matching_strictness`: `LOOSE`, `BALANCED`, `STRICT`
- Payment methods (used in defaults + batches): `BANK_TRANSFER`, `CASH`, `MOBILE_MONEY`, `CHEQUE`

**CashDeskSession**
- `status`: `OPEN`, `CLOSED`

**TreasuryTransaction**
- `source_type`: `BANK`, `CASHDESK`
- `direction`: `IN`, `OUT`
- `category`: `SALARY`, `EXPENSE`, `VENDOR`, `TRANSFER`, `WITHDRAWAL`, `DEPOSIT`, `ADJUSTMENT`, `OTHER`
- `status`: `DRAFT`, `APPROVAL_PENDING`, `APPROVED`, `POSTED`, `CANCELLED`
- `linked_object_type`: `PAYMENT_LINE`, `PAY_RUN`, `EXPENSE`, `BILL`, `MANUAL`, `NONE`

**PaymentBatch**
- `status`: `DRAFT`, `APPROVAL_PENDING`, `APPROVED`, `EXECUTED`, `PARTIALLY_RECONCILED`, `RECONCILED`, `CANCELLED`
- `source_type`: `BANK`, `CASHDESK`
- `payment_method`: `BANK_TRANSFER`, `CASH`, `MOBILE_MONEY`, `CHEQUE`

**PaymentLine**
- `payee_type`: `EMPLOYEE`, `VENDOR`, `OTHER`
- `status`: `PENDING`, `PAID`, `FAILED`, `CANCELLED`
- `linked_object_type`: `PAYSLIP`, `EXPENSE_CLAIM`, `BILL`, `NONE`

**BankStatement**
- `status`: `IMPORTED`, `READY`, `ARCHIVED`

**ReconciliationMatch**
- `match_type`: `PAYMENT_LINE`, `TREASURY_TRANSACTION`
- `status`: `SUGGESTED`, `CONFIRMED`, `REJECTED`

---

## 9) Model fields (backend schema)

These are the fields exposed by serializers (unless noted). Use them for structured forms.

**TreasuryConfiguration** (read‑only: `id`, `institution`, `is_active`, `created_at`, `updated_at`)
- `default_currency`, `enable_bank_accounts`, `enable_cash_desks`, `enable_mobile_money`, `enable_cheques`, `enable_reconciliation`
- `batch_reference_format`, `transaction_reference_format`, `cash_voucher_format`, `sequence_reset_policy`
- `batch_approval_required`, `batch_approval_threshold_amount`, `dual_approval_required_for_payroll`, `allow_self_approval`, `cancellation_requires_approval`
- `line_approval_required`, `line_approval_threshold_amount`, `allow_edit_after_approval`
- `default_salary_payment_method`, `default_expense_payment_method`, `default_vendor_payment_method`
- `require_beneficiary_details_for_non_cash`, `execution_proof_required`
- `enable_csv_export`, `enable_iso20022_export`, `csv_template_code`
- `require_open_session`, `allow_negative_cash_balance`
- `max_cash_desk_balance`, `min_balance_alert`, `cash_out_approval_threshold`, `cash_out_requires_reason`, `adjustments_require_approval`
- `discrepancy_tolerance_amount`, `auto_lock_cash_desk_on_discrepancy`
- `auto_match_enabled`, `match_window_days`, `auto_confirm_confidence_threshold`, `matching_strictness`, `lock_batch_until_reconciled`

**BankAccount** (read‑only: `id`, `employer_id`, `created_at`, `updated_at`)
- `branch`, `name`, `currency`, `bank_name`, `account_number`, `iban`, `account_holder_name`
- `opening_balance`, `current_balance`, `is_active`

**CashDesk** (read‑only: `id`, `employer_id`, `created_at`, `updated_at`)
- `branch`, `name`, `currency`, `custodian_employee`
- `opening_balance`, `current_balance`, `is_active`

**CashDeskSession** (created via open/close endpoints)
- `cashdesk`, `opened_by_id`, `opened_at`, `opening_count_amount`
- `status`, `closed_by_id`, `closed_at`, `closing_count_amount`
- `discrepancy_amount`, `discrepancy_note`, `created_at`, `updated_at`

**PaymentBatch** (read‑only: `id`, `employer_id`, `total_amount`, `created_at`, `updated_at`)
- `branch`, `name`, `source_type`, `source_id`, `payment_method`, `planned_date`
- `status`, `currency`, `created_by_id`, `approved_by_id`, `executed_by_id`, `executed_at`, `reference_number`

**PaymentLine** (read‑only: `id`, `created_at`, `updated_at`)
- `batch`, `batch_name`, `payee_type`, `payee_id`, `payee_name`, `amount`, `currency`
- `status`, `external_reference`, `linked_object_type`, `linked_object_id`
- `requires_approval`, `approved`, `approved_by_id`, `approved_at`

**TreasuryTransaction** (system‑generated; not exposed as CRUD API)
- `employer_id`, `source_type`, `source_id`, `direction`, `category`, `amount`, `currency`
- `transaction_date`, `reference`, `counterparty_name`, `status`
- `created_by_id`, `approved_by_id`, `linked_object_type`, `linked_object_id`, `cashdesk_session`, `notes`

**BankStatement** (read‑only: `id`, `employer_id`, `imported_at`)
- `bank_account`, `bank_account_name`, `bank_account_number`, `bank_account_bank_name`, `bank_account_currency`, `statement_name`, `period_start`, `period_end`, `status`, `source_file`

**BankStatementLine** (read‑only: `id`)
- `bank_statement`, `txn_date`, `description`, `amount_signed`, `currency`, `reference_raw`, `external_id`, `matched`, `matches_count`, `matches`

**ReconciliationMatch** (read‑only: `id`, `created_at`)
- `statement_line`, `match_type`, `match_id`, `confidence`, `status`
- `confirmed_by_id`, `confirmed_at`, `rejected_reason`
