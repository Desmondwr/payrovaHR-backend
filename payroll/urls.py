from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .models import Salary
from .views import (
    AttendancePayrollImpactConfigViewSet,
    CalculationBasisAdvantageViewSet,
    CalculationBasisViewSet,
    PayrollArchiveView,
    PayrollConfigurationViewSet,
    PayrollMyPayslipDetailView,
    PayrollMyPayslipListView,
    PayrollPayslipDetailView,
    PayrollPayslipListView,
    PayrollRunView,
    PayrollValidateView,
)

router = DefaultRouter()
router.register(r"config", PayrollConfigurationViewSet, basename="payroll-config")
router.register(r"attendance-impacts", AttendancePayrollImpactConfigViewSet, basename="payroll-attendance-impacts")
router.register(r"bases", CalculationBasisViewSet, basename="payroll-bases")
router.register(r"basis-advantages", CalculationBasisAdvantageViewSet, basename="payroll-basis-advantages")

urlpatterns = [
    path("", include(router.urls)),
    path("simulate/", PayrollRunView.as_view(), {"mode": Salary.STATUS_SIMULATED}),
    path("generate/", PayrollRunView.as_view(), {"mode": Salary.STATUS_GENERATED}),
    path("payslips/", PayrollPayslipListView.as_view()),
    path("payslips/<uuid:salary_id>/", PayrollPayslipDetailView.as_view()),
    path("my-payslips/", PayrollMyPayslipListView.as_view()),
    path("my-payslips/<uuid:salary_id>/", PayrollMyPayslipDetailView.as_view()),
    path("validate/", PayrollValidateView.as_view()),
    path("archive/", PayrollArchiveView.as_view()),
]
