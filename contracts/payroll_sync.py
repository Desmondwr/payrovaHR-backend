from decimal import Decimal
from typing import Dict, Iterable, Optional, Tuple

from django.db import transaction

from payroll.models import (
    Advantage,
    CalculationBasis,
    CalculationBasisAdvantage,
    Deduction,
    PayrollElement,
)


CONTRACT_ALLOWANCE_SYS_CODE = "CONTRACT_ALLOWANCE"
CONTRACT_DEDUCTION_FIXED_SYS_CODE = "CONTRACT_DEDUCTION_FIXED"
CONTRACT_DEDUCTION_PERCENT_SYS_CODE = "CONTRACT_DEDUCTION_PERCENT"

ALLOWANCE_CODE_PREFIX = "CONTRACT-ALW-"
DEDUCTION_CODE_PREFIX = "CONTRACT-DED-"


def _to_decimal(value, default=Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _effective_month_year(effective_from) -> Tuple[str, str]:
    if not effective_from:
        return "__", "__"
    return f"{effective_from.month:02d}", str(effective_from.year)


def _load_basis_map(employer_id: int, tenant_db: str) -> Dict[str, CalculationBasis]:
    bases = CalculationBasis.objects.using(tenant_db).filter(employer_id=employer_id, is_active=True)
    return {basis.code: basis for basis in bases}


def _replace_basis_links(
    *,
    employer_id: int,
    tenant_db: str,
    advantage: Advantage,
    basis_codes: Iterable[str],
    basis_map: Dict[str, CalculationBasis],
) -> None:
    CalculationBasisAdvantage.objects.using(tenant_db).filter(
        employer_id=employer_id,
        advantage=advantage,
    ).delete()
    links = []
    for code in basis_codes:
        basis = basis_map.get(code)
        if not basis:
            continue
        links.append(
            CalculationBasisAdvantage(
                employer_id=employer_id,
                basis=basis,
                advantage=advantage,
                is_active=True,
            )
        )
    if links:
        CalculationBasisAdvantage.objects.using(tenant_db).bulk_create(links)


def sync_contract_allowances(contract, *, tenant_db: Optional[str] = None) -> None:
    db_alias = tenant_db or contract._state.db or "default"
    employer_id = contract.employer_id

    allowances = list(contract.allowances.all())
    with transaction.atomic(using=db_alias):
        existing_elements = (
            PayrollElement.objects.using(db_alias)
            .filter(
                employer_id=employer_id,
                contract=contract,
                advantage__sys_code=CONTRACT_ALLOWANCE_SYS_CODE,
            )
            .select_related("advantage")
        )
        old_advantage_ids = [element.advantage_id for element in existing_elements if element.advantage_id]
        existing_elements.delete()
        if old_advantage_ids:
            CalculationBasisAdvantage.objects.using(db_alias).filter(
                employer_id=employer_id, advantage_id__in=old_advantage_ids
            ).delete()
            Advantage.objects.using(db_alias).filter(
                employer_id=employer_id, id__in=old_advantage_ids
            ).delete()

        if not allowances:
            return

        basis_map = _load_basis_map(employer_id, db_alias)
        non_tax_basis = basis_map.get("SAL-NON-TAX") or basis_map.get("NON-TAX")
        elements = []
        for allowance in allowances:
            code = f"{ALLOWANCE_CODE_PREFIX}{allowance.id}"[:50]
            advantage, _created = Advantage.objects.using(db_alias).get_or_create(
                employer_id=employer_id,
                code=code,
                defaults={
                    "name": allowance.name,
                    "sys_code": CONTRACT_ALLOWANCE_SYS_CODE,
                    "is_manual": True,
                    "is_taxable": bool(getattr(allowance, "taxable", True)),
                    "is_contributory": bool(getattr(allowance, "cnps_base", True)),
                    "is_active": True,
                },
            )

            advantage.name = allowance.name
            advantage.sys_code = CONTRACT_ALLOWANCE_SYS_CODE
            advantage.is_manual = True
            advantage.is_taxable = bool(getattr(allowance, "taxable", True))
            advantage.is_contributory = bool(getattr(allowance, "cnps_base", True))
            advantage.is_active = True
            advantage.save(using=db_alias)

            basis_codes = ["SAL-BRUT"]
            if getattr(allowance, "taxable", True):
                basis_codes.extend(["SAL-BRUT-TAX", "SAL-BRUT-TAX-IRPP"])
            elif non_tax_basis:
                basis_codes.append(non_tax_basis.code)
            if getattr(allowance, "cnps_base", True):
                basis_codes.extend(["SAL-BRUT-COT-AF-PV", "SAL-BRUT-COT-AT"])

            _replace_basis_links(
                employer_id=employer_id,
                tenant_db=db_alias,
                advantage=advantage,
                basis_codes=basis_codes,
                basis_map=basis_map,
            )

            amount = _to_decimal(getattr(allowance, "amount", None))
            allowance_type = (getattr(allowance, "type", "") or "").upper()
            if allowance_type == "PERCENTAGE":
                amount = _to_decimal(contract.base_salary) * amount / Decimal("100")

            month, year = _effective_month_year(getattr(allowance, "effective_from", None))
            elements.append(
                PayrollElement(
                    employer_id=employer_id,
                    contract=contract,
                    advantage=advantage,
                    amount=amount,
                    month=month,
                    year=year,
                    is_active=True,
                )
            )

        if elements:
            PayrollElement.objects.using(db_alias).bulk_create(elements)


def sync_contract_deductions(contract, *, tenant_db: Optional[str] = None) -> None:
    db_alias = tenant_db or contract._state.db or "default"
    employer_id = contract.employer_id

    deductions = list(contract.deductions.all())
    with transaction.atomic(using=db_alias):
        existing_elements = (
            PayrollElement.objects.using(db_alias)
            .filter(
                employer_id=employer_id,
                contract=contract,
                deduction__sys_code__in=[
                    CONTRACT_DEDUCTION_FIXED_SYS_CODE,
                    CONTRACT_DEDUCTION_PERCENT_SYS_CODE,
                ],
            )
            .select_related("deduction")
        )
        old_deduction_ids = [element.deduction_id for element in existing_elements if element.deduction_id]
        existing_elements.delete()
        if old_deduction_ids:
            Deduction.objects.using(db_alias).filter(
                employer_id=employer_id, id__in=old_deduction_ids
            ).delete()

        if not deductions:
            return

        elements = []
        for deduction in deductions:
            code = f"{DEDUCTION_CODE_PREFIX}{deduction.id}"[:50]
            deduction_type = (getattr(deduction, "type", "") or "").upper()
            is_percentage = deduction_type == "PERCENTAGE"
            sys_code = (
                CONTRACT_DEDUCTION_PERCENT_SYS_CODE
                if is_percentage
                else CONTRACT_DEDUCTION_FIXED_SYS_CODE
            )

            deduction_obj, _created = Deduction.objects.using(db_alias).get_or_create(
                employer_id=employer_id,
                code=code,
                defaults={
                    "name": deduction.name,
                    "sys_code": sys_code,
                    "is_employee": True,
                    "is_employer": False,
                    "is_count": True,
                    "calculation_basis_code": "SAL-BASE" if is_percentage else None,
                    "employee_rate": _to_decimal(getattr(deduction, "amount", None)) if is_percentage else None,
                    "employer_rate": None,
                    "is_rate": True,
                    "is_scale": False,
                    "is_base_table": False,
                    "is_active": True,
                },
            )

            deduction_obj.name = deduction.name
            deduction_obj.sys_code = sys_code
            deduction_obj.is_employee = True
            deduction_obj.is_employer = False
            deduction_obj.is_count = True
            deduction_obj.is_active = True
            if is_percentage:
                deduction_obj.calculation_basis_code = "SAL-BASE"
                deduction_obj.employee_rate = _to_decimal(getattr(deduction, "amount", None))
                deduction_obj.employer_rate = None
                deduction_obj.is_rate = True
                deduction_obj.is_scale = False
                deduction_obj.is_base_table = False
            else:
                deduction_obj.calculation_basis_code = None
                deduction_obj.employee_rate = None
                deduction_obj.employer_rate = None
                deduction_obj.is_rate = True
                deduction_obj.is_scale = False
                deduction_obj.is_base_table = False
            deduction_obj.save(using=db_alias)

            element_amount = (
                _to_decimal(getattr(deduction, "amount", None)) if not is_percentage else Decimal("0.00")
            )
            month, year = _effective_month_year(getattr(deduction, "effective_from", None))
            elements.append(
                PayrollElement(
                    employer_id=employer_id,
                    contract=contract,
                    deduction=deduction_obj,
                    amount=element_amount,
                    month=month,
                    year=year,
                    is_active=True,
                )
            )

        if elements:
            PayrollElement.objects.using(db_alias).bulk_create(elements)


def sync_contract_payroll_elements(
    contract,
    *,
    tenant_db: Optional[str] = None,
    sync_allowances: bool = True,
    sync_deductions: bool = True,
) -> None:
    if sync_allowances:
        sync_contract_allowances(contract, tenant_db=tenant_db)
    if sync_deductions:
        sync_contract_deductions(contract, tenant_db=tenant_db)
