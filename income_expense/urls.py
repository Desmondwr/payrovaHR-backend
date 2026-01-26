from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BudgetLineViewSet,
    BudgetPlanViewSet,
    ExpenseCategoryViewSet,
    ExpenseClaimViewSet,
    IncomeCategoryViewSet,
    IncomeExpenseConfigurationView,
    IncomeRecordViewSet,
    TreasuryPaymentUpdateView,
)

router = DefaultRouter()
router.register(r"expense-categories", ExpenseCategoryViewSet, basename="expense-categories")
router.register(r"income-categories", IncomeCategoryViewSet, basename="income-categories")
router.register(r"budgets", BudgetPlanViewSet, basename="budgets")
router.register(r"budget-lines", BudgetLineViewSet, basename="budget-lines")
router.register(r"expenses", ExpenseClaimViewSet, basename="expenses")
router.register(r"income", IncomeRecordViewSet, basename="income")

urlpatterns = [
    path("config/", IncomeExpenseConfigurationView.as_view(), name="income-expense-config"),
    path("treasury/payment-update/", TreasuryPaymentUpdateView.as_view(), name="income-expense-treasury-update"),
]

urlpatterns += router.urls
