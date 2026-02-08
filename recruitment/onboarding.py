"""
Bridges the recruitment pipeline into the employees and contracts modules.
Called automatically when an applicant crosses a contract-proposal or hired stage.
"""

import logging
import uuid
from decimal import Decimal

from django.utils import timezone


logger = logging.getLogger(__name__)

# JobPosition.employment_type  →  Contract.contract_type
EMPLOYMENT_TO_CONTRACT_TYPE = {
    "FULL_TIME": "PERMANENT",
    "PART_TIME": "PART_TIME",
    "CONTRACT": "FIXED_TERM",
    "TEMPORARY": "FIXED_TERM",
    "INTERN": "INTERNSHIP",
    "CONSULTANT": "CONSULTANT",
}


def _split_full_name(full_name: str):
    parts = (full_name or "").strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def _generate_contract_id(employer_id: int, tenant_db: str, contract_type: str | None = None) -> str:
    """Generate a contract ID using the employer's ContractConfiguration sequence,
    or fall back to a random ID."""
    from contracts.models import Contract

    try:
        temp_contract = Contract(employer_id=employer_id, contract_type=contract_type or "PERMANENT")
        temp_contract._state.db = tenant_db
        generated = temp_contract.generate_contract_id()
        if generated:
            return generated
    except Exception:
        pass

    return f"CNT-{uuid.uuid4().hex[:8].upper()}"


def create_employee_from_applicant(applicant, tenant_db: str, employer_id: int):
    """Create an Employee from a RecruitmentApplicant.  Returns the instance or None."""
    from employees.models import Employee

    first_name, last_name = _split_full_name(applicant.full_name)
    if not first_name:
        logger.warning("Onboarding: skipped employee creation – applicant %s has no name.", applicant.id)
        return None

    job = applicant.job
    try:
        return Employee.objects.using(tenant_db).create(
            employer_id=employer_id,
            first_name=first_name,
            last_name=last_name,
            email=applicant.email,
            phone_number=applicant.phone,
            job_title=job.title,
            employment_type=job.employment_type or "FULL_TIME",
            hire_date=timezone.now().date(),
            department=job.department,
            branch=job.branch,
            employment_status="PENDING",
        )
    except Exception:
        logger.exception("Onboarding: failed to create employee for applicant %s.", applicant.id)
        return None


def create_draft_contract(applicant, employee, tenant_db: str, employer_id: int, user_id: int):
    """Create a DRAFT contract placeholder linked to the employee.

    Uses bulk_create to bypass Contract.full_clean() because base_salary is 0 in
    the auto-generated draft – the employer will fill in compensation details before
    the contract moves forward.  Returns the Contract instance or None.
    """
    from contracts.models import Contract

    job = applicant.job
    contract_type = EMPLOYMENT_TO_CONTRACT_TYPE.get(job.employment_type or "", "PERMANENT")

    try:
        contract_id = _generate_contract_id(employer_id, tenant_db, contract_type)
        contract = Contract(
            employer_id=employer_id,
            contract_id=contract_id,
            employee=employee,
            department=job.department,
            branch=job.branch,
            contract_type=contract_type,
            start_date=timezone.now().date(),
            base_salary=Decimal("0.00"),
            status="DRAFT",
            created_by=user_id,
        )
        Contract.objects.using(tenant_db).bulk_create([contract])
        return contract
    except Exception:
        logger.exception("Onboarding: failed to create draft contract for applicant %s.", applicant.id)
        return None


def sign_contract_for_employee(employee, tenant_db: str):
    """Move the employee's most-recent DRAFT contract to SIGNED.

    Uses queryset.update() to avoid re-triggering Contract.save()/full_clean().
    Returns the contract or None if no draft was found.
    """
    from contracts.models import Contract

    contract = (
        Contract.objects.using(tenant_db)
        .filter(employee=employee, status="DRAFT")
        .order_by("-created_at")
        .first()
    )
    if not contract:
        return None

    Contract.objects.using(tenant_db).filter(id=contract.id).update(status="SIGNED")
    contract.status = "SIGNED"
    return contract
