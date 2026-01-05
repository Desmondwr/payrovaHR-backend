# Contract Backend Implementation Overview

This document provides a detailed explanation of the Contract management system implemented in the backend. It is designed to help frontend developers understand the data structures, lifecycle, and API endpoints.

## 1. Core Concepts

The system manages employee contracts with support for:
- **Multitenancy**: Data is stored in tenant-specific databases.
- **Unified Configuration**: Global and per-contract-type settings.
- **Lifecycle Management**: Transitions from Draft to Active/Terminated.
- **Compensation**: Base salary with flexible Allowances and Deductions.
- **Audit Trail**: Every significant action is logged (Signatures, Amendments, Status Changes).
- **Documents & Templates**: Generation of PDF contracts from templates.

---

## 2. Models & Fields

### Contract Model (`Contract`)
The primary entity representing an employment agreement.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID | Unique identifier (Primary Key). |
| `contract_id` | String | Business ID (e.g., CNT-2024-0001). Auto-generated based on config. |
| `employee` | UUID | Reference to the Employee. |
| `contract_type` | enum | `PERMANENT`, `FIXED_TERM`, `INTERNSHIP`, `CONSULTANT`, `PART_TIME`. |
| `status` | enum | See Lifecycle section below. |
| `start_date` | Date | Start date of employment. |
| `end_date` | Date | End date (nullable for `PERMANENT`). |
| `base_salary` | Decimal | Monthly/Weekly base amount. |
| `currency` | String | ISO Code (default: `XAF`). |
| `pay_frequency` | enum | `MONTHLY`, `BI_WEEKLY`, `WEEKLY`, `DAILY`. |
| `institution` | String | Company/Institution name. |
| `branch` | UUID | Optional link to a Branch. |
| `department` | UUID | Optional link to a Department. |
| `previous_contract`| UUID | Reference to parent contract if this is a renewal. |
| `gross_salary` | Decimal | **Read-only**. Calculated as Base + Allowances. |

### Nested Components (Allowances/Deductions)
When creating or updating a contract, you can pass lists of allowances and deductions. These are nested in the contract request.

- **Allowances (`allowances`)**:
    - `name`: String (e.g., "Transport Allowance")
    - `type`: `FIXED` or `PERCENTAGE`
    - `amount`: Decimal (Value or %)
    - `taxable`: Boolean
    - `cnps_base`: Boolean

- **Deductions (`deductions`)**:
    - Structure mirrors allowances but reduces net pay.

---

## 3. Contract Lifecycle (Status)

The `status` field follows this flow:

1.  **`DRAFT`**: Initial state. Editing allowed.
2.  **`PENDING_APPROVAL`**: Optional. If config `requires_approval` is True.
3.  **`APPROVED`**: Ready to be sent for signature.
4.  **`PENDING_SIGNATURE`**: Sent to parties/generated.
5.  **`SIGNED`**: Both Employee and Employer have signed.
6.  **`ACTIVE`**: Contract is currently in effect (manually activated or auto-activated on start date).
7.  **`EXPIRED`**: End date passed.
8.  **`TERMINATED`**: Contract ended prematurely.
9.  **`CANCELLED`**: Voided before activation.

---

## 4. API Endpoints

All endpoints are relative to the API base (usually `/api/`).

### Contract List & CRUD
- **`GET /contracts/`**: List contracts for the current tenant.
- **`POST /contracts/`**: Create a new contract. Includes `allowances` and `deductions` arrays in body.
- **`GET /contracts/{id}/`**: Retrieve details.
- **`PATCH /contracts/{id}/`**: Update contract.
    - *Note*: You can replace allowances/deductions by sending a new array in the `allowances`/`deductions` fields.
- **`DELETE /contracts/{id}/`**: Delete a draft contract.

### Workflow Actions (POST)
These are custom actions triggered on a specific contract ID.

| Endpoint (POST) | Body Params | Description |
| :--- | :--- | :--- |
| `/contracts/{id}/sign/` | `signature_text` (req), `document_hash` (opt) | Records a signature. If both parties sign, status moves to `SIGNED`. |
| `/contracts/{id}/activate/` | None | Manually move status to `ACTIVE`. Requires staff/admin permissions. |
| `/contracts/{id}/terminate/` | `termination_date` (req), `reason`, `notice_served` (bool) | Ends the contract. Sets `final_pay_flag=True` and status `TERMINATED`. |
| `/contracts/{id}/renew/` | `extend` (bool), `create_new` (bool), `new_end_date` (req), `start_date` (opt) | **Extend**: Updates end_date of current contract. **Create New**: Creates a linked renewal contract. |
| `/contracts/{id}/generate-document/` | `template_id` (opt) | Generates the PDF document based on a template. Returns file URL. |

### Amendments
To view or create history of changes (amendments) for a contract.

- **`GET /contracts/{id}/amendments/`**: List amendments for a specific contract.
- **`POST /contracts/{id}/amendments/`**: *Internal use mostly* - Amendments are usually created automatically via the `renew` (extend) action, but specific adjustments can be recorded here.

### Configuration (`ContractConfiguration`)
Configurations control validation rules (e.g., min wage, max backdate) and ID generation.

- **`GET /config/global/`**: Returns the global configuration object.
- **`GET /config/`**: Returns a list of all configurations (Global + Type-specific overrides).

---

## 5. Configuration Fields to Respect

Frontend should verify these settings from `/config/global/`:

- `requires_approval`: If true, move to `PENDING_APPROVAL` instead of `PENDING_SIGNATURE`.
- `requires_signature`: If false, might skip signing steps.
- `id_prefix`: Used for display logic if needed.
- `max_backdate_days`: Validation rule for `start_date`.
- `min_wage`: Validation rule for `base_salary`.
- `end_date_required`: If true for `FIXED_TERM`, ensure UI validation.

---

## 6. Frontend Integration Guidelines

1.  **Renewals**:
    - When user clicks "Renew", offer two choices: "Extend Current" (`extend=True`) or "New Contract" (`create_new=True`).
    - If "Extend", just ask for `new_end_date`.
    - If "New Contract", ask for `start_date` (defaulting to old end_date + 1) and `new_end_date`.

2.  **Signatures**:
    - The `sign` endpoint detects the user's role (Employee vs Employer) automatically based on the logged-in user.
    - Frontend should prompt for "Digital Signature" text input (e.g., typing their name).

3.  **Status Badges**:
    - `ACTIVE`: Green
    - `PENDING_SIGNATURE` / `PENDING_APPROVAL`: Amber/Yellow
    - `SIGNED`: Blue
    - `TERMINATED` / `EXPIRED`: Red/Grey

4.  **Allowances Logic**:
    - Backend creates `Allowance` objects.
    - Frontend should allow adding multiple rows.
    - `gross_salary` is read-only from backend, but frontend can estimate it: `Base + Sum(Fixed Allowances) + Sum(Base * % Allowances)`.
