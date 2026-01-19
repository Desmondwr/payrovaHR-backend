from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceAllowedWifiViewSet,
    AttendanceConfigurationViewSet,
    AttendanceLocationSiteViewSet,
    AttendanceKioskStationViewSet,
    AttendanceRecordViewSet,
    AttendanceReportView,
    AttendanceStatusView,
    KioskCheckView,
    KioskTokenRegenerateView,
    ManualAttendanceCreateView,
    PortalCheckInView,
    PortalCheckOutView,
    WorkingScheduleViewSet,
)

router = DefaultRouter()
router.register(r"config", AttendanceConfigurationViewSet, basename="attendance-config")
router.register(r"sites", AttendanceLocationSiteViewSet, basename="attendance-site")
router.register(r"wifi", AttendanceAllowedWifiViewSet, basename="attendance-wifi")
router.register(r"kiosk-stations", AttendanceKioskStationViewSet, basename="attendance-kiosk-station")
router.register(r"records", AttendanceRecordViewSet, basename="attendance-record")
router.register(r"schedules", WorkingScheduleViewSet, basename="attendance-schedule")

urlpatterns = router.urls
urlpatterns += [
    path("check-in/", PortalCheckInView.as_view(), name="attendance-check-in"),
    path("check-out/", PortalCheckOutView.as_view(), name="attendance-check-out"),
    path("kiosk/check/", KioskCheckView.as_view(), name="attendance-kiosk-check"),
    path("kiosk/regenerate-url/", KioskTokenRegenerateView.as_view(), name="attendance-kiosk-regenerate"),
    path("manual-create/", ManualAttendanceCreateView.as_view(), name="attendance-manual-create"),
    path("report/", AttendanceReportView.as_view(), name="attendance-report"),
    # Employee convenience alias
    path(
        "me/records/",
        AttendanceRecordViewSet.as_view({"get": "list"}),
        name="attendance-my-records",
    ),
    path("me/status/", AttendanceStatusView.as_view(), name="attendance-my-status"),
    # Employer convenience alias for approval queue
    path(
        "to-approve/",
        AttendanceRecordViewSet.as_view({"get": "to_approve"}),
        name="attendance-to-approve",
    ),
]
