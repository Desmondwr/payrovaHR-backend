from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    FrontdeskStationViewSet,
    StationResponsibleViewSet,
    VisitorViewSet,
    VisitViewSet,
    KioskCheckInView,
    KioskStationView,
    KioskHostsView,
    GlobalKioskCheckInView,
)

router = DefaultRouter()
router.register(r"stations", FrontdeskStationViewSet, basename="frontdesk-station")
router.register(r"station-responsibles", StationResponsibleViewSet, basename="frontdesk-station-responsible")
router.register(r"visitors", VisitorViewSet, basename="frontdesk-visitor")
router.register(r"visits", VisitViewSet, basename="frontdesk-visit")

urlpatterns = router.urls
urlpatterns += [
    # Public kiosk station info by kiosk_slug
    path("kiosk/<slug:kiosk_slug>/", KioskStationView.as_view(), name="frontdesk-kiosk"),
    # Public host list for kiosk by kiosk_slug
    path("kiosk/<slug:kiosk_slug>/hosts/", KioskHostsView.as_view(), name="frontdesk-kiosk-hosts"),
    # Unauthenticated kiosk self check-in by station kiosk_slug
    path("kiosk/<slug:kiosk_slug>/check-in/", KioskCheckInView.as_view(), name="frontdesk-kiosk-check-in"),
    # Global kiosk check-in that takes kiosk_slug in payload
    path("check-in/", GlobalKioskCheckInView.as_view(), name="frontdesk-global-check-in"),
]
