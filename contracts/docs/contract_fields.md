# Contract & Configuration Field Reference

## Contract model fields

| Field | Type | Description |
| ----- | ---- | ----------- |
| `id` | `UUIDField` | Primary key auto-generated with `uuid.uuid4`. |
| `employer_id` | `IntegerField` | Tenant-aware employer identifier (from main database). |
| `contract_id` | `CharField(max_length=50)` | Unique contract identifier (auto-generated or manual). |
| `employee` | `ForeignKey('employees.Employee')` | Employee the contract belongs to. |
| `branch` | `ForeignKey('employees.Branch', null=True, blank=True)` | Optional branch where the employee works. |
| `department` | `ForeignKey('employees.Department', null=True, blank=True)` | Optional associated department. |
| `contract_type` | `CharField(max_length=20)` | Employment type; choices: `PERMANENT`, `FIXED_TERM`, `INTERNSHIP`, `CONSULTANT`, `PART_TIME`. |
| `start_date` | `DateField` | Contract start date. |
| `end_date` | `DateField(null=True, blank=True)` | Nullable end date (required for non-permanent contracts). |
| `status` | `CharField(max_length=20)` | Lifecycle status; choices include `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `PENDING_SIGNATURE`, `SIGNED`, `ACTIVE`, `EXPIRED`, `TERMINATED`, `CANCELLED`. Defaults to `DRAFT`. |
| `salary_scale` | `ForeignKey('SalaryScale', null=True, blank=True)` | Optional salary scale reference. |
| `base_salary` | `DecimalField(max_digits=12, decimal_places=2)` | Base salary amount. |
| `currency` | `CharField(max_length=3)` | ISO currency code (default `XAF`). |
| `pay_frequency` | `CharField(max_length=20)` | Payment cadence; choices: `MONTHLY`, `BI_WEEKLY`, `WEEKLY`, `DAILY`. Defaults to `MONTHLY`. |
| `previous_contract` | `ForeignKey('self', null=True, blank=True)` | Link to a preceding contract when this is a renewal. |
| `termination_date` | `DateField(null=True, blank=True)` | Date when the contract was terminated. |
| `termination_reason` | `TextField(null=True, blank=True)` | Optional explanation for termination. |
| `notice_served` | `BooleanField(default=False)` | Flag indicating whether the required notice period was served. |
| `final_pay_flag` | `BooleanField(default=False)` | Indicates that final payroll processing should occur. |
| `created_by` | `IntegerField` | Creator ID from main database. |
| `created_at` | `DateTimeField(auto_now_add=True)` | Timestamp when the record was created. |
| `updated_at` | `DateTimeField(auto_now=True)` | Timestamp for the last update. |

Note: job-specific metadata (e.g., `job_position`) is now captured via `recruitment_configuration` and its related sections instead of on the `Contract` model.

## ContractConfiguration model fields

| Field | Type | Description |
| ----- | ---- | ----------- |
| `id` | `UUIDField` | Primary key generated via `uuid.uuid4`. |
| `employer_id` | `IntegerField` | Tenant-aware employer reference. |
| `contract_type` | `CharField(max_length=20)` | Optional contract type override (same choices as `Contract.contract_type`). Null implies global settings. |
| `id_prefix` | `CharField(max_length=10)` | Prefix used when generating contract IDs. |
| `id_year_format` | `CharField(choices=[('YYYY', 'YYYY'), ('YY', 'YY')])` | Year formatting used in generated IDs. |
| `id_include_institution_code` | `BooleanField(default=False)` | Whether the employer code is included in generated IDs. |
| `id_sequence_padding` | `IntegerField(default=5)` | Width for the incremental sequence in IDs. |
| `id_reset_sequence_yearly` | `BooleanField(default=True)` | Reset sequence each year if `True`. |
| `last_sequence_number` | `IntegerField(default=0)` | Tracks the last number used for ID generation. |
| `max_backdate_days` | `IntegerField(default=30)` | Maximum days allowed for backdated contracts. |
| `allow_future_contracts` | `BooleanField(default=True)` | Whether start dates in the future are allowed. |
| `min_fixed_term_duration_days` | `IntegerField(default=30)` | Minimum duration for fixed-term contracts. |
| `probation_must_end_before_contract` | `BooleanField(default=True)` | Probation must finish before the contract ends. |
| `default_duration_months` | `IntegerField(null=True, blank=True)` | Fallback duration for duration-unset contracts. |
| `end_date_required` | `BooleanField(default=True)` | Whether an end date must be supplied for non-permanent contracts. |
| `default_probation_period_months` | `IntegerField(default=3)` | Default probation period in months. |
| `overtime_eligible` | `BooleanField(default=True)` | Whether the contract is eligible for overtime. |
| `default_notice_period_days` | `IntegerField(default=30)` | Default notice period duration. |
| `default_leave_policy` | `CharField(max_length=100, null=True, blank=True)` | Default leave policy label. |
| `default_template` | `ForeignKey('ContractTemplate', null=True, blank=True)` | Default contract template for this employer/type. |
| `min_wage` | `DecimalField(max_digits=12, decimal_places=2)` | Minimum allowable salary. |
| `max_salary_without_approval` | `DecimalField(max_digits=12, decimal_places=2)` | Threshold above which approval is required. |
| `salary_scale_enforcement` | `CharField(choices=[('STRICT', 'Strict'), ('WARNING', 'Warning'), ('DISABLED', 'Disabled')])` | Enforcement level for salary scales. |
| `allow_salary_override` | `BooleanField(default=True)` | Whether base salary can diverge from the scale. |
| `require_gross_salary_gt_zero` | `BooleanField(default=True)` | Ensures the gross salary is above zero. |
| `allow_duplicate_allowances` | `BooleanField(default=False)` | Permit multiple allowances with the same name. |
| `auto_apply_default_allowances` | `BooleanField(default=True)` | Automatically apply default allowances. |
| `allow_manual_allowances` | `BooleanField(default=True)` | Allow manual allowance creation. |
| `allow_percentage_allowances` | `BooleanField(default=True)` | Allow percentage-based allowances. |
| `max_allowance_percentage` | `DecimalField(max_digits=5, decimal_places=2)` | Cap on total percentage-based allowances. |
| `approval_enabled` | `BooleanField(default=False)` | Whether contract approval workflow is active. |
| `requires_approval` | `BooleanField(default=False)` | Type-specific override forcing approval. |
| `approval_levels` | `JSONField` | Ordered list of approval roles (e.g., `["HR","FINANCE"]`). |
| `salary_thresholds` | `JSONField` | Thresholds per level (e.g., `{"FINANCE":500000}`). |
| `signature_required` | `BooleanField(default=True)` | Documents must include signatures globally. |
| `requires_signature` | `BooleanField(default=True)` | Type-specific signature override. |
| `signing_order` | `CharField(choices=[('EMPLOYEE_FIRST','Employee -> Employer'),('EMPLOYER_FIRST','Employer -> Employee'),('PARALLEL','Parallel')])` | Signature queue order. |
| `allow_activation_without_signature` | `BooleanField(default=False)` | Permit activation before signing. |
| `signature_reminder_interval_days` | `IntegerField(default=3)` | Days between signature reminders. |
| `signature_expiry_days` | `IntegerField(default=14)` | Days before a signature request expires. |
| `allow_concurrent_contracts_same_inst` | `BooleanField(default=False)` | Permit multiple contracts with same institution. |
| `allow_multi_institution_employment` | `BooleanField(default=False)` | Allow employment across institutions. |
| `auto_activate_on_start` | `BooleanField(default=True)` | Automatically activate contracts on start. |
| `auto_expire_fixed_term` | `BooleanField(default=True)` | Auto-expire fixed term contracts once due. |
| `auto_renew_option_available` | `BooleanField(default=False)` | Indicates if renewal option exists. |
| `expiry_grace_period_days` | `IntegerField(default=0)` | Extra days before treating a contract as expired. |
| `enable_notifications` | `BooleanField(default=True)` | Enable notifications for this configuration. |
| `days_before_expiry_notify` | `IntegerField(default=30)` | Days ahead to notify before expiry. |
| `recruitment_configuration` | `JSONField` | Recruitment metadata defaults (application IDs, offer refs, etc.). |
| `attendance_configuration` | `JSONField` | Attendance rules (schedules, shifts, requirements). |
| `time_off_configuration` | `JSONField` | Leave policy defaults/overrides per type. |
| `payroll_configuration` | `JSONField` | Payroll inputs (tax profile, CNPS, probation, proration). |
| `expense_configuration` | `JSONField` | Expense routing (policy, cost center, reimbursement). |
| `fleet_configuration` | `JSONField` | Fleet entitlements (vehicle, transport allowance). |
| `signature_configuration` | `JSONField` | Document & signature defaults (template, method, hash). |
| `governance_configuration` | `JSONField` | Governance/audit defaults (approval/activation ownership). |
| `created_at` | `DateTimeField(auto_now_add=True)` | Creation timestamp. |
| `updated_at` | `DateTimeField(auto_now=True)` | Last updated timestamp. |

## ContractConfiguration JSON sections

### Recruitment configuration (`recruitment_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `job_position_id` | `IntegerField` | Optional pointer to the master job position record used when generating or syncing this contract. |
| `recruitment_application_id` | `IntegerField` | The candidate application tied to this contract when it originated from the recruitment workflow. |
| `offer_reference` | `CharField` | Employer-specific offer reference or document number for traceability. |

### Attendance configuration (`attendance_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `work_schedule_type` | `CharField` | Expected schedule type (`FIXED` or `SHIFT`). |
| `shift_template_id` | `IntegerField` | Shift template used for attendance rostering. |
| `work_days_per_week` | `IntegerField` | Number of days the employee is expected to work. |
| `hours_per_week` | `DecimalField` | Weekly hours commitment. |
| `daily_start_time` / `daily_end_time` | `TimeField` | Planned daily window. |
| `timezone` | `CharField` | Primary timezone for attendance tracking. |
| `attendance_required` | `BooleanField` | Toggle whether attendance is enforced for this contract. |
| `overtime_eligible` | `BooleanField` | Whether the employee can earn overtime. |
| `overtime_rule_id` | `IntegerField` | Optional linkage to the overtime policy applied. |
| `overtime_weekly_cap` | `DecimalField` | Maximum overtime hours allowed per week. |

### Time off configuration (`time_off_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `leave_policy_id` | `IntegerField` | Preferred leave policy record used when evaluating entitlements. |
| `leave_override_enabled` | `BooleanField` | Controls whether contract-level overrides of policy entitlements are allowed. |
| `leave_entitlements` | `Array` | Optional list of entitlement overrides, each entry describing `leave_type_id`, `annual_allocation`, `accrual_method`, and `effective_from`. |

### Payroll configuration (`payroll_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `payment_method` | `CharField` | Preferred payout channel (`BANK`, `CASH`, `MOBILE_MONEY`). |
| `tax_profile_id` | `IntegerField` | Tax profile used during payroll processing. |
| `cnps_applicable` | `BooleanField` | Whether the employee is subject to CNPS contributions. |
| `probation_period_days` | `IntegerField` | Probation length used for related calculations. |
| `proration_rule_id` | `IntegerField` | Reference to a proration rule (if any). |

### Expense configuration (`expense_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `expense_policy_id` | `IntegerField` | Expense policy governing reimbursements. |
| `cost_center_id` | `IntegerField` | Cost center used for posting expense lines. |
| `reimbursement_method` | `CharField` | Preferred reimbursement type (e.g., `BANK_TRANSFER`). |

### Fleet configuration (`fleet_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `fleet_eligible` | `BooleanField` | Indicates whether the employee can be assigned a fleet vehicle. |
| `vehicle_grade_id` | `IntegerField` | Vehicle grade used when allocating cars. |
| `transport_allowance_eligible` | `BooleanField` | Enables transport allowance payments. |

### Signature configuration (`signature_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `contract_template_id` | `UUIDField` | Template expected to be used when generating the signed contract. |
| `signed_document_id` | `UUIDField` | Document that was signed (if already generated). |
| `signature_method` | `CharField` | Method used for signatures (`DOCUSIGN` or `INTERNAL`). |
| `signed_at` | `DateTimeField` | Timestamp recorded when the signature finished. |
| `document_hash` | `CharField` | Hash of the signed file stored for verification. |
| `signature_audit_id` | `CharField` | Audit trail identifier supplied by the signing provider. |

### Governance configuration (`governance_configuration`)
| Field | Type | Description |
| --- | --- | --- |
| `approval_status` | `CharField` | Latest governance status (`PENDING`, `APPROVED`, `REJECTED`). |
| `approved_by` / `activated_by` / `terminated_by` | `IntegerField` | User IDs responsible for the respective transitions. |
| `approved_at` / `activated_at` / `terminated_at` | `DateTimeField` | Timestamps tracking the lifecycle decisions. |

## Allowance & Deduction metadata

Both `Allowance` and `Deduction` entries now capture optional identifiers and effective dates:
- `allowance_id` / `deduction_id` (`IntegerField`): Optional reference to shared allowance/deduction templates or master records.
- `effective_from` (`DateField`): Date when the component starts applying.

## ContractSignature metadata

The `ContractSignature` audit model now captures additional metadata:
- `signature_method` (`CharField`, choices `DOCUSIGN` / `INTERNAL`): How the signature was collected.
- `signature_audit_id` (`CharField`): Optional provider audit reference (e.g., DocuSign envelope ID).
- `signed_document` (`ForeignKey` → `ContractDocument`): Document that was signed.
