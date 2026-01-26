from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AccidentEventViewSet,
    DriverAssignmentViewSet,
    FleetReportView,
    FleetSettingViewSet,
    ManufacturerViewSet,
    ServiceRecordViewSet,
    ServiceTypeViewSet,
    VendorViewSet,
    VehicleCategoryViewSet,
    VehicleContractViewSet,
    VehicleModelViewSet,
    VehicleViewSet,
)

router = DefaultRouter()
router.register(r"manufacturers", ManufacturerViewSet, basename="fleet-manufacturer")
router.register(r"model-categories", VehicleCategoryViewSet, basename="fleet-model-category")
router.register(r"vehicle-models", VehicleModelViewSet, basename="fleet-vehicle-model")
router.register(r"service-types", ServiceTypeViewSet, basename="fleet-service-type")
router.register(r"vendors", VendorViewSet, basename="fleet-vendor")
router.register(r"settings", FleetSettingViewSet, basename="fleet-setting")
router.register(r"vehicles", VehicleViewSet, basename="fleet-vehicle")
router.register(r"assignments", DriverAssignmentViewSet, basename="fleet-assignment")
router.register(r"contracts", VehicleContractViewSet, basename="fleet-contract")
router.register(r"services", ServiceRecordViewSet, basename="fleet-service")
router.register(r"accidents", AccidentEventViewSet, basename="fleet-accident")

urlpatterns = [
    path("reports/summary/", FleetReportView.as_view(), name="fleet-report-summary"),
] + router.urls
