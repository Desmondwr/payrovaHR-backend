# Contract Backend Implementation Overview

This document provides a detailed explanation of the Contract management system implemented in the backend. It is designed to help frontend developers understand the data structures, lifecycle, and API endpoints.

## 1. Core Concepts

The system manages employee contracts with support for:
- **Multitenancy**: Data is stored in tenant-specific databases.
- **Unified Configuration**: Global and per-contract-type settings.
- **Lifecycle Management**: Transitions from Draft to Active/Terminated.
- **Compensation**: Base salary with flexible Allowances and Deductions.
- **Audit Trail**: Every significant action is logged.

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

- **Fields**:
    - `name`: String (e.g., "Transport Allowance")
    - `type`: `FIXED` or `PERCENTAGE`
    - `amount`: Decimal (Value or %)
    - `taxable`: Boolean
    - `cnps_base`: Boolean

---

## 3. Contract Lifecycle (Status)

The `status` field follows this flow:

1.  **`DRAFT`**: Initial state. Editing allowed.
2.  **`PENDING_APPROVAL`**: Optional. If config requires approval.
3.  **`APPROVED`**: Ready to be sent for signature.
4.  **`PENDING_SIGNATURE`**: Sent to parties.
5.  **`SIGNED`**: Both Employee and Employer have signed.
6.  **`ACTIVE`**: Contract is currently in effect.
7.  **`EXPIRED`**: End date passed.
8.  **`TERMINATED`**: Contract ended prematurely.
9.  **`CANCELLED`**: Voided before activation.

---

## 4. API Endpoints

All endpoints are relative to the API base (usually `/api/`).

### Contract List & CRUD
- **`GET /contracts/`**: List contracts for the current tenant.
- **`POST /contracts/`**: Create a new contract.
- **`GET /contracts/{id}/`**: Retrieve details.
- **`PATCH /contracts/{id}/`**: Update contract.
    - *Note*: You can update allowances by sending a new array in the `allowances` field.
- **`DELETE /contracts/{id}/`**: Delete a draft contract.

### Workflow Actions (POST)
These are custom actions triggered on a specific contract ID.

| Endpoint | Body Params | Description |
| :--- | :--- | :--- |
| `.../{id}/sign/` | `signature_text` | Records a signature. If both parties sign, status moves to `SIGNED`. |
| `.../{id}/activate/` | None | Manually move status to `ACTIVE`. Usually requires staff permissions. |
| `.../{id}/terminate/` | `termination_date`, `reason`, `notice_served` | Ends the contract. Sets `final_pay_flag` to true. |
| `.../{id}/renew/` | `extend` (bool), `new_end_date` | Either extends current contract or creates a new one linked via `previous_contract`. |
| `.../{id}/generate-document/` | None | Generates the PDF document based on a template. |

---

## 5. Configuration (`ContractConfiguration`)

Configurations control validation rules (e.g., min wage, max backdate).

- **Global Config**: `GET /config/global/`
- **Type Overrides**: `GET /config/` (Returns list of all configs including overrides).

### Key Config Fields to Respect:
- `requires_approval`: If true, move to `PENDING_APPROVAL` instead of `PENDING_SIGNATURE`.
- `requires_signature`: If false, contract might skip the signing state.
- `id_prefix`: Used for generating the `contract_id`.
- `max_backdate_days`: Validation rule for `start_date`.
- `min_wage`: Validation rule for `base_salary`.

---

## 6. Frontend Integration Tips

1.  **Dynamic Forms**: Use the results from `/config/global/` to set default values and validation limits in your UI.
2.  **Status Badges**: Use consistent colors for statuses (e.g., Green for `ACTIVE`, Amber for `PENDING`, Red for `TERMINATED`).
3.  **Allowance Calculation**: While the backend calculates `gross_salary`, you might want to mirror the logic (Base + Fixed + (Base * %)) for real-time UI updates.
4.  **Date Validation**: Ensure `end_date` > `start_date` (if applicable) and respect `max_backdate_days`.
