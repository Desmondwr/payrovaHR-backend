import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from employees.models import Branch, Employee


def generate_kiosk_slug():
    """Stable slug generator for kiosk URLs (hex string)."""
    return uuid.uuid4().hex


class FrontdeskStation(models.Model):
    """
    A station represents the physical frontdesk for a branch.
    Station names are locked to their branch name and only one active station
    is allowed per branch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="frontdesk_stations")
    name = models.CharField(max_length=255)
    kiosk_slug = models.CharField(
        max_length=100,
        unique=True,
        default=generate_kiosk_slug,
        help_text="Stable slug used to build kiosk/QR URLs",
    )
    is_active = models.BooleanField(default=True)
    allow_self_check_in = models.BooleanField(default=True, help_text="Allow kiosk/QR self check-in (checkout remains manual)")
    kiosk_theme = models.JSONField(
        default=dict,
        blank=True,
        help_text="Appearance settings for the kiosk (colors, typography, layout text)",
    )
    kiosk_logo = models.ImageField(
        upload_to="frontdesk/kiosk_logos/",
        blank=True,
        null=True,
        help_text="Optional logo displayed on the kiosk UI (uploaded file instead of external URL).",
    )
    terms_and_conditions = models.TextField(blank=True, help_text="Optional terms displayed on the kiosk")
    responsibles = models.ManyToManyField(
        Employee,
        through="StationResponsible",
        related_name="managed_frontdesk_stations",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "frontdesk_stations"
        verbose_name = "Frontdesk Station"
        verbose_name_plural = "Frontdesk Stations"
        constraints = [
            models.UniqueConstraint(
                fields=["branch"],
                condition=Q(is_active=True),
                name="unique_active_frontdesk_station_per_branch",
            ),
        ]
        ordering = ["branch__name", "-is_active", "created_at"]

    def clean(self):
        if self.branch and self.name != self.branch.name:
            raise ValidationError({"name": "Station name must match the branch name."})
        if self.branch and self.employer_id and self.employer_id != self.branch.employer_id:
            raise ValidationError({"branch": "Branch must belong to the same employer as the station."})

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or getattr(self._state, "db", None)
        if using:
            self._state.db = using
        if self.branch:
            self.name = self.branch.name
            if not self.employer_id:
                self.employer_id = self.branch.employer_id
        if not self.kiosk_slug:
            self.kiosk_slug = uuid.uuid4().hex
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def kiosk_url_path(self):
        """Path portion that can be used to render QR codes or kiosk deep links."""
        return f"/frontdesk/kiosk/{self.kiosk_slug}/"

    def __str__(self):
        return f"{self.branch.name} Station ({'Active' if self.is_active else 'Inactive'})"


class StationResponsible(models.Model):
    """
    HR/Office admins responsible for a station. Scoped to the station's branch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    station = models.ForeignKey(FrontdeskStation, on_delete=models.CASCADE, related_name="station_responsibles")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="frontdesk_responsibilities")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "frontdesk_station_responsibles"
        verbose_name = "Station Responsible"
        verbose_name_plural = "Station Responsibles"
        unique_together = [["station", "employee"]]

    def clean(self):
        if self.station and self.employee:
            if self.station.branch_id and self.employee.branch_id and self.station.branch_id != self.employee.branch_id:
                raise ValidationError({"employee": "Responsible must belong to the same branch as the station."})
            if self.employee.employment_status != "ACTIVE":
                raise ValidationError({"employee": "Responsible must be an active employee."})
            if self.station.employer_id != self.employee.employer_id:
                raise ValidationError({"employee": "Responsible must belong to the same employer as the station."})

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or getattr(self._state, "db", None)
        if using:
            self._state.db = using
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.full_name} -> {self.station.name}"


class Visitor(models.Model):
    """
    External visitor identity captured at the frontdesk.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    organization = models.CharField(max_length=255, blank=True, null=True)
    id_type = models.CharField(max_length=100, blank=True, null=True, help_text="ID type provided (e.g., Passport, ID Card)")
    id_number = models.CharField(max_length=100, blank=True, null=True, help_text="ID number captured at check-in")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "frontdesk_visitors"
        verbose_name = "Visitor"
        verbose_name_plural = "Visitors"
        indexes = [
            models.Index(fields=["employer_id", "full_name"]),
            models.Index(fields=["employer_id", "phone"]),
            models.Index(fields=["employer_id", "email"]),
        ]

    def __str__(self):
        return self.full_name


class Visit(models.Model):
    """
    A visit links a visitor to a host and station (and implicitly the branch).
    """

    VISIT_TYPE_CHOICES = [
        ("WALK_IN", "Walk-in"),
        ("PLANNED", "Planned"),
    ]
    STATUS_CHOICES = [
        ("PLANNED", "Planned"),
        ("CHECKED_IN", "Checked In"),
        ("CHECKED_OUT", "Checked Out"),
        ("CANCELLED", "Cancelled"),
    ]
    CHECK_IN_METHOD_CHOICES = [
        ("MANUAL", "Manual"),
        ("KIOSK", "Kiosk/QR"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="frontdesk_visits")
    station = models.ForeignKey(FrontdeskStation, on_delete=models.PROTECT, related_name="visits")
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="visits")
    host = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="hosted_visits")
    visit_type = models.CharField(max_length=10, choices=VISIT_TYPE_CHOICES, default="WALK_IN")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="PLANNED")
    visit_purpose = models.CharField(max_length=255, blank=True, null=True)
    planned_start = models.DateTimeField(blank=True, null=True)
    planned_end = models.DateTimeField(blank=True, null=True)
    check_in_time = models.DateTimeField(blank=True, null=True)
    check_out_time = models.DateTimeField(blank=True, null=True)
    check_in_method = models.CharField(max_length=10, choices=CHECK_IN_METHOD_CHOICES, default="MANUAL")
    check_out_by_id = models.IntegerField(
        blank=True,
        null=True,
        help_text="User ID of HR/Admin who completed checkout. Visitors never self checkout.",
    )
    kiosk_session_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Optional kiosk session/QR reference captured at check-in",
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "frontdesk_visits"
        verbose_name = "Visit"
        verbose_name_plural = "Visits"
        indexes = [
            models.Index(fields=["employer_id", "branch"]),
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["employer_id", "visit_type"]),
        ]

    def clean(self):
        errors = {}
        if self.branch_id and self.station_id and self.branch_id != self.station.branch_id:
            errors["station"] = "Station must belong to the same branch."
        if self.branch_id and self.host_id and self.host.branch_id and self.branch_id != self.host.branch_id:
            errors["host"] = "Host must belong to the same branch as the visit."
        if self.host_id and not self.host.branch_id:
            errors["host"] = "Host must belong to a branch."
        if self.host_id and self.host.employment_status != "ACTIVE":
            errors["host"] = "Host must be an active employee."
        if self.station_id and not self.station.is_active:
            errors["station"] = "Station must be active to receive visitors."
        if self.station_id and self.employer_id and self.station.employer_id != self.employer_id:
            errors["station"] = "Station employer mismatch."
        if self.branch_id and self.employer_id and self.branch.employer_id != self.employer_id:
            errors["branch"] = "Branch employer mismatch."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or getattr(self._state, "db", None)
        if using:
            self._state.db = using
        if self.branch and not self.employer_id:
            self.employer_id = self.branch.employer_id
        if self.status == "CHECKED_IN" and not self.check_in_time:
            self.check_in_time = timezone.now()
        if self.status == "CHECKED_OUT" and not self.check_out_time:
            self.check_out_time = timezone.now()
        self.full_clean()
        super().save(*args, **kwargs)

    def check_in(self, method="MANUAL", kiosk_reference=None):
        """Helper to mark the visit as checked in."""
        normalized_method = (method or "MANUAL").upper()
        if normalized_method not in dict(self.CHECK_IN_METHOD_CHOICES):
            normalized_method = "MANUAL"
        self.status = "CHECKED_IN"
        self.check_in_time = timezone.now()
        self.check_in_method = normalized_method
        if kiosk_reference:
            self.kiosk_session_reference = kiosk_reference
        self.save()

    def check_out(self, user_id=None):
        """Helper to mark the visit as checked out (always by HR/Admin)."""
        self.status = "CHECKED_OUT"
        self.check_out_time = timezone.now()
        if user_id:
            self.check_out_by_id = user_id
        self.save()

    def __str__(self):
        return f"{self.visitor.full_name} -> {self.host.full_name} @ {self.station.name}"
