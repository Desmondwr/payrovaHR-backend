from copy import deepcopy
from typing import Any, Dict, Optional

SIGNATURE_METHOD_CHOICES = [
    ('DOCUSIGN', 'DocuSign'),
    ('INTERNAL', 'Internal'),
]


def _merge_section(default: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Overlay caller data on top of the default configuration section."""
    merged = deepcopy(default)
    if isinstance(override, dict):
        for key, value in override.items():
            merged[key] = value
    return merged


_DEFAULT_RECRUITMENT_CONFIGURATION = {
    "job_position_id": None,
    "recruitment_application_id": None,
    "offer_reference": None,
}

_DEFAULT_ATTENDANCE_CONFIGURATION = {
    "work_schedule_type": None,
    "shift_template_id": None,
    "work_days_per_week": None,
    "hours_per_week": None,
    "daily_start_time": None,
    "daily_end_time": None,
    "timezone": None,
    "attendance_required": True,
    "overtime_eligible": None,
    "overtime_rule_id": None,
    "overtime_weekly_cap": None,
}

_DEFAULT_PAYROLL_CONFIGURATION = {
    "payment_method": None,
    "tax_profile_id": None,
    "cnps_applicable": None,
    "probation_period_days": None,
    "proration_rule_id": None,
}

_DEFAULT_EXPENSE_CONFIGURATION = {
    "expense_policy_id": None,
    "cost_center_id": None,
    "reimbursement_method": None,
}

_DEFAULT_FLEET_CONFIGURATION = {
    "fleet_eligible": False,
    "vehicle_grade_id": None,
    "transport_allowance_eligible": False,
}

_DEFAULT_SIGNATURE_CONFIGURATION = {
    "contract_template_id": None,
    "signed_document_id": None,
    "signature_method": None,
    "signed_at": None,
    "document_hash": None,
    "signature_audit_id": None,
}

_DEFAULT_GOVERNANCE_CONFIGURATION = {
    "approval_status": None,
    "approved_by": None,
    "approved_at": None,
    "activated_by": None,
    "activated_at": None,
    "terminated_by": None,
    "terminated_at": None,
}


def merge_recruitment_configuration(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _merge_section(_DEFAULT_RECRUITMENT_CONFIGURATION, value)


def merge_attendance_configuration(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _merge_section(_DEFAULT_ATTENDANCE_CONFIGURATION, value)


def merge_payroll_configuration(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _merge_section(_DEFAULT_PAYROLL_CONFIGURATION, value)


def merge_expense_configuration(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _merge_section(_DEFAULT_EXPENSE_CONFIGURATION, value)


def merge_fleet_configuration(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _merge_section(_DEFAULT_FLEET_CONFIGURATION, value)


def merge_signature_configuration(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _merge_section(_DEFAULT_SIGNATURE_CONFIGURATION, value)


def merge_governance_configuration(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return _merge_section(_DEFAULT_GOVERNANCE_CONFIGURATION, value)


CONFIGURATION_MERGE_FUNCTIONS = {
    "recruitment_configuration": merge_recruitment_configuration,
    "attendance_configuration": merge_attendance_configuration,
    "payroll_configuration": merge_payroll_configuration,
    "expense_configuration": merge_expense_configuration,
    "fleet_configuration": merge_fleet_configuration,
    "signature_configuration": merge_signature_configuration,
    "governance_configuration": merge_governance_configuration,
}
