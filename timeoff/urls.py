from rest_framework.routers import DefaultRouter
from .views import (
    TimeOffConfigurationViewSet,
    TimeOffRequestViewSet,
    TimeOffBalanceViewSet,
    TimeOffLedgerViewSet,
)

router = DefaultRouter()
router.register(r"timeoff-configurations", TimeOffConfigurationViewSet, basename="timeoff-configuration")
router.register(r"requests", TimeOffRequestViewSet, basename="timeoff-request")
router.register(r"balances", TimeOffBalanceViewSet, basename="timeoff-balance")
router.register(r"ledger", TimeOffLedgerViewSet, basename="timeoff-ledger")

urlpatterns = router.urls
