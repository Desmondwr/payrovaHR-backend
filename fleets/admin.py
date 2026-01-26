from django.contrib import admin

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


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ("name", "employer_id", "is_active", "created_at")
    search_fields = ("name",)


@admin.register(VehicleCategory)
class VehicleCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "employer_id", "priority", "is_active")
    list_filter = ("is_active",)


@admin.register(VehicleModel)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ("name", "manufacturer", "vehicle_type", "employer_id")
    list_filter = ("vehicle_type", "power_source")
    search_fields = ("name", "manufacturer__name")


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "severity", "default_stage", "employer_id")
    list_filter = ("severity", "default_stage", "is_active")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "vendor_type", "employer_id", "is_active")
    search_fields = ("name",)


@admin.register(FleetSetting)
class FleetSettingAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "contract_alert_days", "allow_new_requests")
    raw_id_fields = ("default_vendor",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("license_plate", "vehicle_model", "status", "employer_id")
    list_filter = ("status", "vehicle_model__vehicle_type")
    search_fields = ("license_plate",)


@admin.register(DriverAssignment)
class DriverAssignmentAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "get_driver", "branch", "assignment_type", "start_date", "end_date")
    list_filter = ("assignment_type", "branch")
    raw_id_fields = ("employee", "vehicle", "branch")

    def get_driver(self, obj):
        return obj.employee or obj.external_driver_name

    get_driver.short_description = "Driver"


@admin.register(VehicleContract)
class VehicleContractAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "start_date", "end_date", "status", "employer_id")
    list_filter = ("status",)
    raw_id_fields = ("vehicle", "responsible_person")


@admin.register(ServiceRecord)
class ServiceRecordAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "service_type", "stage", "date", "employer_id")
    list_filter = ("stage", "service_type")
    raw_id_fields = ("vehicle", "vendor")


@admin.register(AccidentEvent)
class AccidentEventAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "category", "reported_at", "employer_id")
    list_filter = ("category",)
    raw_id_fields = ("vehicle",)
