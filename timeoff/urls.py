from rest_framework.routers import DefaultRouter

from .views import (
    AccrualRunViewSet,
    TimeOffAllocationRequestViewSet,
    TimeOffAllocationViewSet,
    TimeOffBalanceViewSet,
    TimeOffConfigurationViewSet,
    TimeOffLedgerViewSet,
    TimeOffRequestViewSet,
    TimeOffTypeViewSet,
)

router = DefaultRouter()
router.register(r"timeoff-configurations", TimeOffConfigurationViewSet, basename="timeoff-configuration")
router.register(r"leave-types", TimeOffTypeViewSet, basename="timeoff-type")
router.register(r"requests", TimeOffRequestViewSet, basename="timeoff-request")
router.register(r"balances", TimeOffBalanceViewSet, basename="timeoff-balance")
router.register(r"ledger", TimeOffLedgerViewSet, basename="timeoff-ledger")
router.register(r"allocations", TimeOffAllocationViewSet, basename="timeoff-allocation")
router.register(r"allocation-requests", TimeOffAllocationRequestViewSet, basename="timeoff-allocation-request")
router.register(r"accrual", AccrualRunViewSet, basename="timeoff-accrual")

urlpatterns = router.urls
