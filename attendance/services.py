import math
from datetime import datetime, timedelta, time, tzinfo
from typing import Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from django.conf import settings
from django.db import connections, models
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from employees.models import Employee
from timeoff.models import TimeOffRequest

from .models import (
    AttendanceAllowedWifi,
    AttendanceConfiguration,
    AttendanceKioskStation,
    AttendanceLocationSite,
    AttendanceRecord,
    WorkingSchedule,
    WorkingScheduleDay,
)


def normalize_datetime(value: Optional[datetime]) -> datetime:
    """Ensure datetimes are timezone-aware using current timezone."""
    if value is None:
        return timezone.now()
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def append_anomaly_reason(existing: Optional[str], reason: Optional[str]) -> Optional[str]:
    if not reason:
        return existing
    if not existing:
        return reason
    if reason.lower() in existing.lower():
        return existing
    return f"{existing}; {reason}"


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two points in meters."""
    radius = 6371000  # meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def find_matching_site(
    employer_id: int,
    latitude: float,
    longitude: float,
    db_alias: str,
    branch_ids: Optional[list] = None,
) -> Optional[AttendanceLocationSite]:
    """Return the first active site that matches provided coordinates within radius (optionally branch-scoped)."""
    sites = AttendanceLocationSite.objects.using(db_alias).filter(employer_id=employer_id, is_active=True)
    if branch_ids:
        sites = sites.filter(models.Q(branch_id__in=branch_ids) | models.Q(branch__isnull=True))
    for site in sites:
        distance = haversine_distance_meters(float(latitude), float(longitude), float(site.latitude), float(site.longitude))
        if distance <= site.radius_meters:
            return site
    return None


def find_matching_wifi(
    employer_id: int,
    ssid: Optional[str],
    bssid: Optional[str],
    db_alias: str,
    site: Optional[AttendanceLocationSite] = None,
    branch_ids: Optional[list] = None,
) -> Optional[AttendanceAllowedWifi]:
    """Return matching Wi-Fi entry based on SSID/BSSID and optional site."""
    if not ssid:
        return None
    qs = AttendanceAllowedWifi.objects.using(db_alias).filter(
        employer_id=employer_id,
        is_active=True,
    )
    if branch_ids:
        qs = qs.filter(models.Q(branch_id__in=branch_ids) | models.Q(branch__isnull=True))
    if site:
        qs = qs.filter(models.Q(site=site) | models.Q(site__isnull=True))
    if bssid:
        match = qs.filter(bssid__iexact=bssid).first()
        if match:
            return match
    # Fallback to SSID match to allow multi-AP networks when BSSID differs.
    return qs.filter(ssid__iexact=ssid).first()


def ensure_attendance_configuration(employer_id: int, db_alias: str) -> AttendanceConfiguration:
    """Fetch or create an enabled configuration for the employer."""
    config, _ = AttendanceConfiguration.objects.using(db_alias).get_or_create(
        employer_id=employer_id,
        defaults={"timezone": getattr(settings, "TIME_ZONE", "UTC")},
    )
    return config


def _resolve_schedule_timezone(schedule: Optional[WorkingSchedule]):
    tz = timezone.get_current_timezone()
    if schedule and schedule.timezone and ZoneInfo:
        try:
            tz = ZoneInfo(schedule.timezone)
        except Exception:
            tz = timezone.get_current_timezone()
    return tz


def _resolve_payload_timezone(tz_name: Optional[str]) -> Optional[tzinfo]:
    if not tz_name or not ZoneInfo:
        return None
    try:
        return ZoneInfo(str(tz_name))
    except Exception:
        return None


def _normalize_timezone_name(tz: Optional[tzinfo]) -> Optional[str]:
    if not tz:
        return None
    key = getattr(tz, "key", None)
    return key or str(tz)


def _resolve_schedule_day_context(
    employee: Employee,
    when: datetime,
    db_alias: str,
    tz_override: Optional[tzinfo] = None,
):
    schedule_id = getattr(employee, "working_schedule_id", None)
    schedule = None
    if schedule_id:
        schedule = WorkingSchedule.objects.using(db_alias).filter(id=schedule_id).first()
    if not schedule:
        schedule = (
            WorkingSchedule.objects.using(db_alias)
            .filter(employer_id=employee.employer_id, is_default=True)
            .first()
        )
    if not schedule:
        tz = tz_override or timezone.get_current_timezone()
        local_when = timezone.localtime(normalize_datetime(when), tz)
        return None, None, tz, local_when, None, None

    tz = tz_override or _resolve_schedule_timezone(schedule)
    aware_when = normalize_datetime(when)
    local_when = timezone.localtime(aware_when, tz)
    day = WorkingScheduleDay.objects.using(db_alias).filter(schedule=schedule, weekday=local_when.weekday()).first()
    if not day:
        return schedule, None, tz, local_when, None, None

    start_dt = datetime.combine(local_when.date(), day.start_time)
    end_dt = datetime.combine(local_when.date(), day.end_time)
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt, tz)
    if timezone.is_naive(end_dt):
        end_dt = timezone.make_aware(end_dt, tz)
    return schedule, day, tz, local_when, start_dt, end_dt


def resolve_break_window(
    employee: Employee,
    when: datetime,
    db_alias: str,
    tz_override: Optional[tzinfo] = None,
) -> Tuple[Optional[datetime], Optional[datetime], tzinfo, datetime, Optional[WorkingScheduleDay]]:
    schedule, day_rule, tz, local_when, _start_dt, _end_dt = _resolve_schedule_day_context(
        employee,
        when,
        db_alias,
        tz_override=tz_override,
    )
    if not day_rule or not day_rule.break_start_time or not day_rule.break_end_time:
        return None, None, tz, local_when, day_rule
    break_start = datetime.combine(local_when.date(), day_rule.break_start_time)
    break_end = datetime.combine(local_when.date(), day_rule.break_end_time)
    if timezone.is_naive(break_start):
        break_start = timezone.make_aware(break_start, tz)
    if timezone.is_naive(break_end):
        break_end = timezone.make_aware(break_end, tz)
    return break_start, break_end, tz, local_when, day_rule


def flag_missing_checkout_if_needed(
    record: AttendanceRecord,
    config: AttendanceConfiguration,
    db_alias: str,
) -> bool:
    if not config or not config.auto_flag_anomalies or not getattr(config, "flag_missing_checkout", False):
        return False
    if record.check_out_at is not None:
        return False
    tz_override = _resolve_payload_timezone(getattr(record, "check_in_timezone", None))
    if not is_missing_checkout_after_cutoff(record, config, db_alias, tz_override=tz_override):
        return False

    penalty_mode = getattr(config, "missing_checkout_penalty_mode", "none")
    new_reason = append_anomaly_reason(record.anomaly_reason, "Missing checkout")
    if penalty_mode == "auto_refuse":
        new_status = AttendanceRecord.STATUS_REFUSED
    else:
        new_status = (
            record.status if record.status == AttendanceRecord.STATUS_REFUSED else AttendanceRecord.STATUS_TO_APPROVE
        )
    if new_reason != record.anomaly_reason or new_status != record.status:
        record.anomaly_reason = new_reason
        record.status = new_status
        record.save(using=db_alias, update_fields=["status", "anomaly_reason", "updated_at"])
    return True


def resolve_missing_checkout_deadline(
    record: AttendanceRecord,
    config: AttendanceConfiguration,
    db_alias: str,
    tz_override: Optional[tzinfo] = None,
) -> Tuple[datetime, tzinfo]:
    schedule, _day_rule, tz, local_check_in, _scheduled_start, scheduled_end = _resolve_schedule_day_context(
        record.employee,
        record.check_in_at,
        db_alias,
        tz_override=tz_override,
    )
    cutoff_minutes = max(int(getattr(config, "missing_checkout_cutoff_minutes", 0) or 0), 0)
    if scheduled_end:
        deadline = scheduled_end + timedelta(minutes=cutoff_minutes)
    else:
        next_day = local_check_in.date() + timedelta(days=1)
        deadline = datetime.combine(next_day, time(0, 0))
        if timezone.is_naive(deadline):
            deadline = timezone.make_aware(deadline, tz)
        deadline = deadline + timedelta(minutes=cutoff_minutes)
    return deadline, tz


def is_missing_checkout_after_cutoff(
    record: AttendanceRecord,
    config: AttendanceConfiguration,
    db_alias: str,
    now: Optional[datetime] = None,
    tz_override: Optional[tzinfo] = None,
) -> bool:
    if record.check_out_at is not None or not config:
        return False
    current_time = normalize_datetime(now) if now else timezone.now()
    deadline, tz = resolve_missing_checkout_deadline(record, config, db_alias, tz_override=tz_override)
    local_now = timezone.localtime(current_time, tz) if tz else current_time
    return local_now > deadline


def _apply_early_check_in_rule(local_check_in: datetime, scheduled_start: Optional[datetime], early_grace_minutes: int):
    if not scheduled_start or not local_check_in:
        return local_check_in
    if local_check_in >= scheduled_start:
        return local_check_in
    grace = max(int(early_grace_minutes or 0), 0)
    if grace <= 0:
        return scheduled_start
    allowed_start = scheduled_start - timedelta(minutes=grace)
    return max(local_check_in, allowed_start)


def _is_within_schedule_window(
    local_check_in: Optional[datetime],
    scheduled_start: Optional[datetime],
    scheduled_end: Optional[datetime],
    early_grace_minutes: int,
) -> bool:
    if not local_check_in or not scheduled_start or not scheduled_end:
        return False
    grace = max(int(early_grace_minutes or 0), 0)
    window_start = scheduled_start - timedelta(minutes=grace)
    return window_start <= local_check_in <= scheduled_end


def _format_shift_time(value: Optional[datetime]) -> str:
    if not value:
        return "--"
    return value.strftime("%I:%M %p").lstrip("0")


def _format_tz_label(tz: Optional[tzinfo]) -> str:
    if not tz:
        return ""
    key = getattr(tz, "key", None)
    return key or str(tz)


def _compute_worked_minutes(local_check_in: datetime, local_check_out: datetime, break_minutes: int) -> int:
    if not local_check_in or not local_check_out:
        return 0
    minutes = int((local_check_out - local_check_in).total_seconds() // 60)
    minutes = max(minutes - int(break_minutes or 0), 0)
    return max(minutes, 0)


def compute_worked_minutes_for_employee(
    employee: Employee,
    check_in_at: datetime,
    check_out_at: datetime,
    config: AttendanceConfiguration,
    db_alias: str,
    tz_override: Optional[tzinfo] = None,
) -> int:
    _schedule, day_rule, tz, local_check_in, scheduled_start, _scheduled_end = _resolve_schedule_day_context(
        employee,
        check_in_at,
        db_alias,
        tz_override=tz_override,
    )
    local_check_out = timezone.localtime(normalize_datetime(check_out_at), tz) if tz else check_out_at
    effective_check_in = _apply_early_check_in_rule(
        local_check_in,
        scheduled_start,
        getattr(config, "early_check_in_grace_minutes", 0),
    )
    break_minutes = int(getattr(day_rule, "break_minutes", 0) or 0) if day_rule else 0
    return _compute_worked_minutes(effective_check_in, local_check_out, break_minutes)


def resolve_expected_minutes(
    employee: Employee,
    check_in_at: datetime,
    db_alias: str,
    tz_override: Optional[tzinfo] = None,
) -> Optional[int]:
    """Compute expected minutes for the given employee/date using working schedule."""
    schedule, day_rule, _tz, _local_when, _start, _end = _resolve_schedule_day_context(
        employee,
        check_in_at,
        db_alias,
        tz_override=tz_override,
    )
    if day_rule:
        return day_rule.expected_minutes
    if schedule:
        return schedule.default_daily_minutes
    return None


def resolve_check_in_timing(
    employee: Employee,
    check_in_at: datetime,
    config: AttendanceConfiguration,
    db_alias: str,
    tz_override: Optional[tzinfo] = None,
):
    """
    Resolve how early/late a check-in is relative to the scheduled start.
    Returns None if no schedule/day rule is found.
    """
    _schedule, day_rule, tz, local_check_in, scheduled_start, _scheduled_end = _resolve_schedule_day_context(
        employee,
        check_in_at,
        db_alias,
        tz_override=tz_override,
    )
    if not day_rule or not scheduled_start or not local_check_in:
        return None

    delta_seconds = (local_check_in - scheduled_start).total_seconds()
    early_minutes = 0
    late_minutes = 0
    if delta_seconds < 0:
        early_minutes = int(abs(delta_seconds) // 60)
    elif delta_seconds > 0:
        late_minutes = int(delta_seconds // 60)

    early_grace = max(int(getattr(config, "early_check_in_grace_minutes", 0) or 0), 0) if config else 0
    late_grace = max(int(getattr(config, "late_check_in_grace_minutes", 0) or 0), 0) if config else 0

    return {
        "tz": tz,
        "local_check_in": local_check_in,
        "scheduled_start": scheduled_start,
        "delta_seconds": delta_seconds,
        "early_minutes": early_minutes,
        "late_minutes": late_minutes,
        "early_grace_minutes": early_grace,
        "late_grace_minutes": late_grace,
    }


def is_employee_on_leave(employee: Employee, when: datetime, db_alias: str) -> bool:
    """Return True if the employee has a SUBMITTED/PENDING/APPROVED leave covering the given datetime."""
    if when is None:
        when = timezone.now()
    return (
        TimeOffRequest.objects.using(db_alias)
        .filter(
            employee=employee,
            status__in=["SUBMITTED", "PENDING", "APPROVED"],
            start_at__lte=when,
            end_at__gte=when,
        )
        .exists()
    )


def _should_enforce_geofence(config: AttendanceConfiguration, mode: str) -> bool:
    if mode == AttendanceRecord.MODE_KIOSK and config.kiosk_bypass_geofence:
        return False
    return config.enforce_geofence


def _should_enforce_wifi(config: AttendanceConfiguration, mode: str, is_checkout: bool) -> bool:
    if mode == AttendanceRecord.MODE_KIOSK and config.kiosk_bypass_wifi:
        return False
    if is_checkout:
        return config.enforce_wifi_on_checkout
    return config.enforce_wifi


def perform_check_in(
    employee: Employee,
    payload: dict,
    config: AttendanceConfiguration,
    db_alias: str,
    mode: str,
    created_by: Optional[int] = None,
) -> AttendanceRecord:
    """Validate and create an attendance record for check-in."""
    if not config.is_enabled:
        raise ValidationError({"detail": "Attendance module is disabled for this employer."})
    if not employee.is_active:
        raise ValidationError({"employee_id": "Employee is not active."})

    open_record = AttendanceRecord.objects.using(db_alias).filter(employee=employee, check_out_at__isnull=True).first()
    if open_record:
        flag_missing_checkout_if_needed(open_record, config, db_alias)
        raise ValidationError({"detail": "An open attendance record already exists for this employee."})

    check_in_at = normalize_datetime(payload.get("device_time"))
    if is_employee_on_leave(employee, check_in_at, db_alias):
        raise ValidationError({"detail": "Employee is on approved leave during this time."})

    enforce_geo = _should_enforce_geofence(config, mode)
    enforce_wifi = _should_enforce_wifi(config, mode, is_checkout=False)

    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    wifi_ssid = payload.get("wifi_ssid")
    wifi_bssid = payload.get("wifi_bssid")
    branch_ids = [str(branch_id) for branch_id in employee.assigned_branch_ids]
    site_match = None

    if enforce_geo:
        if latitude is None or longitude is None:
            raise ValidationError({"detail": "You are not within the allowed company area"})
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_ids)
        if not site_match:
            raise ValidationError({"detail": "You are not within the allowed company area"})
    elif latitude is not None and longitude is not None:
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_ids)

    wifi_match = None
    if enforce_wifi:
        if not wifi_ssid:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking in"})
        wifi_match = find_matching_wifi(employee.employer_id, wifi_ssid, wifi_bssid, db_alias, site_match, branch_ids)
        if not wifi_match:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking in"})

    status = AttendanceRecord.STATUS_APPROVED
    anomaly_reason = None
    payload_tz = payload.get("timezone")
    tz_override = _resolve_payload_timezone(payload_tz)
    _schedule, day_rule, tz, local_check_in, scheduled_start, _scheduled_end = _resolve_schedule_day_context(
        employee,
        check_in_at,
        db_alias,
        tz_override=tz_override,
    )
    if getattr(config, "enforce_schedule_check_in", False):
        if not day_rule or not scheduled_start or not _scheduled_end:
            raise ValidationError(
                {"detail": "You cannot check in today because no shift is scheduled for you. Please contact HR."}
            )
        if not _is_within_schedule_window(
            local_check_in,
            scheduled_start,
            _scheduled_end,
            getattr(config, "early_check_in_grace_minutes", 0),
        ):
            start_label = _format_shift_time(scheduled_start)
            end_label = _format_shift_time(_scheduled_end)
            tz_label = _format_tz_label(tz)
            tz_suffix = f" ({tz_label})" if tz_label else ""
            raise ValidationError(
                {
                    "detail": (
                        "You cannot check in now because your shift is not active. "
                        f"Shift time: {start_label} - {end_label}{tz_suffix}."
                    )
                }
            )
    if day_rule and scheduled_start and config.auto_flag_anomalies:
        late_grace = max(int(getattr(config, "late_check_in_grace_minutes", 0) or 0), 0)
        late_threshold = scheduled_start + timedelta(minutes=late_grace)
        if local_check_in and local_check_in > late_threshold:
            status = AttendanceRecord.STATUS_TO_APPROVE
            minutes_late = int((local_check_in - scheduled_start).total_seconds() // 60)
            anomaly_reason = f"Late check-in ({max(minutes_late, 0)} min)"

    if config.auto_flag_anomalies and getattr(config, "flag_overlaps", False):
        overlap_exists = (
            AttendanceRecord.objects.using(db_alias)
            .filter(employee=employee, check_out_at__isnull=False)
            .filter(check_in_at__lte=check_in_at, check_out_at__gt=check_in_at)
            .exists()
        )
        if overlap_exists:
            status = AttendanceRecord.STATUS_TO_APPROVE
            anomaly_reason = append_anomaly_reason(anomaly_reason, "Overlapping record")

    record = AttendanceRecord.objects.using(db_alias).create(
        employer_id=employee.employer_id,
        employee=employee,
        check_in_at=check_in_at,
        check_in_timezone=_normalize_timezone_name(tz_override) if tz_override else None,
        mode=mode,
        check_in_latitude=latitude,
        check_in_longitude=longitude,
        check_in_site=site_match,
        check_in_wifi_ssid=wifi_ssid,
        check_in_wifi_bssid=wifi_bssid,
        check_in_ip=payload.get("ip_address"),
        created_by_id=created_by,
        status=status,
        anomaly_reason=anomaly_reason,
    )
    if enforce_wifi and wifi_match:
        record.check_in_wifi_ssid = wifi_match.ssid
        record.check_in_wifi_bssid = wifi_match.bssid
        record.save(using=db_alias, update_fields=["check_in_wifi_ssid", "check_in_wifi_bssid"])
    return record


def perform_check_out(
    employee: Employee,
    payload: dict,
    config: AttendanceConfiguration,
    db_alias: str,
    mode: str,
) -> AttendanceRecord:
    """Validate and complete an attendance record for check-out."""
    if not config.is_enabled:
        raise ValidationError({"detail": "Attendance module is disabled for this employer."})
    record = (
        AttendanceRecord.objects.using(db_alias)
        .filter(employee=employee, check_out_at__isnull=True)
        .order_by("-check_in_at")
        .first()
    )
    if not record:
        raise ValidationError({"detail": "No open attendance record found."})

    enforce_geo = config.enforce_geofence_on_checkout and _should_enforce_geofence(config, mode)
    enforce_wifi = _should_enforce_wifi(config, mode, is_checkout=True)

    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    wifi_ssid = payload.get("wifi_ssid")
    wifi_bssid = payload.get("wifi_bssid")
    branch_ids = [str(branch_id) for branch_id in employee.assigned_branch_ids]

    site_match = None
    if enforce_geo:
        if latitude is None or longitude is None:
            raise ValidationError({"detail": "You are not within the allowed company area"})
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_ids)
        if not site_match:
            raise ValidationError({"detail": "You are not within the allowed company area"})
    elif latitude is not None and longitude is not None:
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_ids)

    wifi_match = None
    if enforce_wifi:
        if not wifi_ssid:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking out"})
        wifi_match = find_matching_wifi(employee.employer_id, wifi_ssid, wifi_bssid, db_alias, site_match, branch_ids)
        if not wifi_match:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking out"})

    record.check_out_latitude = latitude
    record.check_out_longitude = longitude
    record.check_out_site = site_match
    record.check_out_wifi_ssid = wifi_ssid
    record.check_out_wifi_bssid = wifi_bssid
    record.check_out_ip = payload.get("ip_address")
    checkout_time = normalize_datetime(payload.get("device_time"))
    payload_tz = payload.get("timezone")
    tz_override = _resolve_payload_timezone(payload_tz) or _resolve_payload_timezone(record.check_in_timezone)
    record.expected_minutes = resolve_expected_minutes(
        employee,
        record.check_in_at,
        db_alias,
        tz_override=tz_override,
    )

    _schedule, day_rule, tz, local_check_in, scheduled_start, _scheduled_end = _resolve_schedule_day_context(
        employee,
        record.check_in_at,
        db_alias,
        tz_override=tz_override,
    )
    local_check_out = timezone.localtime(checkout_time, tz) if tz else checkout_time
    effective_check_in = _apply_early_check_in_rule(
        local_check_in,
        scheduled_start,
        getattr(config, "early_check_in_grace_minutes", 0),
    )
    break_minutes = int(getattr(day_rule, "break_minutes", 0) or 0) if day_rule else 0
    worked_minutes = _compute_worked_minutes(effective_check_in, local_check_out, break_minutes)

    record.check_out_at = checkout_time
    record.check_out_timezone = _normalize_timezone_name(tz_override) if tz_override else None
    record.worked_minutes = worked_minutes
    if record.expected_minutes:
        record.overtime_worked_minutes = max(worked_minutes - int(record.expected_minutes), 0)
    else:
        record.overtime_worked_minutes = 0

    # Auto-flag anomalies
    if config.auto_flag_anomalies and config.max_daily_work_minutes_before_flag:
        if record.worked_minutes > config.max_daily_work_minutes_before_flag:
            record.status = AttendanceRecord.STATUS_TO_APPROVE
            record.anomaly_reason = append_anomaly_reason(record.anomaly_reason, "Excessive hours")

    if config.auto_flag_anomalies and getattr(config, "flag_overlaps", False):
        overlap_exists = (
            AttendanceRecord.objects.using(db_alias)
            .filter(employee=employee)
            .exclude(id=record.id)
            .filter(check_out_at__isnull=False)
            .filter(check_out_at__gt=record.check_in_at, check_in_at__lt=record.check_out_at)
            .exists()
        )
        if overlap_exists:
            if record.status != AttendanceRecord.STATUS_REFUSED:
                record.status = AttendanceRecord.STATUS_TO_APPROVE
            record.anomaly_reason = append_anomaly_reason(record.anomaly_reason, "Overlapping record")
    record.save(using=db_alias)
    return record


def resolve_configuration_by_kiosk_token(token: str) -> Tuple[Optional[AttendanceConfiguration], Optional[str]]:
    """Find configuration by kiosk token across tenant databases."""
    aliases = [alias for alias in settings.DATABASES.keys() if alias.startswith("tenant_")]
    if "default" in settings.DATABASES:
        aliases.append("default")
    for alias in aliases:
        try:
            if "attendance_configurations" not in connections[alias].introspection.table_names():
                continue
            config = AttendanceConfiguration.objects.using(alias).filter(kiosk_access_token=token, is_enabled=True).first()
            if config:
                return config, alias
        except Exception:
            continue
    return None, None


def resolve_station_by_token(token: str) -> Tuple[Optional[AttendanceKioskStation], Optional[str]]:
    """Find kiosk station by token across tenant databases."""
    aliases = [alias for alias in settings.DATABASES.keys() if alias.startswith("tenant_")]
    if "default" in settings.DATABASES:
        aliases.append("default")
    for alias in aliases:
        try:
            if "attendance_kiosk_stations" not in connections[alias].introspection.table_names():
                continue
            station = AttendanceKioskStation.objects.using(alias).filter(kiosk_token=token, is_active=True).first()
            if station:
                return station, alias
        except Exception:
            continue
    return None, None

