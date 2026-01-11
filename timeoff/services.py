"""
Core helpers for time off balances and ledger transitions.
These functions intentionally avoid business-layer concerns (like permissions)
so they can be reused by views, signals, or background jobs.
"""
from datetime import date
from typing import Iterable, Optional, Tuple

from django.db import transaction

from .defaults import get_time_off_defaults
from .models import TimeOffLedgerEntry, TimeOffRequest


def _abs_amount(entry: TimeOffLedgerEntry) -> int:
    """Return absolute minutes for reservation/debit math."""
    return abs(int(entry.amount_minutes or 0))


def compute_balances(
    entries: Iterable[TimeOffLedgerEntry],
    reservation_policy: str = "RESERVE_ON_SUBMIT",
) -> dict:
    """
    Compute earned/reserved/taken/available from a set of ledger entries.
    - earned: ACCRUAL + ALLOCATION + ADJUSTMENT + CARRYOVER - EXPIRY - ENCASHMENT + REVERSAL (as-signed)
    - reserved: RESERVATION (absolute minutes)
    - taken: DEBIT (absolute minutes)
    - available: earned - reserved - taken (or earned - taken when policy deducts on approval)
    """
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
) -> Tuple[Optional[TimeOffLedgerEntry], Optional[TimeOffLedgerEntry]]:
    """
    On submit:
      - if policy is RESERVE_ON_SUBMIT, create a RESERVATION (negative)
      - status moves to PENDING
    Returns (reservation_entry, None)
    """
    reservation_entry = None
    with transaction.atomic(using=db_alias):
        if reservation_policy == "RESERVE_ON_SUBMIT":
            reservation_entry = write_ledger_entry(
                employer_id=request.employer_id,
                tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
                employee=request.employee,
                leave_type_code=request.leave_type_code,
                entry_type="RESERVATION",
                amount_minutes=-abs(duration_minutes),
                created_by=created_by,
                request=request,
                effective_date=effective_date or request.start_at.date(),
                db_alias=db_alias,
            )
        request.mark_pending()
        request.save(using=db_alias)
    return reservation_entry, None


def apply_approval_transitions(
    *,
    request: TimeOffRequest,
    duration_minutes: int,
    reservation_policy: str,
    created_by: int,
    db_alias: str = "default",
    effective_date: Optional[date] = None,
) -> Tuple[Optional[TimeOffLedgerEntry], Optional[TimeOffLedgerEntry]]:
    """
    On approve:
      - Always create DEBIT (-duration)
      - If reservation existed, create REVERSAL (+duration)
      - status -> APPROVED
    Returns (debit_entry, reversal_entry)
    """
    debit_entry = None
    reversal_entry = None
    with transaction.atomic(using=db_alias):
        debit_entry = write_ledger_entry(
            employer_id=request.employer_id,
            tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
            employee=request.employee,
            leave_type_code=request.leave_type_code,
            entry_type="DEBIT",
            amount_minutes=-abs(duration_minutes),
            created_by=created_by,
            request=request,
            effective_date=effective_date or request.start_at.date(),
            db_alias=db_alias,
        )

        if reservation_policy == "RESERVE_ON_SUBMIT":
            reversal_entry = write_ledger_entry(
                employer_id=request.employer_id,
                tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
                employee=request.employee,
                leave_type_code=request.leave_type_code,
                entry_type="REVERSAL",
                amount_minutes=abs(duration_minutes),
                created_by=created_by,
                request=request,
                effective_date=effective_date or request.start_at.date(),
                db_alias=db_alias,
            )

        request.mark_approved()
        request.save(using=db_alias)
    return debit_entry, reversal_entry


def apply_rejection_or_cancellation_transitions(
    *,
    request: TimeOffRequest,
    duration_minutes: int,
    reservation_policy: str,
    created_by: int,
    db_alias: str = "default",
    effective_date: Optional[date] = None,
    cancelled: bool = False,
) -> Optional[TimeOffLedgerEntry]:
    """
    On reject/cancel:
      - If reservation exists (policy is RESERVE_ON_SUBMIT), reverse it (+duration)
      - status -> REJECTED or CANCELLED
    Returns reversal entry or None.
    """
    reversal_entry = None
    with transaction.atomic(using=db_alias):
        if reservation_policy == "RESERVE_ON_SUBMIT":
            reversal_entry = write_ledger_entry(
                employer_id=request.employer_id,
                tenant_id=getattr(request, "tenant_id", None) or request.employer_id,
                employee=request.employee,
                leave_type_code=request.leave_type_code,
                entry_type="REVERSAL",
                amount_minutes=abs(duration_minutes),
                created_by=created_by,
                request=request,
                effective_date=effective_date or request.start_at.date(),
                db_alias=db_alias,
            )

        if cancelled:
            request.mark_cancelled()
        else:
            request.mark_rejected()
        request.save(using=db_alias)

    return reversal_entry
