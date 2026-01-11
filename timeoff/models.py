import uuid
from django.db import models
from django.core.exceptions import ValidationError
from datetime import date
from django.utils import timezone
from .defaults import (
    get_time_off_defaults,
    merge_time_off_defaults,
    validate_time_off_config,
)


class TimeOffConfiguration(models.Model):
    """
    Tenant-scoped configuration for the Time Off module.
    Stores global settings and leave-type definitions as JSON.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")
    tenant_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Alias for employer_id to support tenant-aware queries",
    )
    schema_version = models.IntegerField(default=1, help_text="Schema version for normalization")
    default_time_unit = models.CharField(max_length=10, default="DAYS")
    working_hours_per_day = models.IntegerField(default=8)
    leave_year_type = models.CharField(max_length=10, default="CALENDAR")
    leave_year_start_month = models.IntegerField(default=1)
    holiday_calendar_source = models.CharField(max_length=20, default="DEFAULT")
    time_zone_handling = models.CharField(max_length=30, default="EMPLOYER_LOCAL")
    reservation_policy = models.CharField(max_length=30, default="RESERVE_ON_SUBMIT")
    rounding_increment_minutes = models.IntegerField(default=30)
    rounding_method = models.CharField(max_length=10, default="NEAREST")
    weekend_days = models.JSONField(default=list, blank=True)
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
    configuration = models.JSONField(
        default=get_time_off_defaults,
        blank=True,
        help_text="Time off configuration payload (global + leave types)",
    )
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

    def clean(self):
        """Validate configuration before saving."""
        merged = merge_time_off_defaults(self.configuration or {})
        errors = validate_time_off_config(merged)
        if errors:
            raise ValidationError(errors)
        self.configuration = merged
        self._sync_columns_from_config(merged)

    def save(self, *args, **kwargs):
        # Ensure defaults + validation run on every save
        self.clean()
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        super().save(*args, **kwargs)

    def _sync_columns_from_config(self, cfg):
        """Populate columnized fields from the normalized configuration."""
        global_settings = (cfg or {}).get("global_settings", {}) or {}
        self.schema_version = cfg.get("schema_version") or global_settings.get("schema_version") or 1
        self.default_time_unit = global_settings.get("default_time_unit", "DAYS")
        self.working_hours_per_day = global_settings.get("working_hours_per_day", 8)
        self.leave_year_type = global_settings.get("leave_year_type", "CALENDAR")
        self.leave_year_start_month = global_settings.get("leave_year_start_month", 1)
        self.holiday_calendar_source = global_settings.get("holiday_calendar_source", "DEFAULT")
        self.time_zone_handling = global_settings.get("time_zone_handling", "EMPLOYER_LOCAL")
        self.reservation_policy = global_settings.get("reservation_policy", "RESERVE_ON_SUBMIT")

        rounding = global_settings.get("rounding") or {}
        self.rounding_increment_minutes = rounding.get("increment_minutes", 30) or 0
        self.rounding_method = rounding.get("method", "NEAREST") or "NEAREST"
        self.weekend_days = global_settings.get("weekend_days") or []

        self.module_enabled = global_settings.get("module_enabled", True)
        self.allow_backdated_requests = global_settings.get("allow_backdated_requests", True)
        self.allow_future_dated_requests = global_settings.get("allow_future_dated_requests", True)
        self.allow_negative_balance = global_settings.get("allow_negative_balance", False)
        self.negative_balance_limit = global_settings.get("negative_balance_limit", 0) or 0
        self.allow_overlapping_requests = global_settings.get("allow_overlapping_requests", False)
        self.backdated_limit_days = global_settings.get("backdated_limit_days", 30) or 0
        self.future_window_days = global_settings.get("future_window_days", 180) or 0
        self.max_request_length_days = global_settings.get("max_request_length_days")
        self.max_requests_per_month = global_settings.get("max_requests_per_month")


class TimeOffRequest(models.Model):
    """Represents a time off request made by an employee."""

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
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default="DAYS")
    duration_minutes = models.IntegerField(help_text="Normalized duration in minutes")
    reason = models.TextField(blank=True, null=True)
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
