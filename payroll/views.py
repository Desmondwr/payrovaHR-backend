from django.db import transaction
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.database_utils import ensure_tenant_database_loaded, get_tenant_database_alias
from accounts.middleware import get_current_tenant_db
from accounts.permissions import EmployerAccessPermission, EmployerOrEmployeeAccessPermission
from accounts.rbac import get_active_employer, is_delegate_user

from .models import (
    Advantage,
    CalculationBasis,
    CalculationBasisAdvantage,
    CalculationScale,
    Deduction,
    PayrollConfiguration,
    PayrollElement,
    Salary,
    ScaleRange,
)
from .serializers import (
    AdvantageSerializer,
    CalculationBasisAdvantageSerializer,
    CalculationBasisSerializer,
    CalculationScaleSerializer,
    DeductionSerializer,
    PayrollConfigurationSerializer,
    PayrollElementSerializer,
    PayrollRunSerializer,
    PayrollValidateSerializer,
    SalaryDetailSerializer,
    SalarySummarySerializer,
    ScaleRangeSerializer,
)
from .services import PayrollCalculationService, validate_payroll


class EmployerContextMixin:
    def _parse_header(self):
        header_value = self.request.headers.get("x-employer-id")
        if not header_value:
            return None
        try:
            return int(header_value)
        except ValueError:
            raise PermissionDenied("Invalid employer id in header.")

    def get_employer_id(self):
        employer_id = self._parse_header()
        if employer_id:
            return employer_id
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return None
        if hasattr(user, "employer_profile") and user.employer_profile:
            return user.employer_profile.id
        resolved = get_active_employer(self.request, require_context=False)
        if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
            return resolved.id
        employee = getattr(user, "employee_profile", None)
        if employee:
            return employee.employer_id
        raise PermissionDenied("Employer context could not be determined.")

    def _get_alias_for_employer(self, employer_id):
        from accounts.models import EmployerProfile

        employer_profile = EmployerProfile.objects.filter(id=employer_id).first()
        if employer_profile and employer_profile.database_name:
            ensure_tenant_database_loaded(employer_profile)
            return get_tenant_database_alias(employer_profile)
        return "default"

    def get_tenant_db_alias(self):
        tenant_db = get_current_tenant_db()
        if tenant_db and tenant_db != "default":
            return tenant_db

        employer_id = self.get_employer_id()
        if employer_id:
            alias = self._get_alias_for_employer(employer_id)
            if alias:
                return alias

        return "default"

    def _require_tenant_db_alias(self):
        tenant_db = self.get_tenant_db_alias()
        if tenant_db == "default":
            raise PermissionDenied(
                "Tenant database context is required. Provide X-Employer-Id header or login as employer."
            )
        return tenant_db


class PayrollTenantViewSet(EmployerContextMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {"*": ["payroll.manage"]}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            self._require_tenant_db_alias()

    def get_queryset(self):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        qs = super().get_queryset().using(tenant_db)
        if employer_id:
            qs = qs.filter(employer_id=employer_id)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant_db"] = self.get_tenant_db_alias()
        context["employer_id"] = self.get_employer_id()
        return context

    def perform_create(self, serializer):
        employer_id = self.get_employer_id()
        serializer.save(employer_id=employer_id)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        tenant_db = self.get_tenant_db_alias()
        instance.delete(using=tenant_db)


class PayrollConfigurationViewSet(PayrollTenantViewSet):
    queryset = PayrollConfiguration.objects.all()
    serializer_class = PayrollConfigurationSerializer

    def perform_create(self, serializer):
        employer_id = self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()
        with transaction.atomic(using=tenant_db):
            PayrollConfiguration.objects.using(tenant_db).filter(
                employer_id=employer_id, is_active=True
            ).update(is_active=False)
            serializer.save(employer_id=employer_id, is_active=True)


class AdvantageViewSet(PayrollTenantViewSet):
    queryset = Advantage.objects.all()
    serializer_class = AdvantageSerializer


class DeductionViewSet(PayrollTenantViewSet):
    queryset = Deduction.objects.all()
    serializer_class = DeductionSerializer


class CalculationBasisViewSet(PayrollTenantViewSet):
    queryset = CalculationBasis.objects.all()
    serializer_class = CalculationBasisSerializer


class CalculationBasisAdvantageViewSet(PayrollTenantViewSet):
    queryset = CalculationBasisAdvantage.objects.all()
    serializer_class = CalculationBasisAdvantageSerializer


class CalculationScaleViewSet(PayrollTenantViewSet):
    queryset = CalculationScale.objects.all()
    serializer_class = CalculationScaleSerializer


class ScaleRangeViewSet(PayrollTenantViewSet):
    queryset = ScaleRange.objects.all()
    serializer_class = ScaleRangeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        scale_id = self.request.query_params.get("scale_id")
        if scale_id:
            qs = qs.filter(scale_id=scale_id)
        return qs


class PayrollElementViewSet(PayrollTenantViewSet):
    queryset = PayrollElement.objects.all()
    serializer_class = PayrollElementSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        contract_id = self.request.query_params.get("contract_id")
        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        return qs


class PayrollRunView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["payroll.manage"]

    def post(self, request, mode):
        serializer = PayrollRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        employer_id = data.get("institution_id") or self.get_employer_id()
        if not employer_id:
            raise ValidationError({"institution_id": "Institution id is required."})
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
        salaries = [result.salary for result in results]
        payload = SalaryDetailSerializer(salaries, many=True).data
        return Response({"results": payload, "count": len(payload)})


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

        serializer = SalarySummarySerializer(qs.order_by("-year", "-month"), many=True)
        return Response({"results": serializer.data, "count": len(serializer.data)})


class PayrollPayslipDetailView(EmployerContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["payroll.manage"]

    def get(self, request, salary_id):
        employer_id = self.get_employer_id()
        tenant_db = self.get_tenant_db_alias()
        salary = Salary.objects.using(tenant_db).filter(id=salary_id, employer_id=employer_id).first()
        if not salary:
            raise ValidationError({"detail": "Payslip not found."})
        serializer = SalaryDetailSerializer(salary)
        return Response(serializer.data)


class PayrollMyPayslipListView(APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]

    def get(self, request):
        employee = getattr(request.user, "employee_profile", None)
        if not employee:
            raise PermissionDenied("Employee profile not available.")
        tenant_db = get_current_tenant_db() or "default"
        qs = Salary.objects.using(tenant_db).filter(employee=employee)
        year = request.query_params.get("year")
        month = request.query_params.get("month")
        if year:
            qs = qs.filter(year=year)
        if month:
            qs = qs.filter(month=month)
        serializer = SalarySummarySerializer(qs.order_by("-year", "-month"), many=True)
        return Response({"results": serializer.data, "count": len(serializer.data)})


class PayrollMyPayslipDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]

    def get(self, request, salary_id):
        employee = getattr(request.user, "employee_profile", None)
        if not employee:
            raise PermissionDenied("Employee profile not available.")
        tenant_db = get_current_tenant_db() or "default"
        salary = Salary.objects.using(tenant_db).filter(id=salary_id, employee=employee).first()
        if not salary:
            raise ValidationError({"detail": "Payslip not found."})
        serializer = SalaryDetailSerializer(salary)
        return Response(serializer.data)


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

        batches = validate_payroll(request=request, tenant_db=tenant_db, salaries=list(qs))
        return Response({"batches": [str(batch.id) for batch in batches]})


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

        qs.update(status=Salary.STATUS_ARCHIVED)
        return Response({"detail": "Archived"})
