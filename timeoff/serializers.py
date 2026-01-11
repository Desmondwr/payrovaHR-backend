from rest_framework import serializers
from decimal import Decimal
from .models import TimeOffConfiguration, TimeOffRequest, TimeOffLedgerEntry
from .services import compute_balances
from .defaults import merge_time_off_defaults
from .defaults import merge_time_off_defaults, validate_time_off_config


class TimeOffConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffConfiguration
        fields = "__all__"
        read_only_fields = (
            "id",
            "employer_id",
            "created_at",
            "updated_at",
            "schema_version",
            "default_time_unit",
            "working_hours_per_day",
            "leave_year_type",
            "leave_year_start_month",
            "tenant_id",
            "holiday_calendar_source",
            "time_zone_handling",
            "reservation_policy",
            "rounding_increment_minutes",
            "rounding_method",
            "weekend_days",
            "module_enabled",
            "allow_backdated_requests",
            "allow_future_dated_requests",
            "allow_negative_balance",
            "negative_balance_limit",
            "allow_overlapping_requests",
            "backdated_limit_days",
            "future_window_days",
            "max_request_length_days",
            "max_requests_per_month",
        )

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


class TimeOffAllocationSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField()
    leave_type_code = serializers.CharField()
    amount = serializers.DecimalField(max_digits=9, decimal_places=2)
    unit = serializers.ChoiceField(choices=["DAYS", "HOURS"])
    effective_date = serializers.DateField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "employer_profile"):
            raise serializers.ValidationError({"detail": "Employer context required."})

        employer = request.user.employer_profile
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)

        # Validate employee exists in tenant
        from employees.models import Employee

        employee = Employee.objects.using(tenant_db).filter(id=attrs["employee_id"]).first()
        if not employee:
            raise serializers.ValidationError({"employee_id": ["Employee not found for this tenant."]})

        # Load config and validate leave type
        config_obj = (
            TimeOffConfiguration.objects.using(tenant_db)
            .filter(employer_id=employer.id)
            .first()
        )
        config = config_obj.configuration if config_obj else merge_time_off_defaults({})
        leave_types = (config or {}).get("leave_types", []) or []
        codes = {lt.get("code") for lt in leave_types}
        if attrs["leave_type_code"] not in codes:
            raise serializers.ValidationError({"leave_type_code": ["Unknown leave type for this tenant."]})

        # Validate amount
        amount = attrs["amount"]
        if amount <= 0:
            raise serializers.ValidationError({"amount": ["Amount must be greater than zero."]})

        attrs["employee"] = employee
        attrs["tenant_db"] = tenant_db
        attrs["employer_id"] = employer.id
        attrs["config"] = config
        return attrs

    def _round_minutes(self, minutes: int, rounding: dict) -> int:
        inc = int(rounding.get("increment_minutes") or 0) or 1
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

    def create(self, validated_data):
        employee = validated_data["employee"]
        tenant_db = validated_data["tenant_db"]
        employer_id = validated_data["employer_id"]
        config = validated_data["config"] or {}
        working_hours = (config.get("global_settings") or {}).get("working_hours_per_day", 8) or 8
        rounding_cfg = (config.get("global_settings") or {}).get("rounding") or {}

        amount = Decimal(validated_data["amount"])
        unit = validated_data["unit"]
        minutes = int(amount * 60) if unit == "HOURS" else int(amount * working_hours * 60)
        minutes = self._round_minutes(minutes, rounding_cfg)

        if minutes == 0:
            raise serializers.ValidationError({"amount": ["Computed amount is zero after rounding."]})

        effective_date = validated_data.get("effective_date")
        if not effective_date:
            from django.utils import timezone
            effective_date = timezone.now().date()

        return TimeOffLedgerEntry.objects.using(tenant_db).create(
            employer_id=employer_id,
            tenant_id=employer_id,
            employee=employee,
            leave_type_code=validated_data["leave_type_code"],
            entry_type="ALLOCATION",
            amount_minutes=minutes,
            effective_date=effective_date,
            notes=validated_data.get("notes"),
            created_by=self.context["request"].user.id,
            metadata={"reason": validated_data.get("reason")},
        )
