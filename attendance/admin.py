from django.contrib import admin

from .models import (
    AttendanceDay,
    AttendanceDayAuditLog,
    AttendanceDevice,
    AttendanceEvent,
    AttendanceKioskSettings,
    AttendancePolicy,
    AttendanceRecord,
    DeviceEventIngestLog,
    EmployeeSchedule,
    OvertimeRequest,
    ShiftTemplate,
)


@admin.register(AttendancePolicy)
class AttendancePolicyAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "scope_type", "branch", "department", "employee", "is_active", "updated_at")
    list_filter = ("scope_type", "is_active")
    search_fields = ("employer_id",)


@admin.register(ShiftTemplate)
class ShiftTemplateAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "name", "start_time", "end_time", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(EmployeeSchedule)
class EmployeeScheduleAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "employee", "shift_template", "date_from", "date_to")
    list_filter = ("employer_id",)
    search_fields = ("employee__first_name", "employee__last_name")


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "employee", "event_type", "timestamp", "source")
    list_filter = ("event_type", "source")
    search_fields = ("employee__first_name", "employee__last_name")


@admin.register(AttendanceDay)
class AttendanceDayAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "employee", "date", "status", "worked_minutes", "locked_for_payroll")
    list_filter = ("status", "locked_for_payroll")
    search_fields = ("employee__first_name", "employee__last_name")


@admin.register(AttendanceDayAuditLog)
class AttendanceDayAuditLogAdmin(admin.ModelAdmin):
    list_display = ("attendance_day", "action", "performed_by_id", "timestamp")
    list_filter = ("action",)


@admin.register(AttendanceDevice)
class AttendanceDeviceAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "name", "device_type", "is_active", "last_seen_at")
    list_filter = ("device_type", "is_active")
    search_fields = ("name",)


@admin.register(DeviceEventIngestLog)
class DeviceEventIngestLogAdmin(admin.ModelAdmin):
    list_display = ("device", "received_at", "parsed_ok")
    list_filter = ("parsed_ok",)


@admin.register(AttendanceKioskSettings)
class AttendanceKioskSettingsAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "kiosk_mode", "pin_required", "is_active", "updated_at")
    list_filter = ("kiosk_mode", "pin_required", "is_active")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "employee", "check_in_at", "check_out_at", "mode", "overtime_status")
    list_filter = ("mode", "overtime_status")


@admin.register(OvertimeRequest)
class OvertimeRequestAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "employee", "date", "minutes", "status")
    list_filter = ("status",)

# Register your models here.
