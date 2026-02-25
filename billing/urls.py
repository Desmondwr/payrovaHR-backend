from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BillingInvoiceViewSet,
    BillingMyPayoutsView,
    BillingMyTransactionsView,
    BillingPayoutBatchViewSet,
    BillingPayoutViewSet,
    BillingPayoutConfigurationView,
    BillingPayoutReadinessView,
    BillingPlanViewSet,
    BillingTransactionViewSet,
    EmployerSubscriptionViewSet,
    FundingMethodViewSet,
    GbPayBanksView,
    GbPayConnectionViewSet,
    GbPayCountriesView,
    GbPayCurrenciesView,
    GbPayOperatorsView,
    GbPayProductsView,
    PayoutMethodViewSet,
)


router = DefaultRouter()
router.register(r"funding-methods", FundingMethodViewSet, basename="billing-funding-methods")
router.register(r"gbpay-connections", GbPayConnectionViewSet, basename="billing-gbpay-connections")
router.register(r"payout-methods", PayoutMethodViewSet, basename="billing-payout-methods")
router.register(r"plans", BillingPlanViewSet, basename="billing-plans")
router.register(r"subscriptions", EmployerSubscriptionViewSet, basename="billing-subscriptions")
router.register(r"invoices", BillingInvoiceViewSet, basename="billing-invoices")
router.register(r"transactions", BillingTransactionViewSet, basename="billing-transactions")
router.register(r"payouts", BillingPayoutViewSet, basename="billing-payouts")
router.register(r"payout-batches", BillingPayoutBatchViewSet, basename="billing-payout-batches")


urlpatterns = [
    path("config/payouts/", BillingPayoutConfigurationView.as_view(), name="billing-payout-config"),
    path("payouts/readiness/", BillingPayoutReadinessView.as_view(), name="billing-payout-readiness"),
    path("gbpay/countries/", GbPayCountriesView.as_view(), name="gbpay-countries"),
    path("gbpay/banks/", GbPayBanksView.as_view(), name="gbpay-banks"),
    path("gbpay/operators/", GbPayOperatorsView.as_view(), name="gbpay-operators"),
    path("gbpay/products/", GbPayProductsView.as_view(), name="gbpay-products"),
    path("gbpay/currencies/", GbPayCurrenciesView.as_view(), name="gbpay-currencies"),
    path("my/transactions/", BillingMyTransactionsView.as_view(), name="billing-my-transactions"),
    path("my/payouts/", BillingMyPayoutsView.as_view(), name="billing-my-payouts"),
    path("", include(router.urls)),
]
