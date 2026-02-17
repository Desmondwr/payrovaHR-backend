from rest_framework import serializers

from accounts.models import EmployerProfile
from contracts.models import Allowance

from .models import (
    CalculationBasis,
    CalculationBasisAdvantage,
    PayrollConfiguration,
    Salary,
    SalaryAdvantage,
    SalaryDeduction,
)


class PayrollConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollConfiguration
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class CalculationBasisSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationBasis
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class CalculationBasisAdvantageSerializer(serializers.ModelSerializer):
    basis_code = serializers.CharField(source="basis.code", read_only=True)
    basis_name = serializers.CharField(source="basis.name", read_only=True)
    allowance_name = serializers.CharField(source="allowance.name", read_only=True)
    allowance_code_display = serializers.SerializerMethodField()

    class Meta:
        model = CalculationBasisAdvantage
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "employer_id",
            "basis_code",
            "basis_name",
            "allowance_name",
            "allowance_code_display",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        employer_id = self.context.get("employer_id")
        if tenant_db and "allowance" in self.fields:
            allowance_qs = Allowance.objects.using(tenant_db)
            if employer_id is not None:
                allowance_qs = allowance_qs.filter(contract__employer_id=employer_id)
            self.fields["allowance"].queryset = allowance_qs
        if tenant_db and "basis" in self.fields:
            basis_qs = CalculationBasis.objects.using(tenant_db)
            if employer_id is not None:
                basis_qs = basis_qs.filter(employer_id=employer_id)
            self.fields["basis"].queryset = basis_qs

    def get_allowance_code_display(self, obj):
        if obj.allowance_code:
            return obj.allowance_code
        if obj.allowance:
            return obj.allowance.code
        return None

    def validate(self, attrs):
        allowance = attrs.get("allowance", getattr(self.instance, "allowance", None))
        allowance_code = attrs.get("allowance_code", getattr(self.instance, "allowance_code", None))
        if bool(allowance) == bool(allowance_code):
            raise serializers.ValidationError(
                "Provide exactly one mapping target: allowance OR allowance_code."
            )

        tenant_db = self.context.get("tenant_db")
        employer_id = self.context.get("employer_id")
        basis = attrs.get("basis", getattr(self.instance, "basis", None))

        if tenant_db and basis is not None:
            basis_id = getattr(basis, "id", basis)
            basis_qs = CalculationBasis.objects.using(tenant_db).filter(id=basis_id)
            if employer_id is not None:
                basis_qs = basis_qs.filter(employer_id=employer_id)
            basis_row = basis_qs.first()
            if not basis_row:
                raise serializers.ValidationError(
                    {"basis": "Selected basis does not exist for the active employer/tenant."}
                )
            attrs["basis"] = basis_row

        if tenant_db and allowance is not None:
            allowance_id = getattr(allowance, "id", allowance)
            allowance_qs = Allowance.objects.using(tenant_db).filter(id=allowance_id)
            if employer_id is not None:
                allowance_qs = allowance_qs.filter(contract__employer_id=employer_id)
            allowance_row = allowance_qs.first()
            if not allowance_row:
                raise serializers.ValidationError(
                    {"allowance": "Selected allowance does not exist for the active employer/tenant."}
                )
            attrs["allowance"] = allowance_row

        return attrs


class SalaryAdvantageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryAdvantage
        fields = [
            "id",
            "allowance",
            "code",
            "name",
            "base",
            "amount",
        ]
        read_only_fields = fields


class SalaryDeductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryDeduction
        fields = [
            "id",
            "deduction",
            "code",
            "name",
            "base_amount",
            "rate",
            "amount",
            "is_employee",
            "is_employer",
        ]
        read_only_fields = fields


class SalarySummarySerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_number = serializers.CharField(source="employee.employee_id", read_only=True)

    class Meta:
        model = Salary
        fields = [
            "id",
            "contract",
            "employee",
            "employee_name",
            "employee_number",
            "year",
            "month",
            "status",
            "gross_salary",
            "net_salary",
            "total_employee_deductions",
            "total_employer_deductions",
        ]

    def get_employee_name(self, obj):
        if not obj.employee:
            return ""
        return " ".join(
            part for part in [obj.employee.first_name, obj.employee.middle_name, obj.employee.last_name] if part
        )


class SalaryDetailSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_number = serializers.CharField(source="employee.employee_id", read_only=True)
    contract_ref = serializers.CharField(source="contract.contract_id", read_only=True)
    currency = serializers.CharField(source="contract.currency", read_only=True)
    department_name = serializers.CharField(source="contract.department.name", read_only=True)
    position = serializers.CharField(source="employee.job_title", read_only=True)
    cnps_number = serializers.CharField(source="employee.cnps_number", read_only=True)
    company_name = serializers.SerializerMethodField()
    company_address = serializers.SerializerMethodField()
    company_phone = serializers.SerializerMethodField()
    company_email = serializers.SerializerMethodField()
    company_logo = serializers.SerializerMethodField()
    company_logo_url = serializers.SerializerMethodField()
    advantages = SalaryAdvantageSerializer(many=True, read_only=True)
    deductions = SalaryDeductionSerializer(many=True, read_only=True)

    class Meta:
        model = Salary
        fields = [
            "id",
            "contract",
            "contract_ref",
            "employee",
            "employee_name",
            "employee_number",
            "currency",
            "department_name",
            "position",
            "cnps_number",
            "company_name",
            "company_address",
            "company_phone",
            "company_email",
            "company_logo",
            "company_logo_url",
            "year",
            "month",
            "status",
            "base_salary",
            "gross_salary",
            "taxable_gross_salary",
            "irpp_taxable_gross_salary",
            "contribution_base_af_pv",
            "contribution_base_at",
            "total_advantages",
            "total_employee_deductions",
            "total_employer_deductions",
            "net_salary",
            "leave_days",
            "absence_days",
            "overtime_hours",
            "advantages",
            "deductions",
        ]

    def get_employee_name(self, obj):
        if not obj.employee:
            return ""
        return " ".join(
            part for part in [obj.employee.first_name, obj.employee.middle_name, obj.employee.last_name] if part
        )

    def _get_employer_profile(self, obj):
        employer_id = getattr(obj, "employer_id", None)
        if not employer_id:
            return None
        cache = self.context.setdefault("_employer_profile_cache", {})
        if employer_id not in cache:
            cache[employer_id] = EmployerProfile.objects.filter(id=employer_id).first()
        return cache[employer_id]

    def get_company_name(self, obj):
        employer = self._get_employer_profile(obj)
        return getattr(employer, "company_name", "") if employer else ""

    def get_company_address(self, obj):
        employer = self._get_employer_profile(obj)
        if not employer:
            return ""
        physical = str(getattr(employer, "physical_address", "") or "").strip()
        location = str(getattr(employer, "company_location", "") or "").strip()
        if physical and location:
            return f"{physical}, {location}"
        return physical or location or ""

    def get_company_phone(self, obj):
        employer = self._get_employer_profile(obj)
        return str(getattr(employer, "phone_number", "") or "") if employer else ""

    def get_company_email(self, obj):
        employer = self._get_employer_profile(obj)
        return str(getattr(employer, "official_company_email", "") or "") if employer else ""

    def get_company_logo(self, obj):
        employer = self._get_employer_profile(obj)
        if not employer:
            return ""
        logo_field = getattr(employer, "company_logo", None)
        if not logo_field:
            return ""
        try:
            return logo_field.url or ""
        except Exception:
            return str(logo_field or "")

    def get_company_logo_url(self, obj):
        logo_path = self.get_company_logo(obj)
        if not logo_path:
            return ""
        if str(logo_path).startswith("http://") or str(logo_path).startswith("https://"):
            return logo_path

        request = self.context.get("request")
        if not request:
            return logo_path

        normalized_path = str(logo_path)
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        try:
            return request.build_absolute_uri(normalized_path)
        except Exception:
            return logo_path


class PayrollRunSerializer(serializers.Serializer):
    institution_id = serializers.IntegerField(required=False)
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    contract_id = serializers.UUIDField(required=False, allow_null=True)
    branch_id = serializers.UUIDField(required=False, allow_null=True)
    department_id = serializers.UUIDField(required=False, allow_null=True)


class PayrollValidateSerializer(serializers.Serializer):
    salary_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    year = serializers.IntegerField(required=False)
    month = serializers.IntegerField(required=False)
    allow_simulated = serializers.BooleanField(required=False, default=False)
