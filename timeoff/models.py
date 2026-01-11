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

    def save(self, *args, **kwargs):
        # Ensure defaults + validation run on every save
        self.clean()
        super().save(*args, **kwargs)


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
