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

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "employer_id",
            "employee",
            "employee_full_name",
            "check_in_at",
            "check_out_at",
            "worked_minutes",
            "expected_minutes",
            "overtime_worked_minutes",
            "overtime_approved_minutes",
            "status",
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
            "worked_minutes",
            "expected_minutes",
            "overtime_worked_minutes",
            "status",
            "anomaly_reason",
            "created_at",
            "updated_at",
        ]


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
