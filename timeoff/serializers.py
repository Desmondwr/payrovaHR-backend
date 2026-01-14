from datetime import date
from decimal import Decimal

from rest_framework import serializers

from accounts.database_utils import get_tenant_database_alias
from employees.models import Employee

from .models import (
    TimeOffAccrualPlan,
    TimeOffAccrualSubscription,
    TimeOffAllocation,
    TimeOffAllocationLine,
    TimeOffAllocationRequest,
    TimeOffApprovalStep,
    TimeOffConfiguration,
    TimeOffLedgerEntry,
    TimeOffRequest,
    TimeOffType,
    ensure_timeoff_configuration,
)
from .services import (
    apply_approval_transitions,
    apply_rejection_or_cancellation_transitions,
    apply_submit_transitions,
    calculate_duration_minutes,
    compute_balances,
    convert_amount_to_minutes,
    get_available_balance,
    has_overlap,
)


def _load_config(employer_id: int, tenant_db: str) -> dict:
    config = ensure_timeoff_configuration(employer_id, tenant_db)
    return config.to_config_dict()


class TimeOffApprovalStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffApprovalStep
        fields = ("id", "step_index", "step_type", "required")
        read_only_fields = ("id",)


class TimeOffTypeSerializer(serializers.ModelSerializer):
    approval_steps = TimeOffApprovalStepSerializer(many=True, required=False)

    class Meta:
        model = TimeOffType
        fields = (
            "id",
            "configuration",
            "employer_id",
            "tenant_id",
            "code",
            "name",
            "paid",
            "color",
            "description",
            "mobile_enabled",
            "balance_visible_to_employee",
            "allow_encashment",
            "encashment_max_days",
            "encashment_conversion_rate",
            "allow_comp_off_generation",
            "comp_off_expiry_days",
            "sandwich_rule_enabled",
            "eligibility_gender",
            "eligibility_allowed_in_probation",
            "eligibility_minimum_tenure_months",
            "eligibility_employment_types",
            "eligibility_locations",
            "eligibility_departments",
            "eligibility_job_levels",
            "request_allow_half_day",
            "request_allow_hourly",
            "request_minimum_duration",
            "request_maximum_duration",
            "request_consecutive_days_limit",
            "request_allow_prefix_suffix_holidays",
            "request_count_weekends_as_leave",
            "request_count_holidays_as_leave",
            "request_blackout_dates",
            "request_requires_reason",
            "request_requires_document",
            "request_document_mandatory_after_days",
            "approval_auto_approve",
            "approval_workflow_code",
            "approval_fallback_approver",
            "approval_reminders_enabled",
            "approval_reminder_after_hours",
            "accrual_enabled",
            "accrual_method",
            "accrual_rate_per_period",
            "accrual_start_trigger",
            "accrual_start_offset_days",
            "accrual_waiting_period_days",
            "accrual_proration_method",
            "accrual_proration_on_join",
            "accrual_proration_on_termination",
            "accrual_cap_enabled",
            "accrual_cap_max_balance",
            "carryover_enabled",
            "carryover_max_carryover",
            "carryover_expires_after_days",
            "approval_steps",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "employer_id",
            "tenant_id",
            "configuration",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "employer_profile"):
            raise serializers.ValidationError({"detail": "Employer context required."})
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        config = ensure_timeoff_configuration(employer.id, tenant_db)
        attrs["configuration"] = config
        attrs["employer_id"] = config.employer_id
        attrs["tenant_id"] = config.tenant_id
        self.context["tenant_db"] = tenant_db
        return attrs

    def _sync_steps(self, instance: TimeOffType, steps_data, tenant_db: str):
        instance.approval_steps.all().delete()
        for idx, step in enumerate(steps_data or []):
            step_index = step.get("step_index", idx)
            TimeOffApprovalStep.objects.using(tenant_db).create(
                leave_type=instance,
                step_index=step_index,
                step_type=step.get("step_type") or step.get("type") or "MANAGER",
                required=step.get("required", True),
            )

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db", "default")
        steps = validated_data.pop("approval_steps", [])
        instance = TimeOffType.objects.using(tenant_db).create(**validated_data)
        self._sync_steps(instance, steps, tenant_db)
        return instance

    def update(self, instance, validated_data):
        tenant_db = instance._state.db or self.context.get("tenant_db") or "default"
        steps = validated_data.pop("approval_steps", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save(using=tenant_db)
        if steps is not None:
            self._sync_steps(instance, steps, tenant_db)
        return instance


class TimeOffConfigurationSerializer(serializers.ModelSerializer):
    configuration = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TimeOffConfiguration
        fields = (
            "id",
            "employer_id",
            "tenant_id",
            "schema_version",
            "default_time_unit",
            "working_hours_per_day",
            "minimum_request_unit",
            "leave_year_type",
            "leave_year_start_month",
            "holiday_calendar_source",
            "time_zone_handling",
            "reservation_policy",
            "rounding_unit",
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
            "auto_reset_date",
            "auto_carry_forward_date",
            "year_end_auto_reset_enabled",
            "year_end_auto_carryover_enabled",
            "year_end_process_on_month_day",
            "request_history_years",
            "ledger_history_years",
            "configuration",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "employer_id",
            "tenant_id",
            "schema_version",
            "configuration",
            "created_at",
            "updated_at",
        )

    def get_configuration(self, obj: TimeOffConfiguration):
        return obj.to_config_dict()


class TimeOffRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffRequest
        fields = "__all__"
        read_only_fields = (
            "id",
            "employer_id",
            "tenant_id",
            "status",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "cancelled_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "duration_minutes",
        )


class TimeOffRequestInputSerializer(serializers.ModelSerializer):
    """Serializer handling creation/update with derived fields."""

    start_date = serializers.DateField(write_only=True, required=False)
    end_date = serializers.DateField(write_only=True, required=False)
    date = serializers.DateField(write_only=True, required=False)
    half_day = serializers.BooleanField(write_only=True, required=False, default=False)
    half_day_period = serializers.ChoiceField(
        choices=[("MORNING", "Morning"), ("AFTERNOON", "Afternoon")],
        write_only=True,
        required=False,
    )
    custom_hours = serializers.BooleanField(write_only=True, required=False, default=False)
    from_time = serializers.TimeField(write_only=True, required=False)
    to_time = serializers.TimeField(write_only=True, required=False)
    submit = serializers.BooleanField(write_only=True, required=False, default=False)
    attachments = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = TimeOffRequest
        fields = "__all__"
        read_only_fields = (
            "id",
            "employer_id",
            "tenant_id",
            "status",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "cancelled_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "duration_minutes",
            "unit",
        )

    def validate(self, attrs):
        user = self.context.get("request").user if self.context.get("request") else None
        submit_flag = bool(attrs.pop("submit", False))
        self.context["submit_flag"] = submit_flag
        half_day = bool(attrs.pop("half_day", False))
        custom_hours = bool(attrs.pop("custom_hours", False))
        if half_day and custom_hours:
            raise serializers.ValidationError({"detail": "Choose either half_day or custom_hours, not both."})

        date_single = attrs.pop("date", None)
        start_date = attrs.get("start_date") or date_single or (self.instance.start_at.date() if self.instance else None)
        end_date = attrs.get("end_date") or start_date or (self.instance.end_at.date() if self.instance else None)
        if not start_date:
            raise serializers.ValidationError({"start_date": "start_date or date is required."})

        half_day_period = attrs.get("half_day_period") or (self.instance.half_day_period if self.instance else None)
        from_time_val = attrs.get("from_time") or (self.instance.from_time if self.instance else None)
        to_time_val = attrs.get("to_time") or (self.instance.to_time if self.instance else None)

        if self.instance and not half_day and not custom_hours:
            if self.instance.input_type == "HALF_DAY":
                half_day = True
                half_day_period = half_day_period or self.instance.half_day_period
            elif self.instance.input_type == "CUSTOM_HOURS":
                custom_hours = True
                from_time_val = from_time_val or self.instance.from_time
                to_time_val = to_time_val or self.instance.to_time
        employer_id = None
        tenant_db = self.context.get("tenant_db") or "default"
        employee_obj = None

        if hasattr(user, "employer_profile") and user.employer_profile:
            employer_id = user.employer_profile.id
            employee_id = self.initial_data.get("employee") or self.initial_data.get("employee_id")
            if not employee_id and not self.instance:
                raise serializers.ValidationError({"employee": ["employee is required."]})
            employee_lookup = employee_id or (self.instance.employee_id if self.instance else None)
            if employee_lookup:
                employee_obj = Employee.objects.using(tenant_db).filter(
                    id=employee_lookup, employer_id=employer_id
                ).first()
            if not employee_obj:
                raise serializers.ValidationError({"employee": ["Employee not found for this tenant."]})
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee_obj = user.employee_profile
            tenant_db = employee_obj._state.db or tenant_db
            employer_id = employee_obj.employer_id
        else:
            raise serializers.ValidationError({"detail": "Unable to resolve employee for request."})

        config = _load_config(employer_id, tenant_db)
        global_settings = config.get("global_settings") or {}
        rounding = global_settings.get("rounding") or {}
        working_hours = int(global_settings.get("working_hours_per_day", 8) or 8)
        weekend_days = global_settings.get("weekend_days") or []
        reservation_policy = global_settings.get("reservation_policy") or "RESERVE_ON_SUBMIT"

        leave_type_code = attrs.get("leave_type_code") or self.initial_data.get("leave_type_code")
        leave_types = (config.get("leave_types") or [])
        leave_type = next((lt for lt in leave_types if lt.get("code") == leave_type_code), None)
        if not leave_type:
            raise serializers.ValidationError({"leave_type_code": ["Unknown leave type for this tenant."]})

        request_policy = leave_type.get("request_policy", {}) or {}
        approval_policy = leave_type.get("approval_policy", {}) or {}

        try:
            start_at, end_at, duration_minutes, duration_days = calculate_duration_minutes(
                start_date=start_date,
                end_date=end_date,
                half_day=half_day,
                half_day_period=half_day_period,
                custom_hours=custom_hours,
                from_time_val=from_time_val,
                to_time_val=to_time_val,
                working_hours_per_day=working_hours,
                weekend_days=weekend_days,
                count_weekends_as_leave=request_policy.get("count_weekends_as_leave", False),
                rounding=rounding,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)})

        # Request policy validations
        errors = {}
        if half_day and not request_policy.get("allow_half_day", True):
            errors["half_day"] = "Half-day requests are not allowed for this leave type."
        if custom_hours and not request_policy.get("allow_hourly", False):
            errors["custom_hours"] = "Hourly requests are not allowed for this leave type."

        min_duration = request_policy.get("minimum_duration")
        max_duration = request_policy.get("maximum_duration")
        if min_duration is not None and duration_days < float(min_duration):
            errors["duration"] = f"Minimum duration is {min_duration} day(s)."
        if max_duration is not None and duration_days > float(max_duration):
            errors["duration"] = f"Maximum duration is {max_duration} day(s)."

        consecutive_limit = request_policy.get("consecutive_days_limit")
        if consecutive_limit and duration_days > float(consecutive_limit):
            errors["duration"] = f"Consecutive days cannot exceed {consecutive_limit}."

        blackout_dates = request_policy.get("blackout_dates") or []
        if blackout_dates:
            blackout_set = {str(bd) for bd in blackout_dates}
            for day in (start_at.date(), end_at.date()):
                if str(day) in blackout_set:
                    errors["start_date"] = "Requested dates intersect with blackout dates."
                    break

        description = attrs.get("description") or attrs.get("reason") or self.initial_data.get("description")
        attachments = attrs.get("attachments") or self.initial_data.get("attachments") or []
        if request_policy.get("requires_reason") and not description:
            errors["description"] = "Description/reason is required."

        doc_days = request_policy.get("document_mandatory_after_days")
        if request_policy.get("requires_document") or (doc_days and duration_days >= float(doc_days)):
            if not attachments:
                errors["attachments"] = "Attachments are required for this request."

        # Global validations
        today = date.today()
        if not global_settings.get("allow_backdated_requests", True):
            if start_at.date() < today:
                errors["start_date"] = "Backdated requests are not allowed."
        else:
            limit = int(global_settings.get("backdated_limit_days", 0) or 0)
            if limit and (today - start_at.date()).days > limit:
                errors["start_date"] = f"Backdated requests beyond {limit} days are not allowed."

        if not global_settings.get("allow_future_dated_requests", True):
            if end_at.date() > today:
                errors["end_date"] = "Future-dated requests are not allowed."
        else:
            window = int(global_settings.get("future_window_days", 0) or 0)
            if window and (end_at.date() - today).days > window:
                errors["end_date"] = f"Requests cannot be more than {window} days in the future."

        if not global_settings.get("allow_overlapping_requests", False):
            if has_overlap(
                employee_obj,
                start_at,
                end_at,
                db_alias=tenant_db,
                exclude_request_id=self.instance.id if self.instance else None,
            ):
                errors["detail"] = "Request overlaps with an existing request."

        # Balance validation
        allow_negative = global_settings.get("allow_negative_balance", False)
        if not allow_negative or global_settings.get("negative_balance_limit"):
            available_minutes = get_available_balance(
                employee_obj,
                leave_type_code,
                reservation_policy,
                db_alias=tenant_db,
            )
            projected = available_minutes - duration_minutes
            if not allow_negative and projected < 0:
                errors["detail"] = "Insufficient balance for this request."
            elif allow_negative:
                limit_days = int(global_settings.get("negative_balance_limit") or 0)
                limit_minutes = limit_days * working_hours * 60  # treat limit as days-equivalent
                if limit_minutes and projected < -limit_minutes:
                    errors["detail"] = "Request exceeds allowed negative balance."

        if errors:
            raise serializers.ValidationError(errors)

        attrs["start_at"] = start_at
        attrs["end_at"] = end_at
        attrs["duration_minutes"] = duration_minutes
        attrs["unit"] = "HOURS" if custom_hours else ("HALF_DAYS" if half_day else "DAYS")
        attrs["input_type"] = "CUSTOM_HOURS" if custom_hours else ("HALF_DAY" if half_day else "FULL_DAY")
        attrs["half_day_period"] = half_day_period if half_day else None
        attrs["from_time"] = from_time_val if custom_hours else None
        attrs["to_time"] = to_time_val if custom_hours else None
        attrs["employer_id"] = employer_id
        attrs["tenant_id"] = employer_id
        attrs["employee"] = employee_obj
        attrs["created_by"] = user.id
        attrs["updated_by"] = user.id
        attrs["description"] = description
        attrs["reason"] = description
        attrs["attachments"] = attachments or []
        attrs["reservation_policy"] = reservation_policy
        attrs["approval_policy"] = approval_policy
        return attrs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        submit_flag = self.context.get("submit_flag", False)
        reservation_policy = validated_data.pop("reservation_policy")
        approval_policy = validated_data.pop("approval_policy", {}) or {}
        request_obj = TimeOffRequest.objects.using(tenant_db).create(**validated_data)
        if submit_flag:
            apply_submit_transitions(
                request=request_obj,
                duration_minutes=request_obj.duration_minutes,
                reservation_policy=reservation_policy,
                created_by=request_obj.created_by,
                db_alias=tenant_db,
                effective_date=request_obj.start_at.date(),
            )
            if approval_policy.get("auto_approve"):
                apply_approval_transitions(
                    request=request_obj,
                    duration_minutes=request_obj.duration_minutes,
                    reservation_policy=reservation_policy,
                    created_by=request_obj.created_by,
                    db_alias=tenant_db,
                    effective_date=request_obj.start_at.date(),
                )
        return request_obj

    def update(self, instance, validated_data):
        if hasattr(instance, "is_editable") and not instance.is_editable:
            raise serializers.ValidationError({"detail": "Only draft or submitted requests can be edited."})
        tenant_db = instance._state.db or "default"
        reservation_policy = validated_data.pop("reservation_policy", None)
        approval_policy = validated_data.pop("approval_policy", None)
        submit_flag = self.context.get("submit_flag", False)

        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save(using=tenant_db)

        if submit_flag and reservation_policy:
            apply_submit_transitions(
                request=instance,
                duration_minutes=instance.duration_minutes,
                reservation_policy=reservation_policy,
                created_by=instance.updated_by,
                db_alias=tenant_db,
                effective_date=instance.start_at.date(),
            )
            if approval_policy and approval_policy.get("auto_approve"):
                apply_approval_transitions(
                    request=instance,
                    duration_minutes=instance.duration_minutes,
                    reservation_policy=reservation_policy,
                    created_by=instance.updated_by,
                    db_alias=tenant_db,
                    effective_date=instance.start_at.date(),
                )
        return instance


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


class TimeOffAllocationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffAllocationLine
        fields = ("id", "employee", "status", "created_at")
        read_only_fields = fields


class TimeOffAllocationSerializer(serializers.ModelSerializer):
    lines = TimeOffAllocationLineSerializer(many=True, read_only=True)

    class Meta:
        model = TimeOffAllocation
        fields = "__all__"
        read_only_fields = (
            "id",
            "status",
            "created_at",
            "updated_at",
            "tenant_id",
            "employer_id",
            "lines",
        )


class TimeOffAllocationCreateSerializer(serializers.ModelSerializer):
    employee_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = TimeOffAllocation
        fields = (
            "id",
            "name",
            "leave_type_code",
            "allocation_type",
            "amount",
            "unit",
            "start_date",
            "end_date",
            "employee_id",
            "notes",
            "accrual_plan",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "employer_profile"):
            raise serializers.ValidationError({"detail": "Employer context required."})
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        attrs["tenant_db"] = tenant_db
        attrs["employer_id"] = employer.id

        config = _load_config(employer.id, tenant_db)
        leave_types = config.get("leave_types") or []
        leave_type = next((lt for lt in leave_types if lt.get("code") == attrs.get("leave_type_code")), None)
        if not leave_type:
            raise serializers.ValidationError({"leave_type_code": ["Unknown leave type for this tenant."]})
        attrs["leave_type"] = leave_type

        allocation_type = attrs.get("allocation_type") or "REGULAR"
        if allocation_type == "REGULAR":
            if attrs.get("amount") is None or not attrs.get("unit"):
                raise serializers.ValidationError({"amount": ["amount and unit are required for regular allocations."]})
            if attrs["amount"] <= 0:
                raise serializers.ValidationError({"amount": ["Amount must be positive."]})
        else:
            if not attrs.get("accrual_plan"):
                raise serializers.ValidationError({"accrual_plan": ["accrual_plan is required for accrual allocations."]})

        employee_obj = None
        if attrs.get("employee_id"):
            employee_obj = Employee.objects.using(tenant_db).filter(
                id=attrs["employee_id"], employer_id=employer.id
            ).first()
            if not employee_obj:
                raise serializers.ValidationError({"employee_id": ["Employee not found in tenant."]})
        attrs["employee"] = employee_obj
        attrs["working_hours"] = int((config.get("global_settings") or {}).get("working_hours_per_day", 8) or 8)
        attrs["rounding"] = (config.get("global_settings") or {}).get("rounding") or {}
        return attrs

    def create(self, validated_data):
        tenant_db = validated_data.pop("tenant_db")
        working_hours = validated_data.pop("working_hours", 8)
        rounding = validated_data.pop("rounding", {})
        validated_data.pop("leave_type", None)
        employee = validated_data.pop("employee", None)
        employer_id = validated_data.pop("employer_id")
        allocation = TimeOffAllocation.objects.using(tenant_db).create(
            employer_id=employer_id,
            tenant_id=employer_id,
            created_by=self.context["request"].user.id,
            employee=employee,
            **validated_data,
        )
        if employee:
            TimeOffAllocationLine.objects.using(tenant_db).create(
                allocation=allocation,
                employee=employee,
                status="DRAFT",
            )
        allocation._working_hours = working_hours
        allocation._rounding = rounding
        return allocation


class TimeOffBulkAllocationSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["BY_EMPLOYEE"])
    employee_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    name = serializers.CharField()
    leave_type_code = serializers.CharField()
    allocation_type = serializers.ChoiceField(choices=["REGULAR", "ACCRUAL"], default="REGULAR")
    amount = serializers.DecimalField(max_digits=9, decimal_places=2)
    unit = serializers.ChoiceField(choices=["DAYS", "HOURS"])
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "employer_profile"):
            raise serializers.ValidationError({"detail": "Employer context required."})
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        attrs["tenant_db"] = tenant_db
        attrs["employer_id"] = employer.id

        config = _load_config(employer.id, tenant_db)
        leave_types = config.get("leave_types") or []
        leave_type = next((lt for lt in leave_types if lt.get("code") == attrs.get("leave_type_code")), None)
        if not leave_type:
            raise serializers.ValidationError({"leave_type_code": ["Unknown leave type for this tenant."]})

        employees = list(
            Employee.objects.using(tenant_db).filter(employer_id=employer.id, id__in=attrs["employee_ids"])
        )
        if len(employees) != len(set(attrs["employee_ids"])):
            raise serializers.ValidationError({"employee_ids": ["One or more employees not found for this tenant."]})
        attrs["employees"] = employees
        attrs["working_hours"] = int((config.get("global_settings") or {}).get("working_hours_per_day", 8) or 8)
        attrs["rounding"] = (config.get("global_settings") or {}).get("rounding") or {}
        return attrs

    def create(self, validated_data):
        tenant_db = validated_data["tenant_db"]
        employer_id = validated_data["employer_id"]
        working_hours = validated_data["working_hours"]
        rounding = validated_data["rounding"]

        allocation = TimeOffAllocation.objects.using(tenant_db).create(
            employer_id=employer_id,
            tenant_id=employer_id,
            name=validated_data["name"],
            leave_type_code=validated_data["leave_type_code"],
            allocation_type=validated_data.get("allocation_type") or "REGULAR",
            amount=validated_data["amount"],
            unit=validated_data["unit"],
            start_date=validated_data["start_date"],
            end_date=validated_data.get("end_date"),
            notes=validated_data.get("notes"),
            created_by=self.context["request"].user.id,
        )
        for emp in validated_data["employees"]:
            TimeOffAllocationLine.objects.using(tenant_db).create(
                allocation=allocation,
                employee=emp,
                status="DRAFT",
            )
        allocation._working_hours = working_hours
        allocation._rounding = rounding
        return allocation


class TimeOffAllocationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffAllocationRequest
        fields = "__all__"
        read_only_fields = ("id", "status", "acted_at", "acted_by", "created_at", "tenant_id", "employer_id")

    def validate(self, attrs):
        user = self.context.get("request").user if self.context.get("request") else None
        if not hasattr(user, "employee_profile") or not user.employee_profile:
            raise serializers.ValidationError({"detail": "Only employees can request allocations."})
        employee = user.employee_profile
        tenant_db = employee._state.db or "default"
        attrs["employee"] = employee
        attrs["employer_id"] = employee.employer_id
        attrs["tenant_id"] = employee.employer_id

        config = _load_config(employee.employer_id, tenant_db)
        leave_types = config.get("leave_types") or []
        leave_type = next((lt for lt in leave_types if lt.get("code") == attrs.get("leave_type_code")), None)
        if not leave_type:
            raise serializers.ValidationError({"leave_type_code": ["Unknown leave type for this tenant."]})
        if attrs.get("amount") is None or attrs["amount"] <= 0:
            raise serializers.ValidationError({"amount": ["Amount must be greater than zero."]})
        return attrs
