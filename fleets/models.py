from decimal import Decimal
import uuid

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class EmployerScopedModel(models.Model):
    employer_id = models.IntegerField(db_index=True, help_text="Tenant/employer identifier (main DB)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Manufacturer(EmployerScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    logo_url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "fleet_manufacturers"
        unique_together = [["employer_id", "name"]]
        ordering = ["name"]

    def __str__(self):
        return self.name


class VehicleCategory(EmployerScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    priority = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "fleet_model_categories"
        unique_together = [["employer_id", "name"]]
        ordering = ["priority", "name"]

    def __str__(self):
        return self.name


class VehicleModel(EmployerScopedModel):
    VEHICLE_TYPE_CHOICES = [
        ("CAR", "Car"),
        ("BIKE", "Bike"),
    ]

    POWER_SOURCE_CHOICES = [
        ("FUEL", "Fuel"),
        ("ELECTRIC", "Electric"),
        ("HYBRID", "Hybrid"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="models",
    )
    category = models.ForeignKey(
        VehicleCategory,
        on_delete=models.PROTECT,
        related_name="models",
    )
    vehicle_type = models.CharField(max_length=10, choices=VEHICLE_TYPE_CHOICES)
    seating_capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    doors = models.PositiveSmallIntegerField(null=True, blank=True)
    fuel_type = models.CharField(max_length=50, blank=True)
    transmission = models.CharField(max_length=50, blank=True)
    power_source = models.CharField(max_length=20, choices=POWER_SOURCE_CHOICES, default="FUEL")
    co2_emissions = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "fleet_vehicle_models"
        unique_together = [["manufacturer", "name"]]
        ordering = ["manufacturer__name", "name"]

    def __str__(self):
        return f"{self.manufacturer.name} {self.name}"


class ServiceType(EmployerScopedModel):
    SEVERITY_CHOICES = [
        ("INFO", "Info"),
        ("NORMAL", "Normal"),
        ("HIGH", "High"),
    ]

    STAGE_CHOICES = [
        ("new", "New"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=140)
    description = models.TextField(blank=True, null=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="NORMAL")
    default_stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default="new")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "fleet_service_types"
        unique_together = [["employer_id", "name"]]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Vendor(EmployerScopedModel):
    VENDOR_TYPE_CHOICES = [
        ("DEALER", "Dealer"),
        ("GARAGE", "Garage"),
        ("REPAIR_SHOP", "Repair Shop"),
        ("ACCIDENT_MANAGEMENT", "Accident Management"),
        ("OTHER", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    vendor_type = models.CharField(max_length=30, choices=VENDOR_TYPE_CHOICES, default="OTHER")
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=30, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    service_types = models.ManyToManyField(ServiceType, related_name="vendors", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "fleet_vendors"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FleetSetting(EmployerScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract_alert_days = models.PositiveSmallIntegerField(default=30)
    allow_new_requests = models.BooleanField(default=True)
    default_vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settings_default",
    )
    notification_channels = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    allow_requests_from_inventory_only = models.BooleanField(default=False)

    class Meta:
        db_table = "fleet_settings"
        unique_together = [["employer_id"]]

    def __str__(self):
        return f"Fleet settings for employer {self.employer_id}"


class Vehicle(EmployerScopedModel):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("ordered", "Ordered"),
        ("registered", "Registered"),
        ("downgraded", "Downgraded"),
        ("retired", "Retired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle_model = models.ForeignKey(
        VehicleModel,
        on_delete=models.PROTECT,
        related_name="vehicles",
    )
    license_plate = models.CharField(max_length=30, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")
    location = models.CharField(max_length=200, blank=True)
    odometer = models.PositiveIntegerField(default=0)
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    external_id = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "fleet_vehicles"
        unique_together = [["employer_id", "license_plate"]]
        ordering = ["-created_at"]

    def __str__(self):
        return self.license_plate

    @property
    def current_assignment(self):
        return self.assignments.filter(assignment_type="CURRENT").order_by("-start_date").first()

    @property
    def available(self):
        return self.current_assignment is None


class DriverAssignment(EmployerScopedModel):
    ASSIGNMENT_TYPE_CHOICES = [
        ("CURRENT", "Current"),
        ("FUTURE", "Future"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    branch = models.ForeignKey(
        "employees.Branch",
        on_delete=models.PROTECT,
        related_name="driver_assignments",
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fleet_assignments",
    )
    external_driver_name = models.CharField(max_length=200, blank=True)
    external_driver_contact = models.CharField(max_length=80, blank=True)
    assignment_type = models.CharField(max_length=10, choices=ASSIGNMENT_TYPE_CHOICES, default="CURRENT")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    assignment_notes = models.TextField(blank=True, null=True)
    assigned_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "fleet_driver_assignments"
        ordering = ["-assigned_at"]
        indexes = [
            models.Index(fields=["vehicle", "assignment_type"]),
        ]

    def clean(self):
        if not self.employee and not self.external_driver_name:
            raise ValidationError("Provide either an employee or an external driver name.")

    def __str__(self):
        target = getattr(self.employee, "full_name", None) or self.external_driver_name
        return f"{target or 'External Driver'} → {self.vehicle.license_plate}"


class VehicleContract(EmployerScopedModel):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("expired", "Expired"),
        ("terminated", "Terminated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    responsible_person = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_contracts",
    )
    catalog_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    residual_value = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "fleet_vehicle_contracts"
        ordering = ["-start_date"]

    def clean(self):
        if self.status == "active":
            active_conflict = VehicleContract.objects.filter(
                vehicle=self.vehicle,
                status="active",
            ).exclude(pk=self.pk)
            if active_conflict.exists():
                raise ValidationError("Only one active contract per vehicle is allowed.")

    @property
    def days_to_expiry(self):
        return max((self.end_date - timezone.now().date()).days, 0)

    def __str__(self):
        return f"{self.vehicle.license_plate} ({self.status})"


class ServiceRecord(EmployerScopedModel):
    STAGE_CHOICES = [
        ("new", "New"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="services",
    )
    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.PROTECT,
        related_name="service_records",
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name="services",
    )
    date = models.DateField()
    odometer = models.PositiveIntegerField(null=True, blank=True)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default="new")
    cost_estimate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_final = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    attachments = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "fleet_service_records"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.service_type.name} on {self.date} [{self.vehicle.license_plate}]"

    @property
    def total_cost(self):
        return self.cost_final or self.cost_estimate or Decimal("0.00")


class AccidentEvent(EmployerScopedModel):
    CATEGORY_CHOICES = [
        ("driver_fault", "Driver Fault"),
        ("no_fault", "No Fault"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="accident_events",
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    reported_at = models.DateTimeField(default=timezone.now)
    services = models.ManyToManyField(ServiceRecord, related_name="accidents", blank=True)
    total_estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_actual_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "fleet_accidents"
        ordering = ["-reported_at"]

    def __str__(self):
        return f"Accident on {self.vehicle.license_plate} ({self.category})"

    def refresh_totals(self):
        totals = self.services.aggregate(
            est=models.Sum("cost_estimate"),
            actual=models.Sum("cost_final"),
        )
        self.total_estimated_cost = totals["est"] or Decimal("0.00")
        self.total_actual_cost = totals["actual"] or Decimal("0.00")
        return self.total_actual_cost
