from __future__ import annotations

from datetime import date, datetime, time, timedelta
import copy
from typing import Dict, Iterable, Optional, Tuple

from django.utils import timezone

from timeoff.models import TimeOffRequest, ensure_timeoff_configuration

from .defaults import ATTENDANCE_DEFAULTS
from .models import (
    AttendanceDay,
    AttendanceDevice,
    AttendanceEvent,
    AttendanceKioskSettings,
    AttendancePolicy,
    AttendanceRecord,
    EmployeeSchedule,
    OvertimeRequest,
    ShiftTemplate,
)


WEEKDAY_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_attendance_policy(employer_id: int, tenant_db: str) -> AttendancePolicy:
    policy = (
        AttendancePolicy.objects.using(tenant_db)
        .filter(employer_id=employer_id, scope_type=AttendancePolicy.SCOPE_GLOBAL, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if policy:
        return policy
    defaults = AttendancePolicy.build_defaults(employer_id)
    policy = AttendancePolicy.objects.using(tenant_db).create(
        scope_type=AttendancePolicy.SCOPE_GLOBAL,
        is_active=True,
        **defaults,
    )
    return policy


def ensure_kiosk_settings(employer_id: int, tenant_db: str) -> AttendanceKioskSettings:
    settings = AttendanceKioskSettings.objects.using(tenant_db).filter(employer_id=employer_id).first()
    if settings:
        return settings
    return AttendanceKioskSettings.objects.using(tenant_db).create(employer_id=employer_id)


def _load_timeoff_calendar(employer_id: int, tenant_db: str) -> dict:
    config = ensure_timeoff_configuration(employer_id, tenant_db)
    return config.to_config_dict().get("global_settings") or {}


def resolve_attendance_policy(employee, tenant_db: str) -> dict:
    employer_id = employee.employer_id
    policy = copy.deepcopy(ATTENDANCE_DEFAULTS)

    global_policy = (
        AttendancePolicy.objects.using(tenant_db)
        .filter(employer_id=employer_id, scope_type=AttendancePolicy.SCOPE_GLOBAL, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if global_policy:
        policy = _deep_merge(policy, global_policy.to_policy_dict())

    if employee.branch_id:
        branch_policy = (
            AttendancePolicy.objects.using(tenant_db)
            .filter(
                employer_id=employer_id,
                scope_type=AttendancePolicy.SCOPE_BRANCH,
                branch_id=employee.branch_id,
                is_active=True,
            )
            .order_by("-updated_at")
            .first()
        )
        if branch_policy:
            policy = _deep_merge(policy, branch_policy.to_policy_dict())

    if employee.department_id:
        department_policy = (
            AttendancePolicy.objects.using(tenant_db)
            .filter(
                employer_id=employer_id,
                scope_type=AttendancePolicy.SCOPE_DEPARTMENT,
                department_id=employee.department_id,
                is_active=True,
            )
            .order_by("-updated_at")
            .first()
        )
        if department_policy:
            policy = _deep_merge(policy, department_policy.to_policy_dict())

    employee_policy = (
        AttendancePolicy.objects.using(tenant_db)
        .filter(
            employer_id=employer_id,
            scope_type=AttendancePolicy.SCOPE_EMPLOYEE,
            employee_id=employee.id,
            is_active=True,
        )
        .order_by("-updated_at")
        .first()
    )
    if employee_policy:
        policy = _deep_merge(policy, employee_policy.to_policy_dict())

    calendar = policy.get("working_calendar") or {}
    if not calendar.get("weekend_days"):
        timeoff_calendar = _load_timeoff_calendar(employer_id, tenant_db)
        calendar["weekend_days"] = timeoff_calendar.get("weekend_days") or calendar.get("weekend_days") or []
    if not calendar.get("holiday_calendar_source"):
        timeoff_calendar = _load_timeoff_calendar(employer_id, tenant_db)
        calendar["holiday_calendar_source"] = timeoff_calendar.get("holiday_calendar_source") or "TIMEOFF"
    policy["working_calendar"] = calendar
    return policy


def _make_aware(d: date, t: time) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(d, t), tz)


def _date_in_schedule(schedule: EmployeeSchedule, target: date) -> bool:
    if schedule.date_from and target < schedule.date_from:
        return False
    if schedule.date_to and target > schedule.date_to:
        return False
    if schedule.weekdays:
        return target.weekday() in schedule.weekdays
    return True


def _get_schedule_for_date(employee, target: date, tenant_db: str) -> Optional[EmployeeSchedule]:
    schedules = (
        EmployeeSchedule.objects.using(tenant_db)
        .select_related("shift_template")
        .filter(employee=employee, employer_id=employee.employer_id)
        .order_by("-date_from")
    )
    for schedule in schedules:
        if _date_in_schedule(schedule, target):
            return schedule
    return None


def get_open_attendance_record(employee, tenant_db: str) -> Optional[AttendanceRecord]:
    return (
        AttendanceRecord.objects.using(tenant_db)
        .filter(employee=employee, check_out_at__isnull=True)
        .order_by("-check_in_at")
        .first()
    )


def get_shift_for_timestamp(employee, timestamp: datetime, tenant_db: str) -> Tuple[Optional[ShiftTemplate], date]:
    ts_date = timezone.localdate(timestamp)
    schedule_today = _get_schedule_for_date(employee, ts_date, tenant_db)
    schedule_prev = _get_schedule_for_date(employee, ts_date - timedelta(days=1), tenant_db)

    if schedule_prev and schedule_prev.shift_template.is_overnight:
        shift_start = _make_aware(ts_date - timedelta(days=1), schedule_prev.shift_template.start_time)
        shift_end = _make_aware(ts_date, schedule_prev.shift_template.end_time)
        if shift_start <= timestamp <= shift_end:
            return schedule_prev.shift_template, ts_date - timedelta(days=1)

    if schedule_today:
        return schedule_today.shift_template, ts_date

    return None, ts_date


def assign_attendance_date(employee, timestamp: datetime, tenant_db: str) -> Tuple[Optional[ShiftTemplate], date]:
    shift, shift_date = get_shift_for_timestamp(employee, timestamp, tenant_db)
    return shift, shift_date


def apply_rounding(minutes: int, rounding: dict) -> int:
    unit = (rounding or {}).get("unit", "MINUTES")
    increment = int((rounding or {}).get("increment", 1) or 1)
    method = (rounding or {}).get("method", "NEAREST").upper()

    if unit != "MINUTES" or increment <= 1:
        return minutes

    remainder = minutes % increment
    if remainder == 0:
        return minutes
    if method == "UP":
        return minutes + (increment - remainder)
    if method == "DOWN":
        return minutes - remainder
    if method == "NEAREST":
        if remainder >= increment / 2:
            return minutes + (increment - remainder)
        return minutes - remainder
    return minutes


def compute_overtime_minutes(
    employee,
    check_in_at: datetime,
    check_out_at: datetime,
    tenant_db: str,
    policy: Optional[dict] = None,
) -> Tuple[int, Optional[ShiftTemplate], date]:
    policy = policy or resolve_attendance_policy(employee, tenant_db)
    attendance_policy = policy.get("attendance_policy") or {}
    rounding = attendance_policy.get("rounding") or {}

    shift, attendance_date = assign_attendance_date(employee, check_in_at, tenant_db)
    if not shift:
        return 0, None, attendance_date

    shift_end = _make_aware(attendance_date, shift.end_time)
    if shift.is_overnight:
        shift_end += timedelta(days=1)

    overtime_start_after = shift.overtime_starts_after_minutes or int(
        (policy.get("overtime_policy") or {}).get("starts_after_minutes", 0) or 0
    )
    overtime_delta = check_out_at - (shift_end + timedelta(minutes=overtime_start_after))
    overtime_minutes = max(0, int(overtime_delta.total_seconds() // 60))

    minimum = int((policy.get("overtime_policy") or {}).get("minimum_minutes", 0) or 0)
    if overtime_minutes < minimum:
        overtime_minutes = 0

    overtime_minutes = apply_rounding(overtime_minutes, rounding)
    return overtime_minutes, shift, attendance_date


def compute_worked_minutes(check_in_at: datetime, check_out_at: datetime, rounding: dict) -> int:
    delta = check_out_at - check_in_at
    minutes = max(0, int(delta.total_seconds() // 60))
    return apply_rounding(minutes, rounding)


def create_check_in_record(
    employee,
    tenant_db: str,
    mode: str,
    ip_address: Optional[str] = None,
    gps_lat: Optional[float] = None,
    gps_lng: Optional[float] = None,
    kiosk_device: Optional[AttendanceDevice] = None,
    created_by_id: Optional[int] = None,
) -> AttendanceRecord:
    existing = get_open_attendance_record(employee, tenant_db)
    if existing:
        return existing

    now = timezone.now()
    record = AttendanceRecord.objects.using(tenant_db).create(
        employer_id=employee.employer_id,
        employee=employee,
        check_in_at=now,
        mode=mode,
        ip_check_in=ip_address,
        gps_check_in_lat=gps_lat,
        gps_check_in_lng=gps_lng,
        kiosk_device=kiosk_device,
        created_by_id=created_by_id,
        overtime_status=AttendanceRecord.STATUS_TO_APPROVE,
    )

    shift, attendance_date = assign_attendance_date(employee, now, tenant_db)
    AttendanceEvent.objects.using(tenant_db).create(
        employer_id=employee.employer_id,
        employee=employee,
        attendance_date=attendance_date,
        timestamp=now,
        event_type=AttendanceEvent.EVENT_IN,
        source=_map_mode_to_event_source(mode),
        device=kiosk_device,
        location_lat=gps_lat,
        location_lng=gps_lng,
        ip_address=ip_address,
        created_by_id=created_by_id,
    )
    rebuild_attendance_day(employee, attendance_date, tenant_db)
    return record


def close_check_out_record(
    record: AttendanceRecord,
    tenant_db: str,
    ip_address: Optional[str] = None,
    gps_lat: Optional[float] = None,
    gps_lng: Optional[float] = None,
    overtime_reason: Optional[str] = None,
) -> AttendanceRecord:
    if record.check_out_at:
        return record

    now = timezone.now()
    record.check_out_at = now
    record.ip_check_out = ip_address
    record.gps_check_out_lat = gps_lat
    record.gps_check_out_lng = gps_lng

    policy = resolve_attendance_policy(record.employee, tenant_db)
    attendance_policy = policy.get("attendance_policy") or {}
    rounding = attendance_policy.get("rounding") or {}

    record.worked_minutes = compute_worked_minutes(record.check_in_at, record.check_out_at, rounding)
    overtime_minutes, _, attendance_date = compute_overtime_minutes(
        record.employee,
        record.check_in_at,
        record.check_out_at,
        tenant_db,
        policy=policy,
    )
    record.extra_minutes = overtime_minutes
    require_approval = (policy.get("overtime_policy") or {}).get("require_approval", True)
    if require_approval and overtime_minutes > 0 and not overtime_reason:
        raise ValueError("Overtime reason is required.")
    record.overtime_reason = overtime_reason or record.overtime_reason
    record.overtime_status = (
        AttendanceRecord.STATUS_TO_APPROVE if require_approval and overtime_minutes > 0 else AttendanceRecord.STATUS_APPROVED
    )
    record.save(using=tenant_db)

    AttendanceEvent.objects.using(tenant_db).create(
        employer_id=record.employee.employer_id,
        employee=record.employee,
        attendance_date=attendance_date,
        timestamp=now,
        event_type=AttendanceEvent.EVENT_OUT,
        source=_map_mode_to_event_source(record.mode),
        device=record.kiosk_device,
        location_lat=gps_lat,
        location_lng=gps_lng,
        ip_address=ip_address,
        created_by_id=record.created_by_id,
    )
    rebuild_attendance_day(record.employee, attendance_date, tenant_db, policy)
    return record


def create_manual_record(
    employee,
    tenant_db: str,
    check_in_at: datetime,
    check_out_at: datetime,
    extra_minutes: Optional[int],
    overtime_reason: Optional[str],
    created_by_id: Optional[int],
) -> AttendanceRecord:
    policy = resolve_attendance_policy(employee, tenant_db)
    attendance_policy = policy.get("attendance_policy") or {}
    rounding = attendance_policy.get("rounding") or {}

    worked_minutes = compute_worked_minutes(check_in_at, check_out_at, rounding)
    overtime_minutes, _, attendance_date = compute_overtime_minutes(
        employee,
        check_in_at,
        check_out_at,
        tenant_db,
        policy=policy,
    )
    if extra_minutes is not None:
        overtime_minutes = max(0, int(extra_minutes))
    require_approval = (policy.get("overtime_policy") or {}).get("require_approval", True)
    if require_approval and overtime_minutes > 0 and not overtime_reason:
        raise ValueError("Overtime reason is required.")

    record = AttendanceRecord.objects.using(tenant_db).create(
        employer_id=employee.employer_id,
        employee=employee,
        check_in_at=check_in_at,
        check_out_at=check_out_at,
        worked_minutes=worked_minutes,
        extra_minutes=overtime_minutes,
        overtime_reason=overtime_reason,
        overtime_status=AttendanceRecord.STATUS_APPROVED if overtime_minutes else AttendanceRecord.STATUS_APPROVED,
        mode=AttendanceRecord.MODE_MANUAL,
        created_by_id=created_by_id,
    )

    AttendanceEvent.objects.using(tenant_db).create(
        employer_id=employee.employer_id,
        employee=employee,
        attendance_date=attendance_date,
        timestamp=check_in_at,
        event_type=AttendanceEvent.EVENT_IN,
        source=AttendanceEvent.SOURCE_MANUAL,
        created_by_id=created_by_id,
    )
    AttendanceEvent.objects.using(tenant_db).create(
        employer_id=employee.employer_id,
        employee=employee,
        attendance_date=attendance_date,
        timestamp=check_out_at,
        event_type=AttendanceEvent.EVENT_OUT,
        source=AttendanceEvent.SOURCE_MANUAL,
        created_by_id=created_by_id,
    )
    rebuild_attendance_day(employee, attendance_date, tenant_db, policy)
    return record


def _map_mode_to_event_source(mode: str) -> str:
    if mode == AttendanceRecord.MODE_KIOSK:
        return AttendanceEvent.SOURCE_KIOSK
    if mode == AttendanceRecord.MODE_MANUAL:
        return AttendanceEvent.SOURCE_MANUAL
    return AttendanceEvent.SOURCE_WEB


def _is_weekend(attendance_date: date, policy: dict) -> bool:
    calendar = policy.get("working_calendar") or {}
    weekend_days = calendar.get("weekend_days") or []
    day_name = WEEKDAY_NAMES[attendance_date.weekday()]
    return day_name in weekend_days


def _is_holiday(attendance_date: date, policy: dict) -> bool:
    calendar = policy.get("working_calendar") or {}
    holiday_dates = {str(d) for d in (calendar.get("holiday_dates") or [])}
    return str(attendance_date) in holiday_dates


def _has_approved_leave(employee, attendance_date: date, tenant_db: str) -> bool:
    return TimeOffRequest.objects.using(tenant_db).filter(
        employee=employee,
        status="APPROVED",
        start_at__date__lte=attendance_date,
        end_at__date__gte=attendance_date,
    ).exists()


def _compute_worked_minutes(events: Iterable[AttendanceEvent], shift: Optional[ShiftTemplate]) -> Tuple[int, list]:
    worked_minutes = 0
    break_minutes = 0
    anomalies = []
    current_in = None
    break_start = None

    for event in events:
        if event.event_type == AttendanceEvent.EVENT_IN:
            if current_in:
                anomalies.append("MULTIPLE_IN")
                continue
            current_in = event.timestamp
        elif event.event_type == AttendanceEvent.EVENT_OUT:
            if not current_in:
                anomalies.append("MISSING_IN")
                continue
            delta = event.timestamp - current_in
            worked_minutes += int(delta.total_seconds() // 60)
            current_in = None
        elif event.event_type == AttendanceEvent.EVENT_BREAK_START:
            if break_start:
                anomalies.append("MULTIPLE_BREAK_START")
                continue
            break_start = event.timestamp
        elif event.event_type == AttendanceEvent.EVENT_BREAK_END:
            if not break_start:
                anomalies.append("MISSING_BREAK_START")
                continue
            delta = event.timestamp - break_start
            break_minutes += int(delta.total_seconds() // 60)
            break_start = None

    if current_in:
        anomalies.append("MISSING_OUT")
    if break_start:
        anomalies.append("MISSING_BREAK_END")

    if break_minutes == 0 and shift and shift.break_minutes:
        break_minutes = shift.break_minutes

    worked_minutes = max(0, worked_minutes - break_minutes)
    return worked_minutes, anomalies


def rebuild_attendance_day(employee, attendance_date: date, tenant_db: str, policy: Optional[dict] = None) -> AttendanceDay:
    policy = policy or resolve_attendance_policy(employee, tenant_db)
    shift, _ = assign_attendance_date(employee, timezone.make_aware(datetime.combine(attendance_date, datetime.min.time())), tenant_db)
    events = list(
        AttendanceEvent.objects.using(tenant_db)
        .filter(employee=employee, attendance_date=attendance_date)
        .order_by("timestamp")
    )

    worked_minutes = 0
    anomalies = []
    first_in_at = None
    last_out_at = None

    if events:
        first_in_at = next((e.timestamp for e in events if e.event_type == AttendanceEvent.EVENT_IN), None)
        last_out_at = next((e.timestamp for e in reversed(events) if e.event_type == AttendanceEvent.EVENT_OUT), None)
        worked_minutes, anomalies = _compute_worked_minutes(events, shift)

    attendance_policy = policy.get("attendance_policy") or {}
    rounding = attendance_policy.get("rounding") or {}
    worked_minutes = apply_rounding(worked_minutes, rounding)

    late_minutes = 0
    early_leave_minutes = 0
    overtime_minutes = 0

    if shift and first_in_at:
        shift_start = _make_aware(attendance_date, shift.start_time)
        shift_end = _make_aware(attendance_date, shift.end_time)
        if shift.is_overnight:
            shift_end += timedelta(days=1)
        grace = shift.late_grace_minutes or int(attendance_policy.get("late_grace_minutes", 0) or 0)
        delta = first_in_at - (shift_start + timedelta(minutes=grace))
        late_minutes = max(0, int(delta.total_seconds() // 60))

    if shift and last_out_at:
        shift_start = _make_aware(attendance_date, shift.start_time)
        shift_end = _make_aware(attendance_date, shift.end_time)
        if shift.is_overnight:
            shift_end += timedelta(days=1)
        grace = shift.early_grace_minutes or int(attendance_policy.get("early_grace_minutes", 0) or 0)
        delta = (shift_end - timedelta(minutes=grace)) - last_out_at
        early_leave_minutes = max(0, int(delta.total_seconds() // 60))

        overtime_start_after = shift.overtime_starts_after_minutes or int(
            (policy.get("overtime_policy") or {}).get("starts_after_minutes", 0) or 0
        )
        overtime_delta = last_out_at - (shift_end + timedelta(minutes=overtime_start_after))
        overtime_minutes = max(0, int(overtime_delta.total_seconds() // 60))

    late_minutes = apply_rounding(late_minutes, rounding)
    early_leave_minutes = apply_rounding(early_leave_minutes, rounding)
    overtime_minutes = apply_rounding(overtime_minutes, rounding)

    on_leave = _has_approved_leave(employee, attendance_date, tenant_db)
    is_weekend = _is_weekend(attendance_date, policy)
    is_holiday = _is_holiday(attendance_date, policy)

    status = AttendanceDay.STATUS_ABSENT
    if events:
        if any(flag in anomalies for flag in ["MISSING_OUT", "MISSING_IN"]):
            status = AttendanceDay.STATUS_PARTIAL
        else:
            status = AttendanceDay.STATUS_PRESENT
        if on_leave:
            anomalies.append("WORKED_ON_LEAVE")
        if is_weekend:
            anomalies.append("WORKED_ON_WEEKEND")
        if is_holiday:
            anomalies.append("WORKED_ON_HOLIDAY")
    else:
        if on_leave:
            status = AttendanceDay.STATUS_ON_LEAVE
        elif is_holiday:
            status = AttendanceDay.STATUS_HOLIDAY
        elif is_weekend:
            status = AttendanceDay.STATUS_WEEKEND
        else:
            status = AttendanceDay.STATUS_ABSENT

    approved_minutes = (
        OvertimeRequest.objects.using(tenant_db)
        .filter(employee=employee, date=attendance_date, status=OvertimeRequest.STATUS_APPROVED)
        .values_list("minutes", flat=True)
    )
    approved_overtime_minutes = sum(approved_minutes) if approved_minutes else 0

    attendance_day, _ = AttendanceDay.objects.using(tenant_db).get_or_create(
        employee=employee,
        date=attendance_date,
        defaults={
            "employer_id": employee.employer_id,
            "expected_shift": shift,
        },
    )
    if attendance_day.locked_for_payroll:
        return attendance_day

    attendance_day.expected_shift = shift
    attendance_day.first_in_at = first_in_at
    attendance_day.last_out_at = last_out_at
    attendance_day.worked_minutes = worked_minutes
    attendance_day.late_minutes = late_minutes
    attendance_day.early_leave_minutes = early_leave_minutes
    attendance_day.overtime_minutes = overtime_minutes
    attendance_day.approved_overtime_minutes = approved_overtime_minutes
    attendance_day.status = status
    attendance_day.anomaly_flags = sorted(set(anomalies))
    attendance_day.save(using=tenant_db)
    return attendance_day


def apply_overtime_approval(employee, attendance_date: date, tenant_db: str) -> None:
    day = AttendanceDay.objects.using(tenant_db).filter(employee=employee, date=attendance_date).first()
    if not day:
        return
    approved_minutes = (
        OvertimeRequest.objects.using(tenant_db)
        .filter(employee=employee, date=attendance_date, status=OvertimeRequest.STATUS_APPROVED)
        .values_list("minutes", flat=True)
    )
    day.approved_overtime_minutes = sum(approved_minutes) if approved_minutes else 0
    day.save(using=tenant_db)
