from datetime import datetime

from rest_framework import serializers
from django.utils import timezone

from accounts.database_utils import get_tenant_database_alias
from employees.models import Employee

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
from .services import assign_attendance_date, compute_overtime_minutes, create_manual_record, resolve_attendance_policy


class TenantBoundModelSerializer(serializers.ModelSerializer):
    def _resolve_tenant_db(self) -> str:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user:
            return "default"
        if hasattr(user, "employer_profile") and user.employer_profile:
            return get_tenant_database_alias(user.employer_profile)
        if hasattr(user, "employee_profile") and user.employee_profile:
            return user.employee_profile._state.db or "default"
        return "default"

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or self._resolve_tenant_db()
        return self.Meta.model.objects.using(tenant_db).create(**validated_data)

    def update(self, instance, validated_data):
        tenant_db = instance._state.db or self.context.get("tenant_db") or self._resolve_tenant_db()
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save(using=tenant_db)
        return instance


class AttendancePolicySerializer(TenantBoundModelSerializer):
    class Meta:
        model = AttendancePolicy
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "created_at", "updated_at")


class ShiftTemplateSerializer(TenantBoundModelSerializer):
    class Meta:
        model = ShiftTemplate
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "created_at", "updated_at")


class EmployeeScheduleSerializer(TenantBoundModelSerializer):
    class Meta:
        model = EmployeeSchedule
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "created_at", "updated_at")


class AttendanceEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceEvent
        fields = "__all__"
        read_only_fields = ("id", "attendance_date", "employer_id", "created_at")


class AttendanceEventCreateSerializer(serializers.ModelSerializer):
    employee_id = serializers.UUIDField(write_only=True, required=False)
    timestamp = serializers.DateTimeField(required=False)

    class Meta:
        model = AttendanceEvent
        fields = (
            "employee_id",
            "timestamp",
            "event_type",
            "source",
            "device",
            "location_lat",
            "location_lng",
            "ip_address",
            "metadata",
        )

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user:
            raise serializers.ValidationError({"detail": "User context required."})

        tenant_db = "default"
        employee = None

        if hasattr(user, "employer_profile") and user.employer_profile:
            tenant_db = get_tenant_database_alias(user.employer_profile)
            employee_id = attrs.get("employee_id") or self.initial_data.get("employee_id")
            if not employee_id:
                raise serializers.ValidationError({"employee_id": ["employee_id is required."]})
            employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
            if not employee:
                raise serializers.ValidationError({"employee_id": ["Employee not found for this tenant."]})
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or tenant_db
        else:
            raise serializers.ValidationError({"detail": "Unable to resolve tenant."})

        timestamp = attrs.get("timestamp") or datetime.now()
        if timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp, timezone.get_current_timezone())

        shift, attendance_date = assign_attendance_date(employee, timestamp, tenant_db)

        attrs["timestamp"] = timestamp
        attrs["employee"] = employee
        attrs["employer_id"] = employee.employer_id
        attrs["attendance_date"] = attendance_date
        attrs["created_by_id"] = user.id
        attrs["tenant_db"] = tenant_db
        attrs["expected_shift"] = shift
        return attrs

    def create(self, validated_data):
        tenant_db = validated_data.pop("tenant_db")
        validated_data.pop("expected_shift", None)
        return AttendanceEvent.objects.using(tenant_db).create(**validated_data)


class AttendanceDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceDay
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "created_at", "updated_at")


class AttendanceDayManualMarkSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField()
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=AttendanceDay.STATUS_CHOICES)
    first_in_at = serializers.DateTimeField(required=False, allow_null=True)
    last_out_at = serializers.DateTimeField(required=False, allow_null=True)
    worked_minutes = serializers.IntegerField(required=False, default=0)
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "employer_profile"):
            raise serializers.ValidationError({"detail": "Employer context required."})
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        employee = Employee.objects.using(tenant_db).filter(id=attrs["employee_id"]).first()
        if not employee:
            raise serializers.ValidationError({"employee_id": ["Employee not found for this tenant."]})
        attrs["employee"] = employee
        attrs["tenant_db"] = tenant_db
        return attrs


class AttendanceDeviceSerializer(TenantBoundModelSerializer):
    class Meta:
        model = AttendanceDevice
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "created_at", "updated_at")


class AttendanceKioskSettingsSerializer(TenantBoundModelSerializer):
    class Meta:
        model = AttendanceKioskSettings
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "kiosk_url_token", "created_at", "updated_at")


class AttendanceRecordSerializer(TenantBoundModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "worked_minutes", "created_at", "updated_at")


class AttendanceRecordCreateSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField()
    check_in_at = serializers.DateTimeField()
    check_out_at = serializers.DateTimeField()
    extra_minutes = serializers.IntegerField(required=False, allow_null=True)
    overtime_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "employer_profile"):
            raise serializers.ValidationError({"detail": "Employer context required."})
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        employee = Employee.objects.using(tenant_db).filter(id=attrs["employee_id"]).first()
        if not employee:
            raise serializers.ValidationError({"employee_id": ["Employee not found for this tenant."]})
        if attrs["check_out_at"] <= attrs["check_in_at"]:
            raise serializers.ValidationError({"check_out_at": ["Check-out must be after check-in."]})
        policy = resolve_attendance_policy(employee, tenant_db)
        overtime_minutes, _, _ = compute_overtime_minutes(
            employee,
            attrs["check_in_at"],
            attrs["check_out_at"],
            tenant_db,
            policy=policy,
        )
        requested_extra = attrs.get("extra_minutes")
        if requested_extra is not None:
            overtime_minutes = max(0, int(requested_extra))
        require_approval = (policy.get("overtime_policy") or {}).get("require_approval", True)
        if require_approval and overtime_minutes > 0 and not attrs.get("overtime_reason"):
            raise serializers.ValidationError({"overtime_reason": ["Overtime reason is required."]})
        attrs["employee"] = employee
        attrs["tenant_db"] = tenant_db
        attrs["policy"] = policy
        return attrs

    def create(self, validated_data):
        employee = validated_data["employee"]
        tenant_db = validated_data["tenant_db"]
        return create_manual_record(
            employee=employee,
            tenant_db=tenant_db,
            check_in_at=validated_data["check_in_at"],
            check_out_at=validated_data["check_out_at"],
            extra_minutes=validated_data.get("extra_minutes"),
            overtime_reason=validated_data.get("overtime_reason"),
            created_by_id=self.context["request"].user.id,
        )


class OvertimeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = OvertimeRequest
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "status", "approved_by_id", "approved_at", "created_at")


class OvertimeRequestCreateSerializer(serializers.ModelSerializer):
    employee_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = OvertimeRequest
        fields = ("employee_id", "date", "minutes", "reason")

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user:
            raise serializers.ValidationError({"detail": "User context required."})

        tenant_db = "default"
        employee = None

        if hasattr(user, "employer_profile") and user.employer_profile:
            tenant_db = get_tenant_database_alias(user.employer_profile)
            employee_id = attrs.get("employee_id") or self.initial_data.get("employee_id")
            if not employee_id:
                raise serializers.ValidationError({"employee_id": ["employee_id is required."]})
            employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
            if not employee:
                raise serializers.ValidationError({"employee_id": ["Employee not found for this tenant."]})
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or tenant_db
        else:
            raise serializers.ValidationError({"detail": "Unable to resolve tenant."})

        if attrs.get("minutes") is None or attrs["minutes"] <= 0:
            raise serializers.ValidationError({"minutes": ["Minutes must be greater than zero."]})

        attrs["employee"] = employee
        attrs["employer_id"] = employee.employer_id
        attrs["created_by_id"] = user.id
        attrs["tenant_db"] = tenant_db
        return attrs

    def create(self, validated_data):
        tenant_db = validated_data.pop("tenant_db")
        return OvertimeRequest.objects.using(tenant_db).create(**validated_data)
