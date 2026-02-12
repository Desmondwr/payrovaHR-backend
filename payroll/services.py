import calendar
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP
from typing import Dict, Iterable, List, Optional, Tuple

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import EmployerProfile
from accounts.rbac import get_active_employer
from contracts.models import Contract
from employees.models import Employee
from timeoff.models import TimeOffConfiguration, TimeOffRequest, TimeOffType
from attendance.models import AttendanceRecord
from attendance.services import (
    ensure_attendance_configuration,
    _resolve_payload_timezone,
    is_missing_checkout_after_cutoff,
    resolve_expected_minutes,
)
from treasury.models import BankAccount, CashDesk, PaymentBatch, PaymentLine
from treasury.services import (
    apply_batch_approval_rules,
    apply_line_approval_rules,
    ensure_beneficiary_details,
    ensure_payment_method_allowed,
    ensure_treasury_configuration,
    resolve_default_payment_method,
)

from .models import (
    Advantage,
    CalculationBasis,
    CalculationBasisAdvantage,
    Deduction,
    PayrollConfiguration,
    PayrollElement,
    Salary,
    SalaryAdvantage,
    SalaryDeduction,
    ScaleRange,
)


REQUIRED_BASIS_CODES = [
    "SAL-BRUT",
    "SAL-NON-TAX",
    "SAL-BRUT-TAX",
    "SAL-BRUT-TAX-IRPP",
    "SAL-BRUT-COT-AF-PV",
    "SAL-BRUT-COT-AT",
    "SAL-BASE",
]

NON_TAX_BASIS_ALIASES = {"SAL-NON-TAX", "NON-TAX"}
CONTRACT_ALLOWANCE_SYS_CODE = "CONTRACT_ALLOWANCE"
CONTRACT_DEDUCTION_FIXED_SYS_CODE = "CONTRACT_DEDUCTION_FIXED"
CONTRACT_DEDUCTION_PERCENT_SYS_CODE = "CONTRACT_DEDUCTION_PERCENT"
CONTRACT_DEDUCTION_SYS_CODES = {
    CONTRACT_DEDUCTION_FIXED_SYS_CODE,
    CONTRACT_DEDUCTION_PERCENT_SYS_CODE,
}


def _to_decimal(value, default=Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _month_bounds(year: int, month: int) -> Tuple[date, date, int]:
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)
    return start, end, last_day


def _month_bounds_dt(year: int, month: int) -> Tuple[datetime, datetime]:
    start, end, _ = _month_bounds(year, month)
    start_dt = datetime.combine(start, dtime.min)
    end_dt = datetime.combine(end, dtime.max)
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt)
    if timezone.is_naive(end_dt):
        end_dt = timezone.make_aware(end_dt)
    return start_dt, end_dt


def _days_inclusive(start: date, end: date) -> int:
    if start > end:
        return 0
    return (end - start).days + 1


def _round_money(value: Decimal, scale: int, mode: str) -> Decimal:
    if value is None:
        return Decimal("0.00")
    quant = Decimal("1").scaleb(-scale)
    rounding = {
        PayrollConfiguration.ROUND_HALF_UP: ROUND_HALF_UP,
        PayrollConfiguration.ROUND_DOWN: ROUND_DOWN,
        PayrollConfiguration.ROUND_UP: ROUND_UP,
    }.get(mode, ROUND_HALF_UP)
    return value.quantize(quant, rounding=rounding)


def _normalize_sys_code(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = str(value).strip().upper()
    if normalized.startswith("PVID"):
        return "PVID"
    if normalized.startswith("IRPP"):
        return "IRPP"
    if normalized.startswith("CAC"):
        return "CAC"
    return normalized


@dataclass
class PayrollRunResult:
    salary: Salary
    status: str


class PayrollCalculationService:
    def __init__(self, *, employer_id: int, year: int, month: int, tenant_db: str):
        self.employer_id = employer_id
        self.year = year
        self.month = month
        self.tenant_db = tenant_db or "default"
        self.config = self._ensure_config()

    def _ensure_config(self) -> PayrollConfiguration:
        config = PayrollConfiguration.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id, is_active=True
        ).first()
        if not config:
            config = PayrollConfiguration.objects.using(self.tenant_db).create(employer_id=self.employer_id)
        return config

    def _validate_required_bases(self) -> Dict[str, CalculationBasis]:
        bases = CalculationBasis.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            code__in=set(REQUIRED_BASIS_CODES).union(NON_TAX_BASIS_ALIASES),
            is_active=True,
        )
        basis_map = {b.code: b for b in bases}
        missing = [code for code in REQUIRED_BASIS_CODES if code not in basis_map]
        if "SAL-NON-TAX" in missing and "NON-TAX" in basis_map:
            missing = [code for code in missing if code != "SAL-NON-TAX"]
        if missing:
            raise ValidationError({"bases": f"Missing calculation bases: {', '.join(missing)}"})
        return basis_map

    def _resolve_timeoff(self, employee: Employee, month_start: date, month_end: date) -> Tuple[Decimal, Decimal]:
        config = TimeOffConfiguration.objects.using(self.tenant_db).filter(employer_id=self.employer_id).first()
        if config and not config.module_enabled:
            return Decimal("0.00"), Decimal("0.00")

        working_hours = (config.working_hours_per_day if config else 8) or 8
        minutes_per_day = Decimal(str(working_hours * 60))

        start_dt, end_dt = _month_bounds_dt(self.year, self.month)
        requests = (
            TimeOffRequest.objects.using(self.tenant_db)
            .filter(
                employer_id=self.employer_id,
                employee=employee,
                status="APPROVED",
                start_at__lte=end_dt,
                end_at__gte=start_dt,
            )
            .order_by("start_at")
        )

        paid_minutes = Decimal("0")
        unpaid_minutes = Decimal("0")
        for req in requests:
            leave_type = TimeOffType.objects.using(self.tenant_db).filter(
                employer_id=self.employer_id, code=req.leave_type_code
            ).first()
            if not leave_type:
                continue
            overlap_start = max(req.start_at, start_dt)
            overlap_end = min(req.end_at, end_dt)
            if overlap_end < overlap_start:
                continue
            minutes = Decimal(str((overlap_end - overlap_start).total_seconds() / 60))
            if leave_type.paid:
                paid_minutes += minutes
            else:
                unpaid_minutes += minutes

        paid_days = paid_minutes / minutes_per_day if minutes_per_day else Decimal("0")
        unpaid_days = unpaid_minutes / minutes_per_day if minutes_per_day else Decimal("0")
        return paid_days, unpaid_days

    def _resolve_attendance(self, employee: Employee, month_start: date, month_end: date) -> Tuple[Decimal, Decimal]:
        config = TimeOffConfiguration.objects.using(self.tenant_db).filter(employer_id=self.employer_id).first()
        working_hours = (config.working_hours_per_day if config else 8) or 8
        minutes_per_day = Decimal(str(working_hours * 60))
        attendance_config = ensure_attendance_configuration(self.employer_id, self.tenant_db)
        penalty_mode = getattr(attendance_config, "missing_checkout_penalty_mode", "none")
        penalty_minutes_setting = int(getattr(attendance_config, "missing_checkout_penalty_minutes", 0) or 0)

        records = AttendanceRecord.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            employee=employee,
            check_in_at__date__gte=month_start,
            check_in_at__date__lte=month_end,
            status=AttendanceRecord.STATUS_APPROVED,
        )

        absence_minutes = Decimal("0")
        overtime_minutes = Decimal("0")
        for record in records:
            expected = record.expected_minutes or 0
            worked = record.worked_minutes or 0
            if expected and worked < expected:
                absence_minutes += Decimal(str(expected - worked))
            overtime = record.overtime_approved_minutes or record.overtime_worked_minutes or 0
            overtime_minutes += Decimal(str(overtime))

        if (
            attendance_config
            and attendance_config.auto_flag_anomalies
            and getattr(attendance_config, "flag_missing_checkout", False)
            and penalty_mode
            and penalty_mode != "none"
        ):
            open_records = AttendanceRecord.objects.using(self.tenant_db).filter(
                employer_id=self.employer_id,
                employee=employee,
                check_out_at__isnull=True,
                check_in_at__date__gte=month_start,
                check_in_at__date__lte=month_end,
            )
            for record in open_records:
                tz_override = _resolve_payload_timezone(getattr(record, "check_in_timezone", None))
                if not is_missing_checkout_after_cutoff(
                    record, attendance_config, self.tenant_db, tz_override=tz_override
                ):
                    continue
                expected = record.expected_minutes or resolve_expected_minutes(
                    employee, record.check_in_at, self.tenant_db, tz_override=tz_override
                )
                if not expected:
                    expected = int(minutes_per_day)
                if penalty_mode in ("full_absence", "auto_refuse"):
                    absence_minutes += Decimal(str(expected))
                elif penalty_mode == "fixed_minutes":
                    penalty_minutes = max(penalty_minutes_setting, 0)
                    if expected:
                        penalty_minutes = min(penalty_minutes, int(expected))
                    if penalty_minutes:
                        absence_minutes += Decimal(str(penalty_minutes))

        absence_days = absence_minutes / minutes_per_day if minutes_per_day else Decimal("0")
        overtime_hours = overtime_minutes / Decimal("60")
        return absence_days, overtime_hours

    def _resolve_prorata(self, contract: Contract, month_start: date, month_end: date, unpaid_days: Decimal, absence_days: Decimal) -> Decimal:
        start = max(contract.start_date, month_start)
        end = min(contract.end_date or month_end, month_end)
        total_days = Decimal(str(_days_inclusive(month_start, month_end)))
        active_days = Decimal(str(_days_inclusive(start, end)))
        worked_days = active_days - unpaid_days - absence_days
        if worked_days < 0:
            worked_days = Decimal("0")
        if total_days <= 0:
            return Decimal("0")
        return worked_days / total_days

    def _is_contract_element(self, element: PayrollElement) -> bool:
        advantage = getattr(element, "advantage", None)
        if advantage and _normalize_sys_code(getattr(advantage, "sys_code", None)) == CONTRACT_ALLOWANCE_SYS_CODE:
            return True
        deduction = getattr(element, "deduction", None)
        if deduction and _normalize_sys_code(getattr(deduction, "sys_code", None)) in CONTRACT_DEDUCTION_SYS_CODES:
            return True
        return False

    def _filter_elements(self, elements: Iterable[PayrollElement]) -> List[PayrollElement]:
        month_code = f"{self.month:02d}"
        year_code = str(self.year)
        selected = []
        for element in elements:
            if element.month == "__" and element.year == "__":
                selected.append(element)
                continue

            if self._is_contract_element(element) and element.month != "__" and element.year != "__":
                try:
                    effective_year = int(element.year)
                    effective_month = int(element.month)
                except Exception:
                    effective_year = None
                    effective_month = None

                if effective_year is not None and effective_month is not None:
                    if effective_year < self.year or (
                        effective_year == self.year and effective_month <= self.month
                    ):
                        selected.append(element)
                    continue

            if element.month != "__" and element.month != month_code:
                continue
            if element.year != "__" and element.year != year_code:
                continue
            selected.append(element)
        return selected

    def _calculate_base_map(self, advantage_lines: List[SalaryAdvantage]) -> Dict[str, Decimal]:
        basis_links = CalculationBasisAdvantage.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            is_active=True,
        )
        basis_membership: Dict[str, set] = {}
        for link in basis_links:
            basis_membership.setdefault(link.basis.code, set()).add(link.advantage_id)

        base_values: Dict[str, Decimal] = {code: Decimal("0.00") for code in REQUIRED_BASIS_CODES}
        for line in advantage_lines:
            if not line.advantage_id:
                continue
            for code, ids in basis_membership.items():
                if line.advantage_id in ids:
                    base_values[code] = base_values.get(code, Decimal("0")) + _to_decimal(line.amount)
        return base_values


    def _compute_normal_scale(self, deduction: Deduction, base_amount: Decimal) -> Decimal:
        if not deduction.scale_id:
            return Decimal("0")
        ranges = ScaleRange.objects.using(self.tenant_db).filter(
            scale_id=deduction.scale_id,
            employer_id=self.employer_id,
            is_active=True,
        ).order_by("position")
        for rng in ranges:
            if rng.range_max is None or base_amount <= rng.range_max:
                if rng.coefficient and rng.coefficient != Decimal("0.0000"):
                    return base_amount * rng.coefficient / Decimal("100")
                return rng.indice
        return Decimal("0")

    def _compute_base_table(self, deduction: Deduction, base_amount: Decimal) -> Decimal:
        if not deduction.scale_id:
            return Decimal("0")
        ranges = list(
            ScaleRange.objects.using(self.tenant_db)
            .filter(scale_id=deduction.scale_id, employer_id=self.employer_id, is_active=True)
            .order_by("position")
        )
        if not ranges:
            return Decimal("0")
        for rng in ranges:
            if base_amount <= rng.base_threshold:
                return rng.indice
        return ranges[-1].indice

    def _compute_irpp(self, base_amount: Decimal, pvid_amount: Decimal, deduction: Deduction) -> Decimal:
        config = self.config
        professional_expense = base_amount * _to_decimal(config.professional_expense_rate) / Decimal("100")
        max_prof = _to_decimal(config.max_professional_expense_amount)
        if max_prof and professional_expense > max_prof:
            professional_expense = max_prof
        taxable_monthly = base_amount - professional_expense - pvid_amount
        taxable_annual = (taxable_monthly * Decimal("12")) - _to_decimal(config.tax_exempt_threshold)
        if taxable_annual <= 0:
            return Decimal("0")

        if not deduction.scale_id:
            return Decimal("0")
        ranges = (
            ScaleRange.objects.using(self.tenant_db)
            .filter(scale_id=deduction.scale_id, employer_id=self.employer_id, is_active=True)
            .order_by("position")
        )

        total_irpp = Decimal("0")
        for rng in ranges:
            if rng.range_max is not None and taxable_annual > rng.range_max:
                total_irpp += _to_decimal(rng.indice)
                continue
            remaining = taxable_annual - _to_decimal(rng.range_min)
            if remaining < 0:
                remaining = Decimal("0")
            total_irpp += remaining * _to_decimal(rng.coefficient) / Decimal("100")
            break

        monthly_irpp = total_irpp / Decimal("12")
        return monthly_irpp

    def _add_deduction_line(
        self,
        lines: List[SalaryDeduction],
        deduction: Deduction,
        base_amount: Decimal,
        amount: Decimal,
        rate: Optional[Decimal],
        is_employee: bool,
        is_employer: bool,
        totals: Dict[str, Decimal],
    ):
        amount = _round_money(amount, self.config.rounding_scale, self.config.rounding_mode)
        line = SalaryDeduction(
            employer_id=self.employer_id,
            deduction=deduction,
            code=deduction.code,
            name=deduction.name,
            base_amount=_round_money(base_amount, self.config.rounding_scale, self.config.rounding_mode),
            rate=rate,
            amount=amount,
            is_employee=is_employee,
            is_employer=is_employer,
        )
        lines.append(line)
        if deduction.is_count:
            if is_employee:
                totals["employee"] += amount
            if is_employer:
                totals["employer"] += amount

    def _compute_deductions(
        self,
        elements: List[PayrollElement],
        base_map: Dict[str, Decimal],
        adjusted_basic: Decimal,
    ) -> Tuple[List[SalaryDeduction], Dict[str, Decimal]]:
        lines: List[SalaryDeduction] = []
        totals = {"employee": Decimal("0.00"), "employer": Decimal("0.00")}
        computed_by_sys: Dict[str, Decimal] = {}

        def basis_amount(code: Optional[str]) -> Decimal:
            if not code:
                return Decimal("0")
            if code == "SAL-BASE":
                return adjusted_basic
            return base_map.get(code, Decimal("0"))

        ordered = sorted(
            elements,
            key=lambda el: 0
            if (el.deduction and _normalize_sys_code(el.deduction.sys_code) == "PVID")
            else 2
            if (el.deduction and _normalize_sys_code(el.deduction.sys_code) == "IRPP")
            else 3
            if (el.deduction and _normalize_sys_code(el.deduction.sys_code) == "CAC")
            else 1,
        )

        pending_irpp = None
        pending_cac = None

        for element in ordered:
            deduction = element.deduction
            if not deduction or not deduction.is_active:
                continue
            sys_code = _normalize_sys_code(deduction.sys_code)
            if sys_code == "IRPP":
                pending_irpp = element
                continue
            if sys_code == "CAC":
                pending_cac = element
                continue
            if sys_code == CONTRACT_DEDUCTION_FIXED_SYS_CODE:
                amount = _to_decimal(element.amount)
                if amount > Decimal("0.00"):
                    self._add_deduction_line(
                        lines,
                        deduction,
                        amount,
                        amount,
                        None,
                        deduction.is_employee,
                        deduction.is_employer,
                        totals,
                    )
                continue

            base_amount = basis_amount(deduction.calculation_basis_code)
            if deduction.is_rate:
                if deduction.is_employee:
                    rate = _to_decimal(deduction.employee_rate)
                    amount = base_amount * rate / Decimal("100")
                    self._add_deduction_line(lines, deduction, base_amount, amount, rate, True, False, totals)
                    computed_by_sys[sys_code or deduction.code] = amount
                if deduction.is_employer:
                    rate = _to_decimal(deduction.employer_rate)
                    amount = base_amount * rate / Decimal("100")
                    self._add_deduction_line(lines, deduction, base_amount, amount, rate, False, True, totals)
            elif deduction.is_base_table:
                amount = self._compute_base_table(deduction, base_amount)
                if deduction.is_employee:
                    self._add_deduction_line(lines, deduction, base_amount, amount, None, True, False, totals)
                if deduction.is_employer:
                    self._add_deduction_line(lines, deduction, base_amount, amount, None, False, True, totals)
                computed_by_sys[sys_code or deduction.code] = amount
            elif deduction.is_scale:
                amount = self._compute_normal_scale(deduction, base_amount)
                if deduction.is_employee:
                    self._add_deduction_line(lines, deduction, base_amount, amount, None, True, False, totals)
                if deduction.is_employer:
                    self._add_deduction_line(lines, deduction, base_amount, amount, None, False, True, totals)
                computed_by_sys[sys_code or deduction.code] = amount

        if pending_irpp and pending_irpp.deduction:
            deduction = pending_irpp.deduction
            base_amount = basis_amount(deduction.calculation_basis_code)
            pvid_amount = computed_by_sys.get("PVID", Decimal("0.00"))
            irpp_amount = self._compute_irpp(base_amount, pvid_amount, deduction)
            self._add_deduction_line(lines, deduction, base_amount, irpp_amount, None, True, False, totals)
            computed_by_sys["IRPP"] = irpp_amount

        if pending_cac and pending_cac.deduction:
            deduction = pending_cac.deduction
            irpp_amount = computed_by_sys.get("IRPP", Decimal("0.00"))
            cac_amount = irpp_amount * Decimal("0.10")
            self._add_deduction_line(lines, deduction, irpp_amount, cac_amount, None, True, False, totals)

        return lines, totals

    def run(self, *, mode: str, contract_id=None, branch_id=None, department_id=None) -> List[PayrollRunResult]:
        if not self.config.module_enabled:
            raise ValidationError({"detail": "Payroll module is disabled for this institution."})
        if not self.year or not self.month:
            raise ValidationError({"detail": "Year and month are required."})
        if self.month < 1 or self.month > 12:
            raise ValidationError({"detail": "Month must be between 1 and 12."})

        self._validate_required_bases()
        month_start, month_end, total_days = _month_bounds(self.year, self.month)

        contracts_qs = Contract.objects.using(self.tenant_db).filter(employer_id=self.employer_id, status="ACTIVE")
        if contract_id:
            contracts_qs = contracts_qs.filter(id=contract_id)
        if branch_id:
            contracts_qs = contracts_qs.filter(branch_id=branch_id)
        if department_id:
            contracts_qs = contracts_qs.filter(department_id=department_id)

        results: List[PayrollRunResult] = []
        for contract in contracts_qs.select_related("employee"):
            employee = contract.employee
            if not employee or employee.employment_status != "ACTIVE":
                continue
            if contract.start_date > month_end:
                continue
            if contract.end_date and contract.end_date < month_start:
                continue

            paid_days, unpaid_days = self._resolve_timeoff(employee, month_start, month_end)
            absence_days, overtime_hours = self._resolve_attendance(employee, month_start, month_end)
            prorata = self._resolve_prorata(contract, month_start, month_end, unpaid_days, absence_days)
            adjusted_basic = _to_decimal(contract.base_salary) * prorata

            advantage_elements = PayrollElement.objects.using(self.tenant_db).filter(
                employer_id=self.employer_id,
                contract=contract,
                advantage__isnull=False,
                is_active=True,
            ).select_related("advantage")
            deduction_elements = PayrollElement.objects.using(self.tenant_db).filter(
                employer_id=self.employer_id,
                contract=contract,
                deduction__isnull=False,
                is_active=True,
            ).select_related("deduction")

            advantage_elements = self._filter_elements(advantage_elements)
            deduction_elements = self._filter_elements(deduction_elements)

            advantage_lines: List[SalaryAdvantage] = []
            total_advantages = Decimal("0.00")
            has_basic_element = False
            for element in advantage_elements:
                advantage = element.advantage
                if not advantage or not advantage.is_active:
                    continue
                amount = _to_decimal(element.amount)
                if (advantage.sys_code or "").upper() == "BASIC_SALARY":
                    has_basic_element = True
                    amount = adjusted_basic
                if (advantage.sys_code or "").upper() == "OVERTIME":
                    amount = _to_decimal(element.amount) * _to_decimal(overtime_hours)
                amount = _round_money(amount, self.config.rounding_scale, self.config.rounding_mode)
                line = SalaryAdvantage(
                    employer_id=self.employer_id,
                    advantage=advantage,
                    code=advantage.code,
                    name=advantage.name,
                    base=None,
                    amount=amount,
                )
                advantage_lines.append(line)
                total_advantages += amount

            base_map = self._calculate_base_map(advantage_lines)

            base_adjustments: Dict[str, Decimal] = {code: Decimal("0.00") for code in REQUIRED_BASIS_CODES}

            if not has_basic_element:
                basic_amount = _round_money(adjusted_basic, self.config.rounding_scale, self.config.rounding_mode)
                if basic_amount > Decimal("0.00"):
                    advantage_lines.append(
                        SalaryAdvantage(
                            employer_id=self.employer_id,
                            advantage=None,
                            code="BASIC",
                            name="Base Salary",
                            base=None,
                            amount=basic_amount,
                        )
                    )
                    total_advantages += basic_amount
                    base_adjustments["SAL-BRUT"] += basic_amount
                    base_adjustments["SAL-BRUT-TAX"] += basic_amount
                    base_adjustments["SAL-BRUT-TAX-IRPP"] += basic_amount
                    base_adjustments["SAL-BRUT-COT-AF-PV"] += basic_amount
                    base_adjustments["SAL-BRUT-COT-AT"] += basic_amount
                    base_adjustments["SAL-BASE"] += basic_amount

            for code, amount in base_adjustments.items():
                if amount:
                    base_map[code] = base_map.get(code, Decimal("0.00")) + amount
            gross_salary = base_map.get("SAL-BRUT", Decimal("0"))
            non_taxable = base_map.get("SAL-NON-TAX", base_map.get("NON-TAX", Decimal("0")))
            if self.config.pit_gross_salary_percentage_mode:
                taxable_gross = gross_salary * _to_decimal(self.config.pit_gross_salary_percentage) / Decimal("100")
                irpp_taxable = taxable_gross
            else:
                taxable_gross = gross_salary - non_taxable
                irpp_taxable = base_map.get("SAL-BRUT-TAX-IRPP", Decimal("0"))
            contrib_af_pv = base_map.get("SAL-BRUT-COT-AF-PV", Decimal("0"))
            contrib_at = base_map.get("SAL-BRUT-COT-AT", Decimal("0"))

            deduction_lines, deduction_totals = self._compute_deductions(
                deduction_elements, base_map, adjusted_basic
            )
            total_employee = deduction_totals["employee"]
            total_employer = deduction_totals["employer"]

            net_salary = gross_salary - total_employee

            gross_salary = _round_money(gross_salary, self.config.rounding_scale, self.config.rounding_mode)
            taxable_gross = _round_money(taxable_gross, self.config.rounding_scale, self.config.rounding_mode)
            irpp_taxable = _round_money(irpp_taxable, self.config.rounding_scale, self.config.rounding_mode)
            contrib_af_pv = _round_money(contrib_af_pv, self.config.rounding_scale, self.config.rounding_mode)
            contrib_at = _round_money(contrib_at, self.config.rounding_scale, self.config.rounding_mode)
            net_salary = _round_money(net_salary, self.config.rounding_scale, self.config.rounding_mode)
            total_advantages = _round_money(total_advantages, self.config.rounding_scale, self.config.rounding_mode)
            total_employee = _round_money(total_employee, self.config.rounding_scale, self.config.rounding_mode)
            total_employer = _round_money(total_employer, self.config.rounding_scale, self.config.rounding_mode)

            with transaction.atomic(using=self.tenant_db):
                salary = Salary.objects.using(self.tenant_db).filter(
                    employer_id=self.employer_id,
                    contract=contract,
                    year=self.year,
                    month=self.month,
                ).first()

                if salary:
                    if salary.status in [Salary.STATUS_VALIDATED, Salary.STATUS_ARCHIVED]:
                        if mode == Salary.STATUS_GENERATED:
                            raise ValidationError(
                                {"detail": f"Salary for {contract.contract_id} already validated/archived."}
                            )
                        results.append(PayrollRunResult(salary=salary, status="SKIPPED"))
                        continue
                    if salary.status == Salary.STATUS_GENERATED and mode == Salary.STATUS_GENERATED:
                        results.append(PayrollRunResult(salary=salary, status="SKIPPED"))
                        continue
                else:
                    salary = Salary(
                        employer_id=self.employer_id,
                        contract=contract,
                        employee=employee,
                        year=self.year,
                        month=self.month,
                    )

                salary.status = mode
                salary.base_salary = _round_money(adjusted_basic, self.config.rounding_scale, self.config.rounding_mode)
                salary.gross_salary = gross_salary
                salary.taxable_gross_salary = taxable_gross
                salary.irpp_taxable_gross_salary = irpp_taxable
                salary.contribution_base_af_pv = contrib_af_pv
                salary.contribution_base_at = contrib_at
                salary.total_advantages = total_advantages
                salary.total_employee_deductions = total_employee
                salary.total_employer_deductions = total_employer
                salary.net_salary = net_salary
                salary.leave_days = _round_money(paid_days + unpaid_days, 2, self.config.rounding_mode)
                salary.absence_days = _round_money(absence_days, 2, self.config.rounding_mode)
                salary.overtime_hours = _round_money(overtime_hours, 2, self.config.rounding_mode)
                salary.save(using=self.tenant_db)

                SalaryAdvantage.objects.using(self.tenant_db).filter(salary=salary).delete()
                SalaryDeduction.objects.using(self.tenant_db).filter(salary=salary).delete()

                for line in advantage_lines:
                    line.salary = salary
                    line.employer_id = self.employer_id
                SalaryAdvantage.objects.using(self.tenant_db).bulk_create(advantage_lines)

                for line in deduction_lines:
                    line.salary = salary
                    line.employer_id = self.employer_id
                SalaryDeduction.objects.using(self.tenant_db).bulk_create(deduction_lines)

                results.append(PayrollRunResult(salary=salary, status="OK"))

        return results


def validate_payroll(
    *,
    request,
    tenant_db: str,
    salaries: Iterable[Salary],
):
    if not salaries:
        raise ValidationError({"detail": "No salaries found to validate."})

    employer = get_active_employer(request, require_context=False)
    if not employer:
        # fallback to resolve from employee
        first_salary = next(iter(salaries))
        employer = EmployerProfile.objects.filter(id=first_salary.employer_id).first()
    if not employer:
        raise ValidationError({"detail": "Unable to resolve employer."})

    config = ensure_treasury_configuration(employer, tenant_db=tenant_db)

    grouped: Dict[str, List[Salary]] = {}
    for salary in salaries:
        method = getattr(salary.contract, "payment_method", None)
        if not method:
            method = resolve_default_payment_method(config, PaymentLine.PAYEE_EMPLOYEE)
        grouped.setdefault(method, []).append(salary)

    batches = []
    with transaction.atomic(using=tenant_db):
        for method, batch_salaries in grouped.items():
            method = (method or "").upper()
            ensure_payment_method_allowed(config, method)

            if method == "CASH":
                source = CashDesk.objects.using(tenant_db).filter(employer_id=employer.id, is_active=True).first()
                if not source:
                    raise ValidationError({"detail": "No active cash desk available for payroll payment batch."})
                source_type = "CASHDESK"
            else:
                source = BankAccount.objects.using(tenant_db).filter(employer_id=employer.id, is_active=True).first()
                if not source:
                    raise ValidationError({"detail": "No active bank account available for payroll payment batch."})
                source_type = "BANK"

            planned_date = timezone.now().date()
            year = batch_salaries[0].year
            month = batch_salaries[0].month
            batch = PaymentBatch.objects.using(tenant_db).create(
                employer_id=employer.id,
                branch=None,
                name=f"Payroll {month:02d}/{year} ({method})",
                source_type=source_type,
                source_id=source.id,
                payment_method=method,
                planned_date=planned_date,
                status=PaymentBatch.STATUS_DRAFT,
                total_amount=Decimal("0.00"),
                currency=config.default_currency,
                created_by_id=getattr(request.user, "id", None),
            )

            for salary in batch_salaries:
                if salary.status != Salary.STATUS_GENERATED:
                    raise ValidationError({"detail": "Only GENERATED salaries can be validated."})
                employee = salary.employee
                has_details = bool(employee.bank_account_number) or bool(employee.bank_name)
                ensure_beneficiary_details(config, method, has_details)
                line = PaymentLine.objects.using(tenant_db).create(
                    batch=batch,
                    payee_type=PaymentLine.PAYEE_EMPLOYEE,
                    payee_id=employee.id,
                    payee_name=" ".join(filter(None, [employee.first_name, employee.middle_name, employee.last_name])),
                    amount=salary.net_salary,
                    currency=config.default_currency,
                    status=PaymentLine.STATUS_PENDING,
                    linked_object_type="PAYSLIP",
                    linked_object_id=salary.id,
                )
                apply_line_approval_rules(line, config)
                line.save(using=tenant_db)

            batch.recalculate_total()
            if config.dual_approval_required_for_payroll:
                batch.status = PaymentBatch.STATUS_APPROVAL_PENDING
            else:
                apply_batch_approval_rules(batch, config)
            batch.save(using=tenant_db)

            batches.append(batch)

            for salary in batch_salaries:
                salary.status = Salary.STATUS_VALIDATED
                salary.save(using=tenant_db, update_fields=["status", "updated_at"])

    return batches
