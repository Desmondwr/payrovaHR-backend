from datetime import timedelta

from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.database_utils import (
    ensure_tenant_database_loaded,
    get_tenant_database_alias,
)
from accounts.middleware import get_current_tenant_db
from accounts.permissions import EmployerAccessPermission
from accounts.rbac import get_active_employer, is_delegate_user

from .models import (
    AccidentEvent,
    DriverAssignment,
    FleetSetting,
    Manufacturer,
    ServiceRecord,
    ServiceType,
    Vendor,
    Vehicle,
    VehicleCategory,
    VehicleContract,
    VehicleModel,
)
from .serializers import (
    AccidentEventSerializer,
    DriverAssignmentSerializer,
    FleetSettingSerializer,
    ManufacturerSerializer,
    ServiceRecordSerializer,
    ServiceTypeSerializer,
    VendorSerializer,
    VehicleCategorySerializer,
    VehicleContractSerializer,
    VehicleModelSerializer,
    VehicleSerializer,
)


class EmployerContextMixin:
    def _parse_header(self):
        header_value = self.request.headers.get("x-employer-id")
        if not header_value:
            return None
        try:
            return int(header_value)
        except ValueError:
            raise PermissionDenied("Invalid employer id in header.")

    def get_employer_id(self):
        employer_id = self._parse_header()
        if employer_id:
            return employer_id
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return None
        if hasattr(user, "employer_profile") and user.employer_profile:
            return user.employer_profile.id
        resolved = get_active_employer(self.request, require_context=False)
        if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
            return resolved.id
        employee = getattr(user, "employee_profile", None)
        if employee:
            return employee.employer_id
        raise PermissionDenied("Employer context could not be determined.")


class FleetTenantViewSet(EmployerContextMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {"*": ["fleets.manage"]}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            self._require_tenant_db_alias()

    def get_tenant_db_alias(self):
        tenant_db = get_current_tenant_db()
        if tenant_db and tenant_db != "default":
            return tenant_db

        employer_id = self.get_employer_id()
        if employer_id:
            alias = self._get_alias_for_employer(employer_id)
            if alias and alias != "default":
                return alias

        header_value = self.request.headers.get("x-employer-id") if hasattr(self.request, "headers") else None
        if header_value:
            try:
                header_id = int(header_value)
            except (TypeError, ValueError):
                header_id = None
            if header_id:
                alias = self._get_alias_for_employer(header_id)
                if alias:
                    return alias

        return "default"

    def _get_alias_for_employer(self, employer_id):
        from accounts.models import EmployerProfile

        employer_profile = EmployerProfile.objects.filter(id=employer_id).first()
        if employer_profile and employer_profile.database_name:
            ensure_tenant_database_loaded(employer_profile)
            return get_tenant_database_alias(employer_profile)
        return "default"

    def filter_queryset(self, queryset):
        employer_id = self.get_employer_id()
        if employer_id:
            queryset = queryset.filter(employer_id=employer_id)
        return super().filter_queryset(queryset)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["employer_id"] = self.get_employer_id()
        context["tenant_db"] = self.get_tenant_db_alias()
        return context

    def _require_employer_context(self):
        employer_id = self.get_employer_id()
        if employer_id is None:
            raise PermissionDenied("Employer context is required to create this resource.")
        return employer_id

    def _require_tenant_db_alias(self):
        tenant_db = self.get_tenant_db_alias()
        if tenant_db == "default":
            raise PermissionDenied(
                "Tenant database context is required. Provide X-Employer-Id header or login as employer."
            )
        return tenant_db

    def perform_create(self, serializer):
        serializer.save(employer_id=self._require_employer_context())

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        tenant_db = self.get_tenant_db_alias()
        instance.delete(using=tenant_db)

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_db = self.get_tenant_db_alias()
        return queryset.using(tenant_db)


class ManufacturerViewSet(FleetTenantViewSet):
    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer


class VehicleCategoryViewSet(FleetTenantViewSet):
    queryset = VehicleCategory.objects.all()
    serializer_class = VehicleCategorySerializer


class VehicleModelViewSet(FleetTenantViewSet):
    queryset = VehicleModel.objects.all()
    serializer_class = VehicleModelSerializer


class ServiceTypeViewSet(FleetTenantViewSet):
    queryset = ServiceType.objects.all()
    serializer_class = ServiceTypeSerializer


class VendorViewSet(FleetTenantViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer


class FleetSettingViewSet(FleetTenantViewSet):
    queryset = FleetSetting.objects.all()
    serializer_class = FleetSettingSerializer


class VehicleViewSet(FleetTenantViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer


class DriverAssignmentViewSet(FleetTenantViewSet):
    queryset = DriverAssignment.objects.all()
    serializer_class = DriverAssignmentSerializer


class VehicleContractViewSet(FleetTenantViewSet):
    queryset = VehicleContract.objects.all()
    serializer_class = VehicleContractSerializer


class ServiceRecordViewSet(FleetTenantViewSet):
    queryset = ServiceRecord.objects.all()
    serializer_class = ServiceRecordSerializer


class AccidentEventViewSet(FleetTenantViewSet):
    queryset = AccidentEvent.objects.all()
    serializer_class = AccidentEventSerializer


class FleetReportView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        employer_id = self.get_employer_id()
        filters = {"employer_id": employer_id} if employer_id is not None else {}

        contracts = VehicleContract.objects.filter(**filters)
        services = ServiceRecord.objects.filter(**filters)
        vehicles = Vehicle.objects.filter(**filters)
        driver_assignments = DriverAssignment.objects.filter(**filters)

        contract_total = contracts.aggregate(
            total=Coalesce(
                Sum("catalog_value"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]

        service_total = services.aggregate(
            total=Coalesce(
                Sum("cost_final"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]

        fleet_settings = FleetSetting.objects.filter(**filters).first()
        alert_days = fleet_settings.contract_alert_days if fleet_settings else 30
        threshold = timezone.now().date() + timedelta(days=alert_days)

        vehicles_nearing_contract_end = (
            contracts.filter(status="active", end_date__lte=threshold)
            .order_by("end_date")
            .values("vehicle__id", "vehicle__license_plate", "end_date")[:5]
        )

        vehicle_costs = (
            vehicles.annotate(
                service_cost=Coalesce(
                    Sum("services__cost_final"),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                contract_cost=Coalesce(
                    Sum("contracts__catalog_value"),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("-service_cost")[:5]
        )

        driver_costs = (
            driver_assignments.filter(employee__isnull=False)
            .annotate(
                service_cost=Coalesce(
                    Sum("vehicle__services__cost_final"),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .values(
                "employee_id",
                "employee__first_name",
                "employee__middle_name",
                "employee__last_name",
                "employee__employee_id",
                "service_cost",
            )
            .order_by("-service_cost")[:5]
        )

        payload = {
            "total_vehicle_cost": contract_total + service_total,
            "total_contract_cost": contract_total,
            "total_service_cost": service_total,
            "vehicle_costs": [
                {
                    "vehicle_id": vehicle.id,
                    "license_plate": vehicle.license_plate,
                    "service_cost": float(vehicle.service_cost),
                    "contract_cost": float(vehicle.contract_cost),
                }
                for vehicle in vehicle_costs
            ],
            "vehicles_nearing_contract_end": list(vehicles_nearing_contract_end),
            "driver_costs": [
                {
                    "employee_id": driver["employee_id"],
                    "name": " ".join(
                        part
                        for part in (
                            driver["employee__first_name"],
                            driver["employee__middle_name"],
                            driver["employee__last_name"],
                        )
                        if part
                    ).strip(),
                    "employee_number": driver["employee__employee_id"],
                    "service_cost": float(driver["service_cost"]),
                }
                for driver in driver_costs
            ],
        }

        return Response(payload)
