"""
Default schema and helper utilities for the Time Off module.

The configuration is stored as JSON (see timeoff.models.TimeOffConfiguration.configuration).
This module keeps a canonical default structure and merge/validation helpers so every tenant
starts with a usable configuration and partial updates stay well-formed.
"""
from copy import deepcopy
from typing import Any, Dict, List

ALLOWED_TIME_UNITS = {"DAYS", "HALF_DAYS", "HOURS"}
ALLOWED_LEAVE_YEAR_TYPES = {"CALENDAR", "FISCAL"}
ALLOWED_ACCRUAL_METHODS = {"FIXED_ANNUAL", "MONTHLY", "BI_WEEKLY", "PER_PAY_PERIOD", "PER_ATTENDANCE"}
ALLOWED_ACCRUAL_START = {"DATE_OF_JOINING", "CONFIRMATION_DATE", "FIXED_DATE"}
ALLOWED_PRORATION_METHODS = {"DAILY", "MONTHLY"}

ALLOWED_WEEKDAY_NAMES = {
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
}
ALLOWED_RESERVATION_POLICIES = {"RESERVE_ON_SUBMIT", "DEDUCT_ON_APPROVAL"}
ALLOWED_ROUNDING_UNITS = {"MINUTES"}
ALLOWED_ROUNDING_METHODS = {"UP", "DOWN", "NEAREST"}
ALLOWED_HOLIDAY_CALENDAR_SOURCE = {"DEFAULT", "COUNTRY", "CUSTOM"}
ALLOWED_APPROVAL_STEP_TYPES = {"MANAGER", "HR", "ROLE"}
ALLOWED_FALLBACK_APPROVER = {"HR", "NONE"}

# Default policy blocks for new schema (v2)
DEFAULT_ROUNDING = {"unit": "MINUTES", "increment_minutes": 30, "method": "NEAREST"}
DEFAULT_YEAR_END_PROCESSING = {
    "auto_carryover_enabled": False,
    "auto_reset_enabled": False,
    "process_on_month_day": "01-01",
}
DEFAULT_DATA_RETENTION = {"request_history_years": 7, "ledger_history_years": 7}

DEFAULT_REQUEST_POLICY = {
    "allow_half_day": True,
    "allow_hourly": False,
    "minimum_duration": 0.5,
    "maximum_duration": None,
    "consecutive_days_limit": None,
    "allow_prefix_suffix_holidays": True,
    "count_weekends_as_leave": False,
    "count_holidays_as_leave": False,
    "blackout_dates": [],
    "requires_reason": True,
    "requires_document": False,
    "document_mandatory_after_days": None,
}

DEFAULT_APPROVAL_POLICY = {
    "workflow_code": "DEFAULT",
    "auto_approve": False,
    "steps": [{"type": "MANAGER", "required": True}],
    "fallback_approver": "HR",
    "reminders": {"enabled": True, "after_hours": 48},
}

DEFAULT_ACCRUAL_POLICY = {
    "enabled": False,
    "method": "MONTHLY",
    "rate_per_period": 0,
    "start_trigger": "DATE_OF_JOINING",
    "start_offset_days": 0,
    "waiting_period_days": 0,
    "proration": {"on_join": True, "on_termination": True, "method": "DAILY"},
    "cap": {"enabled": False, "max_balance": None},
}

DEFAULT_CARRYOVER_POLICY = {"enabled": False, "max_carryover": None, "expires_after_days": None}

DEFAULT_LEAVE_ENTITLEMENT = {
    "leave_type_id": None,
    "annual_allocation": None,
    "accrual_method": None,
    "effective_from": None,
}


def _deep_merge(base: Any, override: Any) -> Any:
    """
    Merge two mappings with preference to override.
    Lists are replaced (not merged) to keep ordering predictable.
    """
    if isinstance(base, dict) and isinstance(override, dict):
        merged = deepcopy(base)
        for key, value in override.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(override if override is not None else base)


TIME_OFF_DEFAULTS: Dict[str, Any] = {
    "schema_version": 2,
    "global_settings": {
        "module_enabled": True,
        "default_time_unit": "DAYS",
        "working_hours_per_day": 8,
        "minimum_request_unit": 0.5,
        "allow_backdated_requests": True,
        "backdated_limit_days": 30,
        "allow_future_dated_requests": True,
        "future_window_days": 180,
        "allow_negative_balance": False,
        "negative_balance_limit": 0,
        "allow_overlapping_requests": False,
        "time_zone_handling": "EMPLOYER_LOCAL",
        "leave_year_type": "CALENDAR",
        "leave_year_start_month": 1,
        "auto_carry_forward_date": None,
        "auto_reset_date": None,
        "weekend_days": ["SATURDAY", "SUNDAY"],
        "reservation_policy": "RESERVE_ON_SUBMIT",
        "rounding": DEFAULT_ROUNDING,
        "holiday_calendar_source": "DEFAULT",
        "max_request_length_days": None,
        "max_requests_per_month": None,
        "year_end_processing": DEFAULT_YEAR_END_PROCESSING,
        "data_retention": DEFAULT_DATA_RETENTION,
    },
    "policy_defaults": {
        "accrual_and_allocation": {
            "accrual_method": "FIXED_ANNUAL",
            "accrual_frequency": "MONTHLY",
            "accrual_amount_per_period": 1.75,  # ~21 days/year
            "accrual_start_trigger": "DATE_OF_JOINING",
            "proration": True,
            "accrual_during_probation": True,
            "accrual_during_notice": False,
            "accrual_during_unpaid_leave": False,
            "maximum_accrual_cap": None,
            "carry_forward_allowed": True,
            "carry_forward_limit": 10.0,
            "carry_forward_expiry_months": 3,
            "auto_expire_unused_leave": True,
            "accrual_rounding_rule": "NEAREST_HALF",
            "manual_override_allowed": True,
        },
        "carry_forward_and_reset": {
            "year_end_behavior": "CARRY_FORWARD",  # CARRY_FORWARD | RESET | LAPSE
            "carry_forward_enabled": True,
            "carry_forward_method": "LIMITED",  # FULL | LIMITED | NONE
            "max_carry_forward_days": 10.0,
            "carry_forward_expiry_date": None,
            "auto_lapse_remaining_balance": True,
            "reset_on_year_end": False,
            "allow_manual_reset": True,
            "notify_before_expiry": True,
            "grace_period_days": 0,
        },
        "approval_workflow": {
            "approval_required": True,
            "approval_levels": ["REPORTING_MANAGER"],
            "approval_logic": "SEQUENTIAL",
            "auto_approval_conditions": {"max_duration_hours": None},
            "parallel_approvals_allowed": False,
            "approval_sla_hours": 48,
            "auto_escalation_enabled": False,
            "escalation_recipient": None,
            "delegate_approver_allowed": True,
            "bulk_approval_allowed": True,
            "approval_via_email": True,
            "approval_via_mobile": True,
            "allow_approver_override": False,
            "require_rejection_reason": True,
            "approval_comments_mandatory": False,
        },
        "comp_off": {
            "enabled": False,
            "eligibility_rules": {},
            "earn_on": {"weekend_work": False, "holiday_work": False, "overtime": False},
            "minimum_hours_to_earn": 4,
            "conversion_rate": 1.0,
            "approval_required_for_earning": True,
            "expiry_days": 90,
            "allow_cash_payout": False,
            "auto_credit": False,
            "attendance_integration_required": True,
        },
        "holiday_and_weekend": {
            "holiday_calendar": None,
            "location_based_holidays": True,
            "optional_holidays": [],
            "floating_holidays": {"count": 0, "rules": ""},
            "weekend_days": ["SAT", "SUN"],
            "alternate_working_saturdays": [],
            "half_day_holidays": [],
            "holiday_overlap_handling": "EXCLUDE_HOLIDAYS",
            "sandwich_rule": {"enabled": False, "applies_to": []},
            "calendar_visibility": "EMPLOYEE",
        },
        "balance_adjustment": {
            "allow_manual_adjustment": True,
            "adjustment_approval_required": True,
            "adjustment_reason_mandatory": True,
            "adjustment_audit_logging": True,
            "allow_negative_adjustments": True,
            "bulk_adjustments_allowed": True,
            "import_adjustments_allowed": True,
            "lock_after_payroll_run": True,
        },
        "leave_request_rules": {
            "minimum_gap_before_start_days": 0,
            "maximum_continuous_leave_days": None,
            "blocked_dates": [],
            "team_leave_quota_limit": None,
            "minimum_staffing_threshold": None,
            "conflict_warning_rules": {"enabled": True},
            "allow_cancellation_after_approval": True,
            "cancellation_cutoff_hours": 0,
            "partial_cancellation_allowed": True,
            "retroactive_cancellation_allowed": False,
        },
    },
    "leave_types": [
        {
            "code": "ANL",
            "name": "Annual Leave",
            "paid": True,
            "color": "#2E86DE",
            "description": "Default annual leave.",
            "eligibility": {
                "gender": "ALL",
                "employment_types": ["FULL_TIME", "PART_TIME"],
                "locations": [],
                "departments": [],
                "job_levels": [],
                "minimum_tenure_months": 0,
                "allowed_in_probation": True,
            },
            "requires_reason": True,
            "requires_document": False,
            "document_mandatory_after_days": None,
            "allow_half_day": True,
            "allow_hourly": False,
            "consecutive_days_limit": None,
            "minimum_duration": 0.5,
            "maximum_duration": None,
            "sandwich_rule_enabled": False,
            "count_weekends_as_leave": False,
            "count_holidays_as_leave": False,
            "allow_prefix_suffix_holidays": True,
            "auto_approve": False,
            "approval_workflow": "DEFAULT",
            "balance_visible_to_employee": True,
            "allow_encashment": False,
            "encashment_rules": {"max_days": 0, "conversion_rate": 1.0},
            "allow_comp_off_generation": False,
            "comp_off_expiry_days": None,
            "mobile_enabled": True,
            "accrual_and_allocation": {
                "accrual_method": "FIXED_ANNUAL",
                "accrual_frequency": "MONTHLY",
                "accrual_amount_per_period": 1.75,
                "accrual_start_trigger": "DATE_OF_JOINING",
                "proration": True,
                "accrual_during_probation": True,
                "accrual_during_notice": False,
                "accrual_during_unpaid_leave": False,
                "maximum_accrual_cap": None,
                "carry_forward_allowed": True,
                "carry_forward_limit": 10.0,
                "carry_forward_expiry_months": 3,
                "auto_expire_unused_leave": True,
                "accrual_rounding_rule": "NEAREST_HALF",
                "manual_override_allowed": True,
            },
            "carry_forward_and_reset": {
                "year_end_behavior": "CARRY_FORWARD",
                "carry_forward_enabled": True,
                "carry_forward_method": "LIMITED",
                "max_carry_forward_days": 10.0,
                "carry_forward_expiry_date": None,
                "auto_lapse_remaining_balance": True,
                "reset_on_year_end": False,
                "allow_manual_reset": True,
                "notify_before_expiry": True,
                "grace_period_days": 0,
            },
            "leave_request_rules": {
                "minimum_gap_before_start_days": 2,
                "maximum_continuous_leave_days": 20,
                "blocked_dates": [],
                "team_leave_quota_limit": None,
                "minimum_staffing_threshold": None,
                "conflict_warning_rules": {"enabled": True},
                "allow_cancellation_after_approval": True,
                "cancellation_cutoff_hours": 24,
                "partial_cancellation_allowed": True,
                "retroactive_cancellation_allowed": False,
            },
            "request_policy": _deep_merge(DEFAULT_REQUEST_POLICY, {
                "allow_half_day": True,
                "allow_hourly": False,
                "minimum_duration": 0.5,
                "maximum_duration": None,
                "consecutive_days_limit": None,
                "allow_prefix_suffix_holidays": True,
                "count_weekends_as_leave": False,
                "count_holidays_as_leave": False,
                "requires_reason": True,
                "requires_document": False,
                "document_mandatory_after_days": None,
            }),
            "approval_policy": _deep_merge(DEFAULT_APPROVAL_POLICY, {
                "workflow_code": "DEFAULT",
                "auto_approve": False,
            }),
            "accrual_policy": _deep_merge(DEFAULT_ACCRUAL_POLICY, {
                "enabled": True,
                "method": "FIXED_ANNUAL",
                "rate_per_period": 1.75,
                "start_trigger": "DATE_OF_JOINING",
                "proration": {"on_join": True, "on_termination": True, "method": "DAILY"},
            }),
            "carryover_policy": _deep_merge(DEFAULT_CARRYOVER_POLICY, {
                "enabled": True,
                "max_carryover": 10.0,
                "expires_after_days": 90,
            }),
        },
        {
            "code": "SCK",
            "name": "Sick Leave",
            "paid": True,
            "color": "#28A745",
            "description": "Short-term illness leave.",
            "eligibility": {
                "gender": "ALL",
                "employment_types": ["FULL_TIME", "PART_TIME"],
                "locations": [],
                "departments": [],
                "job_levels": [],
                "minimum_tenure_months": 0,
                "allowed_in_probation": True,
            },
            "requires_reason": True,
            "requires_document": True,
            "document_mandatory_after_days": 2,
            "allow_half_day": True,
            "allow_hourly": True,
            "consecutive_days_limit": 10,
            "minimum_duration": 0.5,
            "maximum_duration": 10,
            "sandwich_rule_enabled": False,
            "count_weekends_as_leave": False,
            "count_holidays_as_leave": False,
            "allow_prefix_suffix_holidays": True,
            "auto_approve": False,
            "approval_workflow": "DEFAULT",
            "balance_visible_to_employee": True,
            "allow_encashment": False,
            "encashment_rules": {"max_days": 0, "conversion_rate": 1.0},
            "allow_comp_off_generation": False,
            "comp_off_expiry_days": None,
            "mobile_enabled": True,
            "accrual_and_allocation": {
                "accrual_method": "MONTHLY",
                "accrual_frequency": "MONTHLY",
                "accrual_amount_per_period": 0.84,  # ~10 days/year
                "accrual_start_trigger": "DATE_OF_JOINING",
                "proration": True,
                "accrual_during_probation": True,
                "accrual_during_notice": False,
                "accrual_during_unpaid_leave": False,
                "maximum_accrual_cap": 15,
                "carry_forward_allowed": False,
                "carry_forward_limit": 0,
                "carry_forward_expiry_months": None,
                "auto_expire_unused_leave": True,
                "accrual_rounding_rule": "NEAREST_HALF",
                "manual_override_allowed": True,
            },
            "carry_forward_and_reset": {
                "year_end_behavior": "LAPSE",
                "carry_forward_enabled": False,
                "carry_forward_method": "NONE",
                "max_carry_forward_days": 0,
                "carry_forward_expiry_date": None,
                "auto_lapse_remaining_balance": True,
                "reset_on_year_end": True,
                "allow_manual_reset": True,
                "notify_before_expiry": True,
                "grace_period_days": 0,
            },
            "leave_request_rules": {
                "minimum_gap_before_start_days": 0,
                "maximum_continuous_leave_days": 10,
                "blocked_dates": [],
                "team_leave_quota_limit": None,
                "minimum_staffing_threshold": None,
                "conflict_warning_rules": {"enabled": True},
                "allow_cancellation_after_approval": True,
                "cancellation_cutoff_hours": 0,
                "partial_cancellation_allowed": True,
                "retroactive_cancellation_allowed": True,
            },
            "request_policy": _deep_merge(DEFAULT_REQUEST_POLICY, {
                "allow_half_day": True,
                "allow_hourly": True,
                "minimum_duration": 0.5,
                "maximum_duration": 10,
                "consecutive_days_limit": 10,
                "allow_prefix_suffix_holidays": True,
                "count_weekends_as_leave": False,
                "count_holidays_as_leave": False,
                "requires_reason": True,
                "requires_document": True,
                "document_mandatory_after_days": 2,
            }),
            "approval_policy": _deep_merge(DEFAULT_APPROVAL_POLICY, {
                "workflow_code": "DEFAULT",
                "auto_approve": False,
            }),
            "accrual_policy": _deep_merge(DEFAULT_ACCRUAL_POLICY, {
                "enabled": True,
                "method": "MONTHLY",
                "rate_per_period": 0.84,
                "start_trigger": "DATE_OF_JOINING",
                "proration": {"on_join": True, "on_termination": True, "method": "DAILY"},
                "cap": {"enabled": True, "max_balance": 15},
            }),
            "carryover_policy": _deep_merge(DEFAULT_CARRYOVER_POLICY, {
                "enabled": False,
                "max_carryover": 0,
                "expires_after_days": None,
            }),
        },
    ],
    "leave_policy_id": None,
    "leave_override_enabled": False,
    "leave_entitlements": [],
}


def get_time_off_defaults() -> Dict[str, Any]:
    """Return a deep-copied default configuration so callers can mutate safely."""
    return deepcopy(TIME_OFF_DEFAULTS)


def merge_time_off_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Overlay caller-provided config on top of defaults.
    Useful when only a subset of fields is posted from the UI.
    """
    base = get_time_off_defaults()
    incoming = config or {}
    merged = _deep_merge(base, incoming)

    # Schema versioning: if missing, treat as v1
    incoming_version = incoming.get("schema_version")
    merged["schema_version"] = incoming_version if incoming_version is not None else 1

    return normalize_time_off_config(merged)


def _normalize_leave_entitlement(entitlement: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure each entitlement entry exposes the expected keys."""
    base = DEFAULT_LEAVE_ENTITLEMENT.copy()
    if isinstance(entitlement, dict):
        base.update(entitlement)
    return base


def _normalize_leave_type(leave_type: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure leave type has v2 policy blocks while keeping v1 fields in sync."""
    lt = deepcopy(leave_type or {})

    # Request policy
    request_policy = _deep_merge(DEFAULT_REQUEST_POLICY, lt.get("request_policy", {}))
    if not lt.get("request_policy"):
        # Pull from legacy top-level fields when present
        mapping = {
            "allow_half_day": "allow_half_day",
            "allow_hourly": "allow_hourly",
            "minimum_duration": "minimum_duration",
            "maximum_duration": "maximum_duration",
            "consecutive_days_limit": "consecutive_days_limit",
            "allow_prefix_suffix_holidays": "allow_prefix_suffix_holidays",
            "count_weekends_as_leave": "count_weekends_as_leave",
            "count_holidays_as_leave": "count_holidays_as_leave",
            "requires_reason": "requires_reason",
            "requires_document": "requires_document",
            "document_mandatory_after_days": "document_mandatory_after_days",
        }
        for target, source in mapping.items():
            if source in lt:
                request_policy[target] = lt.get(source, request_policy.get(target))
        if "blackout_dates" in lt:
            request_policy["blackout_dates"] = lt.get("blackout_dates") or []
    lt["request_policy"] = request_policy
    # Sync legacy fields back from request_policy for backward compatibility
    lt["allow_half_day"] = request_policy.get("allow_half_day")
    lt["allow_hourly"] = request_policy.get("allow_hourly")
    lt["minimum_duration"] = request_policy.get("minimum_duration")
    lt["maximum_duration"] = request_policy.get("maximum_duration")
    lt["consecutive_days_limit"] = request_policy.get("consecutive_days_limit")
    lt["allow_prefix_suffix_holidays"] = request_policy.get("allow_prefix_suffix_holidays")
    lt["count_weekends_as_leave"] = request_policy.get("count_weekends_as_leave")
    lt["count_holidays_as_leave"] = request_policy.get("count_holidays_as_leave")
    lt["requires_reason"] = request_policy.get("requires_reason")
    lt["requires_document"] = request_policy.get("requires_document")
    lt["document_mandatory_after_days"] = request_policy.get("document_mandatory_after_days")

    # Approval policy
    approval_policy = _deep_merge(DEFAULT_APPROVAL_POLICY, lt.get("approval_policy", {}))
    if not lt.get("approval_policy"):
        if "auto_approve" in lt:
            approval_policy["auto_approve"] = lt.get("auto_approve")
        if "approval_workflow" in lt:
            approval_policy["workflow_code"] = lt.get("approval_workflow")
    lt["approval_policy"] = approval_policy
    lt["auto_approve"] = approval_policy.get("auto_approve")
    lt["approval_workflow"] = approval_policy.get("workflow_code")

    # Accrual policy
    accrual_policy = _deep_merge(DEFAULT_ACCRUAL_POLICY, lt.get("accrual_policy", {}))
    if not lt.get("accrual_policy"):
        acc = lt.get("accrual_and_allocation", {}) or {}
        if acc:
            accrual_policy["enabled"] = True
        if acc.get("accrual_method") is not None:
            accrual_policy["method"] = acc.get("accrual_method")
        if acc.get("accrual_amount_per_period") is not None:
            accrual_policy["rate_per_period"] = acc.get("accrual_amount_per_period")
        if acc.get("accrual_start_trigger") is not None:
            accrual_policy["start_trigger"] = acc.get("accrual_start_trigger")
    lt["accrual_policy"] = accrual_policy
    # Keep legacy accrual fields roughly aligned
    legacy_acc = lt.get("accrual_and_allocation", {}) or {}
    legacy_acc["accrual_method"] = accrual_policy.get("method")
    legacy_acc["accrual_amount_per_period"] = accrual_policy.get("rate_per_period")
    legacy_acc["accrual_start_trigger"] = accrual_policy.get("start_trigger")
    lt["accrual_and_allocation"] = legacy_acc

    # Carryover policy
    carryover_policy = _deep_merge(DEFAULT_CARRYOVER_POLICY, lt.get("carryover_policy", {}))
    if not lt.get("carryover_policy"):
        cf = lt.get("carry_forward_and_reset", {}) or {}
        if cf.get("carry_forward_enabled") is not None:
            carryover_policy["enabled"] = cf.get("carry_forward_enabled")
        if cf.get("max_carry_forward_days") is not None:
            carryover_policy["max_carryover"] = cf.get("max_carry_forward_days")
        if cf.get("carry_forward_expiry_months") is not None:
            # Rough conversion to days for legacy month-based expiries
            carryover_policy["expires_after_days"] = (
                cf.get("carry_forward_expiry_months") or 0
            ) * 30
    lt["carryover_policy"] = carryover_policy
    legacy_cf = lt.get("carry_forward_and_reset", {}) or {}
    legacy_cf["carry_forward_enabled"] = carryover_policy.get("enabled")
    legacy_cf["max_carry_forward_days"] = carryover_policy.get("max_carryover")
    lt["carry_forward_and_reset"] = legacy_cf

    return lt


def normalize_time_off_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize config to include v2 blocks and synced legacy fields."""
    cfg = deepcopy(config or {})
    cfg["schema_version"] = cfg.get("schema_version", 1)

    # Ensure global settings include new keys
    cfg["global_settings"] = _deep_merge(TIME_OFF_DEFAULTS["global_settings"], cfg.get("global_settings", {}))

    # Normalize leave types
    leave_types = cfg.get("leave_types", []) or []
    normalized_leaves: List[Dict[str, Any]] = []
    for leave_type in leave_types:
        normalized_leaves.append(_normalize_leave_type(leave_type))
    cfg["leave_types"] = normalized_leaves

    raw_entitlements = cfg.get("leave_entitlements", []) or []
    if not isinstance(raw_entitlements, list):
        raw_entitlements = []
    cfg["leave_entitlements"] = [
        _normalize_leave_entitlement(entitlement)
        for entitlement in raw_entitlements
    ]

    cfg["leave_policy_id"] = cfg.get("leave_policy_id")
    cfg["leave_override_enabled"] = cfg.get("leave_override_enabled", False)

    return cfg


def _required(fields: List[str], payload: Dict[str, Any], prefix: str, errors: Dict[str, str]) -> None:
    for field in fields:
        if payload.get(field) in (None, ""):
            errors[f"{prefix}.{field}"] = "This field is required."


def validate_time_off_config(config: Dict[str, Any]) -> Dict[str, str]:
    """
    Lightweight validation to keep JSON predictable.
    Returns a mapping of dotted-path errors (empty dict means valid).
    """
    errors: Dict[str, str] = {}
    cfg = normalize_time_off_config(config or {})
    global_settings = cfg.get("global_settings", {})

    unit = global_settings.get("default_time_unit")
    if unit and unit not in ALLOWED_TIME_UNITS:
        errors["global_settings.default_time_unit"] = f"Invalid unit '{unit}'. Allowed: {sorted(ALLOWED_TIME_UNITS)}"

    leave_year_type = global_settings.get("leave_year_type")
    if leave_year_type and leave_year_type not in ALLOWED_LEAVE_YEAR_TYPES:
        errors["global_settings.leave_year_type"] = f"Invalid leave year type '{leave_year_type}'."

    # New global settings validations
    weekend_days = global_settings.get("weekend_days", [])
    if weekend_days:
        invalid_days = [day for day in weekend_days if day not in ALLOWED_WEEKDAY_NAMES]
        if invalid_days:
            errors["global_settings.weekend_days"] = f"Invalid weekend days: {', '.join(invalid_days)}."

    reservation_policy = global_settings.get("reservation_policy")
    if reservation_policy and reservation_policy not in ALLOWED_RESERVATION_POLICIES:
        errors["global_settings.reservation_policy"] = (
            f"Invalid reservation_policy '{reservation_policy}'. Allowed: {sorted(ALLOWED_RESERVATION_POLICIES)}"
        )

    rounding = global_settings.get("rounding") or {}
    if rounding:
        unit_val = rounding.get("unit")
        method_val = rounding.get("method")
        increment = rounding.get("increment_minutes")
        if unit_val and unit_val not in ALLOWED_ROUNDING_UNITS:
            errors["global_settings.rounding.unit"] = (
                f"Invalid rounding unit '{unit_val}'. Allowed: {sorted(ALLOWED_ROUNDING_UNITS)}"
            )
        if method_val and method_val not in ALLOWED_ROUNDING_METHODS:
            errors["global_settings.rounding.method"] = (
                f"Invalid rounding method '{method_val}'. Allowed: {sorted(ALLOWED_ROUNDING_METHODS)}"
            )
        if increment is not None:
            try:
                inc_val = int(increment)
                if inc_val <= 0 or inc_val % 5 != 0:
                    errors["global_settings.rounding.increment_minutes"] = "Increment must be > 0 and divisible by 5."
            except (TypeError, ValueError):
                errors["global_settings.rounding.increment_minutes"] = "Increment must be an integer."

    holiday_source = global_settings.get("holiday_calendar_source")
    if holiday_source and holiday_source not in ALLOWED_HOLIDAY_CALENDAR_SOURCE:
        errors["global_settings.holiday_calendar_source"] = (
            f"Invalid holiday_calendar_source '{holiday_source}'. Allowed: {sorted(ALLOWED_HOLIDAY_CALENDAR_SOURCE)}"
        )

    if not isinstance(cfg.get("schema_version", 1), int):
        errors["schema_version"] = "schema_version must be an integer."

    leave_policy_id = cfg.get("leave_policy_id")
    if leave_policy_id is not None and not isinstance(leave_policy_id, int):
        errors["leave_policy_id"] = "leave_policy_id must be an integer."

    leave_override_enabled = cfg.get("leave_override_enabled")
    if leave_override_enabled is not None and not isinstance(leave_override_enabled, bool):
        errors["leave_override_enabled"] = "leave_override_enabled must be a boolean."

    leave_entitlements = cfg.get("leave_entitlements", []) or []
    if not isinstance(leave_entitlements, list):
        errors["leave_entitlements"] = "leave_entitlements must be a list."
        leave_entitlements = []
    for ent_idx, entitlement in enumerate(leave_entitlements):
        if not isinstance(entitlement, dict):
            errors[f"leave_entitlements[{ent_idx}]"] = "Each entitlement must be an object."
            continue
        leave_type_id = entitlement.get("leave_type_id")
        if leave_type_id is not None and not isinstance(leave_type_id, int):
            errors[f"leave_entitlements[{ent_idx}].leave_type_id"] = "leave_type_id must be an integer."
        annual_allocation = entitlement.get("annual_allocation")
        if annual_allocation is not None:
            try:
                float(annual_allocation)
            except (TypeError, ValueError):
                errors[f"leave_entitlements[{ent_idx}].annual_allocation"] = "annual_allocation must be numeric."

    policy_defaults = (cfg or {}).get("policy_defaults", {})
    accrual_defaults = policy_defaults.get("accrual_and_allocation", {})
    method = accrual_defaults.get("accrual_method")
    if method and method not in ALLOWED_ACCRUAL_METHODS:
        errors["policy_defaults.accrual_and_allocation.accrual_method"] = (
            f"Invalid accrual method '{method}'."
        )

    start_trigger = accrual_defaults.get("accrual_start_trigger")
    if start_trigger and start_trigger not in ALLOWED_ACCRUAL_START:
        errors["policy_defaults.accrual_and_allocation.accrual_start_trigger"] = (
            f"Invalid accrual start trigger '{start_trigger}'."
        )

    leave_types = cfg.get("leave_types", []) or []
    for idx, leave_type in enumerate(leave_types):
        prefix = f"leave_types[{idx}]"
        _required(["code", "name", "paid"], leave_type, prefix, errors)

        # Request policy validation
        rp = leave_type.get("request_policy", {}) or {}
        allow_hourly = rp.get("allow_hourly")
        if allow_hourly is False and global_settings.get("default_time_unit") == "HOURS":
            errors[f"{prefix}.request_policy.allow_hourly"] = (
                "Hourly requests are disabled for this leave type while default_time_unit is HOURS."
            )

        # Approval policy validation
        ap = leave_type.get("approval_policy", {}) or {}
        steps = ap.get("steps") or []
        for step_idx, step in enumerate(steps):
            step_type = step.get("type")
            if step_type and step_type not in ALLOWED_APPROVAL_STEP_TYPES:
                errors[f"{prefix}.approval_policy.steps[{step_idx}].type"] = (
                    f"Invalid approval step type '{step_type}'."
                )
        fallback = ap.get("fallback_approver")
        if fallback and fallback not in ALLOWED_FALLBACK_APPROVER:
            errors[f"{prefix}.approval_policy.fallback_approver"] = (
                f"Invalid fallback_approver '{fallback}'."
            )

        # Accrual validation
        accrual_policy = leave_type.get("accrual_policy", {}) or {}
        acc_method = accrual_policy.get("method")
        if acc_method and acc_method not in ALLOWED_ACCRUAL_METHODS:
            errors[f"{prefix}.accrual_policy.method"] = f"Invalid accrual method '{acc_method}'."
        start_trig = accrual_policy.get("start_trigger")
        if start_trig and start_trig not in ALLOWED_ACCRUAL_START:
            errors[f"{prefix}.accrual_policy.start_trigger"] = f"Invalid start trigger '{start_trig}'."
        if accrual_policy.get("enabled"):
            rate = accrual_policy.get("rate_per_period")
            try:
                if rate is not None and float(rate) < 0:
                    errors[f"{prefix}.accrual_policy.rate_per_period"] = "rate_per_period must be >= 0."
            except (TypeError, ValueError):
                errors[f"{prefix}.accrual_policy.rate_per_period"] = "rate_per_period must be numeric."
        proration_method = (accrual_policy.get("proration") or {}).get("method")
        if proration_method and proration_method not in ALLOWED_PRORATION_METHODS:
            errors[f"{prefix}.accrual_policy.proration.method"] = (
                f"Invalid proration method '{proration_method}'."
            )

        # Carryover validation
        carry_policy = leave_type.get("carryover_policy", {}) or {}
        max_carry = carry_policy.get("max_carryover")
        if max_carry is not None:
            try:
                if float(max_carry) < 0:
                    errors[f"{prefix}.carryover_policy.max_carryover"] = "max_carryover must be >= 0."
            except (TypeError, ValueError):
                errors[f"{prefix}.carryover_policy.max_carryover"] = "max_carryover must be numeric."
        expires_days = carry_policy.get("expires_after_days")
        if expires_days is not None:
            try:
                if int(expires_days) < 0:
                    errors[f"{prefix}.carryover_policy.expires_after_days"] = "expires_after_days must be >= 0."
            except (TypeError, ValueError):
                errors[f"{prefix}.carryover_policy.expires_after_days"] = "expires_after_days must be an integer."

    return errors
