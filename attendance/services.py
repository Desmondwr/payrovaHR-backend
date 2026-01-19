import math
from datetime import datetime
from typing import Optional, Tuple

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
    branch_id: Optional[str] = None,
) -> Optional[AttendanceLocationSite]:
    """Return the first active site that matches provided coordinates within radius (optionally branch-scoped)."""
    sites = AttendanceLocationSite.objects.using(db_alias).filter(employer_id=employer_id, is_active=True)
    if branch_id:
        sites = sites.filter(models.Q(branch_id=branch_id) | models.Q(branch__isnull=True))
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
    branch_id: Optional[str] = None,
) -> Optional[AttendanceAllowedWifi]:
    """Return matching Wi-Fi entry based on SSID/BSSID and optional site."""
    if not ssid:
        return None
    qs = AttendanceAllowedWifi.objects.using(db_alias).filter(
        employer_id=employer_id,
        is_active=True,
    )
    if branch_id:
        qs = qs.filter(models.Q(branch_id=branch_id) | models.Q(branch__isnull=True))
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


def resolve_expected_minutes(employee: Employee, check_in_at: datetime, db_alias: str) -> Optional[int]:
    """Compute expected minutes for the given employee/date using working schedule."""
    schedule_id = getattr(employee, "working_schedule_id", None)
    if not schedule_id:
        return None
    schedule = WorkingSchedule.objects.using(db_alias).filter(id=schedule_id).first()
    if not schedule:
        return None
    weekday = check_in_at.weekday()
    day = WorkingScheduleDay.objects.using(db_alias).filter(schedule=schedule, weekday=weekday).first()
    if day:
        return day.expected_minutes
    return schedule.default_daily_minutes


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
    branch_id = getattr(employee, "branch_id", None)
    site_match = None

    if enforce_geo:
        if latitude is None or longitude is None:
            raise ValidationError({"detail": "You are not within the allowed company area"})
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_id)
        if not site_match:
            raise ValidationError({"detail": "You are not within the allowed company area"})
    elif latitude is not None and longitude is not None:
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_id)

    wifi_match = None
    if enforce_wifi:
        if not wifi_ssid:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking in"})
        wifi_match = find_matching_wifi(employee.employer_id, wifi_ssid, wifi_bssid, db_alias, site_match, branch_id)
        if not wifi_match:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking in"})

    record = AttendanceRecord.objects.using(db_alias).create(
        employer_id=employee.employer_id,
        employee=employee,
        check_in_at=check_in_at,
        mode=mode,
        check_in_latitude=latitude,
        check_in_longitude=longitude,
        check_in_site=site_match,
        check_in_wifi_ssid=wifi_ssid,
        check_in_wifi_bssid=wifi_bssid,
        check_in_ip=payload.get("ip_address"),
        created_by_id=created_by,
        status=AttendanceRecord.STATUS_APPROVED,
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
    branch_id = getattr(employee, "branch_id", None)

    site_match = None
    if enforce_geo:
        if latitude is None or longitude is None:
            raise ValidationError({"detail": "You are not within the allowed company area"})
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_id)
        if not site_match:
            raise ValidationError({"detail": "You are not within the allowed company area"})
    elif latitude is not None and longitude is not None:
        site_match = find_matching_site(employee.employer_id, float(latitude), float(longitude), db_alias, branch_id)

    wifi_match = None
    if enforce_wifi:
        if not wifi_ssid:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking out"})
        wifi_match = find_matching_wifi(employee.employer_id, wifi_ssid, wifi_bssid, db_alias, site_match, branch_id)
        if not wifi_match:
            raise ValidationError({"detail": "Connect to company Wi-Fi before checking out"})

    record.check_out_latitude = latitude
    record.check_out_longitude = longitude
    record.check_out_site = site_match
    record.check_out_wifi_ssid = wifi_ssid
    record.check_out_wifi_bssid = wifi_bssid
    record.check_out_ip = payload.get("ip_address")
    record.expected_minutes = resolve_expected_minutes(employee, record.check_in_at, db_alias)
    record.mark_checkout(normalize_datetime(payload.get("device_time")))

    # Auto-flag anomalies
    if config.auto_flag_anomalies and config.max_daily_work_minutes_before_flag:
        if record.worked_minutes > config.max_daily_work_minutes_before_flag:
            record.status = AttendanceRecord.STATUS_TO_APPROVE
            record.anomaly_reason = "Excessive hours"
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
