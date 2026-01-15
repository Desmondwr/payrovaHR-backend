"""
Core helpers for time off balances, request transitions, and allocations.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from django.db import transaction

from .defaults import get_time_off_defaults
from .models import (
    TimeOffAllocation,
    TimeOffAllocationLine,
    TimeOffAllocationRequest,
    TimeOffAccrualSubscription,
    TimeOffLedgerEntry,
    TimeOffRequest,
)

WEEKDAY_NAME_TO_INDEX = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}


def _abs_amount(entry: TimeOffLedgerEntry) -> int:
    """Return absolute minutes for reservation/debit math."""
    return abs(int(entry.amount_minutes or 0))


def round_minutes(minutes: int, rounding: dict) -> int:
    """Apply rounding config to a minutes value."""
    inc = int(rounding.get("increment_minutes") or 0) or 0
    method = (rounding.get("method") or "NEAREST").upper()
    if inc <= 0:
        return minutes
    remainder = minutes % inc
    if remainder == 0:
        return minutes
    if method == "DOWN":
        return minutes - remainder
    if method == "UP":
        return minutes + (inc - remainder)
    # NEAREST
    if remainder >= inc / 2:
        return minutes + (inc - remainder)
    return minutes - remainder


def _daterange(start: date, end: date):
    curr = start
    while curr <= end:
        yield curr
        curr += timedelta(days=1)


def calculate_duration_minutes(
    *,
    start_date: date,
    end_date: Optional[date],
    half_day: bool,
    half_day_period: Optional[str],
    custom_hours: bool,
    from_time_val: Optional[time],
    to_time_val: Optional[time],
    working_hours_per_day: int,
    weekend_days: list,
    count_weekends_as_leave: bool,
    rounding: dict,
) -> Tuple[datetime, datetime, int, float]:
    """
    Compute start_at/end_at and duration in minutes + day-equivalent.
    Returns (start_at, end_at, minutes, day_equivalent)
    """
    if custom_hours:
        if not from_time_val or not to_time_val:
            raise ValueError("from_time and to_time are required for custom hours.")
        start_at = datetime.combine(start_date, from_time_val)
        end_at = datetime.combine(start_date, to_time_val)
        if end_at <= start_at:
            raise ValueError("to_time must be after from_time.")
        minutes = int((end_at - start_at).total_seconds() // 60)
        minutes = round_minutes(minutes, rounding)
        day_equiv = minutes / float(working_hours_per_day * 60)
        return start_at, end_at, minutes, day_equiv

    if half_day:
        if not half_day_period:
            raise ValueError("half_day_period is required when requesting half-day.")
        start_at = datetime.combine(start_date, time.min if half_day_period == "MORNING" else time(12, 0))
        end_at = datetime.combine(start_date, time(12, 0) if half_day_period == "MORNING" else time.max)
        minutes = int((working_hours_per_day * 60) / 2)
        minutes = round_minutes(minutes, rounding)
        return start_at, end_at, minutes, 0.5

    # Full day range
    end_date = end_date or start_date
    start_at = datetime.combine(start_date, time.min)
    end_at = datetime.combine(end_date, time.max)
    weekend_ints = {WEEKDAY_NAME_TO_INDEX.get(d) for d in weekend_days or []}
    leave_days = 0
    for day in _daterange(start_date, end_date):
        if not count_weekends_as_leave and day.weekday() in weekend_ints:
            continue
        # Holidays support can be added here (currently none counted)
        leave_days += 1
    minutes = int(leave_days * working_hours_per_day * 60)
    minutes = round_minutes(minutes, rounding)
    return start_at, end_at, minutes, float(leave_days)


def compute_balances(
    entries: Iterable[TimeOffLedgerEntry],
    reservation_policy: str = "RESERVE_ON_SUBMIT",
    as_of: Optional[date] = None,
) -> dict:
    """
    Compute earned/reserved/taken/available from a set of ledger entries.
    - earned: ACCRUAL + ALLOCATION + ADJUSTMENT + CARRYOVER - EXPIRY - ENCASHMENT + REVERSAL (as-signed)
    - reserved: RESERVATION (absolute minutes)
    - taken: DEBIT (absolute minutes)
    - available: earned - reserved - taken (or earned - taken when policy deducts on approval)
    """
    if as_of:
        if hasattr(entries, "filter"):
            entries = entries.filter(effective_date__lte=as_of)
        else:
            entries = [e for e in entries if getattr(e, "effective_date", None) and e.effective_date <= as_of]

    earned = 0
    reserved = 0
    taken = 0

    for entry in entries:
        etype = entry.entry_type
        amt = int(entry.amount_minutes or 0)

        if etype in {"ACCRUAL", "ALLOCATION", "ADJUSTMENT", "CARRYOVER", "REVERSAL"}:
            earned += amt
        elif etype in {"EXPIRY", "ENCASHMENT"}:
            earned -= abs(amt)
        elif etype == "RESERVATION":
            reserved += _abs_amount(entry)
        elif etype == "DEBIT":
            taken += _abs_amount(entry)

    if reservation_policy == "RESERVE_ON_SUBMIT":
        available = earned - reserved - taken
    else:
        available = earned - taken

    return {
        "earned_minutes": earned,
        "reserved_minutes": reserved,
        "taken_minutes": taken,
        "available_minutes": available,
    }


def get_available_balance(
    employee,
    leave_type_code: str,
    reservation_policy: str,
    db_alias: str = "default",
    as_of: Optional[date] = None,
) -> int:
    """Return available minutes for an employee/leave type (optionally as of a date)."""
    entries = TimeOffLedgerEntry.objects.using(db_alias).filter(
        employee=employee,
        leave_type_code=leave_type_code,
    )
    return compute_balances(entries, reservation_policy, as_of=as_of).get("available_minutes", 0)


def has_overlap(employee, start_at: datetime, end_at: datetime, db_alias: str, exclude_request_id=None) -> bool:
    """Check overlapping requests in PENDING/APPROVED/SUBMITTED state."""
    qs = TimeOffRequest.objects.using(db_alias).filter(
        employee=employee,
        status__in=["SUBMITTED", "PENDING", "APPROVED"],
        start_at__lte=end_at,
        end_at__gte=start_at,
    )
    if exclude_request_id:
        qs = qs.exclude(id=exclude_request_id)
    return qs.exists()


def write_ledger_entry(
    *,
    employer_id: int,
    tenant_id: Optional[int],
    employee,
    leave_type_code: str,
    entry_type: str,
    amount_minutes: int,
    created_by: int,
    request: Optional[TimeOffRequest] = None,
    allocation: Optional[TimeOffAllocation] = None,
    allocation_request: Optional[TimeOffAllocationRequest] = None,
    source_reference: Optional[str] = None,
    effective_date: Optional[date] = None,
    notes: Optional[str] = None,
    metadata: Optional[dict] = None,
    db_alias: str = "default",
) -> TimeOffLedgerEntry:
    """Create a ledger entry in an atomic, reusable way."""
    effective = effective_date or date.today()
    return TimeOffLedgerEntry.objects.using(db_alias).create(
        employer_id=employer_id,
        tenant_id=tenant_id or employer_id,
        employee=employee,
        leave_type_code=leave_type_code,
        entry_type=entry_type,
        amount_minutes=amount_minutes,
        effective_date=effective,
        request=request,
        allocation=allocation,
        allocation_request=allocation_request,
        source_reference=source_reference,
        notes=notes,
        created_by=created_by,
        metadata=metadata or {},
    )


def apply_submit_transitions(
    *,
    request: TimeOffRequest,
    duration_minutes: int,
    reservation_policy: str,
    created_by: int,
    db_alias: str = "default",
    effective_date: Optional[date] = None,
):
    """
    On submit:
      - if policy is RESERVE_ON_SUBMIT, create a RESERVATION (negative)
      - status moves to PENDING
    Idempotent: skips creating duplicate reservation if one exists for the request.
    """
    with transaction.atomic(using=db_alias):
        if reservation_policy == "RESERVE_ON_SUBMIT":
            exists = TimeOffLedgerEntry.objects.using(db_alias).filter(
                request=request,
                entry_type="RESERVATION",
            ).exists()
            if not exists:
                write_ledger_entry(
                    employer_id=request.employer_id,
                    tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
                    employee=request.employee,
                    leave_type_code=request.leave_type_code,
                    entry_type="RESERVATION",
                    amount_minutes=-abs(duration_minutes),
                    created_by=created_by,
                    request=request,
                    effective_date=effective_date or request.start_at.date(),
                    source_reference=f"request:{request.id}",
                    metadata={"source": "reservation"},
                    db_alias=db_alias,
                )
        request.mark_pending()
        request.save(using=db_alias)


def apply_approval_transitions(
    *,
    request: TimeOffRequest,
    duration_minutes: int,
    reservation_policy: str,
    created_by: int,
    db_alias: str = "default",
    effective_date: Optional[date] = None,
):
    """
    On approve:
      - Always create DEBIT (-duration) if not already present
      - If reservation existed, create REVERSAL (+duration) (idempotent)
      - status -> APPROVED
    """
    with transaction.atomic(using=db_alias):
        debit_exists = TimeOffLedgerEntry.objects.using(db_alias).filter(
            request=request,
            entry_type="DEBIT",
        ).exists()
        if not debit_exists:
            write_ledger_entry(
                employer_id=request.employer_id,
                tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
                employee=request.employee,
                leave_type_code=request.leave_type_code,
                entry_type="DEBIT",
                amount_minutes=-abs(duration_minutes),
                created_by=created_by,
                request=request,
                effective_date=effective_date or request.start_at.date(),
                source_reference=f"request:{request.id}",
                metadata={"source": "approval_debit"},
                db_alias=db_alias,
            )

        if reservation_policy == "RESERVE_ON_SUBMIT":
            reversal_exists = TimeOffLedgerEntry.objects.using(db_alias).filter(
                request=request,
                entry_type="REVERSAL",
            ).exists()
            if not reversal_exists:
                write_ledger_entry(
                    employer_id=request.employer_id,
                    tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
                    employee=request.employee,
                leave_type_code=request.leave_type_code,
                entry_type="REVERSAL",
                amount_minutes=abs(duration_minutes),
                created_by=created_by,
                request=request,
                effective_date=effective_date or request.start_at.date(),
                source_reference=f"request:{request.id}",
                metadata={"source": "reservation_reversal"},
                db_alias=db_alias,
            )

        request.mark_approved()
        request.save(using=db_alias)


def apply_rejection_or_cancellation_transitions(
    *,
    request: TimeOffRequest,
    duration_minutes: int,
    reservation_policy: str,
    created_by: int,
    db_alias: str = "default",
    effective_date: Optional[date] = None,
    cancelled: bool = False,
):
    """
    On reject/cancel:
      - If reservation exists (policy is RESERVE_ON_SUBMIT), reverse it (+duration) if not already reversed
      - status -> REJECTED or CANCELLED
    """
    with transaction.atomic(using=db_alias):
        if reservation_policy == "RESERVE_ON_SUBMIT":
            reversal_exists = TimeOffLedgerEntry.objects.using(db_alias).filter(
                request=request,
                entry_type="REVERSAL",
            ).exists()
            if not reversal_exists:
                write_ledger_entry(
                    employer_id=request.employer_id,
                    tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
                    employee=request.employee,
                leave_type_code=request.leave_type_code,
                entry_type="REVERSAL",
                amount_minutes=abs(duration_minutes),
                created_by=created_by,
                request=request,
                effective_date=effective_date or request.start_at.date(),
                source_reference=f"request:{request.id}",
                metadata={"source": "cancellation_reversal" if cancelled else "rejection_reversal"},
                db_alias=db_alias,
            )

        if cancelled:
            request.mark_cancelled()
        else:
            request.mark_rejected()
        request.save(using=db_alias)


def convert_amount_to_minutes(amount: Decimal, unit: str, working_hours: int, rounding: dict) -> int:
    """Normalize allocation amounts to minutes with rounding."""
    minutes = int(amount * 60) if unit == "HOURS" else int(amount * Decimal(working_hours) * 60)
    return round_minutes(minutes, rounding)


def post_allocation_entries(
    *,
    allocation: TimeOffAllocation,
    lines,
    working_hours: int,
    rounding: dict,
    created_by: int,
    db_alias: str,
):
    """Create ALLOCATION ledger entries for each line (idempotent per allocation+employee)."""
    for line in lines:
        exists = TimeOffLedgerEntry.objects.using(db_alias).filter(
            allocation=allocation,
            employee=line.employee,
            leave_type_code=allocation.leave_type_code,
            entry_type="ALLOCATION",
        ).exists()
        if exists:
            continue
        amount = Decimal(allocation.amount or 0)
        unit = allocation.unit or "DAYS"
        minutes = convert_amount_to_minutes(amount, unit, working_hours, rounding)
        write_ledger_entry(
            employer_id=allocation.employer_id,
            tenant_id=allocation.tenant_id or allocation.employer_id,
            employee=line.employee,
            leave_type_code=allocation.leave_type_code,
            entry_type="ALLOCATION",
            amount_minutes=minutes,
            created_by=created_by,
            allocation=allocation,
            effective_date=allocation.start_date,
            source_reference=f"allocation:{allocation.id}",
            metadata={"source": "allocation"},
            db_alias=db_alias,
        )
        line.status = "CONFIRMED"
        line.save(using=db_alias)


def run_accruals_for_subscriptions(
    *,
    upto_date: date,
    created_by: int,
    db_alias: str,
):
    """
    Generate accrual ledger entries up to a given date for active subscriptions.
    Currently supports monthly frequency.
    """
    subs = TimeOffAccrualSubscription.objects.using(db_alias).select_related("plan", "employee").filter(
        status="ACTIVE",
        start_date__lte=upto_date,
    )
    for sub in subs:
        plan = sub.plan
        if plan.frequency != "MONTHLY":
            continue

        def snap_start(d: date, gain: str) -> date:
            first = d.replace(day=1)
            if gain == "START":
                return first
            # END -> next period start
            if first.month == 12:
                return date(first.year + 1, 1, 1)
            return date(first.year, first.month + 1, 1)

        def add_month(d: date) -> date:
            if d.month == 12:
                return date(d.year + 1, 1, d.day)
            return date(d.year, d.month + 1, d.day)

        current = sub.last_accrual_date or snap_start(sub.start_date, plan.accrual_gain_time)
        # Skip until inside window
        while current < sub.start_date:
            current = add_month(current)

        while current <= upto_date and (sub.end_date is None or current <= sub.end_date):
            exists = TimeOffLedgerEntry.objects.using(db_alias).filter(
                allocation=sub.allocation,
                employee=sub.employee,
                leave_type_code=sub.leave_type_code,
                entry_type="ACCRUAL",
                effective_date=current,
            ).exists()
            if not exists:
                write_ledger_entry(
                    employer_id=sub.employee.employer_id,
                    tenant_id=sub.allocation.tenant_id if sub.allocation else sub.employee.employer_id,
                    employee=sub.employee,
                    leave_type_code=sub.leave_type_code,
                    entry_type="ACCRUAL",
                    amount_minutes=plan.amount_minutes,
                    created_by=created_by,
                    allocation=sub.allocation,
                    effective_date=current,
                    source_reference=f"accrual_plan:{plan.id}",
                    metadata={"source": "accrual_run", "subscription_id": str(sub.id)},
                    db_alias=db_alias,
                )
                sub.last_accrual_date = current
                sub.save(using=db_alias)
            current = add_month(current)


def write_adjustment(
    *,
    employer_id: int,
    tenant_id: int,
    employee,
    leave_type_code: str,
    amount_minutes: int,
    created_by: int,
    effective_date: date,
    source_reference: str,
    notes: Optional[str] = None,
    metadata: Optional[dict] = None,
    db_alias: str = "default",
) -> TimeOffLedgerEntry:
    """Manual correction recorded as an ADJUSTMENT entry."""
    return write_ledger_entry(
        employer_id=employer_id,
        tenant_id=tenant_id,
        employee=employee,
        leave_type_code=leave_type_code,
        entry_type="ADJUSTMENT",
        amount_minutes=amount_minutes,
        created_by=created_by,
        effective_date=effective_date,
        source_reference=source_reference,
        notes=notes,
        metadata=metadata,
        db_alias=db_alias,
    )


def write_carryover(
    *,
    employer_id: int,
    tenant_id: int,
    employee,
    leave_type_code: str,
    amount_minutes: int,
    created_by: int,
    effective_date: date,
    source_reference: str,
    metadata: Optional[dict] = None,
    db_alias: str = "default",
) -> TimeOffLedgerEntry:
    """Year-end carryover entry."""
    return write_ledger_entry(
        employer_id=employer_id,
        tenant_id=tenant_id,
        employee=employee,
        leave_type_code=leave_type_code,
        entry_type="CARRYOVER",
        amount_minutes=amount_minutes,
        created_by=created_by,
        effective_date=effective_date,
        source_reference=source_reference,
        metadata=metadata,
        db_alias=db_alias,
    )


def write_expiry(
    *,
    employer_id: int,
    tenant_id: int,
    employee,
    leave_type_code: str,
    amount_minutes: int,
    created_by: int,
    effective_date: date,
    source_reference: str,
    metadata: Optional[dict] = None,
    db_alias: str = "default",
) -> TimeOffLedgerEntry:
    """Expiry entry when unused balance lapses."""
    return write_ledger_entry(
        employer_id=employer_id,
        tenant_id=tenant_id,
        employee=employee,
        leave_type_code=leave_type_code,
        entry_type="EXPIRY",
        amount_minutes=-abs(amount_minutes),
        created_by=created_by,
        effective_date=effective_date,
        source_reference=source_reference,
        metadata=metadata,
        db_alias=db_alias,
    )


def write_encashment(
    *,
    employer_id: int,
    tenant_id: int,
    employee,
    leave_type_code: str,
    amount_minutes: int,
    created_by: int,
    effective_date: date,
    source_reference: str,
    metadata: Optional[dict] = None,
    db_alias: str = "default",
) -> TimeOffLedgerEntry:
    """Encashment entry for converted leave."""
    return write_ledger_entry(
        employer_id=employer_id,
        tenant_id=tenant_id,
        employee=employee,
        leave_type_code=leave_type_code,
        entry_type="ENCASHMENT",
        amount_minutes=-abs(amount_minutes),
        created_by=created_by,
        effective_date=effective_date,
        source_reference=source_reference,
        metadata=metadata,
        db_alias=db_alias,
    )
