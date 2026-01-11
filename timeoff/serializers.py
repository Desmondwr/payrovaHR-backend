from rest_framework import serializers
from .models import TimeOffConfiguration, TimeOffRequest, TimeOffLedgerEntry
from .services import compute_balances
from .defaults import merge_time_off_defaults, validate_time_off_config


class TimeOffConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffConfiguration
        fields = "__all__"
        read_only_fields = ("id", "employer_id", "created_at", "updated_at")

    def validate_configuration(self, value):
        merged = merge_time_off_defaults(value or {})
        errors = validate_time_off_config(merged)
        if errors:
            raise serializers.ValidationError(errors)
        return merged

    def create(self, validated_data):
        validated_data["configuration"] = merge_time_off_defaults(validated_data.get("configuration", {}))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "configuration" in validated_data:
            validated_data["configuration"] = merge_time_off_defaults(validated_data.get("configuration", {}))
        return super().update(instance, validated_data)


class TimeOffRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffRequest
        fields = "__all__"
        read_only_fields = (
            "id",
            "employer_id",
            "status",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "cancelled_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant_db = "default"
        if request and hasattr(request, "user") and hasattr(request.user, "employer_profile"):
            from accounts.database_utils import get_tenant_database_alias
            from employees.models import Employee

            tenant_db = get_tenant_database_alias(request.user.employer_profile)
            if "employee" in self.fields:
                self.fields["employee"].queryset = Employee.objects.using(tenant_db).all()
        elif request and hasattr(request, "user") and hasattr(request.user, "employee_profile") and request.user.employee_profile:
            from employees.models import Employee

            employee = request.user.employee_profile
            tenant_db = employee._state.db or "default"
            if "employee" in self.fields:
                self.fields["employee"].queryset = Employee.objects.using(tenant_db).filter(id=employee.id)
                self.fields["employee"].required = False
        elif self.instance and not isinstance(self.instance, (list, tuple)):
            tenant_db = self.instance._state.db or "default"
            if "employee" in self.fields:
                self.fields["employee"].queryset = self.instance.__class__.objects.using(tenant_db).all()

    def validate(self, attrs):
        # Basic start/end sanity check
        start_at = attrs.get("start_at") or getattr(self.instance, "start_at", None)
        end_at = attrs.get("end_at") or getattr(self.instance, "end_at", None)
        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "End time must be after start time."})
        return attrs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db", "default")
        return TimeOffRequest.objects.using(tenant_db).create(**validated_data)


class TimeOffBalanceSerializer(serializers.Serializer):
    leave_type_code = serializers.CharField()
    earned_minutes = serializers.IntegerField()
    reserved_minutes = serializers.IntegerField()
    taken_minutes = serializers.IntegerField()
    available_minutes = serializers.IntegerField()

    @staticmethod
    def from_entries(entries, reservation_policy):
        grouped = {}
        for entry in entries:
            code = entry.leave_type_code
            grouped.setdefault(code, []).append(entry)

        results = []
        for code, items in grouped.items():
            balances = compute_balances(items, reservation_policy=reservation_policy)
            results.append(
                {
                    "leave_type_code": code,
                    **balances,
                }
            )
        return results


class TimeOffLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffLedgerEntry
        fields = "__all__"
        read_only_fields = ("id", "created_at")
