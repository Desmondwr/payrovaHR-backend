import calendar
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import EmployerProfile
from accounts.rbac import get_active_employer
from attendance.models import AttendanceConfiguration, AttendanceRecord, WorkingSchedule, WorkingScheduleDay
from attendance.services import resolve_check_in_timing
from contracts.models import (
    Allowance,
    CalculationScale,
    Contract,
    ContractElement,
    Deduction,
    ScaleRange,
)
from contracts.payroll_defaults import (
    CAMEROON_IRPP_DEFAULT_SCALE_CODE,
    CAMEROON_RAV_DEFAULT_SCALE_CODE,
    CAMEROON_TDL_DEFAULT_SCALE_CODE,
    ensure_cameroon_default_scales,
    ensure_payroll_default_bases,
)
from timeoff.models import TimeOffConfiguration, TimeOffRequest, TimeOffType
from treasury.models import BankAccount, CashDesk, PaymentBatch, PaymentLine, TreasuryTransaction
from treasury.services import (
    apply_batch_approval_rules,
    apply_line_approval_rules,
    ensure_beneficiary_details,
    ensure_payment_method_allowed,
    ensure_treasury_configuration,
    resolve_default_payment_method,
)

from .models import (
    AttendancePayrollImpactConfig,
    CalculationBasis,
    CalculationBasisAdvantage,
    PayrollConfiguration,
    PayrollGeneratedItem,
    Salary,
    SalaryAdvantage,
    SalaryDeduction,
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

BASIS_ALIASES = {
    "NON-TAX": "SAL-NON-TAX",
    "BASE-SALARY": "SAL-BASE",
    "BASIC-SALARY": "SAL-BASE",
    "GROSS-SALARY": "SAL-BRUT",
    "TAXABLE-GROSS-SALARY": "SAL-BRUT-TAX",
    "IRPP-TAXABLE-GROSS-SALARY": "SAL-BRUT-TAX-IRPP",
}

DEFAULT_IRPP_WITHHOLDING_THRESHOLD = Decimal("62000.00")
DEFAULT_CAC_RATE_PERCENTAGE = Decimal("10.00")

SOCIAL_DEDUCTION_SYS_CODES = {
    "AF",
    "AT",
    "CNPS",
    "PENSION",
    "PV",
    "PVID",
}

ATTENDANCE_EVENT_LABELS = {
    AttendancePayrollImpactConfig.EVENT_LATENESS: "Attendance Lateness",
    AttendancePayrollImpactConfig.EVENT_ABSENCE: "Attendance Absence",
    AttendancePayrollImpactConfig.EVENT_OVERTIME: "Attendance Overtime",
    AttendancePayrollImpactConfig.EVENT_EARLY_DEPARTURE: "Attendance Early Departure",
    AttendancePayrollImpactConfig.EVENT_WEEKEND_WORK: "Attendance Weekend Work",
    AttendancePayrollImpactConfig.EVENT_HOLIDAY_WORK: "Attendance Holiday Work",
    AttendancePayrollImpactConfig.EVENT_UNPAID_LEAVE: "Attendance Unpaid Leave",
}


def _to_decimal(value, default=Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _to_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    return default


def _normalize_code(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[\s_]+", "-", str(value).strip().upper())
    normalized = re.sub(r"-+", "-", normalized)
    return normalized.strip("-")


def _canonical_basis_code(value: Optional[str]) -> str:
    normalized = _normalize_code(value)
    if not normalized:
        return ""
    return BASIS_ALIASES.get(normalized, normalized)


def _normalize_sys_code(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]+", "", str(value).strip().upper())


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


def _days_inclusive(start: date, end: date) -> Decimal:
    if start > end:
        return Decimal("0")
    return Decimal(str((end - start).days + 1))


@dataclass
class MonthlyAdjustments:
    paid_days: Decimal = Decimal("0.00")
    unpaid_days: Decimal = Decimal("0.00")
    absence_days: Decimal = Decimal("0.00")
    overtime_hours: Decimal = Decimal("0.00")


@dataclass
class PayrollRunResult:
    salary: Salary
    outcome: str
    reason: str = ""


class AttendancePayrollImpactService:
    def __init__(
        self,
        *,
        employer_id: int,
        year: int,
        month: int,
        tenant_db: str,
        round_money,
    ):
        self.employer_id = employer_id
        self.year = year
        self.month = month
        self.tenant_db = tenant_db
        self.round_money = round_money
        self._month_start, self._month_end, self._month_days = _month_bounds(self.year, self.month)
        self._attendance_config_cache: Dict[int, Optional[AttendanceConfiguration]] = {}
        self._unpaid_leave_codes: Optional[Set[str]] = None

    def has_active_configs(self) -> bool:
        return AttendancePayrollImpactConfig.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            is_active=True,
        ).exists()

    def _event_label(self, event_code: str) -> str:
        return ATTENDANCE_EVENT_LABELS.get(event_code, str(event_code or "Attendance Impact").replace("_", " ").title())

    def _resolve_attendance_config(self, employer_id: int) -> Optional[AttendanceConfiguration]:
        if employer_id not in self._attendance_config_cache:
            self._attendance_config_cache[employer_id] = (
                AttendanceConfiguration.objects.using(self.tenant_db)
                .filter(employer_id=employer_id)
                .first()
            )
        return self._attendance_config_cache[employer_id]

    def _resolve_unpaid_leave_codes(self) -> Set[str]:
        if self._unpaid_leave_codes is None:
            rows = TimeOffType.objects.using(self.tenant_db).filter(
                employer_id=self.employer_id,
                paid=False,
            )
            self._unpaid_leave_codes = {str(row.code) for row in rows if row.code}
        return self._unpaid_leave_codes

    def _resolve_schedule_context(self, contract: Contract, record: AttendanceRecord) -> Tuple[Optional[datetime], Optional[datetime]]:
        employee = contract.employee
        if not employee or not record.check_in_at:
            return None, None

        schedule = None
        employee_schedule_id = getattr(employee, "working_schedule_id", None)
        if employee_schedule_id:
            schedule = (
                WorkingSchedule.objects.using(self.tenant_db)
                .filter(employer_id=self.employer_id, id=employee_schedule_id)
                .first()
            )
        if not schedule:
            schedule = (
                WorkingSchedule.objects.using(self.tenant_db)
                .filter(employer_id=self.employer_id, is_default=True)
                .first()
            )
        if not schedule:
            return None, None

        tz = timezone.get_current_timezone()
        if schedule.timezone:
            try:
                from zoneinfo import ZoneInfo

                tz = ZoneInfo(schedule.timezone)
            except Exception:
                tz = timezone.get_current_timezone()

        check_in_at = record.check_in_at
        if timezone.is_naive(check_in_at):
            local_check_in = timezone.make_aware(check_in_at, tz)
        else:
            local_check_in = timezone.localtime(check_in_at, tz)

        weekday = local_check_in.weekday()
        day_rule = (
            WorkingScheduleDay.objects.using(self.tenant_db)
            .filter(schedule=schedule, weekday=weekday)
            .first()
        )
        if not day_rule or not day_rule.start_time or not day_rule.end_time:
            return None, None

        scheduled_start = datetime.combine(local_check_in.date(), day_rule.start_time)
        scheduled_end = datetime.combine(local_check_in.date(), day_rule.end_time)
        if timezone.is_naive(scheduled_start):
            scheduled_start = timezone.make_aware(scheduled_start, tz)
        if timezone.is_naive(scheduled_end):
            scheduled_end = timezone.make_aware(scheduled_end, tz)
        return scheduled_start, scheduled_end

    def _build_attendance_metrics(
        self,
        *,
        contract: Contract,
        config: AttendancePayrollImpactConfig,
        minutes_per_day: Decimal,
    ) -> List[Dict[str, Any]]:
        employee = contract.employee
        if not employee:
            return []

        records_qs = AttendanceRecord.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            employee=employee,
            check_out_at__isnull=False,
            check_in_at__date__gte=self._month_start,
            check_in_at__date__lte=self._month_end,
        )
        if config.requires_validation:
            records_qs = records_qs.filter(status=AttendanceRecord.STATUS_APPROVED)
        else:
            records_qs = records_qs.filter(status__in=[AttendanceRecord.STATUS_APPROVED, AttendanceRecord.STATUS_TO_APPROVE])
        records = list(records_qs.order_by("check_in_at"))

        grace_minutes = max(int(config.grace_minutes or 0), 0)
        metrics: List[Dict[str, Any]] = []

        for record in records:
            minutes = Decimal("0.0000")
            hours = Decimal("0.0000")
            days = Decimal("0.0000")

            if config.event_code == AttendancePayrollImpactConfig.EVENT_LATENESS:
                attendance_cfg = self._resolve_attendance_config(self.employer_id)
                timing = resolve_check_in_timing(
                    employee=employee,
                    check_in_at=record.check_in_at,
                    config=attendance_cfg,
                    db_alias=self.tenant_db,
                )
                late_minutes = int((timing or {}).get("late_minutes") or 0)
                payable_minutes = max(late_minutes - grace_minutes, 0)
                minutes = Decimal(str(payable_minutes))
                if minutes_per_day > 0:
                    days = minutes / minutes_per_day
                hours = minutes / Decimal("60")
            elif config.event_code == AttendancePayrollImpactConfig.EVENT_ABSENCE:
                expected = Decimal(str(max(int(record.expected_minutes or 0), 0)))
                worked = Decimal(str(max(int(record.worked_minutes or 0), 0)))
                minutes = max(expected - worked, Decimal("0.0000"))
                if minutes_per_day > 0:
                    days = minutes / minutes_per_day
                hours = minutes / Decimal("60")
            elif config.event_code == AttendancePayrollImpactConfig.EVENT_OVERTIME:
                overtime_minutes = int(record.overtime_worked_minutes or 0)
                if config.requires_validation:
                    overtime_minutes = int(record.overtime_approved_minutes or 0)
                minutes = Decimal(str(max(overtime_minutes, 0)))
                hours = minutes / Decimal("60")
                if minutes_per_day > 0:
                    days = minutes / minutes_per_day
            elif config.event_code == AttendancePayrollImpactConfig.EVENT_EARLY_DEPARTURE:
                if not record.check_out_at:
                    continue
                _scheduled_start, scheduled_end = self._resolve_schedule_context(contract, record)
                if not scheduled_end:
                    continue
                check_out = record.check_out_at
                if timezone.is_naive(check_out):
                    check_out = timezone.make_aware(check_out, timezone.get_current_timezone())
                check_out_local = timezone.localtime(check_out, scheduled_end.tzinfo)
                if check_out_local < scheduled_end:
                    delta = scheduled_end - check_out_local
                    raw_minutes = max(int(delta.total_seconds() // 60), 0)
                    payable_minutes = max(raw_minutes - grace_minutes, 0)
                    minutes = Decimal(str(payable_minutes))
                    hours = minutes / Decimal("60")
                    if minutes_per_day > 0:
                        days = minutes / minutes_per_day
            elif config.event_code == AttendancePayrollImpactConfig.EVENT_WEEKEND_WORK:
                check_in = record.check_in_at
                if timezone.is_naive(check_in):
                    check_in = timezone.make_aware(check_in, timezone.get_current_timezone())
                if timezone.localtime(check_in).weekday() in {5, 6}:
                    minutes = Decimal(str(max(int(record.worked_minutes or 0), 0)))
                    hours = minutes / Decimal("60")
                    if minutes_per_day > 0:
                        days = minutes / minutes_per_day
            elif config.event_code == AttendancePayrollImpactConfig.EVENT_HOLIDAY_WORK:
                # No holiday calendar exists in attendance module today.
                minutes = Decimal("0.0000")
            else:
                continue

            if minutes <= 0 and hours <= 0 and days <= 0:
                continue
            metrics.append(
                {
                    "source_record_id": record.id,
                    "minutes": minutes,
                    "hours": hours,
                    "days": days,
                    "event_date_key": record.check_in_at.date().isoformat() if record.check_in_at else None,
                }
            )
        return metrics

    def _build_unpaid_leave_metrics(
        self,
        *,
        contract: Contract,
        config: AttendancePayrollImpactConfig,
        minutes_per_day: Decimal,
    ) -> List[Dict[str, Any]]:
        employee = contract.employee
        if not employee:
            return []

        unpaid_codes = self._resolve_unpaid_leave_codes()
        if not unpaid_codes:
            return []

        start_dt = datetime.combine(self._month_start, dtime.min)
        end_dt = datetime.combine(self._month_end, dtime.max)
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)

        requests_qs = TimeOffRequest.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            employee=employee,
            leave_type_code__in=unpaid_codes,
            start_at__lte=end_dt,
            end_at__gte=start_dt,
            status="APPROVED",
        )
        requests = list(requests_qs.order_by("start_at"))

        metrics: List[Dict[str, Any]] = []
        for request in requests:
            overlap_start = max(request.start_at, start_dt)
            overlap_end = min(request.end_at, end_dt)
            if overlap_end <= overlap_start:
                continue
            minutes = Decimal(str((overlap_end - overlap_start).total_seconds() / 60))
            if minutes <= 0:
                continue
            days = Decimal("0.0000")
            if minutes_per_day > 0:
                days = minutes / minutes_per_day
            metrics.append(
                {
                    "source_record_id": request.id,
                    "minutes": minutes,
                    "hours": minutes / Decimal("60"),
                    "days": days,
                    "event_date_key": overlap_start.date().isoformat(),
                }
            )
        return metrics

    def _compute_amount_and_rate(
        self,
        *,
        config: AttendancePayrollImpactConfig,
        metric: Dict[str, Any],
        basic_salary: Decimal,
        daily_rate: Decimal,
        hourly_rate: Decimal,
    ) -> Tuple[Decimal, Decimal, Decimal]:
        minutes = _to_decimal(metric.get("minutes"), default=Decimal("0.0000"))
        hours = _to_decimal(metric.get("hours"), default=Decimal("0.0000"))
        days = _to_decimal(metric.get("days"), default=Decimal("0.0000"))
        value = _to_decimal(config.value, default=Decimal("0.0000"))

        if config.calc_method == AttendancePayrollImpactConfig.CALC_FIXED_AMOUNT:
            quantity = Decimal("1.0000")
            unit_rate = value
            amount = unit_rate
        elif config.calc_method == AttendancePayrollImpactConfig.CALC_PER_MINUTE:
            quantity = minutes
            unit_rate = value
            amount = quantity * unit_rate
        elif config.calc_method == AttendancePayrollImpactConfig.CALC_PER_HOUR:
            quantity = hours
            unit_rate = value
            amount = quantity * unit_rate
        elif config.calc_method == AttendancePayrollImpactConfig.CALC_PER_DAY:
            quantity = days
            unit_rate = value
            amount = quantity * unit_rate
        elif config.calc_method == AttendancePayrollImpactConfig.CALC_PERCENT_DAILY_RATE:
            quantity = days
            unit_rate = daily_rate * value / Decimal("100")
            amount = quantity * unit_rate
        elif config.calc_method == AttendancePayrollImpactConfig.CALC_PERCENT_BASIC:
            quantity = days if days > 0 else Decimal("1.0000")
            unit_rate = basic_salary * value / Decimal("100")
            amount = quantity * unit_rate
        elif config.calc_method == AttendancePayrollImpactConfig.CALC_MULTIPLIER_HOURLY_RATE:
            quantity = hours
            multiplier = _to_decimal(config.multiplier, default=Decimal("0.0000"))
            if multiplier <= 0:
                multiplier = value if value > 0 else Decimal("1.0000")
            unit_rate = hourly_rate * multiplier
            amount = quantity * unit_rate
        else:
            quantity = Decimal("0.0000")
            unit_rate = Decimal("0.000000")
            amount = Decimal("0.00")

        return quantity, unit_rate, amount

    def _resolve_effective_target(self, contract: Contract, config: AttendancePayrollImpactConfig) -> Tuple[Optional[Deduction], Optional[Allowance]]:
        deduction = None
        allowance = None
        target_code = str(getattr(config, "target_code", "") or "").strip().upper()

        if config.bucket == AttendancePayrollImpactConfig.BUCKET_DEDUCTION:
            selected = config.deduction
            if selected and selected.contract_id == contract.id:
                deduction = selected
            elif target_code:
                deduction = (
                    Deduction.objects.using(self.tenant_db)
                    .filter(contract=contract, code=target_code, is_enable=True)
                    .first()
                )
            elif selected and selected.code:
                deduction = (
                    Deduction.objects.using(self.tenant_db)
                    .filter(contract=contract, code=selected.code, is_enable=True)
                    .first()
                )
        else:
            selected = config.allowance
            if selected and selected.contract_id == contract.id:
                allowance = selected
            elif target_code:
                allowance = (
                    Allowance.objects.using(self.tenant_db)
                    .filter(contract=contract, code=target_code, is_enable=True)
                    .first()
                )
            elif selected and selected.code:
                allowance = (
                    Allowance.objects.using(self.tenant_db)
                    .filter(contract=contract, code=selected.code, is_enable=True)
                    .first()
                )

        return deduction, allowance

    def generate_for_contract(
        self,
        *,
        contract: Contract,
        existing_salary: Optional[Salary],
        minutes_per_day: Decimal,
    ) -> Tuple[List[SalaryAdvantage], List[SalaryDeduction]]:
        employee = contract.employee
        if not employee:
            return [], []

        configs = list(
            AttendancePayrollImpactConfig.objects.using(self.tenant_db)
            .filter(employer_id=self.employer_id, is_active=True)
            .order_by("event_code", "id")
        )
        if not configs:
            return [], []

        basic_salary = _to_decimal(getattr(contract, "base_salary", None), default=Decimal("0.00"))
        month_days = Decimal(str(max(self._month_days, 1)))
        daily_rate = basic_salary / month_days
        minutes_per_day = _to_decimal(minutes_per_day, default=Decimal("480"))
        if minutes_per_day <= 0:
            minutes_per_day = Decimal("480")
        hourly_rate = daily_rate / (minutes_per_day / Decimal("60"))

        active_keys: Set[str] = set()
        created_or_updated_items: List[PayrollGeneratedItem] = []
        impacted_events = {cfg.event_code for cfg in configs}

        for config in configs:
            if config.event_code == AttendancePayrollImpactConfig.EVENT_UNPAID_LEAVE:
                metrics = self._build_unpaid_leave_metrics(
                    contract=contract,
                    config=config,
                    minutes_per_day=minutes_per_day,
                )
            else:
                metrics = self._build_attendance_metrics(
                    contract=contract,
                    config=config,
                    minutes_per_day=minutes_per_day,
                )

            running_total = Decimal("0.00")
            cap_amount = _to_decimal(config.cap_amount, default=None)
            deduction_target, allowance_target = self._resolve_effective_target(contract, config)

            if not config.affects_payroll:
                continue

            for metric in metrics:
                quantity, unit_rate, raw_amount = self._compute_amount_and_rate(
                    config=config,
                    metric=metric,
                    basic_salary=basic_salary,
                    daily_rate=daily_rate,
                    hourly_rate=hourly_rate,
                )
                amount = self.round_money(raw_amount)
                if amount <= Decimal("0.00"):
                    continue

                if cap_amount is not None and cap_amount > Decimal("0.00"):
                    remaining = cap_amount - running_total
                    if remaining <= Decimal("0.00"):
                        continue
                    if amount > remaining:
                        amount = self.round_money(remaining)
                        if unit_rate > 0:
                            quantity = amount / unit_rate
                    running_total += amount
                else:
                    running_total += amount

                source_id = metric.get("source_record_id")
                source_id_text = str(source_id) if source_id else str(metric.get("event_date_key") or "period")
                idempotency_key = (
                    f"ATT:{self.employer_id}:{contract.id}:{employee.id}:{self.year:04d}{self.month:02d}:"
                    f"{config.event_code}:{config.bucket}:{source_id_text}"
                )
                active_keys.add(idempotency_key)

                defaults = {
                    "employer_id": self.employer_id,
                    "salary": existing_salary,
                    "contract": contract,
                    "employee": employee,
                    "year": self.year,
                    "month": self.month,
                    "source_type": PayrollGeneratedItem.SOURCE_ATTENDANCE,
                    "source_event_code": config.event_code,
                    "source_record_id": source_id,
                    "source_date_range_key": metric.get("event_date_key"),
                    "bucket": config.bucket,
                    "deduction": deduction_target,
                    "allowance": allowance_target,
                    "quantity": quantity,
                    "unit_rate": unit_rate,
                    "amount": amount,
                    "status": PayrollGeneratedItem.STATUS_DRAFT,
                    "metadata": {
                        "config_id": str(config.id),
                        "calc_method": config.calc_method,
                        "grace_minutes": int(config.grace_minutes or 0),
                        "requires_validation": bool(config.requires_validation),
                        "target_code": config.target_code,
                        "target_name": config.target_name,
                    },
                    "is_active": True,
                }
                item, _ = PayrollGeneratedItem.objects.using(self.tenant_db).update_or_create(
                    idempotency_key=idempotency_key,
                    defaults=defaults,
                )
                created_or_updated_items.append(item)

        stale_qs = PayrollGeneratedItem.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            contract=contract,
            employee=employee,
            year=self.year,
            month=self.month,
            source_type=PayrollGeneratedItem.SOURCE_ATTENDANCE,
            source_event_code__in=impacted_events,
            status=PayrollGeneratedItem.STATUS_DRAFT,
            is_active=True,
        )
        if active_keys:
            stale_qs = stale_qs.exclude(idempotency_key__in=active_keys)
        stale_qs.update(
            is_active=False,
            salary=existing_salary,
            updated_at=timezone.now(),
        )

        active_items = [
            item
            for item in created_or_updated_items
            if item.is_active and item.amount and _to_decimal(item.amount) > Decimal("0.00")
        ]
        advantage_lines: List[SalaryAdvantage] = []
        deduction_lines: List[SalaryDeduction] = []

        for item in active_items:
            label = self._event_label(item.source_event_code)
            amount = self.round_money(_to_decimal(item.amount))
            if amount <= Decimal("0.00"):
                continue
            metadata = item.metadata or {}
            template_target_code = str(metadata.get("target_code") or "").strip().upper()
            template_target_name = str(metadata.get("target_name") or "").strip()

            if item.bucket == AttendancePayrollImpactConfig.BUCKET_ADVANTAGE:
                allowance = item.allowance
                advantage_lines.append(
                    SalaryAdvantage(
                        employer_id=self.employer_id,
                        allowance=allowance,
                        code=(
                            allowance.code
                            if allowance and allowance.code
                            else (template_target_code or f"ATT_{item.source_event_code}")
                        ),
                        name=(
                            allowance.name
                            if allowance and allowance.name
                            else (template_target_name or label)
                        ),
                        base=self.round_money(_to_decimal(item.quantity, default=Decimal("0.00"))),
                        amount=amount,
                    )
                )
            else:
                deduction = item.deduction
                deduction_lines.append(
                    SalaryDeduction(
                        employer_id=self.employer_id,
                        deduction=deduction,
                        code=(
                            deduction.code
                            if deduction and deduction.code
                            else (template_target_code or f"ATT_{item.source_event_code}")
                        ),
                        name=(
                            deduction.name
                            if deduction and deduction.name
                            else (template_target_name or label)
                        ),
                        base_amount=self.round_money(_to_decimal(item.quantity, default=Decimal("0.00"))),
                        rate=None,
                        amount=amount,
                        is_employee=True,
                        is_employer=False,
                    )
                )

        return advantage_lines, deduction_lines

    def attach_salary_to_generated_items(self, *, contract: Contract, salary: Salary) -> None:
        PayrollGeneratedItem.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            contract=contract,
            employee=contract.employee,
            year=self.year,
            month=self.month,
            source_type=PayrollGeneratedItem.SOURCE_ATTENDANCE,
            status=PayrollGeneratedItem.STATUS_DRAFT,
            is_active=True,
        ).update(salary=salary, updated_at=timezone.now())


class PayrollCalculationService:
    def __init__(self, *, employer_id: int, year: int, month: int, tenant_db: str):
        self.employer_id = employer_id
        self.year = year
        self.month = month
        self.tenant_db = tenant_db or "default"
        self.config = self._ensure_config()
        self._ranges_cache: Dict[str, List[ScaleRange]] = {}
        self.attendance_impact_service = AttendancePayrollImpactService(
            employer_id=self.employer_id,
            year=self.year,
            month=self.month,
            tenant_db=self.tenant_db,
            round_money=self._round_money,
        )
        self._has_attendance_impact_configs = self.attendance_impact_service.has_active_configs()
        self._ensure_cameroon_default_scales()
        self._ensure_payroll_default_bases()

    def _ensure_cameroon_default_scales(self) -> None:
        ensure_cameroon_default_scales(
            employer_id=self.employer_id,
            tenant_db=self.tenant_db,
        )

    def _ensure_payroll_default_bases(self) -> None:
        ensure_payroll_default_bases(
            employer_id=self.employer_id,
            tenant_db=self.tenant_db,
        )

    def _ensure_config(self) -> PayrollConfiguration:
        config = PayrollConfiguration.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            is_active=True,
        ).first()
        if config:
            return config
        return PayrollConfiguration.objects.using(self.tenant_db).create(employer_id=self.employer_id)

    def _round_money(self, amount: Decimal) -> Decimal:
        amount = _to_decimal(amount)
        scale = int(self.config.rounding_scale or 0)
        quant = Decimal("1").scaleb(-scale)
        rounding = {
            PayrollConfiguration.ROUND_HALF_UP: ROUND_HALF_UP,
            PayrollConfiguration.ROUND_DOWN: ROUND_DOWN,
            PayrollConfiguration.ROUND_UP: ROUND_UP,
        }.get(self.config.rounding_mode, ROUND_HALF_UP)
        return amount.quantize(quant, rounding=rounding)

    def _validate_required_bases(self) -> None:
        basis_rows = CalculationBasis.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            is_active=True,
        )
        available = {_canonical_basis_code(row.code) for row in basis_rows}
        missing = [code for code in REQUIRED_BASIS_CODES if code not in available]
        if missing:
            raise ValidationError(
                {"basis_codes": f"Missing required calculation basis codes: {', '.join(missing)}"}
            )

    def _matches_period_value(self, value: Optional[str], selected_numeric: int, selected_text: str) -> bool:
        if value is None:
            return False
        raw = str(value).strip()
        if raw == "__":
            return True
        try:
            return int(raw) == selected_numeric
        except Exception:
            return raw == selected_text

    def _is_element_effective_for_period(self, element: ContractElement) -> bool:
        target = element.advantage or element.deduction
        if not target:
            return True
        effective_from = getattr(target, "effective_from", None)
        if not effective_from:
            return True
        _, month_end, _ = _month_bounds(self.year, self.month)
        return effective_from <= month_end

    def _filter_elements(self, elements: Iterable[ContractElement]) -> List[ContractElement]:
        month_text = f"{self.month:02d}"
        year_text = str(self.year)
        filtered: List[ContractElement] = []
        for element in elements:
            if not self._matches_period_value(element.month, self.month, month_text):
                continue
            if not self._matches_period_value(element.year, self.year, year_text):
                continue
            if not self._is_element_effective_for_period(element):
                continue
            filtered.append(element)
        return filtered

    def _is_basic_salary(self, allowance: Optional[Allowance]) -> bool:
        if not allowance:
            return False
        return _normalize_sys_code(allowance.sys or allowance.code) == "BASICSALARY"

    def _is_overtime_allowance(self, allowance: Optional[Allowance]) -> bool:
        if not allowance:
            return False
        return _normalize_sys_code(allowance.sys or allowance.code) == "OVERTIME"

    def _resolve_contract_month_window(self, contract: Contract) -> Tuple[date, date]:
        month_start, month_end, _ = _month_bounds(self.year, self.month)
        contract_start = max(contract.start_date or month_start, month_start)
        contract_end = min(contract.end_date or month_end, month_end)
        return contract_start, contract_end

    def _resolve_contract_attendance_config(self, contract: Contract) -> Dict[str, object]:
        try:
            config = contract.get_effective_config("attendance_configuration", {}) or {}
        except Exception:
            config = {}
        if isinstance(config, dict):
            return config
        return {}

    def _should_apply_attendance_adjustments(self, contract: Contract) -> bool:
        contract_attendance = self._resolve_contract_attendance_config(contract)
        if not _to_bool(contract_attendance.get("attendance_required"), default=True):
            return False

        attendance_config = AttendanceConfiguration.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id
        ).first()
        if attendance_config and not attendance_config.is_enabled:
            return False
        return True

    def _resolve_attendance_minutes_per_day(self, contract: Contract) -> Decimal:
        # Keep the previous Time Off working-hours fallback for tenants without attendance schedules.
        fallback_minutes = Decimal("480")
        timeoff_config = TimeOffConfiguration.objects.using(self.tenant_db).filter(employer_id=self.employer_id).first()
        if timeoff_config:
            fallback_hours = int(getattr(timeoff_config, "working_hours_per_day", 8) or 8)
            fallback_minutes = Decimal(str(max(fallback_hours, 1) * 60))

        schedule = None
        employee_schedule_id = getattr(contract.employee, "working_schedule_id", None)
        if employee_schedule_id:
            schedule = (
                WorkingSchedule.objects.using(self.tenant_db)
                .filter(employer_id=self.employer_id, id=employee_schedule_id)
                .first()
            )
        if not schedule:
            schedule = (
                WorkingSchedule.objects.using(self.tenant_db)
                .filter(employer_id=self.employer_id, is_default=True)
                .first()
            )
        if schedule:
            schedule_minutes = int(getattr(schedule, "default_daily_minutes", 0) or 0)
            if schedule_minutes > 0:
                return Decimal(str(schedule_minutes))

        contract_attendance = self._resolve_contract_attendance_config(contract)
        hours_per_week = _to_decimal(contract_attendance.get("hours_per_week"), default=Decimal("0"))
        days_per_week = _to_decimal(contract_attendance.get("work_days_per_week"), default=Decimal("0"))
        if hours_per_week > 0 and days_per_week > 0:
            return (hours_per_week * Decimal("60")) / days_per_week

        return fallback_minutes

    def _resolve_timeoff_adjustments(self, contract: Contract) -> Tuple[Decimal, Decimal]:
        config = TimeOffConfiguration.objects.using(self.tenant_db).filter(employer_id=self.employer_id).first()
        if config and not config.module_enabled:
            return Decimal("0.00"), Decimal("0.00")

        working_hours = int(getattr(config, "working_hours_per_day", 8) or 8)
        minutes_per_day = Decimal(str(max(working_hours, 1) * 60))

        contract_start, contract_end = self._resolve_contract_month_window(contract)
        if contract_end < contract_start:
            return Decimal("0.00"), Decimal("0.00")

        start_dt = datetime.combine(contract_start, dtime.min)
        end_dt = datetime.combine(contract_end, dtime.max)
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)
        requests = (
            TimeOffRequest.objects.using(self.tenant_db)
            .filter(
                employer_id=self.employer_id,
                employee=contract.employee,
                status="APPROVED",
                start_at__lte=end_dt,
                end_at__gte=start_dt,
            )
            .order_by("start_at")
        )

        leave_type_cache: Dict[str, Optional[TimeOffType]] = {}
        paid_minutes = Decimal("0.00")
        unpaid_minutes = Decimal("0.00")

        for request in requests:
            leave_code = request.leave_type_code
            if leave_code not in leave_type_cache:
                leave_type_cache[leave_code] = TimeOffType.objects.using(self.tenant_db).filter(
                    employer_id=self.employer_id,
                    code=leave_code,
                ).first()
            leave_type = leave_type_cache[leave_code]
            if not leave_type:
                continue

            overlap_start = max(request.start_at, start_dt)
            overlap_end = min(request.end_at, end_dt)
            if overlap_end <= overlap_start:
                continue

            minutes = Decimal(str((overlap_end - overlap_start).total_seconds() / 60))
            if leave_type.paid:
                paid_minutes += minutes
            else:
                unpaid_minutes += minutes

        paid_days = paid_minutes / minutes_per_day
        unpaid_days = unpaid_minutes / minutes_per_day
        return paid_days, unpaid_days

    def _resolve_attendance_adjustments(self, contract: Contract) -> Tuple[Decimal, Decimal]:
        # Attendance payroll impact is now config-driven. When impact configs exist,
        # legacy prorata/overtime attendance adjustments are disabled to avoid double counting.
        if self._has_attendance_impact_configs:
            return Decimal("0.00"), Decimal("0.00")

        if not self._should_apply_attendance_adjustments(contract):
            return Decimal("0.00"), Decimal("0.00")

        minutes_per_day = self._resolve_attendance_minutes_per_day(contract)
        contract_start, contract_end = self._resolve_contract_month_window(contract)
        if contract_end < contract_start:
            return Decimal("0.00"), Decimal("0.00")

        records = AttendanceRecord.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            employee=contract.employee,
            check_in_at__date__gte=contract_start,
            check_in_at__date__lte=contract_end,
            status=AttendanceRecord.STATUS_APPROVED,
        )

        absence_minutes = Decimal("0.00")
        overtime_minutes = Decimal("0.00")
        for record in records:
            expected = Decimal(str(max(int(record.expected_minutes or 0), 0)))
            worked = Decimal(str(max(int(record.worked_minutes or 0), 0)))
            if expected > worked:
                absence_minutes += expected - worked

            approved_overtime = (
                record.overtime_approved_minutes
                if record.overtime_approved_minutes is not None
                else record.overtime_worked_minutes
            )
            overtime = max(int(approved_overtime or 0), 0)
            overtime_minutes += Decimal(str(overtime))

        absence_days = absence_minutes / minutes_per_day
        overtime_hours = overtime_minutes / Decimal("60")
        return absence_days, overtime_hours

    def build_monthly_adjustments(self, contract: Contract) -> MonthlyAdjustments:
        paid_days, unpaid_days = self._resolve_timeoff_adjustments(contract)
        absence_days, overtime_hours = self._resolve_attendance_adjustments(contract)
        return MonthlyAdjustments(
            paid_days=paid_days,
            unpaid_days=unpaid_days,
            absence_days=absence_days,
            overtime_hours=overtime_hours,
        )

    def _resolve_prorata_factor(self, contract: Contract, adjustments: MonthlyAdjustments) -> Decimal:
        month_start, month_end, _ = _month_bounds(self.year, self.month)
        contract_start, contract_end = self._resolve_contract_month_window(contract)
        if contract_end < contract_start:
            return Decimal("0")
        total_days = _days_inclusive(month_start, month_end)
        active_days = _days_inclusive(contract_start, contract_end)
        worked_days = active_days - adjustments.unpaid_days - adjustments.absence_days
        if worked_days < 0:
            worked_days = Decimal("0")
        if total_days <= 0:
            return Decimal("0")
        return worked_days / total_days

    def _compute_advantage_amount(
        self,
        *,
        contract: Contract,
        element: ContractElement,
        adjusted_basic_salary: Decimal,
        overtime_hours: Decimal,
    ) -> Tuple[Decimal, Optional[Decimal]]:
        allowance = element.advantage
        amount = _to_decimal(element.amount)
        base_value: Optional[Decimal] = None

        if allowance and allowance.type == "PERCENTAGE":
            base_value = _to_decimal(contract.base_salary)
            amount = base_value * amount / Decimal("100")

        if self._is_basic_salary(allowance):
            base_value = _to_decimal(contract.base_salary)
            amount = adjusted_basic_salary
        elif self._is_overtime_allowance(allowance):
            base_value = overtime_hours
            amount = amount * overtime_hours

        return amount, base_value

    def _build_advantage_lines(
        self,
        *,
        contract: Contract,
        advantage_elements: List[ContractElement],
        adjusted_basic_salary: Decimal,
        adjustments: MonthlyAdjustments,
    ) -> List[SalaryAdvantage]:
        lines: List[SalaryAdvantage] = []
        has_basic_line = False

        for element in advantage_elements:
            allowance = element.advantage
            if not allowance or not allowance.is_enable:
                continue

            amount, base_value = self._compute_advantage_amount(
                contract=contract,
                element=element,
                adjusted_basic_salary=adjusted_basic_salary,
                overtime_hours=adjustments.overtime_hours,
            )
            amount = self._round_money(amount)
            if amount == Decimal("0"):
                continue

            code = allowance.code or allowance.name or "ALLOWANCE"
            lines.append(
                SalaryAdvantage(
                    employer_id=self.employer_id,
                    allowance=allowance,
                    code=code,
                    name=allowance.name,
                    base=self._round_money(base_value) if base_value is not None else None,
                    amount=amount,
                )
            )
            if self._is_basic_salary(allowance):
                has_basic_line = True

        if not has_basic_line and adjusted_basic_salary > 0:
            lines.append(
                SalaryAdvantage(
                    employer_id=self.employer_id,
                    allowance=None,
                    code="BASIC_SALARY",
                    name="Basic Salary",
                    base=self._round_money(_to_decimal(contract.base_salary)),
                    amount=self._round_money(adjusted_basic_salary),
                )
            )

        return lines

    def _build_basis_membership(self) -> Dict[str, Dict[str, set]]:
        links = CalculationBasisAdvantage.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            is_active=True,
        ).select_related("basis")

        membership: Dict[str, Dict[str, set]] = {}
        for link in links:
            basis_code = _canonical_basis_code(link.basis.code)
            if basis_code not in membership:
                membership[basis_code] = {"allowance_ids": set(), "codes": set()}
            if link.allowance_id:
                membership[basis_code]["allowance_ids"].add(link.allowance_id)
            if link.allowance_code:
                membership[basis_code]["codes"].add(_normalize_code(link.allowance_code))
        return membership

    def _infer_unmapped_default_bases(self, advantage_lines: List[SalaryAdvantage]) -> Dict[str, Decimal]:
        total_advantages = Decimal("0.00")
        basic_component = Decimal("0.00")

        for line in advantage_lines:
            amount = _to_decimal(line.amount)
            total_advantages += amount

            is_basic = False
            if line.allowance and self._is_basic_salary(line.allowance):
                is_basic = True
            elif _normalize_sys_code(line.code) == "BASICSALARY":
                is_basic = True

            if is_basic:
                basic_component += amount

        contribution_base = basic_component if basic_component > Decimal("0.00") else total_advantages
        return {
            "SAL-BRUT": total_advantages,
            "SAL-BRUT-TAX": total_advantages,
            "SAL-BRUT-TAX-IRPP": total_advantages,
            "SAL-BRUT-COT-AF-PV": contribution_base,
            "SAL-BRUT-COT-AT": contribution_base,
        }

    def _is_basic_advantage_line(self, line: SalaryAdvantage) -> bool:
        if line.allowance and self._is_basic_salary(line.allowance):
            return True
        return _normalize_sys_code(line.code) == "BASICSALARY"

    def _sum_advantage_amounts(self, advantage_lines: List[SalaryAdvantage]) -> Decimal:
        return sum((_to_decimal(line.amount) for line in advantage_lines), Decimal("0.00"))

    def _sum_basic_advantages(self, advantage_lines: List[SalaryAdvantage]) -> Decimal:
        total = Decimal("0.00")
        for line in advantage_lines:
            if self._is_basic_advantage_line(line):
                total += _to_decimal(line.amount)
        return total

    def _line_matches_basis(self, line: SalaryAdvantage, basis_links: Dict[str, set]) -> bool:
        if line.allowance_id and line.allowance_id in basis_links.get("allowance_ids", set()):
            return True
        normalized_code = _normalize_code(line.code)
        if normalized_code and normalized_code in basis_links.get("codes", set()):
            return True
        return False

    def _gross_basis_has_basic_mapping(
        self,
        *,
        advantage_lines: List[SalaryAdvantage],
        membership: Dict[str, Dict[str, set]],
    ) -> bool:
        sal_brut_links = membership.get("SAL-BRUT")
        # If SAL-BRUT has no explicit mapping rows, fallback bases already include the basic component.
        if not sal_brut_links:
            return True

        for line in advantage_lines:
            if not self._is_basic_advantage_line(line):
                continue
            if self._line_matches_basis(line, sal_brut_links):
                return True
        return False

    def _calculate_bases(
        self,
        advantage_lines: List[SalaryAdvantage],
        adjusted_basic_salary: Decimal,
        membership: Optional[Dict[str, Dict[str, set]]] = None,
    ) -> Dict[str, Decimal]:
        membership = membership or self._build_basis_membership()
        bases = {code: Decimal("0.00") for code in REQUIRED_BASIS_CODES}

        for line in advantage_lines:
            normalized_code = _normalize_code(line.code)
            for basis_code, links in membership.items():
                if line.allowance_id and line.allowance_id in links["allowance_ids"]:
                    bases[basis_code] = bases.get(basis_code, Decimal("0.00")) + _to_decimal(line.amount)
                    continue
                if normalized_code and normalized_code in links["codes"]:
                    bases[basis_code] = bases.get(basis_code, Decimal("0.00")) + _to_decimal(line.amount)

        # If a required basis has no mapping rows configured, infer pragmatic defaults from advantage lines.
        linked_basis_codes = set(membership.keys())
        inferred_defaults = self._infer_unmapped_default_bases(advantage_lines)
        for basis_code, inferred_value in inferred_defaults.items():
            if basis_code in linked_basis_codes:
                continue
            if _to_decimal(bases.get(basis_code), default=Decimal("0.00")) != Decimal("0.00"):
                continue
            bases[basis_code] = _to_decimal(inferred_value, default=Decimal("0.00"))

        bases["SAL-BASE"] = _to_decimal(adjusted_basic_salary)
        return bases

    def _resolve_scale_ranges(self, deduction: Deduction) -> List[ScaleRange]:
        sys_code = self._deduction_sys_code(deduction)
        raw_ref = str(getattr(deduction, "calculation_scale", "") or "").strip()
        if not raw_ref and sys_code == "IRPP":
            raw_ref = CAMEROON_IRPP_DEFAULT_SCALE_CODE
        elif not raw_ref and sys_code == "TDL":
            raw_ref = CAMEROON_TDL_DEFAULT_SCALE_CODE
        elif not raw_ref and sys_code in {"RAV", "CRTV"}:
            raw_ref = CAMEROON_RAV_DEFAULT_SCALE_CODE
        if not raw_ref:
            return []

        cache_key = f"{self.employer_id}:{raw_ref}"
        if cache_key in self._ranges_cache:
            return self._ranges_cache[cache_key]

        scale_qs = CalculationScale.objects.using(self.tenant_db).filter(
            employer_id=self.employer_id,
            is_enable=True,
        )

        scale = None
        try:
            scale = scale_qs.filter(id=uuid.UUID(raw_ref)).first()
        except Exception:
            scale = scale_qs.filter(Q(code__iexact=raw_ref) | Q(name__iexact=raw_ref)).first()

        if not scale and sys_code in {"IRPP", "TDL", "RAV", "CRTV"}:
            defaults = ensure_cameroon_default_scales(
                employer_id=self.employer_id,
                tenant_db=self.tenant_db,
            )
            if sys_code == "IRPP":
                scale = defaults.get("irpp")
            elif sys_code == "TDL":
                scale = defaults.get("tdl")
            else:
                scale = defaults.get("rav")

        if not scale:
            self._ranges_cache[cache_key] = []
            return []

        ranges = list(
            ScaleRange.objects.using(self.tenant_db)
            .filter(
                employer_id=self.employer_id,
                calculation_scale=scale,
                is_enable=True,
            )
            .order_by("range1", "range2", "id")
        )
        self._ranges_cache[cache_key] = ranges
        return ranges

    def _deduction_sys_code(self, deduction: Optional[Deduction]) -> str:
        if not deduction:
            return ""
        candidates = [
            getattr(deduction, "sys", None),
            getattr(deduction, "code", None),
            getattr(deduction, "name", None),
        ]
        for value in candidates:
            normalized = _normalize_sys_code(value)
            if normalized:
                return normalized
        return ""

    def _compute_scale_amount(self, deduction: Deduction, base_amount: Decimal) -> Decimal:
        ranges = self._resolve_scale_ranges(deduction)
        if not ranges:
            return Decimal("0.00")

        chosen = None
        for rng in ranges:
            min_value = _to_decimal(rng.range1, default=Decimal("0.00"))
            max_value = _to_decimal(rng.range2, default=None)
            if base_amount < min_value:
                continue
            if max_value is not None and base_amount > max_value:
                continue
            chosen = rng
            break

        if not chosen:
            chosen = ranges[-1]

        coefficient = _to_decimal(chosen.coefficient, default=Decimal("0.00"))
        if coefficient > 0:
            return base_amount * coefficient / Decimal("100")
        return _to_decimal(chosen.indice, default=Decimal("0.00"))

    def _compute_base_table_amount(self, deduction: Deduction, base_amount: Decimal) -> Decimal:
        ranges = self._resolve_scale_ranges(deduction)
        if not ranges:
            return Decimal("0.00")

        ordered = sorted(
            ranges,
            key=lambda row: (_to_decimal(row.base, default=Decimal("999999999999")), row.id),
        )
        for rng in ordered:
            threshold = _to_decimal(rng.base, default=None)
            if threshold is None:
                continue
            if base_amount <= threshold:
                return _to_decimal(rng.indice, default=Decimal("0.00"))
        return _to_decimal(ordered[-1].indice, default=Decimal("0.00"))

    def _compute_irpp_progressive(self, deduction: Deduction, monthly_base: Decimal, pvid_amount: Decimal) -> Decimal:
        monthly_base = _to_decimal(monthly_base, default=Decimal("0.00"))
        irpp_withholding_threshold = _to_decimal(
            getattr(self.config, "irpp_withholding_threshold", None),
            default=DEFAULT_IRPP_WITHHOLDING_THRESHOLD,
        )
        if monthly_base <= irpp_withholding_threshold:
            return Decimal("0.00")

        professional_expense = monthly_base * _to_decimal(self.config.professional_expense_rate) / Decimal("100")
        max_professional = _to_decimal(self.config.max_professional_expense_amount)
        if max_professional > 0 and professional_expense > max_professional:
            professional_expense = max_professional

        rngai = ((monthly_base - professional_expense - pvid_amount) * Decimal("12")) - _to_decimal(
            self.config.tax_exempt_threshold
        )
        if rngai <= 0:
            return Decimal("0.00")

        ranges = self._resolve_scale_ranges(deduction)
        if not ranges:
            return Decimal("0.00")

        ordered = sorted(ranges, key=lambda row: (_to_decimal(row.range1, default=Decimal("0.00")), row.id))
        annual_tax = Decimal("0.00")
        for rng in ordered:
            range_min = _to_decimal(rng.range1, default=Decimal("0.00"))
            range_max = _to_decimal(rng.range2, default=None)
            coefficient = _to_decimal(rng.coefficient, default=Decimal("0.00"))
            fixed_indice = _to_decimal(rng.indice, default=Decimal("0.00"))

            if range_max is not None and rngai > range_max:
                annual_tax += fixed_indice
                continue

            remaining = rngai - range_min
            if remaining < 0:
                remaining = Decimal("0.00")
            annual_tax += remaining * coefficient / Decimal("100")
            break

        return annual_tax / Decimal("12")

    def _resolve_basis_amount(self, basis_code: Optional[str], bases: Dict[str, Decimal], adjusted_basic_salary: Decimal) -> Decimal:
        code = _canonical_basis_code(basis_code)
        if code == "SAL-BASE":
            return _to_decimal(adjusted_basic_salary)
        return _to_decimal(bases.get(code), default=Decimal("0.00"))

    def _append_deduction_line(
        self,
        lines: List[SalaryDeduction],
        totals: Dict[str, Decimal],
        *,
        deduction: Deduction,
        base_amount: Decimal,
        amount: Decimal,
        rate: Optional[Decimal],
        is_employee: bool,
        is_employer: bool,
    ) -> Decimal:
        rounded_amount = self._round_money(amount)
        lines.append(
            SalaryDeduction(
                employer_id=self.employer_id,
                deduction=deduction,
                code=deduction.code or deduction.name or "DEDUCTION",
                name=deduction.name or deduction.code or "Deduction",
                base_amount=self._round_money(base_amount),
                rate=rate,
                amount=rounded_amount,
                is_employee=is_employee,
                is_employer=is_employer,
            )
        )

        if deduction.is_count is False:
            return rounded_amount
        if is_employee:
            totals["employee"] += rounded_amount
        if is_employer:
            totals["employer"] += rounded_amount
        return rounded_amount

    def _deduction_sort_key(self, element: ContractElement):
        deduction = element.deduction
        position = getattr(deduction, "position", None)
        if position is None:
            position = 1_000_000
        sys_code = self._deduction_sys_code(deduction)
        code = _normalize_code(getattr(deduction, "code", None) or getattr(deduction, "name", None))
        deduction_id = str(getattr(deduction, "id", "") or "")
        element_id = str(getattr(element, "id", "") or "")
        return (int(position), sys_code, code, deduction_id, element_id)

    def _is_social_deduction(self, deduction: Deduction, sys_code: str) -> bool:
        if not deduction:
            return False
        if sys_code in SOCIAL_DEDUCTION_SYS_CODES or sys_code.startswith("CNPS"):
            return True

        haystack = " ".join(
            [
                str(getattr(deduction, "deduction_type", "") or "").upper(),
                str(getattr(deduction, "name", "") or "").upper(),
                str(getattr(deduction, "code", "") or "").upper(),
                str(getattr(deduction, "sys", "") or "").upper(),
            ]
        )
        if "IRPP" in haystack or "CAC" in haystack:
            return False
        return any(token in haystack for token in ["SOCIAL", "CNPS", "PENSION", "ACCIDENT", "FAMILY"])

    def _compute_regular_deduction_element(
        self,
        *,
        element: ContractElement,
        lines: List[SalaryDeduction],
        totals: Dict[str, Decimal],
        bases: Dict[str, Decimal],
        adjusted_basic_salary: Decimal,
    ) -> Tuple[str, Decimal]:
        deduction = element.deduction
        if not deduction:
            return "", Decimal("0.00")

        sys_code = self._deduction_sys_code(deduction)
        basis_code = deduction.calculation_basis or deduction.deduction_basis
        if not basis_code and sys_code == "TDL":
            basis_code = "SAL-BASE"
        elif not basis_code and sys_code in {"RAV", "CRTV"}:
            basis_code = "SAL-BRUT"
        base_amount = self._resolve_basis_amount(
            basis_code,
            bases,
            adjusted_basic_salary,
        )

        is_rate = bool(deduction.is_rate)
        is_scale = bool(deduction.is_scale)
        is_base_table = bool(deduction.is_base) and not is_rate and not is_scale
        if not is_rate and not is_scale and not is_base_table:
            if deduction.employee_rate is not None or deduction.employer_rate is not None:
                is_rate = True
            elif sys_code in {"TDL", "RAV", "CRTV"}:
                is_base_table = True

        apply_employee = deduction.is_employee if deduction.is_employee is not None else True
        apply_employer = bool(deduction.is_employer)
        if not apply_employee and not apply_employer:
            apply_employee = True

        total_employee_amount = Decimal("0.00")

        if is_rate:
            employee_rate = _to_decimal(element.employee_rate, default=_to_decimal(deduction.employee_rate))
            employer_rate = _to_decimal(element.employer_rate, default=_to_decimal(deduction.employer_rate))
            if apply_employee:
                employee_amount = base_amount * employee_rate / Decimal("100")
                total_employee_amount += self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=employee_amount,
                    rate=employee_rate,
                    is_employee=True,
                    is_employer=False,
                )
            if apply_employer:
                employer_amount = base_amount * employer_rate / Decimal("100")
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=employer_amount,
                    rate=employer_rate,
                    is_employee=False,
                    is_employer=True,
                )
        elif is_base_table:
            amount = self._compute_base_table_amount(deduction, base_amount)
            if apply_employee:
                total_employee_amount += self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=amount,
                    rate=None,
                    is_employee=True,
                    is_employer=False,
                )
            if apply_employer:
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=amount,
                    rate=None,
                    is_employee=False,
                    is_employer=True,
                )
        elif is_scale:
            amount = self._compute_scale_amount(deduction, base_amount)
            if apply_employee:
                total_employee_amount += self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=amount,
                    rate=None,
                    is_employee=True,
                    is_employer=False,
                )
            if apply_employer:
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=amount,
                    rate=None,
                    is_employee=False,
                    is_employer=True,
                )
        else:
            fixed_amount = _to_decimal(element.amount, default=_to_decimal(deduction.amount))
            if apply_employee:
                total_employee_amount += self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=fixed_amount,
                    rate=None,
                    is_employee=True,
                    is_employer=False,
                )
            if apply_employer:
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=base_amount,
                    amount=fixed_amount,
                    rate=None,
                    is_employee=False,
                    is_employer=True,
                )

        return sys_code, self._round_money(total_employee_amount)

    def _compute_deductions(
        self,
        *,
        deduction_elements: List[ContractElement],
        bases: Dict[str, Decimal],
        adjusted_basic_salary: Decimal,
    ) -> Tuple[List[SalaryDeduction], Dict[str, Decimal]]:
        lines: List[SalaryDeduction] = []
        totals = {"employee": Decimal("0.00"), "employer": Decimal("0.00")}
        computed_sys_amounts: Dict[str, Decimal] = {}

        social_elements: List[ContractElement] = []
        other_elements: List[ContractElement] = []
        irpp_elements: List[ContractElement] = []
        cac_elements: List[ContractElement] = []

        for element in sorted(deduction_elements, key=self._deduction_sort_key):
            deduction = element.deduction
            if not deduction or not deduction.is_enable:
                continue
            sys_code = self._deduction_sys_code(deduction)
            if sys_code == "IRPP":
                irpp_elements.append(element)
            elif sys_code == "CAC":
                cac_elements.append(element)
            elif self._is_social_deduction(deduction, sys_code):
                social_elements.append(element)
            else:
                other_elements.append(element)

        # Pass 1: social contributions (CNPS/PVID/etc.) so IRPP can subtract them.
        for element in social_elements:
            sys_code, employee_amount = self._compute_regular_deduction_element(
                element=element,
                lines=lines,
                totals=totals,
                bases=bases,
                adjusted_basic_salary=adjusted_basic_salary,
            )
            if sys_code:
                computed_sys_amounts[sys_code] = computed_sys_amounts.get(sys_code, Decimal("0.00")) + employee_amount

        for element in irpp_elements:
            deduction = element.deduction
            if not deduction:
                continue

            irpp_base = self._resolve_basis_amount(
                deduction.calculation_basis or deduction.deduction_basis,
                bases,
                adjusted_basic_salary,
            )
            pvid_amount = computed_sys_amounts.get("PVID", Decimal("0.00"))
            irpp_amount = self._compute_irpp_progressive(deduction, irpp_base, pvid_amount)

            apply_employee = deduction.is_employee is not False
            apply_employer = bool(deduction.is_employer)
            if apply_employee:
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=irpp_base,
                    amount=irpp_amount,
                    rate=None,
                    is_employee=True,
                    is_employer=False,
                )
                computed_sys_amounts["IRPP"] = self._round_money(irpp_amount)
            if apply_employer:
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=irpp_base,
                    amount=irpp_amount,
                    rate=None,
                    is_employee=False,
                    is_employer=True,
                )

        for element in cac_elements:
            deduction = element.deduction
            if not deduction:
                continue

            irpp_amount = _to_decimal(computed_sys_amounts.get("IRPP"), default=Decimal("0.00"))

            apply_employee = deduction.is_employee is not False
            apply_employer = bool(deduction.is_employer)
            default_rate = _to_decimal(
                getattr(self.config, "cac_rate_percentage", None),
                default=DEFAULT_CAC_RATE_PERCENTAGE,
            )
            employee_rate = _to_decimal(
                element.employee_rate,
                default=_to_decimal(deduction.employee_rate, default=default_rate),
            )
            employer_rate = _to_decimal(
                element.employer_rate,
                default=_to_decimal(deduction.employer_rate, default=employee_rate),
            )
            if apply_employee:
                cac_amount = irpp_amount * employee_rate / Decimal("100")
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=irpp_amount,
                    amount=cac_amount,
                    rate=employee_rate,
                    is_employee=True,
                    is_employer=False,
                )
            if apply_employer:
                cac_amount = irpp_amount * employer_rate / Decimal("100")
                self._append_deduction_line(
                    lines,
                    totals,
                    deduction=deduction,
                    base_amount=irpp_amount,
                    amount=cac_amount,
                    rate=employer_rate,
                    is_employee=False,
                    is_employer=True,
                )

        # Pass 3: remaining non-social deductions.
        for element in other_elements:
            sys_code, employee_amount = self._compute_regular_deduction_element(
                element=element,
                lines=lines,
                totals=totals,
                bases=bases,
                adjusted_basic_salary=adjusted_basic_salary,
            )
            if sys_code:
                computed_sys_amounts[sys_code] = computed_sys_amounts.get(sys_code, Decimal("0.00")) + employee_amount

        return lines, totals

    def _apply_status_rules(self, *, mode: str, existing_salary: Optional[Salary], contract: Contract) -> Optional[str]:
        if not existing_salary:
            return None

        if mode == Salary.STATUS_GENERATED:
            if existing_salary.status in {Salary.STATUS_VALIDATED, Salary.STATUS_ARCHIVED}:
                raise ValidationError(
                    {
                        "detail": (
                            f"Cannot regenerate payroll for contract {contract.contract_id} "
                            f"({self.month:02d}/{self.year}): already {existing_salary.status}."
                        )
                    }
                )
            if existing_salary.status == Salary.STATUS_GENERATED:
                return "SKIPPED_GENERATED"

        if mode == Salary.STATUS_SIMULATED:
            if existing_salary.status in {Salary.STATUS_VALIDATED, Salary.STATUS_ARCHIVED}:
                return "SKIPPED_LOCKED"

        return None

    def run(self, *, mode: str, contract_id=None, branch_id=None, department_id=None) -> List[PayrollRunResult]:
        if mode not in {Salary.STATUS_SIMULATED, Salary.STATUS_GENERATED}:
            raise ValidationError({"mode": "Mode must be SIMULATED or GENERATED."})
        if not (1 <= int(self.month) <= 12):
            raise ValidationError({"month": "Month must be between 1 and 12."})
        if not int(self.year):
            raise ValidationError({"year": "Year is required."})
        if not self.config.module_enabled:
            raise ValidationError({"detail": "Payroll module is disabled for this institution."})

        self._validate_required_bases()
        month_start, month_end, _ = _month_bounds(self.year, self.month)

        contracts_qs = (
            Contract.objects.using(self.tenant_db)
            .filter(employer_id=self.employer_id, status="ACTIVE")
            .select_related("employee")
        )
        if contract_id:
            contracts_qs = contracts_qs.filter(id=contract_id)
        if branch_id:
            contracts_qs = contracts_qs.filter(
                Q(branch_id=branch_id) | Q(employee__secondary_branches__id=branch_id)
            ).distinct()
        if department_id:
            contracts_qs = contracts_qs.filter(department_id=department_id)

        results: List[PayrollRunResult] = []
        for contract in contracts_qs:
            if not contract.employee or contract.employee.employment_status not in {"ACTIVE", "PROBATION"}:
                continue
            if contract.start_date and contract.start_date > month_end:
                continue
            if contract.end_date and contract.end_date < month_start:
                continue

            existing_salary = Salary.objects.using(self.tenant_db).filter(
                employer_id=self.employer_id,
                contract=contract,
                year=self.year,
                month=self.month,
            ).first()
            rule = self._apply_status_rules(mode=mode, existing_salary=existing_salary, contract=contract)
            if rule == "SKIPPED_GENERATED":
                results.append(
                    PayrollRunResult(
                        salary=existing_salary,
                        outcome="SKIPPED",
                        reason="Salary already generated for this period.",
                    )
                )
                continue
            if rule == "SKIPPED_LOCKED":
                results.append(
                    PayrollRunResult(
                        salary=existing_salary,
                        outcome="SKIPPED",
                        reason="Salary already validated/archived.",
                    )
                )
                continue

            adjustments = self.build_monthly_adjustments(contract)
            prorata = self._resolve_prorata_factor(contract, adjustments)
            adjusted_basic_salary = _to_decimal(contract.base_salary) * prorata

            advantage_elements_qs = ContractElement.objects.using(self.tenant_db).filter(
                institution_id=self.employer_id,
                contract=contract,
                is_enable=True,
                advantage__isnull=False,
            ).select_related("advantage")
            deduction_elements_qs = ContractElement.objects.using(self.tenant_db).filter(
                institution_id=self.employer_id,
                contract=contract,
                is_enable=True,
                deduction__isnull=False,
            ).select_related("deduction")

            advantage_elements = self._filter_elements(advantage_elements_qs)
            deduction_elements = self._filter_elements(deduction_elements_qs)

            advantage_lines = self._build_advantage_lines(
                contract=contract,
                advantage_elements=advantage_elements,
                adjusted_basic_salary=adjusted_basic_salary,
                adjustments=adjustments,
            )
            attendance_advantage_lines: List[SalaryAdvantage] = []
            attendance_deduction_lines: List[SalaryDeduction] = []
            if self._has_attendance_impact_configs:
                attendance_advantage_lines, attendance_deduction_lines = self.attendance_impact_service.generate_for_contract(
                    contract=contract,
                    existing_salary=existing_salary,
                    minutes_per_day=self._resolve_attendance_minutes_per_day(contract),
                )
                if attendance_advantage_lines:
                    advantage_lines.extend(attendance_advantage_lines)

            membership = self._build_basis_membership()
            bases = self._calculate_bases(
                advantage_lines,
                adjusted_basic_salary,
                membership=membership,
            )
            gross_salary = _to_decimal(bases.get("SAL-BRUT"), default=Decimal("0.00"))
            basic_component = self._sum_basic_advantages(advantage_lines)
            if basic_component > Decimal("0.00") and not self._gross_basis_has_basic_mapping(
                advantage_lines=advantage_lines,
                membership=membership,
            ):
                gross_salary += basic_component
                bases["SAL-BRUT"] = gross_salary

            non_taxable_amount = _to_decimal(bases.get("SAL-NON-TAX"), default=Decimal("0.00"))

            if self.config.pit_gross_salary_percentage_mode:
                percentage = _to_decimal(self.config.pit_gross_salary_percentage)
                taxable_gross_salary = gross_salary * percentage / Decimal("100")
                irpp_taxable_gross_salary = gross_salary * percentage / Decimal("100")
            else:
                taxable_gross_salary = gross_salary - non_taxable_amount
                irpp_taxable_gross_salary = _to_decimal(bases.get("SAL-BRUT-TAX-IRPP"), default=Decimal("0.00"))

            taxable_gross_salary = max(taxable_gross_salary, Decimal("0.00"))
            irpp_taxable_gross_salary = max(irpp_taxable_gross_salary, Decimal("0.00"))
            bases["SAL-BRUT-TAX"] = taxable_gross_salary

            deduction_lines, deduction_totals = self._compute_deductions(
                deduction_elements=deduction_elements,
                bases=bases,
                adjusted_basic_salary=adjusted_basic_salary,
            )
            for line in attendance_deduction_lines:
                amount = self._round_money(_to_decimal(line.amount))
                if amount <= Decimal("0.00"):
                    continue
                line.amount = amount
                line.base_amount = self._round_money(_to_decimal(line.base_amount))
                deduction_lines.append(line)
                should_count = True
                if line.deduction and line.deduction.is_count is False:
                    should_count = False
                if should_count and line.is_employee:
                    deduction_totals["employee"] += amount
                if should_count and line.is_employer:
                    deduction_totals["employer"] += amount

            total_advantages = self._sum_advantage_amounts(advantage_lines)
            total_employee_deductions = deduction_totals["employee"]
            total_employer_deductions = deduction_totals["employer"]
            net_salary = gross_salary - total_employee_deductions

            gross_salary = self._round_money(gross_salary)
            taxable_gross_salary = self._round_money(taxable_gross_salary)
            irpp_taxable_gross_salary = self._round_money(irpp_taxable_gross_salary)
            contribution_base_af_pv = self._round_money(_to_decimal(bases.get("SAL-BRUT-COT-AF-PV")))
            contribution_base_at = self._round_money(_to_decimal(bases.get("SAL-BRUT-COT-AT")))
            total_advantages = self._round_money(total_advantages)
            total_employee_deductions = self._round_money(total_employee_deductions)
            total_employer_deductions = self._round_money(total_employer_deductions)
            net_salary = self._round_money(net_salary)

            with transaction.atomic(using=self.tenant_db):
                salary = existing_salary or Salary(
                    employer_id=self.employer_id,
                    contract=contract,
                    employee=contract.employee,
                    year=self.year,
                    month=self.month,
                )

                salary.status = mode
                salary.base_salary = self._round_money(adjusted_basic_salary)
                salary.gross_salary = gross_salary
                salary.taxable_gross_salary = taxable_gross_salary
                salary.irpp_taxable_gross_salary = irpp_taxable_gross_salary
                salary.contribution_base_af_pv = contribution_base_af_pv
                salary.contribution_base_at = contribution_base_at
                salary.total_advantages = total_advantages
                salary.total_employee_deductions = total_employee_deductions
                salary.total_employer_deductions = total_employer_deductions
                salary.net_salary = net_salary
                salary.leave_days = self._round_money(adjustments.paid_days + adjustments.unpaid_days)
                salary.absence_days = self._round_money(adjustments.absence_days)
                salary.overtime_hours = self._round_money(adjustments.overtime_hours)
                salary.save(using=self.tenant_db)
                if self._has_attendance_impact_configs:
                    self.attendance_impact_service.attach_salary_to_generated_items(contract=contract, salary=salary)

                SalaryAdvantage.objects.using(self.tenant_db).filter(salary=salary).delete()
                SalaryDeduction.objects.using(self.tenant_db).filter(salary=salary).delete()

                for line in advantage_lines:
                    line.salary = salary
                    line.employer_id = self.employer_id
                if advantage_lines:
                    SalaryAdvantage.objects.using(self.tenant_db).bulk_create(advantage_lines)

                for line in deduction_lines:
                    line.salary = salary
                    line.employer_id = self.employer_id
                if deduction_lines:
                    SalaryDeduction.objects.using(self.tenant_db).bulk_create(deduction_lines)

            results.append(PayrollRunResult(salary=salary, outcome="OK"))

        return results


def _get_contract_payment_method(contract: Contract) -> Optional[str]:
    direct_value = getattr(contract, "payment_method", None)
    if direct_value:
        return str(direct_value).upper()

    try:
        payroll_cfg = contract.get_effective_config("payroll_configuration", {}) or {}
    except Exception:
        payroll_cfg = {}
    value = payroll_cfg.get("payment_method")
    if value:
        return str(value).upper()
    return None


def _resolve_or_create_payroll_bank_source(
    *,
    employer: EmployerProfile,
    tenant_db: str,
    currency: str,
) -> Tuple[Optional[BankAccount], str]:
    """
    Resolve an active employer treasury bank account for payroll source.
    Returns (account, status) where status is one of:
    - "active": an active treasury bank account exists
    - "created": auto-created from employer profile bank fields
    - "inactive_only": treasury bank accounts exist but none is active
    - "missing": no treasury bank account and insufficient employer profile bank fields
    """
    qs = BankAccount.objects.using(tenant_db).filter(employer_id=employer.id)
    active = qs.filter(is_active=True).first()
    if active:
        return active, "active"

    if qs.exists():
        return None, "inactive_only"

    bank_name = str(getattr(employer, "bank_name", "") or "").strip()
    account_number = str(getattr(employer, "bank_account_number", "") or "").strip()
    if not bank_name or not account_number:
        return None, "missing"

    account_holder_name = (
        str(getattr(employer, "company_name", "") or "").strip()
        or str(getattr(employer, "employer_name_or_group", "") or "").strip()
        or "Employer"
    )
    account = BankAccount.objects.using(tenant_db).create(
        employer_id=employer.id,
        name="Default Payroll Bank Account",
        currency=(currency or "XAF"),
        bank_name=bank_name,
        account_number=account_number,
        account_holder_name=account_holder_name,
        is_active=True,
    )
    return account, "created"


def validate_payroll(*, request, tenant_db: str, salaries: Iterable[Salary], allow_simulated: bool = False):
    salaries = list(salaries or [])
    if not salaries:
        raise ValidationError({"detail": "No salaries found to validate."})

    allowed_statuses = {Salary.STATUS_GENERATED}
    if allow_simulated:
        allowed_statuses.add(Salary.STATUS_SIMULATED)
    for salary in salaries:
        if salary.status not in allowed_statuses:
            raise ValidationError({"detail": "Only generated salaries can be validated."})

    employer = None
    try:
        employer = get_active_employer(request, require_context=False)
    except Exception:
        employer = None
    if not employer:
        employer = EmployerProfile.objects.filter(id=salaries[0].employer_id).first()
    if not employer:
        raise ValidationError({"detail": "Unable to resolve employer context."})

    config = None
    try:
        config = ensure_treasury_configuration(employer, tenant_db=tenant_db)
    except Exception:
        config = None

    grouped: Dict[str, List[Salary]] = {}
    for salary in salaries:
        method = _get_contract_payment_method(salary.contract)
        if not method and config:
            method = resolve_default_payment_method(config, PaymentLine.PAYEE_EMPLOYEE)
        if not method:
            method = "BANK_TRANSFER"
        grouped.setdefault(method, []).append(salary)

    batches = []
    with transaction.atomic(using=tenant_db):
        for method, batch_salaries in grouped.items():
            method = str(method or "").upper()
            if config:
                ensure_payment_method_allowed(config, method)

            first_salary = batch_salaries[0]
            currency = getattr(config, "default_currency", None) or first_salary.contract.currency or "XAF"

            if method == "CASH":
                source = CashDesk.objects.using(tenant_db).filter(employer_id=employer.id, is_active=True).first()
                if not source:
                    raise ValidationError({"detail": "No active cash desk found for payroll validation."})
                source_type = TreasuryTransaction.SOURCE_CASHDESK
            else:
                source, source_status = _resolve_or_create_payroll_bank_source(
                    employer=employer,
                    tenant_db=tenant_db,
                    currency=currency,
                )
                if not source:
                    if source_status == "inactive_only":
                        raise ValidationError(
                            {
                                "detail": (
                                    "No active employer treasury bank account found for payroll validation. "
                                    "Employee bank accounts are beneficiary details only. "
                                    "Activate an account in Treasury > Bank Accounts."
                                )
                            }
                        )
                    raise ValidationError(
                        {
                            "detail": (
                                "No employer treasury bank account found for payroll validation. "
                                "Employee bank accounts are beneficiary details only. "
                                "Create an account in Treasury > Bank Accounts or set employer bank details."
                            )
                        }
                    )
                source_type = TreasuryTransaction.SOURCE_BANK

            batch = PaymentBatch.objects.using(tenant_db).create(
                employer_id=employer.id,
                branch=None,
                name=f"Payroll {first_salary.month:02d}/{first_salary.year} ({method})",
                source_type=source_type,
                source_id=source.id,
                payment_method=method,
                planned_date=timezone.now().date(),
                status=PaymentBatch.STATUS_DRAFT,
                total_amount=Decimal("0.00"),
                currency=currency,
                created_by_id=getattr(request.user, "id", None),
            )
            payout_batch = None
            try:
                from billing.services import ensure_payout_batch
            except Exception:
                ensure_payout_batch = None
            if ensure_payout_batch:
                payout_batch = ensure_payout_batch(
                    tenant_db=tenant_db,
                    employer_id=employer.id,
                    batch_type="PAYROLL",
                    treasury_batch_id=batch.id,
                    created_by_id=getattr(request.user, "id", None),
                )

            for salary in batch_salaries:
                employee = salary.employee
                has_details = bool(
                    getattr(employee, "bank_account_number", None)
                    or getattr(employee, "bank_name", None)
                    or getattr(employee, "phone_number", None)
                )
                if config:
                    ensure_beneficiary_details(config, method, has_details)

                payee_name = " ".join(filter(None, [employee.first_name, employee.middle_name, employee.last_name]))
                line = PaymentLine.objects.using(tenant_db).create(
                    batch=batch,
                    payee_type=PaymentLine.PAYEE_EMPLOYEE,
                    payee_id=employee.id,
                    payee_name=payee_name or employee.email or str(employee.id),
                    amount=salary.net_salary,
                    currency=currency,
                    status=PaymentLine.STATUS_PENDING,
                    linked_object_type="PAYSLIP",
                    linked_object_id=salary.id,
                )
                try:
                    from billing.models import BillingPayout
                    from billing.services import create_payout_with_transactions
                except Exception:
                    create_payout_with_transactions = None
                    BillingPayout = None
                if create_payout_with_transactions and BillingPayout:
                    exists = BillingPayout.objects.using(tenant_db).filter(
                        linked_object_type="PAYSLIP",
                        linked_object_id=salary.id,
                        employer_id=employer.id,
                    ).exists()
                    if not exists:
                        create_payout_with_transactions(
                            tenant_db=tenant_db,
                            employer_id=employer.id,
                            employee=employee,
                            amount=salary.net_salary,
                            currency=currency,
                            category="PAYROLL",
                            batch=payout_batch,
                            linked_object_type="PAYSLIP",
                            linked_object_id=salary.id,
                            treasury_payment_line_id=line.id,
                            treasury_batch_id=batch.id,
                            actor_id=getattr(request.user, "id", None),
                        )
                if config:
                    apply_line_approval_rules(line, config)
                    line.save(using=tenant_db, update_fields=["requires_approval", "approved", "updated_at"])

            batch.recalculate_total()
            if config:
                if config.dual_approval_required_for_payroll:
                    batch.status = PaymentBatch.STATUS_APPROVAL_PENDING
                else:
                    apply_batch_approval_rules(batch, config)
            else:
                batch.status = PaymentBatch.STATUS_APPROVED
            batch.save(using=tenant_db, update_fields=["status", "updated_at"])
            batches.append(batch)

            for salary in batch_salaries:
                salary.status = Salary.STATUS_VALIDATED
                salary.save(using=tenant_db, update_fields=["status", "updated_at"])
                PayrollGeneratedItem.objects.using(tenant_db).filter(
                    salary=salary,
                    source_type=PayrollGeneratedItem.SOURCE_ATTENDANCE,
                    status=PayrollGeneratedItem.STATUS_DRAFT,
                    is_active=True,
                ).update(status=PayrollGeneratedItem.STATUS_LOCKED, updated_at=timezone.now())

    return batches
