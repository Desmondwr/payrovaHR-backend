import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from employees.models import Branch, Department, Employee
from .defaults import ATTENDANCE_DEFAULTS


class AttendancePolicy(models.Model):
    """Hierarchical attendance policy overrides (global -> branch -> department -> employee)."""

    SCOPE_GLOBAL = "GLOBAL"
    SCOPE_BRANCH = "BRANCH"
    SCOPE_DEPARTMENT = "DEPARTMENT"
    SCOPE_EMPLOYEE = "EMPLOYEE"

    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_BRANCH, "Branch"),
        (SCOPE_DEPARTMENT, "Department"),
        (SCOPE_EMPLOYEE, "Employee"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_GLOBAL)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True)
    schema_version = models.IntegerField(default=1)

    working_timezone = models.CharField(max_length=50, null=True, blank=True)
    working_days = ArrayField(models.CharField(max_length=10), null=True, blank=True)
    weekend_days = ArrayField(models.CharField(max_length=10), null=True, blank=True)
    holiday_calendar_source = models.CharField(max_length=20, null=True, blank=True)
    holiday_dates = ArrayField(models.DateField(), null=True, blank=True)
    special_days = ArrayField(models.DateField(), null=True, blank=True)

    allow_self_check_in = models.BooleanField(null=True, blank=True)
    allow_manual_edits = models.BooleanField(null=True, blank=True)
    allow_device_only = models.BooleanField(null=True, blank=True)
    max_early_check_in_minutes = models.IntegerField(null=True, blank=True)
    max_late_check_out_minutes = models.IntegerField(null=True, blank=True)
    duplicate_punch_handling = models.CharField(max_length=20, null=True, blank=True)
    missing_punch_handling = models.CharField(max_length=20, null=True, blank=True)
    allow_employee_correction = models.BooleanField(null=True, blank=True)
    late_grace_minutes = models.IntegerField(null=True, blank=True)
    early_grace_minutes = models.IntegerField(null=True, blank=True)
    rounding_unit = models.CharField(max_length=20, null=True, blank=True)
    rounding_increment = models.IntegerField(null=True, blank=True)
    rounding_method = models.CharField(max_length=10, null=True, blank=True)
    rounding_in_rounding = models.CharField(max_length=10, null=True, blank=True)
    rounding_out_rounding = models.CharField(max_length=10, null=True, blank=True)
    require_edit_reason = models.BooleanField(null=True, blank=True)
    edit_approval_after_days = models.IntegerField(null=True, blank=True)

    overtime_starts_after_minutes = models.IntegerField(null=True, blank=True)
    overtime_minimum_minutes = models.IntegerField(null=True, blank=True)
    overtime_require_approval = models.BooleanField(null=True, blank=True)
    overtime_rate_weekday = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    overtime_rate_weekend = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    overtime_rate_holiday = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    max_overtime_minutes_per_day = models.IntegerField(null=True, blank=True)

    shift_assignment_strategy = models.CharField(max_length=20, null=True, blank=True)
    default_shift_template = models.ForeignKey(
        "ShiftTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_policy_for",
    )

    payroll_count_worked_minutes = models.BooleanField(null=True, blank=True)
    payroll_count_approved_overtime_only = models.BooleanField(null=True, blank=True)
    payroll_late_penalty_mode = models.CharField(max_length=30, null=True, blank=True)
    payroll_absence_penalty_mode = models.CharField(max_length=30, null=True, blank=True)

    geo_enabled = models.BooleanField(null=True, blank=True)
    geo_radius_meters = models.IntegerField(null=True, blank=True)
    geo_allowed_locations = ArrayField(
        models.CharField(max_length=100),
        null=True,
        blank=True,
        help_text="List of allowed coordinates or location identifiers.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_policies"
        verbose_name = "Attendance Policy"
        verbose_name_plural = "Attendance Policies"
        indexes = [
            models.Index(fields=["employer_id", "scope_type"]),
            models.Index(fields=["employer_id", "branch"]),
            models.Index(fields=["employer_id", "department"]),
            models.Index(fields=["employer_id", "employee"]),
        ]

    def __str__(self):
        return f"Attendance Policy {self.scope_type} (Employer {self.employer_id})"

    @staticmethod
    def _set_if(target: dict, key: str, value, include_null: bool) -> None:
        if value is None and not include_null:
            return
        target[key] = value

    @classmethod
    def build_defaults(cls, employer_id: int) -> dict:
        defaults = ATTENDANCE_DEFAULTS
        calendar = defaults.get("working_calendar") or {}
        attendance_policy = defaults.get("attendance_policy") or {}
        rounding = attendance_policy.get("rounding") or {}
        overtime_policy = defaults.get("overtime_policy") or {}
        rates = overtime_policy.get("rate_categories") or {}
        shift_policy = defaults.get("shift_policy") or {}
        payroll_mapping = defaults.get("payroll_mapping") or {}
        geo_rules = defaults.get("geo_rules") or {}

        return {
            "employer_id": employer_id,
            "schema_version": defaults.get("schema_version", 1),
            "working_timezone": calendar.get("timezone"),
            "working_days": calendar.get("working_days"),
            "weekend_days": calendar.get("weekend_days"),
            "holiday_calendar_source": calendar.get("holiday_calendar_source"),
            "holiday_dates": calendar.get("holiday_dates"),
            "special_days": calendar.get("special_days"),
            "allow_self_check_in": attendance_policy.get("allow_self_check_in"),
            "allow_manual_edits": attendance_policy.get("allow_manual_edits"),
            "allow_device_only": attendance_policy.get("allow_device_only"),
            "max_early_check_in_minutes": attendance_policy.get("max_early_check_in_minutes"),
            "max_late_check_out_minutes": attendance_policy.get("max_late_check_out_minutes"),
            "duplicate_punch_handling": attendance_policy.get("duplicate_punch_handling"),
            "missing_punch_handling": attendance_policy.get("missing_punch_handling"),
            "allow_employee_correction": attendance_policy.get("allow_employee_correction"),
            "late_grace_minutes": attendance_policy.get("late_grace_minutes"),
            "early_grace_minutes": attendance_policy.get("early_grace_minutes"),
            "rounding_unit": rounding.get("unit"),
            "rounding_increment": rounding.get("increment"),
            "rounding_method": rounding.get("method"),
            "rounding_in_rounding": rounding.get("in_rounding"),
            "rounding_out_rounding": rounding.get("out_rounding"),
            "require_edit_reason": attendance_policy.get("require_edit_reason"),
            "edit_approval_after_days": attendance_policy.get("edit_approval_after_days"),
            "overtime_starts_after_minutes": overtime_policy.get("starts_after_minutes"),
            "overtime_minimum_minutes": overtime_policy.get("minimum_minutes"),
            "overtime_require_approval": overtime_policy.get("require_approval"),
            "overtime_rate_weekday": rates.get("WEEKDAY"),
            "overtime_rate_weekend": rates.get("WEEKEND"),
            "overtime_rate_holiday": rates.get("HOLIDAY"),
            "max_overtime_minutes_per_day": overtime_policy.get("max_overtime_minutes_per_day"),
            "shift_assignment_strategy": shift_policy.get("assignment_strategy"),
            "payroll_count_worked_minutes": payroll_mapping.get("count_worked_minutes"),
            "payroll_count_approved_overtime_only": payroll_mapping.get("count_approved_overtime_only"),
            "payroll_late_penalty_mode": payroll_mapping.get("late_penalty_mode"),
            "payroll_absence_penalty_mode": payroll_mapping.get("absence_penalty_mode"),
            "geo_enabled": geo_rules.get("enabled"),
            "geo_radius_meters": geo_rules.get("radius_meters"),
            "geo_allowed_locations": geo_rules.get("allowed_locations"),
        }

    def to_policy_dict(self, include_null: bool = False) -> dict:
        policy: dict = {}

        working_calendar: dict = {}
        self._set_if(working_calendar, "timezone", self.working_timezone, include_null)
        self._set_if(working_calendar, "working_days", self.working_days, include_null)
        self._set_if(working_calendar, "weekend_days", self.weekend_days, include_null)
        self._set_if(working_calendar, "holiday_calendar_source", self.holiday_calendar_source, include_null)
        self._set_if(working_calendar, "holiday_dates", self.holiday_dates, include_null)
        self._set_if(working_calendar, "special_days", self.special_days, include_null)
        if working_calendar or include_null:
            policy["working_calendar"] = working_calendar

        attendance_policy: dict = {}
        self._set_if(attendance_policy, "allow_self_check_in", self.allow_self_check_in, include_null)
        self._set_if(attendance_policy, "allow_manual_edits", self.allow_manual_edits, include_null)
        self._set_if(attendance_policy, "allow_device_only", self.allow_device_only, include_null)
        self._set_if(attendance_policy, "max_early_check_in_minutes", self.max_early_check_in_minutes, include_null)
        self._set_if(attendance_policy, "max_late_check_out_minutes", self.max_late_check_out_minutes, include_null)
        self._set_if(attendance_policy, "duplicate_punch_handling", self.duplicate_punch_handling, include_null)
        self._set_if(attendance_policy, "missing_punch_handling", self.missing_punch_handling, include_null)
        self._set_if(attendance_policy, "allow_employee_correction", self.allow_employee_correction, include_null)
        self._set_if(attendance_policy, "late_grace_minutes", self.late_grace_minutes, include_null)
        self._set_if(attendance_policy, "early_grace_minutes", self.early_grace_minutes, include_null)
        self._set_if(attendance_policy, "require_edit_reason", self.require_edit_reason, include_null)
        self._set_if(attendance_policy, "edit_approval_after_days", self.edit_approval_after_days, include_null)

        rounding: dict = {}
        self._set_if(rounding, "unit", self.rounding_unit, include_null)
        self._set_if(rounding, "increment", self.rounding_increment, include_null)
        self._set_if(rounding, "method", self.rounding_method, include_null)
        self._set_if(rounding, "in_rounding", self.rounding_in_rounding, include_null)
        self._set_if(rounding, "out_rounding", self.rounding_out_rounding, include_null)
        if rounding or include_null:
            attendance_policy["rounding"] = rounding

        if attendance_policy or include_null:
            policy["attendance_policy"] = attendance_policy

        overtime_policy: dict = {}
        self._set_if(overtime_policy, "starts_after_minutes", self.overtime_starts_after_minutes, include_null)
        self._set_if(overtime_policy, "minimum_minutes", self.overtime_minimum_minutes, include_null)
        self._set_if(overtime_policy, "require_approval", self.overtime_require_approval, include_null)
        self._set_if(overtime_policy, "max_overtime_minutes_per_day", self.max_overtime_minutes_per_day, include_null)

        rate_categories: dict = {}
        self._set_if(rate_categories, "WEEKDAY", self.overtime_rate_weekday, include_null)
        self._set_if(rate_categories, "WEEKEND", self.overtime_rate_weekend, include_null)
        self._set_if(rate_categories, "HOLIDAY", self.overtime_rate_holiday, include_null)
        if rate_categories or include_null:
            overtime_policy["rate_categories"] = rate_categories

        if overtime_policy or include_null:
            policy["overtime_policy"] = overtime_policy

        shift_policy: dict = {}
        self._set_if(shift_policy, "assignment_strategy", self.shift_assignment_strategy, include_null)
        self._set_if(
            shift_policy,
            "default_shift_template_id",
            str(self.default_shift_template_id) if self.default_shift_template_id else None,
            include_null,
        )
        if shift_policy or include_null:
            policy["shift_policy"] = shift_policy

        payroll_mapping: dict = {}
        self._set_if(payroll_mapping, "count_worked_minutes", self.payroll_count_worked_minutes, include_null)
        self._set_if(
            payroll_mapping,
            "count_approved_overtime_only",
            self.payroll_count_approved_overtime_only,
            include_null,
        )
        self._set_if(payroll_mapping, "late_penalty_mode", self.payroll_late_penalty_mode, include_null)
        self._set_if(payroll_mapping, "absence_penalty_mode", self.payroll_absence_penalty_mode, include_null)
        if payroll_mapping or include_null:
            policy["payroll_mapping"] = payroll_mapping

        geo_rules: dict = {}
        self._set_if(geo_rules, "enabled", self.geo_enabled, include_null)
        self._set_if(geo_rules, "radius_meters", self.geo_radius_meters, include_null)
        self._set_if(geo_rules, "allowed_locations", self.geo_allowed_locations, include_null)
        if geo_rules or include_null:
            policy["geo_rules"] = geo_rules

        return policy


class ShiftTemplate(models.Model):
    """Reusable shift template with rules for lateness and overtime."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.IntegerField(default=0)
    late_grace_minutes = models.IntegerField(default=0)
    early_grace_minutes = models.IntegerField(default=0)
    overtime_starts_after_minutes = models.IntegerField(default=0)
    requires_checkout = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_shift_templates"
        verbose_name = "Shift Template"
        verbose_name_plural = "Shift Templates"
        unique_together = [["employer_id", "name"]]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"

    @property
    def is_overnight(self):
        return self.end_time <= self.start_time


class EmployeeSchedule(models.Model):
    """Assign shift templates to employees over date ranges."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="schedules")
    shift_template = models.ForeignKey(ShiftTemplate, on_delete=models.PROTECT, related_name="assignments")
    date_from = models.DateField()
    date_to = models.DateField(null=True, blank=True)
    weekdays = models.JSONField(
        default=list,
        blank=True,
        help_text="List of weekday numbers (0=Mon..6=Sun); empty means all days.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_employee_schedules"
        verbose_name = "Employee Schedule"
        verbose_name_plural = "Employee Schedules"
        indexes = [
            models.Index(fields=["employer_id", "employee"]),
            models.Index(fields=["date_from", "date_to"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} -> {self.shift_template.name}"


class AttendanceDevice(models.Model):
    """Registered devices for attendance event ingestion."""

    DEVICE_TYPES = [
        ("RFID", "RFID"),
        ("BIOMETRIC", "Biometric"),
        ("KIOSK", "Kiosk"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    auth_token = models.CharField(max_length=255, blank=True, null=True)
    public_key = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_devices"
        verbose_name = "Attendance Device"
        verbose_name_plural = "Attendance Devices"
        unique_together = [["employer_id", "name"]]

    def __str__(self):
        return f"{self.name} ({self.device_type})"


def _generate_kiosk_token() -> str:
    return uuid.uuid4().hex


class AttendanceKioskSettings(models.Model):
    """Tenant-scoped kiosk configuration."""

    MODE_BARCODE = "BARCODE_RFID"
    MODE_MANUAL = "MANUAL"
    MODE_BOTH = "BOTH"

    MODE_CHOICES = [
        (MODE_BARCODE, "Barcode/RFID"),
        (MODE_MANUAL, "Manual"),
        (MODE_BOTH, "Both"),
    ]

    BARCODE_SCANNER = "SCANNER"
    BARCODE_FRONT = "FRONT_CAMERA"
    BARCODE_BACK = "BACK_CAMERA"

    BARCODE_CHOICES = [
        (BARCODE_SCANNER, "Scanner"),
        (BARCODE_FRONT, "Front Camera"),
        (BARCODE_BACK, "Back Camera"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    kiosk_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_BOTH)
    barcode_source = models.CharField(max_length=20, choices=BARCODE_CHOICES, default=BARCODE_SCANNER)
    display_time_seconds = models.IntegerField(default=3)
    pin_required = models.BooleanField(default=False)
    kiosk_url_token = models.CharField(max_length=64, default=_generate_kiosk_token, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_kiosk_settings"
        verbose_name = "Attendance Kiosk Settings"
        verbose_name_plural = "Attendance Kiosk Settings"
        unique_together = [["employer_id"]]

    def __str__(self):
        return f"Kiosk Settings (Employer {self.employer_id})"

    def regenerate_token(self):
        self.kiosk_url_token = _generate_kiosk_token()


class DeviceEventIngestLog(models.Model):
    """Audit log for device pushes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(AttendanceDevice, on_delete=models.CASCADE, related_name="ingest_logs")
    received_at = models.DateTimeField(auto_now_add=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    parsed_ok = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "attendance_device_ingest_logs"
        verbose_name = "Device Event Ingest Log"
        verbose_name_plural = "Device Event Ingest Logs"
        ordering = ["-received_at"]

    def __str__(self):
        status = "OK" if self.parsed_ok else "FAILED"
        return f"{self.device.name} ingest ({status})"


class AttendanceEvent(models.Model):
    """Immutable raw attendance events."""

    EVENT_IN = "IN"
    EVENT_OUT = "OUT"
    EVENT_BREAK_START = "BREAK_START"
    EVENT_BREAK_END = "BREAK_END"

    EVENT_CHOICES = [
        (EVENT_IN, "Check In"),
        (EVENT_OUT, "Check Out"),
        (EVENT_BREAK_START, "Break Start"),
        (EVENT_BREAK_END, "Break End"),
    ]

    SOURCE_MANUAL = "MANUAL"
    SOURCE_MOBILE = "MOBILE"
    SOURCE_WEB = "WEB"
    SOURCE_DEVICE = "DEVICE"
    SOURCE_IMPORT = "IMPORT"
    SOURCE_KIOSK = "KIOSK"

    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_MOBILE, "Mobile"),
        (SOURCE_WEB, "Web"),
        (SOURCE_DEVICE, "Device"),
        (SOURCE_IMPORT, "Import"),
        (SOURCE_KIOSK, "Kiosk"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance_events")
    attendance_date = models.DateField(db_index=True, help_text="Shift start date for this event")
    timestamp = models.DateTimeField()
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    device = models.ForeignKey(AttendanceDevice, on_delete=models.SET_NULL, null=True, blank=True)
    location_lat = models.FloatField(null=True, blank=True)
    location_lng = models.FloatField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_events"
        verbose_name = "Attendance Event"
        verbose_name_plural = "Attendance Events"
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["employer_id", "employee", "attendance_date"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} {self.event_type} @ {self.timestamp}"


class AttendanceRecord(models.Model):
    """Odoo-style interval record (check in/out)."""

    MODE_SYSTRAY = "SYSTRAY"
    MODE_KIOSK = "KIOSK"
    MODE_MANUAL = "MANUAL"

    MODE_CHOICES = [
        (MODE_SYSTRAY, "Systray"),
        (MODE_KIOSK, "Kiosk"),
        (MODE_MANUAL, "Manual"),
    ]

    STATUS_TO_APPROVE = "TO_APPROVE"
    STATUS_APPROVED = "APPROVED"
    STATUS_REFUSED = "REFUSED"

    STATUS_CHOICES = [
        (STATUS_TO_APPROVE, "To Approve"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REFUSED, "Refused"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance_records")
    check_in_at = models.DateTimeField()
    check_out_at = models.DateTimeField(null=True, blank=True)
    worked_minutes = models.IntegerField(default=0)
    extra_minutes = models.IntegerField(default=0)
    overtime_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TO_APPROVE)
    overtime_reason = models.TextField(blank=True, null=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_SYSTRAY)
    ip_check_in = models.GenericIPAddressField(null=True, blank=True)
    ip_check_out = models.GenericIPAddressField(null=True, blank=True)
    gps_check_in_lat = models.FloatField(null=True, blank=True)
    gps_check_in_lng = models.FloatField(null=True, blank=True)
    gps_check_out_lat = models.FloatField(null=True, blank=True)
    gps_check_out_lng = models.FloatField(null=True, blank=True)
    kiosk_device = models.ForeignKey(
        AttendanceDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_records",
    )
    created_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_records"
        verbose_name = "Attendance Record"
        verbose_name_plural = "Attendance Records"
        indexes = [
            models.Index(fields=["employer_id", "employee"]),
            models.Index(fields=["check_in_at"]),
            models.Index(fields=["overtime_status"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} {self.check_in_at} ({self.mode})"

    def update_worked_minutes(self):
        if self.check_out_at and self.check_in_at:
            delta = self.check_out_at - self.check_in_at
            self.worked_minutes = max(0, int(delta.total_seconds() // 60))


class AttendanceDay(models.Model):
    """Daily attendance summary derived from events."""

    STATUS_PRESENT = "PRESENT"
    STATUS_ABSENT = "ABSENT"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_ON_LEAVE = "ON_LEAVE"
    STATUS_HOLIDAY = "HOLIDAY"
    STATUS_WEEKEND = "WEEKEND"
    STATUS_REST_DAY = "REST_DAY"

    STATUS_CHOICES = [
        (STATUS_PRESENT, "Present"),
        (STATUS_ABSENT, "Absent"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_ON_LEAVE, "On Leave"),
        (STATUS_HOLIDAY, "Holiday"),
        (STATUS_WEEKEND, "Weekend"),
        (STATUS_REST_DAY, "Rest Day"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance_days")
    date = models.DateField(db_index=True)
    expected_shift = models.ForeignKey(ShiftTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    first_in_at = models.DateTimeField(null=True, blank=True)
    last_out_at = models.DateTimeField(null=True, blank=True)
    worked_minutes = models.IntegerField(default=0)
    late_minutes = models.IntegerField(default=0)
    early_leave_minutes = models.IntegerField(default=0)
    overtime_minutes = models.IntegerField(default=0)
    approved_overtime_minutes = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ABSENT)
    anomaly_flags = models.JSONField(default=list, blank=True)
    locked_for_payroll = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_days"
        verbose_name = "Attendance Day"
        verbose_name_plural = "Attendance Days"
        unique_together = [["employee", "date"]]
        indexes = [
            models.Index(fields=["employer_id", "date"]),
            models.Index(fields=["employer_id", "employee"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} - {self.date} ({self.status})"


class AttendanceDayAuditLog(models.Model):
    """Audit log for manual edits to attendance days."""

    ACTION_CHOICES = [
        ("CREATED", "Created"),
        ("UPDATED", "Updated"),
        ("LOCKED", "Locked for Payroll"),
        ("UNLOCKED", "Unlocked for Payroll"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance_day = models.ForeignKey(AttendanceDay, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "attendance_day_audit_logs"
        verbose_name = "Attendance Day Audit Log"
        verbose_name_plural = "Attendance Day Audit Logs"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.attendance_day.employee.full_name} {self.action} @ {self.timestamp}"


class OvertimeRequest(models.Model):
    """Overtime approvals per day."""

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="overtime_requests")
    date = models.DateField(db_index=True)
    minutes = models.IntegerField(default=0)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    approved_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_overtime_requests"
        verbose_name = "Overtime Request"
        verbose_name_plural = "Overtime Requests"
        unique_together = [["employee", "date"]]
        indexes = [
            models.Index(fields=["employer_id", "employee", "date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"OT {self.employee.full_name} {self.date} ({self.status})"

    def approve(self, approver_id):
        self.status = self.STATUS_APPROVED
        self.approved_by_id = approver_id
        self.approved_at = timezone.now()

    def reject(self, approver_id):
        self.status = self.STATUS_REJECTED
        self.approved_by_id = approver_id
        self.approved_at = timezone.now()

# Create your models here.
