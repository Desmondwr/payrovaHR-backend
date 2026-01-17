from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceDayViewSet,
    AttendanceDeviceViewSet,
    AttendanceEventViewSet,
    AttendanceKioskSettingsViewSet,
    AttendancePolicyViewSet,
    AttendanceRecordViewSet,
    DeviceEventIngestView,
    EmployeeScheduleViewSet,
    KioskPunchView,
    OvertimeRequestViewSet,
    ShiftTemplateViewSet,
)

router = DefaultRouter()
router.register(r"policies", AttendancePolicyViewSet, basename="attendance-policy")
router.register(r"shifts", ShiftTemplateViewSet, basename="attendance-shift")
router.register(r"schedules", EmployeeScheduleViewSet, basename="attendance-schedule")
router.register(r"events", AttendanceEventViewSet, basename="attendance-event")
router.register(r"days", AttendanceDayViewSet, basename="attendance-day")
router.register(r"devices", AttendanceDeviceViewSet, basename="attendance-device")
router.register(r"kiosk-settings", AttendanceKioskSettingsViewSet, basename="attendance-kiosk-settings")
router.register(r"overtime", OvertimeRequestViewSet, basename="attendance-overtime")
router.register(r"records", AttendanceRecordViewSet, basename="attendance-record")

urlpatterns = router.urls + [
    path("device-push/", DeviceEventIngestView.as_view(), name="attendance-device-push"),
    path("kiosk/punch/", KioskPunchView.as_view(), name="attendance-kiosk-punch"),
]
