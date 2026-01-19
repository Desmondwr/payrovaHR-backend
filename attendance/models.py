import uuid
from datetime import datetime
from typing import Optional

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from employees.models import Employee


class AttendanceConfiguration(models.Model):
    """
    Tenant-scoped attendance configuration (one active row per employer).
    Stored as columns only (no JSON).
    """

    KIOSK_MODE_MANUAL = "manual"
    KIOSK_MODE_BARCODE = "barcode_rfid"
    KIOSK_MODE_COMBINED = "barcode_rfid_and_manual"
    KIOSK_MODE_CHOICES = [
        (KIOSK_MODE_MANUAL, "Manual Selection"),
        (KIOSK_MODE_BARCODE, "Barcode/RFID Only"),
        (KIOSK_MODE_COMBINED, "Barcode/RFID + Manual"),
    ]

    BARCODE_SOURCE_SCANNER = "scanner"
    BARCODE_SOURCE_FRONT_CAMERA = "front_camera"
    BARCODE_SOURCE_BACK_CAMERA = "back_camera"
    BARCODE_SOURCE_CHOICES = [
        (BARCODE_SOURCE_SCANNER, "Scanner"),
        (BARCODE_SOURCE_FRONT_CAMERA, "Front Camera"),
        (BARCODE_SOURCE_BACK_CAMERA, "Back Camera"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer/company id from main database")
    is_enabled = models.BooleanField(default=True)
    allow_systray_portal = models.BooleanField(default=True)
    allow_kiosk = models.BooleanField(default=True)
    kiosk_mode = models.CharField(max_length=40, choices=KIOSK_MODE_CHOICES, default=KIOSK_MODE_COMBINED)
    barcode_source = models.CharField(max_length=20, choices=BARCODE_SOURCE_CHOICES, blank=True, null=True)
    kiosk_display_seconds = models.IntegerField(default=5, validators=[MinValueValidator(1)])
    require_pin_for_kiosk = models.BooleanField(default=False)
    require_pin_for_portal = models.BooleanField(default=False)
    enforce_geofence = models.BooleanField(default=True)
    enforce_wifi = models.BooleanField(default=False)
    enforce_geofence_on_checkout = models.BooleanField(default=True)
    enforce_wifi_on_checkout = models.BooleanField(default=False)
    allow_mobile_gps = models.BooleanField(default=True)
    allow_ip_logging = models.BooleanField(default=True)
    allow_gps_logging = models.BooleanField(default=True)
    timezone = models.CharField(max_length=64, default="UTC")
    auto_flag_anomalies = models.BooleanField(default=True)
    max_daily_work_minutes_before_flag = models.IntegerField(blank=True, null=True)
    kiosk_bypass_geofence = models.BooleanField(default=True)
    kiosk_bypass_wifi = models.BooleanField(default=True)
    kiosk_access_token = models.CharField(
        max_length=64,
        default="",
        blank=True,
        help_text="Opaque token to protect kiosk endpoints",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_configurations"
        verbose_name = "Attendance Configuration"
        verbose_name_plural = "Attendance Configurations"
        constraints = [
            models.UniqueConstraint(
                fields=["employer_id"],
                condition=Q(is_enabled=True),
                name="uniq_attendance_config_active_per_employer",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.kiosk_access_token:
            self.kiosk_access_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Attendance Config for employer {self.employer_id}"


class AttendanceLocationSite(models.Model):
    """
    Allowed physical sites for attendance geofencing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    branch = models.ForeignKey(
        "employees.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_sites",
        help_text="Branch this site belongs to (optional for global sites).",
    )
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    radius_meters = models.IntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_location_sites"
        verbose_name = "Attendance Location Site"
        verbose_name_plural = "Attendance Location Sites"
        unique_together = [["employer_id", "branch", "name"]]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
            models.Index(fields=["latitude", "longitude"]),
            models.Index(fields=["employer_id", "branch"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.employer_id})"


class AttendanceAllowedWifi(models.Model):
    """
    Allowed Wi-Fi networks for check-in/out validation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    branch = models.ForeignKey(
        "employees.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_wifi_networks",
        help_text="Branch this Wi-Fi is restricted to (optional for global).",
    )
    site = models.ForeignKey(
        AttendanceLocationSite,
        on_delete=models.CASCADE,
        related_name="wifi_networks",
        blank=True,
        null=True,
    )
    ssid = models.CharField(max_length=255)
    bssid = models.CharField(max_length=64, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_allowed_wifi"
        verbose_name = "Attendance Allowed Wi-Fi"
        verbose_name_plural = "Attendance Allowed Wi-Fi"
        constraints = [
            models.UniqueConstraint(
                fields=["employer_id", "branch", "ssid", "bssid"], name="uniq_attendance_wifi_entry"
            ),
        ]
        indexes = [
            models.Index(fields=["employer_id", "ssid"]),
            models.Index(fields=["employer_id", "bssid"]),
            models.Index(fields=["employer_id", "branch"]),
        ]

    def __str__(self):
        return f"{self.ssid} ({self.bssid or 'no bssid'})"


class AttendanceKioskStation(models.Model):
    """
    Branch-scoped kiosk stations with their own access token/slug.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    branch = models.ForeignKey(
        "employees.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_kiosk_stations",
    )
    name = models.CharField(max_length=255)
    kiosk_token = models.CharField(max_length=64, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_kiosk_stations"
        verbose_name = "Attendance Kiosk Station"
        verbose_name_plural = "Attendance Kiosk Stations"
        indexes = [
            models.Index(fields=["employer_id", "branch", "is_active"]),
        ]

    def save(self, *args, **kwargs):
        if not self.kiosk_token:
            self.kiosk_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.branch_id or 'no branch'})"


class WorkingSchedule(models.Model):
    """
    Simplified working schedule (per employer).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default="UTC")
    default_daily_minutes = models.IntegerField(default=480, validators=[MinValueValidator(1)])
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_working_schedules"
        verbose_name = "Working Schedule"
        verbose_name_plural = "Working Schedules"
        unique_together = [["employer_id", "name"]]
        constraints = [
            models.UniqueConstraint(
                fields=["employer_id"],
                condition=Q(is_default=True),
                name="uniq_default_working_schedule_per_employer",
            )
        ]
        indexes = [
            models.Index(fields=["employer_id", "is_default"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.employer_id})"


class WorkingScheduleDay(models.Model):
    """
    Weekday-specific rules for a working schedule.
    """

    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(WorkingSchedule, on_delete=models.CASCADE, related_name="days")
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    expected_minutes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_working_schedule_days"
        verbose_name = "Working Schedule Day"
        verbose_name_plural = "Working Schedule Days"
        unique_together = [["schedule", "weekday"]]
        constraints = [
            models.CheckConstraint(
                check=Q(end_time__gt=F("start_time")),
                name="working_schedule_day_end_after_start",
            )
        ]

    def save(self, *args, **kwargs):
        start_dt = datetime.combine(datetime.today(), self.start_time)
        end_dt = datetime.combine(datetime.today(), self.end_time)
        delta = end_dt - start_dt
        total_minutes = int(delta.total_seconds() // 60)
        total_minutes = max(total_minutes - int(self.break_minutes or 0), 0)
        self.expected_minutes = total_minutes
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_weekday_display()} - {self.schedule.name}"


class AttendanceRecord(models.Model):
    """
    Clock-in/out records with geofence and Wi-Fi context.
    """

    STATUS_TO_APPROVE = "to_approve"
    STATUS_APPROVED = "approved"
    STATUS_REFUSED = "refused"
    STATUS_CHOICES = [
        (STATUS_TO_APPROVE, "To Approve"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REFUSED, "Refused"),
    ]

    MODE_PORTAL = "portal_systray"
    MODE_KIOSK = "kiosk"
    MODE_MANUAL = "manual"
    MODE_CHOICES = [
        (MODE_PORTAL, "Portal/Systray"),
        (MODE_KIOSK, "Kiosk"),
        (MODE_MANUAL, "Manual"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="attendance_records")
    check_in_at = models.DateTimeField()
    check_out_at = models.DateTimeField(blank=True, null=True)
    worked_minutes = models.IntegerField(default=0)
    expected_minutes = models.IntegerField(blank=True, null=True)
    overtime_worked_minutes = models.IntegerField(default=0)
    overtime_approved_minutes = models.IntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_APPROVED, db_index=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_PORTAL, db_index=True)
    check_in_ip = models.GenericIPAddressField(blank=True, null=True)
    check_in_latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    check_in_longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    check_in_site = models.ForeignKey(
        AttendanceLocationSite,
        on_delete=models.SET_NULL,
        related_name="check_in_records",
        blank=True,
        null=True,
    )
    check_in_wifi_ssid = models.CharField(max_length=255, blank=True, null=True)
    check_in_wifi_bssid = models.CharField(max_length=64, blank=True, null=True)
    check_out_ip = models.GenericIPAddressField(blank=True, null=True)
    check_out_latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    check_out_longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    check_out_site = models.ForeignKey(
        AttendanceLocationSite,
        on_delete=models.SET_NULL,
        related_name="check_out_records",
        blank=True,
        null=True,
    )
    check_out_wifi_ssid = models.CharField(max_length=255, blank=True, null=True)
    check_out_wifi_bssid = models.CharField(max_length=64, blank=True, null=True)
    anomaly_reason = models.CharField(max_length=255, blank=True, null=True)
    created_by_id = models.IntegerField(blank=True, null=True, db_index=True)
    kiosk_session_reference = models.CharField(max_length=100, blank=True, null=True)
    kiosk_station = models.ForeignKey(
        "AttendanceKioskStation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_records",
        help_text="Branch kiosk station used for this record.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_records"
        verbose_name = "Attendance Record"
        verbose_name_plural = "Attendance Records"
        ordering = ["-check_in_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(check_out_at__isnull=True),
                name="uniq_open_attendance_record_per_employee",
            ),
            models.CheckConstraint(
                check=Q(check_out_at__gt=F("check_in_at")) | Q(check_out_at__isnull=True),
                name="attendance_checkout_after_checkin",
            ),
        ]
        indexes = [
            models.Index(fields=["employer_id", "employee"]),
            models.Index(fields=["status"]),
            models.Index(fields=["mode"]),
            models.Index(fields=["check_in_at"]),
        ]

    def compute_worked_minutes(self) -> int:
        end_time = self.check_out_at or timezone.now()
        delta = end_time - self.check_in_at
        minutes = int(delta.total_seconds() // 60)
        return max(minutes, 0)

    def mark_checkout(self, checkout_time: Optional[datetime] = None) -> None:
        self.check_out_at = checkout_time or timezone.now()
        self.worked_minutes = self.compute_worked_minutes()
        overtime = 0
        if self.expected_minutes:
            overtime = max(self.worked_minutes - int(self.expected_minutes), 0)
        self.overtime_worked_minutes = overtime

    def __str__(self):
        return f"{self.employee_id} @ {self.check_in_at}"
