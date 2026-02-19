from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from accounts.database_utils import ensure_tenant_database_loaded, get_tenant_database_alias
from accounts.middleware import get_current_tenant_db
from accounts.models import EmployerProfile
from accounts.permissions import EmployerAccessPermission, EmployerOrEmployeeAccessPermission
from accounts.rbac import get_active_employer, is_delegate_user
from accounts.utils import api_response
from contracts.payroll_defaults import ensure_payroll_default_bases

from .models import CalculationBasis, CalculationBasisAdvantage, PayrollConfiguration, Salary
from .serializers import (
    CalculationBasisAdvantageSerializer,
    CalculationBasisSerializer,
    PayrollConfigurationSerializer,
    PayrollRunSerializer,
    PayrollValidateSerializer,
    SalaryDetailSerializer,
    SalarySummarySerializer,
)
from .services import PayrollCalculationService, validate_payroll


def _resolve_employee_tenant_db(employee):
    tenant_db = get_current_tenant_db()
    if tenant_db and tenant_db != "default":
        return tenant_db

    employer_id = getattr(employee, "employer_id", None)
    if not employer_id:
        return tenant_db or "default"

    employer = EmployerProfile.objects.filter(id=employer_id).first()
    if not employer:
        return tenant_db or "default"

    if employer.database_name:
        return ensure_tenant_database_loaded(employer)
    return get_tenant_database_alias(employer)


class EmployerContextMixin:
    def _resolve_employer(self):
        user = self.request.user
        if getattr(user, "employer_profile", None):
            return user.employer_profile

        resolved = get_active_employer(self.request, require_context=False)
        if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
            return resolved

        employee = getattr(user, "employee_profile", None)
        if employee and employee.employer_id:
            return EmployerProfile.objects.filter(id=employee.employer_id).first()
        return None

    def get_employer_id(self):
        employer = self._resolve_employer()
        if employer:
            return employer.id
        raise PermissionDenied("Employer context could not be resolved.")

    def get_tenant_db_alias(self):
        tenant_db = get_current_tenant_db()
        if tenant_db and tenant_db != "default":
            return tenant_db

        employer = self._resolve_employer()
        if employer:
            if employer.database_name:
                return ensure_tenant_database_loaded(employer)
            return get_tenant_database_alias(employer)
        return "default"


class PayrollTenantViewSet(EmployerContextMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {"*": ["payroll.manage"]}

    def get_queryset(self):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        return super().get_queryset().using(tenant_db).filter(employer_id=employer_id)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant_db"] = self.get_tenant_db_alias()
        context["employer_id"] = self.get_employer_id()
        return context

    def _create_in_tenant(self, serializer, **extra_fields):
        tenant_db = self.get_tenant_db_alias()
        model_cls = serializer.Meta.model
        create_data = dict(serializer.validated_data)
        create_data.update(extra_fields)
        instance = model_cls.objects.using(tenant_db).create(**create_data)
        serializer.instance = instance
        return instance

    def perform_create(self, serializer):
        self._create_in_tenant(serializer, employer_id=self.get_employer_id())

    def perform_destroy(self, instance):
        instance.delete(using=self.get_tenant_db_alias())


class PayrollConfigurationViewSet(PayrollTenantViewSet):
    queryset = PayrollConfiguration.objects.all()
    serializer_class = PayrollConfigurationSerializer

    def perform_create(self, serializer):
        employer_id = self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()
        with transaction.atomic(using=tenant_db):
            PayrollConfiguration.objects.using(tenant_db).filter(
                employer_id=employer_id,
                is_active=True,
            ).update(is_active=False)
            self._create_in_tenant(serializer, employer_id=employer_id, is_active=True)


class CalculationBasisViewSet(PayrollTenantViewSet):
    queryset = CalculationBasis.objects.all()
    serializer_class = CalculationBasisSerializer

    def get_queryset(self):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        ensure_payroll_default_bases(
            employer_id=employer_id,
            tenant_db=tenant_db,
        )
        return CalculationBasis.objects.using(tenant_db).filter(employer_id=employer_id)


class CalculationBasisAdvantageViewSet(PayrollTenantViewSet):
    queryset = CalculationBasisAdvantage.objects.all()
    serializer_class = CalculationBasisAdvantageSerializer


class PayrollRunView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["payroll.manage"]

    def post(self, request, mode):
        serializer = PayrollRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        employer_id = data.get("institution_id") or self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()

        service = PayrollCalculationService(
            employer_id=employer_id,
            year=data["year"],
            month=data["month"],
            tenant_db=tenant_db,
        )
        results = service.run(
            mode=mode,
            contract_id=data.get("contract_id"),
            branch_id=data.get("branch_id"),
            department_id=data.get("department_id"),
        )

        payload = []
        skipped = 0
        for result in results:
            row = SalaryDetailSerializer(result.salary, context={"request": request}).data
            row["outcome"] = result.outcome
            if result.reason:
                row["reason"] = result.reason
            if result.outcome != "OK":
                skipped += 1
            payload.append(row)

        return api_response(
            success=True,
            message="Payroll run completed.",
            data={
                "results": payload,
                "count": len(payload),
                "skipped": skipped,
                "processed": len(payload) - skipped,
            },
        )


class PayrollPayslipListView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["payroll.manage"]

    def get(self, request):
        employer_id = self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()

        qs = Salary.objects.using(tenant_db).filter(employer_id=employer_id)
        year = request.query_params.get("year")
        month = request.query_params.get("month")
        status = request.query_params.get("status")
        employee_id = request.query_params.get("employee_id")
        contract_id = request.query_params.get("contract_id")
        branch_id = request.query_params.get("branch_id")
        department_id = request.query_params.get("department_id")

        if year:
            qs = qs.filter(year=year)
        if month:
            qs = qs.filter(month=month)
        if status:
            qs = qs.filter(status=status)
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        if branch_id:
            qs = qs.filter(
                Q(contract__branch_id=branch_id) | Q(contract__employee__secondary_branches__id=branch_id)
            ).distinct()
        if department_id:
            qs = qs.filter(contract__department_id=department_id)

        serializer = SalarySummarySerializer(qs.order_by("-year", "-month", "-created_at"), many=True)
        return api_response(
            success=True,
            message="Payslips retrieved.",
            data={"results": serializer.data, "count": len(serializer.data)},
        )


class PayrollPayslipDetailView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["payroll.manage"]

    def get(self, request, salary_id):
        employer_id = self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()
        salary = get_object_or_404(
            Salary.objects.using(tenant_db),
            id=salary_id,
            employer_id=employer_id,
        )
        serializer = SalaryDetailSerializer(salary, context={"request": request})
        return api_response(success=True, message="Payslip retrieved.", data=serializer.data)


class PayrollMyPayslipListView(APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]

    def get(self, request):
        employee = getattr(request.user, "employee_profile", None)
        if not employee:
            raise PermissionDenied("Employee profile not available.")

        tenant_db = _resolve_employee_tenant_db(employee)
        qs = Salary.objects.using(tenant_db).filter(
            employee=employee,
            status=Salary.STATUS_VALIDATED,
        )
        year = request.query_params.get("year")
        month = request.query_params.get("month")
        if year:
            qs = qs.filter(year=year)
        if month:
            qs = qs.filter(month=month)

        serializer = SalarySummarySerializer(qs.order_by("-year", "-month", "-created_at"), many=True)
        return api_response(
            success=True,
            message="Payslips retrieved.",
            data={"results": serializer.data, "count": len(serializer.data)},
        )


class PayrollMyPayslipDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]

    def get(self, request, salary_id):
        employee = getattr(request.user, "employee_profile", None)
        if not employee:
            raise PermissionDenied("Employee profile not available.")

        tenant_db = _resolve_employee_tenant_db(employee)
        salary = get_object_or_404(
            Salary.objects.using(tenant_db),
            id=salary_id,
            employee=employee,
            status=Salary.STATUS_VALIDATED,
        )
        serializer = SalaryDetailSerializer(salary, context={"request": request})
        return api_response(success=True, message="Payslip retrieved.", data=serializer.data)


class PayrollValidateView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["payroll.manage"]

    def post(self, request):
        serializer = PayrollValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        employer_id = self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()

        qs = Salary.objects.using(tenant_db).filter(employer_id=employer_id)
        salary_ids = data.get("salary_ids")
        if salary_ids:
            qs = qs.filter(id__in=salary_ids)
        else:
            if data.get("year"):
                qs = qs.filter(year=data["year"])
            if data.get("month"):
                qs = qs.filter(month=data["month"])

        batches = validate_payroll(
            request=request,
            tenant_db=tenant_db,
            salaries=list(qs),
            allow_simulated=data.get("allow_simulated", False),
        )
        return api_response(
            success=True,
            message="Payroll validated and treasury batches created.",
            data={"batch_ids": [str(batch.id) for batch in batches]},
        )


class PayrollArchiveView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["payroll.manage"]

    def post(self, request):
        serializer = PayrollValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        employer_id = self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()

        qs = Salary.objects.using(tenant_db).filter(employer_id=employer_id)
        salary_ids = data.get("salary_ids")
        if salary_ids:
            qs = qs.filter(id__in=salary_ids)
        else:
            if data.get("year"):
                qs = qs.filter(year=data["year"])
            if data.get("month"):
                qs = qs.filter(month=data["month"])

        updated = qs.update(status=Salary.STATUS_ARCHIVED)
        return api_response(
            success=True,
            message="Payroll archived.",
            data={"archived_count": updated},
        )
