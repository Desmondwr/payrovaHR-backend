import uuid
from datetime import date, time
from decimal import Decimal
from typing import Iterable, List, Optional

from django.contrib.postgres.fields import ArrayField
from django.db import IntegrityError, models
from django.utils import timezone

from .defaults import TIME_OFF_DEFAULTS


class TimeOffConfiguration(models.Model):
    """
    Tenant-scoped configuration for the Time Off module.
    Global settings are stored as columns; leave types live in TimeOffType rows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")
    tenant_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Alias for employer_id to support tenant-aware queries",
    )
    schema_version = models.IntegerField(default=2, help_text="Schema version for normalization")
    default_time_unit = models.CharField(max_length=10, default="DAYS")
    working_hours_per_day = models.IntegerField(default=8)
    minimum_request_unit = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.50"))
    leave_year_type = models.CharField(max_length=10, default="CALENDAR")
    leave_year_start_month = models.IntegerField(default=1)
    holiday_calendar_source = models.CharField(max_length=20, default="DEFAULT")
    time_zone_handling = models.CharField(max_length=30, default="EMPLOYER_LOCAL")
    reservation_policy = models.CharField(max_length=30, default="RESERVE_ON_SUBMIT")
    rounding_unit = models.CharField(max_length=20, default="MINUTES")
    rounding_increment_minutes = models.IntegerField(default=30)
    rounding_method = models.CharField(max_length=10, default="NEAREST")
    weekend_days = models.JSONField(default=list, blank=True, help_text="Weekend names e.g. ['SATURDAY']")
    module_enabled = models.BooleanField(default=True)
    allow_backdated_requests = models.BooleanField(default=True)
    allow_future_dated_requests = models.BooleanField(default=True)
    allow_negative_balance = models.BooleanField(default=False)
    negative_balance_limit = models.IntegerField(default=0)
    allow_overlapping_requests = models.BooleanField(default=False)
    backdated_limit_days = models.IntegerField(default=30)
    future_window_days = models.IntegerField(default=180)
    max_request_length_days = models.IntegerField(null=True, blank=True)
    max_requests_per_month = models.IntegerField(null=True, blank=True)
    auto_reset_date = models.DateField(blank=True, null=True)
    auto_carry_forward_date = models.DateField(blank=True, null=True)
    year_end_auto_reset_enabled = models.BooleanField(default=False)
    year_end_auto_carryover_enabled = models.BooleanField(default=False)
    year_end_process_on_month_day = models.CharField(max_length=5, default="01-01")
    request_history_years = models.IntegerField(default=7)
    ledger_history_years = models.IntegerField(default=7)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "timeoff_configurations"
        verbose_name = "Time Off Configuration"
        verbose_name_plural = "Time Off Configurations"
        unique_together = [["employer_id"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Time Off Config - Employer {self.employer_id}"

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        if not self.schema_version:
            self.schema_version = 2
        super().save(*args, **kwargs)

    @classmethod
    def build_defaults(cls, employer_id: int) -> dict:
        defaults = TIME_OFF_DEFAULTS.get("global_settings", {})
        return {
            "employer_id": employer_id,
            "tenant_id": employer_id,
            "schema_version": TIME_OFF_DEFAULTS.get("schema_version", 2),
            "default_time_unit": defaults.get("default_time_unit", "DAYS"),
            "working_hours_per_day": defaults.get("working_hours_per_day", 8),
            "minimum_request_unit": defaults.get("minimum_request_unit", 0.5),
            "leave_year_type": defaults.get("leave_year_type", "CALENDAR"),
            "leave_year_start_month": defaults.get("leave_year_start_month", 1),
            "holiday_calendar_source": defaults.get("holiday_calendar_source", "DEFAULT"),
            "time_zone_handling": defaults.get("time_zone_handling", "EMPLOYER_LOCAL"),
            "reservation_policy": defaults.get("reservation_policy", "RESERVE_ON_SUBMIT"),
            "rounding_unit": (defaults.get("rounding") or {}).get("unit", "MINUTES"),
            "rounding_increment_minutes": (defaults.get("rounding") or {}).get("increment_minutes", 30),
            "rounding_method": (defaults.get("rounding") or {}).get("method", "NEAREST"),
            "weekend_days": defaults.get("weekend_days", []),
            "module_enabled": defaults.get("module_enabled", True),
            "allow_backdated_requests": defaults.get("allow_backdated_requests", True),
            "allow_future_dated_requests": defaults.get("allow_future_dated_requests", True),
            "allow_negative_balance": defaults.get("allow_negative_balance", False),
            "negative_balance_limit": defaults.get("negative_balance_limit", 0),
            "allow_overlapping_requests": defaults.get("allow_overlapping_requests", False),
            "backdated_limit_days": defaults.get("backdated_limit_days", 30),
            "future_window_days": defaults.get("future_window_days", 180),
            "max_request_length_days": defaults.get("max_request_length_days"),
            "max_requests_per_month": defaults.get("max_requests_per_month"),
            "auto_reset_date": defaults.get("auto_reset_date"),
            "auto_carry_forward_date": defaults.get("auto_carry_forward_date"),
            "year_end_auto_reset_enabled": (defaults.get("year_end_processing") or {}).get("auto_reset_enabled", False),
            "year_end_auto_carryover_enabled": (defaults.get("year_end_processing") or {}).get("auto_carryover_enabled", False),
            "year_end_process_on_month_day": (defaults.get("year_end_processing") or {}).get("process_on_month_day", "01-01"),
            "request_history_years": (defaults.get("data_retention") or {}).get("request_history_years", 7),
            "ledger_history_years": (defaults.get("data_retention") or {}).get("ledger_history_years", 7),
        }

    def to_global_settings(self) -> dict:
        return {
            "module_enabled": self.module_enabled,
            "default_time_unit": self.default_time_unit,
            "working_hours_per_day": self.working_hours_per_day,
            "minimum_request_unit": float(self.minimum_request_unit or 0),
            "allow_backdated_requests": self.allow_backdated_requests,
            "backdated_limit_days": self.backdated_limit_days,
            "allow_future_dated_requests": self.allow_future_dated_requests,
            "future_window_days": self.future_window_days,
            "allow_negative_balance": self.allow_negative_balance,
            "negative_balance_limit": self.negative_balance_limit,
            "allow_overlapping_requests": self.allow_overlapping_requests,
            "time_zone_handling": self.time_zone_handling,
            "leave_year_type": self.leave_year_type,
            "leave_year_start_month": self.leave_year_start_month,
            "auto_carry_forward_date": self.auto_carry_forward_date,
            "auto_reset_date": self.auto_reset_date,
            "weekend_days": self.weekend_days or [],
            "reservation_policy": self.reservation_policy,
            "rounding": {
                "unit": self.rounding_unit,
                "increment_minutes": self.rounding_increment_minutes,
                "method": self.rounding_method,
            },
            "holiday_calendar_source": self.holiday_calendar_source,
            "max_request_length_days": self.max_request_length_days,
            "max_requests_per_month": self.max_requests_per_month,
            "year_end_processing": {
                "auto_carryover_enabled": self.year_end_auto_carryover_enabled,
                "auto_reset_enabled": self.year_end_auto_reset_enabled,
                "process_on_month_day": self.year_end_process_on_month_day,
            },
            "data_retention": {
                "request_history_years": self.request_history_years,
                "ledger_history_years": self.ledger_history_years,
            },
        }

    def to_config_dict(self) -> dict:
        policy_defaults = TIME_OFF_DEFAULTS.get("policy_defaults", {})
        leave_types = [lt.to_config_dict() for lt in self.leave_types.all().order_by("name")]
        payload = {
            "schema_version": self.schema_version or 2,
            "global_settings": self.to_global_settings(),
            "policy_defaults": policy_defaults,
            "leave_types": leave_types,
            "leave_entitlements": [],
            "leave_override_enabled": False,
            "leave_policy_id": None,
        }
        return payload

    def seed_default_leave_types(self, db_alias: str = "default") -> None:
        defaults = TIME_OFF_DEFAULTS.get("leave_types", [])
        for entry in defaults:
            code = entry.get("code")
            if code and TimeOffType.objects.using(db_alias).filter(employer_id=self.employer_id, code=code).exists():
                continue
            TimeOffType.from_dict(configuration=self, data=entry, db_alias=db_alias)


class TimeOffType(models.Model):
    """
    Stores an individual leave type definition (was previously nested JSON).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(
        TimeOffConfiguration,
        on_delete=models.CASCADE,
        related_name="leave_types",
    )
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    code = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=255)
    paid = models.BooleanField(default=True)
    color = models.CharField(max_length=7, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    mobile_enabled = models.BooleanField(default=True)
    balance_visible_to_employee = models.BooleanField(default=True)
    allow_encashment = models.BooleanField(default=False)
    encashment_max_days = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    encashment_conversion_rate = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("1.00"))
    allow_comp_off_generation = models.BooleanField(default=False)
    comp_off_expiry_days = models.IntegerField(blank=True, null=True)
    sandwich_rule_enabled = models.BooleanField(default=False)

    eligibility_gender = models.CharField(max_length=10, default="ALL")
    eligibility_allowed_in_probation = models.BooleanField(default=True)
    eligibility_minimum_tenure_months = models.IntegerField(default=0)
    eligibility_employment_types = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    eligibility_locations = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    eligibility_departments = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    eligibility_job_levels = ArrayField(models.CharField(max_length=50), default=list, blank=True)

    request_allow_half_day = models.BooleanField(default=True)
    request_allow_hourly = models.BooleanField(default=False)
    request_minimum_duration = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    request_maximum_duration = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    request_consecutive_days_limit = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    request_allow_prefix_suffix_holidays = models.BooleanField(default=True)
    request_count_weekends_as_leave = models.BooleanField(default=False)
    request_count_holidays_as_leave = models.BooleanField(default=False)
    request_blackout_dates = ArrayField(models.DateField(), default=list, blank=True)
    request_requires_reason = models.BooleanField(default=True)
    request_requires_document = models.BooleanField(default=False)
    request_document_mandatory_after_days = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)

    approval_auto_approve = models.BooleanField(default=False)
    approval_workflow_code = models.CharField(max_length=100, default="DEFAULT")
    approval_fallback_approver = models.CharField(max_length=20, default="HR")
    approval_reminders_enabled = models.BooleanField(default=True)
    approval_reminder_after_hours = models.IntegerField(default=48)

    accrual_enabled = models.BooleanField(default=False)
    accrual_method = models.CharField(max_length=30, default="MONTHLY")
    accrual_rate_per_period = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    accrual_start_trigger = models.CharField(max_length=30, default="DATE_OF_JOINING")
    accrual_start_offset_days = models.IntegerField(default=0)
    accrual_waiting_period_days = models.IntegerField(default=0)
    accrual_proration_method = models.CharField(max_length=20, blank=True, null=True)
    accrual_proration_on_join = models.BooleanField(default=True)
    accrual_proration_on_termination = models.BooleanField(default=True)
    accrual_cap_enabled = models.BooleanField(default=False)
    accrual_cap_max_balance = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)

    carryover_enabled = models.BooleanField(default=False)
    carryover_max_carryover = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    carryover_expires_after_days = models.IntegerField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "timeoff_types"
        ordering = ["code"]
        unique_together = [["employer_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["employer_id", "code"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @staticmethod
    def _to_decimal(value: Optional[object]) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    @staticmethod
    def _coerce_dates(values: Iterable) -> List[date]:
        dates: List[date] = []
        for val in values or []:
            if isinstance(val, date):
                dates.append(val)
            else:
                try:
                    dates.append(date.fromisoformat(str(val)))
                except Exception:
                    continue
        return dates

    @classmethod
    def from_dict(cls, configuration: TimeOffConfiguration, data: dict, db_alias: str = "default") -> "TimeOffType":
        eligibility = data.get("eligibility") or {}
        request_policy = data.get("request_policy") or {}
        approval_policy = data.get("approval_policy") or {}
        accrual_policy = data.get("accrual_policy") or {}
        carryover_policy = data.get("carryover_policy") or {}
        encashment = data.get("encashment_rules") or {}

        blackout_dates = cls._coerce_dates(request_policy.get("blackout_dates") or [])

        instance, _ = cls.objects.using(db_alias).get_or_create(
            configuration=configuration,
            employer_id=configuration.employer_id,
            tenant_id=configuration.tenant_id,
            code=data.get("code"),
            defaults={
                "name": data.get("name"),
                "paid": data.get("paid", True),
                "color": data.get("color"),
                "description": data.get("description"),
                "mobile_enabled": data.get("mobile_enabled", True),
                "balance_visible_to_employee": data.get("balance_visible_to_employee", True),
                "allow_encashment": data.get("allow_encashment", False),
                "encashment_max_days": cls._to_decimal(encashment.get("max_days")),
                "encashment_conversion_rate": cls._to_decimal(encashment.get("conversion_rate", 1.0)) or Decimal("1.00"),
                "allow_comp_off_generation": data.get("allow_comp_off_generation", False),
                "comp_off_expiry_days": data.get("comp_off_expiry_days"),
                "sandwich_rule_enabled": data.get("sandwich_rule_enabled", False),
                "eligibility_gender": eligibility.get("gender", "ALL"),
                "eligibility_allowed_in_probation": eligibility.get("allowed_in_probation", True),
                "eligibility_minimum_tenure_months": eligibility.get("minimum_tenure_months", 0) or 0,
                "eligibility_employment_types": eligibility.get("employment_types") or [],
                "eligibility_locations": eligibility.get("locations") or [],
                "eligibility_departments": eligibility.get("departments") or [],
                "eligibility_job_levels": eligibility.get("job_levels") or [],
                "request_allow_half_day": request_policy.get("allow_half_day", True),
                "request_allow_hourly": request_policy.get("allow_hourly", False),
                "request_minimum_duration": cls._to_decimal(request_policy.get("minimum_duration")),
                "request_maximum_duration": cls._to_decimal(request_policy.get("maximum_duration")),
                "request_consecutive_days_limit": cls._to_decimal(request_policy.get("consecutive_days_limit")),
                "request_allow_prefix_suffix_holidays": request_policy.get("allow_prefix_suffix_holidays", True),
                "request_count_weekends_as_leave": request_policy.get("count_weekends_as_leave", False),
                "request_count_holidays_as_leave": request_policy.get("count_holidays_as_leave", False),
                "request_blackout_dates": blackout_dates,
                "request_requires_reason": request_policy.get("requires_reason", True),
                "request_requires_document": request_policy.get("requires_document", False),
                "request_document_mandatory_after_days": cls._to_decimal(request_policy.get("document_mandatory_after_days")),
                "approval_auto_approve": approval_policy.get("auto_approve", False),
                "approval_workflow_code": approval_policy.get("workflow_code", "DEFAULT"),
                "approval_fallback_approver": approval_policy.get("fallback_approver", "HR"),
                "approval_reminders_enabled": (approval_policy.get("reminders") or {}).get("enabled", True),
                "approval_reminder_after_hours": (approval_policy.get("reminders") or {}).get("after_hours", 48),
                "accrual_enabled": accrual_policy.get("enabled", False),
                "accrual_method": accrual_policy.get("method", "MONTHLY"),
                "accrual_rate_per_period": cls._to_decimal(accrual_policy.get("rate_per_period")) or Decimal("0.00"),
                "accrual_start_trigger": accrual_policy.get("start_trigger", "DATE_OF_JOINING"),
                "accrual_start_offset_days": accrual_policy.get("start_offset_days", 0) or 0,
                "accrual_waiting_period_days": accrual_policy.get("waiting_period_days", 0) or 0,
                "accrual_proration_method": (accrual_policy.get("proration") or {}).get("method"),
                "accrual_proration_on_join": (accrual_policy.get("proration") or {}).get("on_join", True),
                "accrual_proration_on_termination": (accrual_policy.get("proration") or {}).get("on_termination", True),
                "accrual_cap_enabled": (accrual_policy.get("cap") or {}).get("enabled", False),
                "accrual_cap_max_balance": cls._to_decimal((accrual_policy.get("cap") or {}).get("max_balance")),
                "carryover_enabled": carryover_policy.get("enabled", False),
                "carryover_max_carryover": cls._to_decimal(carryover_policy.get("max_carryover")),
                "carryover_expires_after_days": carryover_policy.get("expires_after_days"),
            },
        )

        steps = approval_policy.get("steps") or []
        if not _ and instance.approval_steps.exists():
            instance.approval_steps.using(db_alias).all().delete()
        for idx, step in enumerate(steps):
            TimeOffApprovalStep.objects.using(db_alias).create(
                leave_type=instance,
                step_index=idx,
                step_type=step.get("type", "MANAGER"),
                required=step.get("required", True),
            )

        return instance

    def to_config_dict(self) -> dict:
        approval_steps = [
            {"type": step.step_type, "required": step.required}
            for step in self.approval_steps.all().order_by("step_index")
        ]
        return {
            "code": self.code,
            "name": self.name,
            "paid": self.paid,
            "color": self.color,
            "description": self.description,
            "mobile_enabled": self.mobile_enabled,
            "balance_visible_to_employee": self.balance_visible_to_employee,
            "allow_encashment": self.allow_encashment,
            "encashment_rules": {
                "max_days": float(self.encashment_max_days) if self.encashment_max_days is not None else None,
                "conversion_rate": float(self.encashment_conversion_rate) if self.encashment_conversion_rate is not None else None,
            },
            "allow_comp_off_generation": self.allow_comp_off_generation,
            "comp_off_expiry_days": self.comp_off_expiry_days,
            "sandwich_rule_enabled": self.sandwich_rule_enabled,
            "eligibility": {
                "gender": self.eligibility_gender,
                "employment_types": self.eligibility_employment_types or [],
                "locations": self.eligibility_locations or [],
                "departments": self.eligibility_departments or [],
                "job_levels": self.eligibility_job_levels or [],
                "minimum_tenure_months": self.eligibility_minimum_tenure_months,
                "allowed_in_probation": self.eligibility_allowed_in_probation,
            },
            "allow_half_day": self.request_allow_half_day,
            "allow_hourly": self.request_allow_hourly,
            "minimum_duration": float(self.request_minimum_duration) if self.request_minimum_duration is not None else None,
            "maximum_duration": float(self.request_maximum_duration) if self.request_maximum_duration is not None else None,
            "consecutive_days_limit": float(self.request_consecutive_days_limit) if self.request_consecutive_days_limit is not None else None,
            "allow_prefix_suffix_holidays": self.request_allow_prefix_suffix_holidays,
            "count_weekends_as_leave": self.request_count_weekends_as_leave,
            "count_holidays_as_leave": self.request_count_holidays_as_leave,
            "requires_reason": self.request_requires_reason,
            "requires_document": self.request_requires_document,
            "document_mandatory_after_days": float(self.request_document_mandatory_after_days) if self.request_document_mandatory_after_days is not None else None,
            "request_policy": {
                "allow_half_day": self.request_allow_half_day,
                "allow_hourly": self.request_allow_hourly,
                "minimum_duration": float(self.request_minimum_duration) if self.request_minimum_duration is not None else None,
                "maximum_duration": float(self.request_maximum_duration) if self.request_maximum_duration is not None else None,
                "consecutive_days_limit": float(self.request_consecutive_days_limit) if self.request_consecutive_days_limit is not None else None,
                "allow_prefix_suffix_holidays": self.request_allow_prefix_suffix_holidays,
                "count_weekends_as_leave": self.request_count_weekends_as_leave,
                "count_holidays_as_leave": self.request_count_holidays_as_leave,
                "blackout_dates": [str(d) for d in self.request_blackout_dates or []],
                "requires_reason": self.request_requires_reason,
                "requires_document": self.request_requires_document,
                "document_mandatory_after_days": float(self.request_document_mandatory_after_days) if self.request_document_mandatory_after_days is not None else None,
            },
            "approval_policy": {
                "workflow_code": self.approval_workflow_code,
                "auto_approve": self.approval_auto_approve,
                "steps": approval_steps,
                "fallback_approver": self.approval_fallback_approver,
                "reminders": {
                    "enabled": self.approval_reminders_enabled,
                    "after_hours": self.approval_reminder_after_hours,
                },
            },
            "accrual_policy": {
                "enabled": self.accrual_enabled,
                "method": self.accrual_method,
                "rate_per_period": float(self.accrual_rate_per_period) if self.accrual_rate_per_period is not None else None,
                "start_trigger": self.accrual_start_trigger,
                "start_offset_days": self.accrual_start_offset_days,
                "waiting_period_days": self.accrual_waiting_period_days,
                "proration": {
                    "method": self.accrual_proration_method,
                    "on_join": self.accrual_proration_on_join,
                    "on_termination": self.accrual_proration_on_termination,
                },
                "cap": {
                    "enabled": self.accrual_cap_enabled,
                    "max_balance": float(self.accrual_cap_max_balance) if self.accrual_cap_max_balance is not None else None,
                },
            },
            "carryover_policy": {
                "enabled": self.carryover_enabled,
                "max_carryover": float(self.carryover_max_carryover) if self.carryover_max_carryover is not None else None,
                "expires_after_days": self.carryover_expires_after_days,
            },
            "approval_workflow": self.approval_workflow_code,
            "auto_approve": self.approval_auto_approve,
        }


class TimeOffApprovalStep(models.Model):
    """Represents a step in the approval workflow for a leave type."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    leave_type = models.ForeignKey(TimeOffType, related_name="approval_steps", on_delete=models.CASCADE)
    step_index = models.IntegerField(help_text="Zero-based index of the step")
    step_type = models.CharField(max_length=30, help_text="MANAGER | HR | ROLE")
    required = models.BooleanField(default=True)

    class Meta:
        db_table = "timeoff_type_approval_steps"
        ordering = ["step_index"]
        unique_together = [["leave_type", "step_index"]]

    def __str__(self):
        return f"{self.leave_type.code} step {self.step_index} ({self.step_type})"


def ensure_timeoff_configuration(employer_id: int, db_alias: str = "default") -> TimeOffConfiguration:
    """
    Fetch or create a configuration row and seed default leave types if none exist.
    """
    defaults = TimeOffConfiguration.build_defaults(employer_id)
    config, created = TimeOffConfiguration.objects.using(db_alias).get_or_create(
        employer_id=employer_id,
        defaults=defaults,
    )
    updates = []
    if config.tenant_id is None:
        config.tenant_id = employer_id
        updates.append("tenant_id")
    if not config.schema_version:
        config.schema_version = defaults["schema_version"]
        updates.append("schema_version")
    if updates:
        config.save(using=db_alias, update_fields=updates)
    existing_types = TimeOffType.objects.using(db_alias).filter(employer_id=employer_id).exists()
    if not existing_types:
        try:
            config.seed_default_leave_types(db_alias=db_alias)
        except IntegrityError:
            # If parallel requests attempt seeding, just proceed with existing rows.
            pass
    return config


class TimeOffRequest(models.Model):
    """Represents a time off request made by an employee."""

    INPUT_CHOICES = [
        ("FULL_DAY", "Full Day"),
        ("HALF_DAY", "Half Day"),
        ("CUSTOM_HOURS", "Custom Hours"),
    ]

    HALF_DAY_PERIOD_CHOICES = [
        ("MORNING", "Morning"),
        ("AFTERNOON", "Afternoon"),
    ]

    UNIT_CHOICES = [
        ("DAYS", "Days"),
        ("HALF_DAYS", "Half Days"),
        ("HOURS", "Hours"),
    ]

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("PENDING", "Pending Approval"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="Tenant identifier")
    employer_id = models.IntegerField(db_index=True, help_text="Employer/tenant identifier (main DB)")
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="time_off_requests",
        help_text="Employee requesting time off",
    )
    leave_type_code = models.CharField(max_length=50, db_index=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    input_type = models.CharField(max_length=20, choices=INPUT_CHOICES, default="FULL_DAY")
    half_day_period = models.CharField(
        max_length=20,
        choices=HALF_DAY_PERIOD_CHOICES,
        blank=True,
        null=True,
        help_text="Relevant when input_type is HALF_DAY",
    )
    from_time = models.TimeField(blank=True, null=True, help_text="For custom hours start time")
    to_time = models.TimeField(blank=True, null=True, help_text="For custom hours end time")
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default="DAYS")
    duration_minutes = models.IntegerField(help_text="Normalized duration in minutes")
    reason = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True, help_text="User-provided description/reason")
    attachments = models.JSONField(default=list, blank=True, help_text="Attachment metadata (if any)")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="DRAFT", db_index=True)

    submitted_at = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    rejected_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    created_by = models.IntegerField(help_text="User ID from main DB", db_index=True)
    updated_by = models.IntegerField(help_text="User ID from main DB", db_index=True)

    metadata = models.JSONField(default=dict, blank=True, help_text="Device/location/additional context")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "timeoff_requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["employer_id", "employee"]),
            models.Index(fields=["employer_id", "leave_type_code"]),
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["start_at", "end_at"]),
        ]

    def __str__(self):
        return f"{self.leave_type_code} request by {self.employee_id} ({self.status})"

    @property
    def is_editable(self) -> bool:
        return self.status in ["DRAFT", "SUBMITTED"]

    def mark_submitted(self):
        self.status = "SUBMITTED"
        self.submitted_at = timezone.now()

    def mark_pending(self):
        self.status = "PENDING"
        if not self.submitted_at:
            self.submitted_at = timezone.now()

    def mark_approved(self):
        self.status = "APPROVED"
        self.approved_at = timezone.now()

    def mark_rejected(self):
        self.status = "REJECTED"
        self.rejected_at = timezone.now()

    def mark_cancelled(self):
        self.status = "CANCELLED"
        self.cancelled_at = timezone.now()


class TimeOffApproval(models.Model):
    """Tracks approval steps for a time off request."""

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("SKIPPED", "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        TimeOffRequest,
        on_delete=models.CASCADE,
        related_name="approvals",
        help_text="Request this approval belongs to",
    )
    step_index = models.IntegerField(help_text="Zero-based index of the step")
    approver_user_id = models.IntegerField(db_index=True, help_text="User ID in main DB")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    comment = models.TextField(blank=True, null=True)
    acted_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "timeoff_approvals"
        ordering = ["request_id", "step_index"]
        unique_together = [["request", "step_index", "approver_user_id"]]

    def __str__(self):
        return f"Approval step {self.step_index} for {self.request_id} ({self.status})"


class TimeOffLedgerEntry(models.Model):
    """Immutable ledger entries used to compute balances."""

    ENTRY_TYPES = [
        ("ACCRUAL", "Accrual"),
        ("ALLOCATION", "Allocation"),
        ("ADJUSTMENT", "Adjustment"),
        ("RESERVATION", "Reservation"),
        ("DEBIT", "Debit"),
        ("REVERSAL", "Reversal"),
        ("CARRYOVER", "Carryover"),
        ("EXPIRY", "Expiry"),
        ("ENCASHMENT", "Encashment"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer/tenant identifier (main DB)")
    tenant_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Alias for employer/tenant identifier to simplify lookups",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="time_off_ledger_entries",
        help_text="Employee affected by this entry",
    )
    leave_type_code = models.CharField(max_length=50, db_index=True)
    entry_type = models.CharField(max_length=15, choices=ENTRY_TYPES, db_index=True)
    amount_minutes = models.IntegerField(help_text="Positive/negative minutes; immutable once saved")
    effective_date = models.DateField(default=date.today, help_text="Date the entry applies to")
    request = models.ForeignKey(
        TimeOffRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
        help_text="Linked request (if any)",
    )
    allocation = models.ForeignKey(
        "timeoff.TimeOffAllocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
        help_text="Linked allocation (if any)",
    )
    allocation_request = models.ForeignKey(
        "timeoff.TimeOffAllocationRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
        help_text="Linked allocation request (if any)",
    )
    notes = models.TextField(blank=True, null=True)
    created_by = models.IntegerField(help_text="User ID from main DB", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "timeoff_ledger_entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "employee"]),
            models.Index(fields=["employer_id", "leave_type_code"]),
            models.Index(fields=["entry_type"]),
            models.Index(fields=["effective_date"]),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount_minutes}m for {self.leave_type_code}"


class TimeOffAllocation(models.Model):
    """Represents a granted or accrual-based allocation header."""

    ALLOCATION_TYPES = [
        ("REGULAR", "Regular"),
        ("ACCRUAL", "Accrual"),
    ]

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("CONFIRMED", "Confirmed"),
        ("CANCELLED", "Cancelled"),
    ]

    UNIT_CHOICES = [
        ("DAYS", "Days"),
        ("HOURS", "Hours"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="Tenant identifier")
    employer_id = models.IntegerField(db_index=True, help_text="Employer/tenant identifier")
    name = models.CharField(max_length=255)
    leave_type_code = models.CharField(max_length=50, db_index=True)
    allocation_type = models.CharField(max_length=10, choices=ALLOCATION_TYPES, default="REGULAR")
    amount = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="time_off_allocations",
    )
    accrual_plan = models.ForeignKey(
        "timeoff.TimeOffAccrualPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="allocations",
    )
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="DRAFT", db_index=True)
    created_by = models.IntegerField(help_text="User ID from main DB", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "timeoff_allocations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "leave_type_code"], name="timeoff_alloc_emp_lt_idx"),
            models.Index(fields=["status"], name="timeoff_alloc_status_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.allocation_type})"


class TimeOffAllocationLine(models.Model):
    """Individual employees receiving an allocation (supports bulk)."""

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("CONFIRMED", "Confirmed"),
        ("CANCELLED", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    allocation = models.ForeignKey(
        TimeOffAllocation,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="time_off_allocation_lines",
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="DRAFT", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "timeoff_allocation_lines"
        ordering = ["created_at"]
        unique_together = [["allocation", "employee"]]

    def __str__(self):
        return f"Allocation line {self.allocation_id} -> {self.employee_id}"


class TimeOffAccrualPlan(models.Model):
    """Accrual plan definition used for subscriptions."""

    FREQUENCY_CHOICES = [
        ("MONTHLY", "Monthly"),
    ]

    GAIN_TIME_CHOICES = [
        ("START", "At period start"),
        ("END", "At period end"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    employer_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default="MONTHLY")
    amount_minutes = models.IntegerField(default=0, help_text="Minutes accrued per period")
    accrual_gain_time = models.CharField(max_length=10, choices=GAIN_TIME_CHOICES, default="START")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "timeoff_accrual_plans"
        ordering = ["name"]

    def __str__(self):
        return self.name


class TimeOffAccrualSubscription(models.Model):
    """Links employees to an accrual plan and allocation header."""

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("ENDED", "Ended"),
        ("CANCELLED", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    allocation = models.ForeignKey(
        TimeOffAllocation,
        on_delete=models.CASCADE,
        related_name="accrual_subscriptions",
        null=True,
        blank=True,
    )
    plan = models.ForeignKey(
        TimeOffAccrualPlan,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="time_off_accrual_subscriptions",
    )
    leave_type_code = models.CharField(max_length=50, db_index=True)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    last_accrual_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ACTIVE", db_index=True)
    created_by = models.IntegerField(help_text="User ID from main DB", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "timeoff_accrual_subscriptions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["leave_type_code"], name="timeoff_accrual_lt_idx"),
            models.Index(fields=["status"], name="timeoff_accrual_status_idx"),
        ]

    def __str__(self):
        return f"{self.employee_id} -> {self.plan_id}"


class TimeOffAllocationRequest(models.Model):
    """Employee-initiated allocation requests for extra leave."""

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
    ]

    UNIT_CHOICES = [
        ("DAYS", "Days"),
        ("HOURS", "Hours"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    employer_id = models.IntegerField(db_index=True)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="time_off_allocation_requests",
    )
    leave_type_code = models.CharField(max_length=50, db_index=True)
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    acted_at = models.DateTimeField(blank=True, null=True)
    acted_by = models.IntegerField(blank=True, null=True, help_text="Approver user id")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "timeoff_allocation_requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "leave_type_code"], name="timeoff_allocreq_emp_lt_idx"),
            models.Index(fields=["status"], name="timeoff_allocreq_status_idx"),
        ]

    def __str__(self):
        return f"Allocation request {self.leave_type_code} for {self.employee_id} ({self.status})"
