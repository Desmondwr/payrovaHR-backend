from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - zoneinfo is stdlib on supported Python versions
    ZoneInfo = None

from django.utils import timezone
from rest_framework import serializers

from accounts.rbac import get_active_employer, is_delegate_user

from employees.models import Branch
from .models import (
    AttendanceAllowedWifi,
    AttendanceConfiguration,
    AttendanceKioskStation,
    AttendanceLocationSite,
    AttendanceRecord,
    WorkingSchedule,
    WorkingScheduleDay,
)


class AttendanceConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceConfiguration
        fields = "__all__"
        read_only_fields = ["id", "employer_id", "created_at", "updated_at", "kiosk_access_token"]


class AttendanceLocationSiteSerializer(serializers.ModelSerializer):
    branch = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=Branch.objects.none())
    branch_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AttendanceLocationSite
        fields = [
            "id",
            "employer_id",
            "branch",
            "branch_name",
            "name",
            "address",
            "latitude",
            "longitude",
            "radius_meters",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            from accounts.database_utils import get_tenant_database_alias

            employer = None
            if getattr(request.user, "employer_profile", None):
                employer = request.user.employer_profile
            else:
                resolved = get_active_employer(request, require_context=False)
                if resolved and is_delegate_user(request.user, resolved.id):
                    employer = resolved

            if employer:
                tenant_db = get_tenant_database_alias(employer)
                self.fields["branch"].queryset = Branch.objects.using(tenant_db).filter(
                    employer_id=employer.id
                )

    def validate_branch(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if not request:
            return value

        employer = None
        if getattr(request.user, "employer_profile", None):
            employer = request.user.employer_profile
        else:
            resolved = get_active_employer(request, require_context=False)
            if resolved and is_delegate_user(request.user, resolved.id):
                employer = resolved
        if not employer:
            return value
        if value.employer_id != employer.id:
            raise serializers.ValidationError("Branch not found for this employer.")
        return value

    def get_branch_name(self, obj):
        return getattr(obj.branch, "name", None)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Default to the single branch if only one exists for the employer
        if not attrs.get("branch"):
            request = self.context.get("request")
            if request:
                qs = self.fields["branch"].queryset
                if qs is not None and qs.count() == 1:
                    attrs["branch"] = qs.first()
        return attrs


class AttendanceAllowedWifiSerializer(serializers.ModelSerializer):
    branch = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=Branch.objects.none())
    branch_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AttendanceAllowedWifi
        fields = [
            "id",
            "employer_id",
            "branch",
            "branch_name",
            "site",
            "ssid",
            "bssid",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            from accounts.database_utils import get_tenant_database_alias

            employer = None
            if getattr(request.user, "employer_profile", None):
                employer = request.user.employer_profile
            else:
                resolved = get_active_employer(request, require_context=False)
                if resolved and is_delegate_user(request.user, resolved.id):
                    employer = resolved
            if employer:
                tenant_db = get_tenant_database_alias(employer)
                self.fields["branch"].queryset = Branch.objects.using(tenant_db).filter(
                    employer_id=employer.id
                )

    def validate_branch(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if not request:
            return value
        employer = None
        if getattr(request.user, "employer_profile", None):
            employer = request.user.employer_profile
        else:
            resolved = get_active_employer(request, require_context=False)
            if resolved and is_delegate_user(request.user, resolved.id):
                employer = resolved
        if not employer:
            return value
        if value.employer_id != employer.id:
            raise serializers.ValidationError("Branch not found for this employer.")
        return value

    def get_branch_name(self, obj):
        return getattr(obj.branch, "name", None)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        site = attrs.get("site")
        branch = attrs.get("branch")
        if site and branch and site.branch_id and site.branch_id != branch.id:
            raise serializers.ValidationError({"branch": "Wi-Fi branch must match the site branch."})
        if site and site.branch_id and branch is None:
            attrs["branch"] = site.branch
            branch = site.branch
        # Default to the single branch if none provided and no site branch
        if branch is None:
            request = self.context.get("request")
            if request:
                qs = self.fields["branch"].queryset
                if qs is not None and qs.count() == 1:
                    attrs["branch"] = qs.first()
        return attrs


class AttendanceKioskStationSerializer(serializers.ModelSerializer):
    branch = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=Branch.objects.none())
    branch_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AttendanceKioskStation
        fields = [
            "id",
            "employer_id",
            "name",
            "branch",
            "branch_name",
            "kiosk_token",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "kiosk_token", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            from accounts.database_utils import get_tenant_database_alias

            employer = None
            if getattr(request.user, "employer_profile", None):
                employer = request.user.employer_profile
            else:
                resolved = get_active_employer(request, require_context=False)
                if resolved and is_delegate_user(request.user, resolved.id):
                    employer = resolved
            if employer:
                tenant_db = get_tenant_database_alias(employer)
                self.fields["branch"].queryset = Branch.objects.using(tenant_db).filter(
                    employer_id=employer.id
                )

    def validate_branch(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if not request:
            return value
        employer = None
        if getattr(request.user, "employer_profile", None):
            employer = request.user.employer_profile
        else:
            resolved = get_active_employer(request, require_context=False)
            if resolved and is_delegate_user(request.user, resolved.id):
                employer = resolved
        if not employer:
            return value
        if value.employer_id != employer.id:
            raise serializers.ValidationError("Branch not found for this employer.")
        return value

    def get_branch_name(self, obj):
        return getattr(obj.branch, "name", None)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("branch"):
            request = self.context.get("request")
            if request:
                qs = self.fields["branch"].queryset
                if qs is not None and qs.count() == 1:
                    attrs["branch"] = qs.first()
        return attrs


class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_full_name = serializers.CharField(source="employee.full_name", read_only=True)
    status = serializers.SerializerMethodField()
    raw_status = serializers.CharField(source="status", read_only=True)
    overtime_status = serializers.SerializerMethodField()
    late_status = serializers.SerializerMethodField()
    is_editable = serializers.SerializerMethodField()
    break_start_time = serializers.SerializerMethodField()
    break_end_time = serializers.SerializerMethodField()
    break_minutes = serializers.SerializerMethodField()
    schedule_start_time = serializers.SerializerMethodField()
    schedule_end_time = serializers.SerializerMethodField()
    schedule_expected_minutes = serializers.SerializerMethodField()
    schedule_start_at = serializers.SerializerMethodField()
    schedule_end_at = serializers.SerializerMethodField()
    schedule_timezone = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "employer_id",
            "employee",
            "employee_full_name",
            "check_in_at",
            "check_in_timezone",
            "check_out_at",
            "check_out_timezone",
            "break_start_time",
            "break_end_time",
            "break_minutes",
            "schedule_start_time",
            "schedule_end_time",
            "schedule_expected_minutes",
            "schedule_start_at",
            "schedule_end_at",
            "schedule_timezone",
            "worked_minutes",
            "expected_minutes",
            "overtime_worked_minutes",
            "overtime_approved_minutes",
            "status",
            "raw_status",
            "overtime_status",
            "late_status",
            "is_editable",
            "mode",
            "check_in_ip",
            "check_in_latitude",
            "check_in_longitude",
            "check_in_site",
            "check_in_wifi_ssid",
            "check_in_wifi_bssid",
            "check_out_ip",
            "check_out_latitude",
            "check_out_longitude",
            "check_out_site",
            "check_out_wifi_ssid",
            "check_out_wifi_bssid",
            "anomaly_reason",
            "created_by_id",
            "kiosk_session_reference",
            "kiosk_station",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "employer_id",
            "check_in_timezone",
            "check_out_timezone",
            "break_start_time",
            "break_end_time",
            "break_minutes",
            "schedule_start_time",
            "schedule_end_time",
            "schedule_expected_minutes",
            "schedule_start_at",
            "schedule_end_at",
            "schedule_timezone",
            "worked_minutes",
            "expected_minutes",
            "overtime_worked_minutes",
            "status",
            "anomaly_reason",
            "created_at",
            "updated_at",
        ]

    def get_status(self, obj):
        if obj.status == AttendanceRecord.STATUS_APPROVED:
            return "approved"
        if obj.status == AttendanceRecord.STATUS_REFUSED:
            return "rejected"
        return "pending"

    def get_overtime_status(self, obj):
        overtime_worked = obj.overtime_worked_minutes or 0
        if overtime_worked <= 0:
            return "none"
        if obj.status == AttendanceRecord.STATUS_REFUSED:
            return "rejected"
        if (obj.overtime_approved_minutes or 0) > 0:
            return "approved"
        return "pending"

    def get_is_editable(self, obj):
        return self.get_status(obj) != "approved"

    def _get_schedule_cache(self):
        return self.context.setdefault("attendance_schedule_cache", {})

    def _get_schedule_day_cache(self):
        return self.context.setdefault("attendance_schedule_day_cache", {})

    def _get_config_cache(self):
        return self.context.setdefault("attendance_config_cache", {})

    def _resolve_schedule(self, db_alias, schedule_id):
        cache = self._get_schedule_cache()
        key = (db_alias, str(schedule_id))
        if key not in cache:
            cache[key] = WorkingSchedule.objects.using(db_alias).filter(id=schedule_id).first()
        return cache[key]

    def _resolve_default_schedule(self, db_alias, employer_id):
        cache = self._get_schedule_cache()
        key = (db_alias, f"default:{employer_id}")
        if key not in cache:
            cache[key] = (
                WorkingSchedule.objects.using(db_alias)
                .filter(employer_id=employer_id, is_default=True)
                .first()
            )
        return cache[key]

    def _resolve_schedule_day(self, db_alias, schedule_id, weekday):
        cache = self._get_schedule_day_cache()
        key = (db_alias, str(schedule_id), weekday)
        if key not in cache:
            cache[key] = (
                WorkingScheduleDay.objects.using(db_alias)
                .filter(schedule_id=schedule_id, weekday=weekday)
                .first()
            )
        return cache[key]

    def _resolve_config(self, db_alias, employer_id):
        cache = self._get_config_cache()
        key = (db_alias, int(employer_id))
        if key not in cache:
            cache[key] = (
                AttendanceConfiguration.objects.using(db_alias)
                .filter(employer_id=employer_id, is_enabled=True)
                .first()
            )
        return cache[key]

    def _resolve_timezone(self, schedule):
        tz = timezone.get_current_timezone()
        if schedule and schedule.timezone and ZoneInfo:
            try:
                tz = ZoneInfo(schedule.timezone)
            except Exception:
                tz = timezone.get_current_timezone()
        return tz

    def _resolve_schedule_day_for_record(self, obj):
        employee = getattr(obj, "employee", None)
        schedule_id = getattr(employee, "working_schedule_id", None) if employee else None
        if not schedule_id or not obj.check_in_at:
            if not employee or not obj.check_in_at:
                return None, None

        db_alias = obj._state.db or "default"
        schedule = None
        if schedule_id:
            schedule = self._resolve_schedule(db_alias, schedule_id)
        if not schedule and employee:
            schedule = self._resolve_default_schedule(db_alias, employee.employer_id)
        if not schedule:
            return None, None
        if not schedule_id:
            schedule_id = schedule.id

        tz = self._resolve_timezone(schedule)
        tz_override = getattr(obj, "check_in_timezone", None)
        if tz_override and ZoneInfo:
            try:
                tz = ZoneInfo(tz_override)
            except Exception:
                tz = tz
        check_in_at = obj.check_in_at
        if timezone.is_naive(check_in_at):
            check_in_at = timezone.make_aware(check_in_at, tz)
        else:
            check_in_at = timezone.localtime(check_in_at, tz)

        weekday = check_in_at.weekday()
        day = self._resolve_schedule_day(db_alias, schedule_id, weekday)
        return day, tz

    def _resolve_local_check_in(self, obj, tz):
        check_in_at = obj.check_in_at
        if timezone.is_naive(check_in_at):
            return timezone.make_aware(check_in_at, tz)
        return timezone.localtime(check_in_at, tz)

    def _resolve_schedule_datetimes_for_record(self, obj):
        day, tz = self._resolve_schedule_day_for_record(obj)
        if not day or not tz or not obj.check_in_at:
            return None, None, tz
        local_check_in = self._resolve_local_check_in(obj, tz)
        start_dt = None
        end_dt = None
        if day.start_time:
            start_dt = datetime.combine(local_check_in.date(), day.start_time)
            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(start_dt, tz)
        if day.end_time:
            end_dt = datetime.combine(local_check_in.date(), day.end_time)
            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(end_dt, tz)
        return start_dt, end_dt, tz

    def get_break_start_time(self, obj):
        day, _tz = self._resolve_schedule_day_for_record(obj)
        if not day or not day.break_start_time:
            return None
        return day.break_start_time.strftime("%H:%M:%S")

    def get_break_end_time(self, obj):
        day, _tz = self._resolve_schedule_day_for_record(obj)
        if not day or not day.break_end_time:
            return None
        return day.break_end_time.strftime("%H:%M:%S")

    def get_break_minutes(self, obj):
        day, _tz = self._resolve_schedule_day_for_record(obj)
        if not day:
            return 0
        return int(day.break_minutes or 0)

    def get_schedule_start_time(self, obj):
        day, _tz = self._resolve_schedule_day_for_record(obj)
        if not day or not day.start_time:
            return None
        return day.start_time.strftime("%H:%M:%S")

    def get_schedule_end_time(self, obj):
        day, _tz = self._resolve_schedule_day_for_record(obj)
        if not day or not day.end_time:
            return None
        return day.end_time.strftime("%H:%M:%S")

    def get_schedule_expected_minutes(self, obj):
        day, _tz = self._resolve_schedule_day_for_record(obj)
        if not day:
            return None
        return int(day.expected_minutes or 0)

    def get_schedule_start_at(self, obj):
        start_dt, _end_dt, _tz = self._resolve_schedule_datetimes_for_record(obj)
        return start_dt.isoformat() if start_dt else None

    def get_schedule_end_at(self, obj):
        _start_dt, end_dt, _tz = self._resolve_schedule_datetimes_for_record(obj)
        return end_dt.isoformat() if end_dt else None

    def get_schedule_timezone(self, obj):
        _day, tz = self._resolve_schedule_day_for_record(obj)
        if not tz:
            return None
        return getattr(tz, "key", None) or str(tz)

    def get_late_status(self, obj):
        employee = getattr(obj, "employee", None)
        schedule_id = getattr(employee, "working_schedule_id", None) if employee else None
        if not schedule_id or not obj.check_in_at:
            if not employee or not obj.check_in_at:
                return False

        db_alias = obj._state.db or "default"
        schedule = None
        if schedule_id:
            schedule = self._resolve_schedule(db_alias, schedule_id)
        if not schedule and employee:
            schedule = self._resolve_default_schedule(db_alias, employee.employer_id)
        if not schedule:
            return False

        tz = self._resolve_timezone(schedule)
        check_in_at = obj.check_in_at
        if timezone.is_naive(check_in_at):
            check_in_at = timezone.make_aware(check_in_at, tz)
        else:
            check_in_at = timezone.localtime(check_in_at, tz)

        weekday = check_in_at.weekday()
        day = self._resolve_schedule_day(db_alias, schedule_id, weekday)
        if not day or not day.start_time:
            return False

        scheduled_start = datetime.combine(check_in_at.date(), day.start_time)
        if timezone.is_naive(scheduled_start):
            scheduled_start = timezone.make_aware(scheduled_start, tz)
        config = self._resolve_config(db_alias, obj.employer_id)
        late_grace = 0
        if config:
            late_grace = int(getattr(config, "late_check_in_grace_minutes", 0) or 0)
        late_threshold = scheduled_start + timedelta(minutes=max(late_grace, 0))
        return check_in_at > late_threshold


class AttendanceCheckInSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField(required=False)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    wifi_ssid = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    wifi_bssid = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    device_time = serializers.DateTimeField(required=False)
    timezone = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AttendanceCheckOutSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField(required=False)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    wifi_ssid = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    wifi_bssid = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    device_time = serializers.DateTimeField(required=False)
    timezone = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AttendanceManualCreateSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField()
    check_in_at = serializers.DateTimeField()
    check_out_at = serializers.DateTimeField()
    overtime_approved_minutes = serializers.IntegerField(required=False, min_value=0, default=0)

    def validate(self, attrs):
        if attrs["check_out_at"] <= attrs["check_in_at"]:
            raise serializers.ValidationError({"check_out_at": "check_out_at must be after check_in_at"})
        return attrs


class KioskCheckSerializer(serializers.Serializer):
    employee_identifier = serializers.CharField()
    pin = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    kiosk_token = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    wifi_ssid = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    wifi_bssid = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PartialApproveSerializer(serializers.Serializer):
    overtime_approved_minutes = serializers.IntegerField(min_value=0)


class AttendanceReportQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    employee_id = serializers.UUIDField(required=False)
    department_id = serializers.UUIDField(required=False)
    group_by = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    measures = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
        required=False,
    )

    def validate(self, attrs):
        if attrs.get("date_from") and attrs.get("date_to") and attrs["date_to"] < attrs["date_from"]:
            raise serializers.ValidationError({"date_to": "date_to must be on/after date_from"})

        group_raw = attrs.get("group_by")
        if group_raw is None or group_raw == "":
            attrs["group_by"] = []
        else:
            parts = [p.strip() for p in str(group_raw).split(",") if p.strip()]
            allowed = {"month", "employee", "department"}
            invalid = [p for p in parts if p not in allowed]
            if invalid:
                raise serializers.ValidationError({"group_by": f"Invalid group(s): {', '.join(invalid)}"})
            attrs["group_by"] = parts

        measures_raw = attrs.get("measures")
        allowed_measures = {
            "worked": "worked",
            "worked_minutes": "worked",
            "worked_hours": "worked",
            "expected": "expected",
            "expected_minutes": "expected",
            "expected_hours": "expected",
            "difference": "difference",
            "balance": "balance",
            "overtime_balance": "balance",
        }
        if measures_raw is None:
            attrs["measures"] = ["worked", "expected", "difference", "balance"]
        else:
            if isinstance(measures_raw, str):
                measures_list = [m.strip() for m in measures_raw.split(",") if m.strip()]
            else:
                measures_list = measures_raw
            normalized = []
            invalid = []
            for m in measures_list:
                key = allowed_measures.get(str(m).strip())
                if key:
                    normalized.append(key)
                else:
                    invalid.append(m)
            if invalid:
                raise serializers.ValidationError({"measures": f"Invalid measure(s): {', '.join(invalid)}"})
            attrs["measures"] = normalized or ["worked", "expected", "difference", "balance"]
        return attrs


class WorkingScheduleDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkingScheduleDay
        fields = [
            "id",
            "schedule",
            "weekday",
            "start_time",
            "end_time",
            "break_start_time",
            "break_end_time",
            "break_minutes",
            "expected_minutes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "schedule", "expected_minutes", "created_at", "updated_at"]

    def validate(self, attrs):
        start = attrs.get("start_time") or getattr(self.instance, "start_time", None)
        end = attrs.get("end_time") or getattr(self.instance, "end_time", None)
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": "end_time must be after start_time"})
        break_start = attrs.get("break_start_time") or getattr(self.instance, "break_start_time", None)
        break_end = attrs.get("break_end_time") or getattr(self.instance, "break_end_time", None)
        if (break_start and not break_end) or (break_end and not break_start):
            raise serializers.ValidationError({"break_start_time": "Both break start and end times are required."})
        if break_start and break_end:
            if break_end <= break_start:
                raise serializers.ValidationError({"break_end_time": "break_end_time must be after break_start_time"})
            if start and break_start < start:
                raise serializers.ValidationError({"break_start_time": "Break must start within the shift hours."})
            if end and break_end > end:
                raise serializers.ValidationError({"break_end_time": "Break must end within the shift hours."})
        return attrs


class WorkingScheduleSerializer(serializers.ModelSerializer):
    days = WorkingScheduleDaySerializer(many=True, read_only=True)

    class Meta:
        model = WorkingSchedule
        fields = [
            "id",
            "employer_id",
            "name",
            "timezone",
            "default_daily_minutes",
            "is_default",
            "days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "created_at", "updated_at", "days"]
