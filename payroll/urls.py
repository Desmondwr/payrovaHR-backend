from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CalculationBasisAdvantageViewSet,
    CalculationBasisViewSet,
    CalculationScaleViewSet,
    PayrollArchiveView,
    PayrollConfigurationViewSet,
    PayrollElementViewSet,
    PayrollPayslipDetailView,
    PayrollPayslipListView,
    PayrollMyPayslipDetailView,
    PayrollMyPayslipListView,
    PayrollRunView,
    PayrollValidateView,
    ScaleRangeViewSet,
)
from .models import Salary

router = DefaultRouter()
router.register(r"config", PayrollConfigurationViewSet, basename="payroll-config")
router.register(r"bases", CalculationBasisViewSet, basename="payroll-bases")
router.register(r"basis-advantages", CalculationBasisAdvantageViewSet, basename="payroll-basis-advantages")
router.register(r"scales", CalculationScaleViewSet, basename="payroll-scales")
router.register(r"scale-ranges", ScaleRangeViewSet, basename="payroll-scale-ranges")
router.register(r"elements", PayrollElementViewSet, basename="payroll-elements")

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
