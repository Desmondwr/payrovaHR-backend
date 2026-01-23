from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BankAccountViewSet,
    BankStatementViewSet,
    CashDeskViewSet,
    PaymentBatchViewSet,
    PaymentLineViewSet,
    ReconciliationAutoMatchView,
    ReconciliationConfirmView,
    ReconciliationRejectView,
)

router = DefaultRouter()
router.register(r"bank-accounts", BankAccountViewSet, basename="treasury-bank-account")
router.register(r"cash-desks", CashDeskViewSet, basename="treasury-cash-desk")
router.register(r"batches", PaymentBatchViewSet, basename="treasury-batch")
router.register(r"lines", PaymentLineViewSet, basename="treasury-line")
router.register(r"statements", BankStatementViewSet, basename="treasury-statement")

urlpatterns = [
    path("reconcile/auto-match/<uuid:statement_id>/", ReconciliationAutoMatchView.as_view(), name="treasury-reconcile-auto"),
    path("reconcile/confirm/", ReconciliationConfirmView.as_view(), name="treasury-reconcile-confirm"),
    path("reconcile/reject/", ReconciliationRejectView.as_view(), name="treasury-reconcile-reject"),
]

urlpatterns += router.urls
