from rest_framework import serializers

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
    advantages = SalaryAdvantageSerializer(many=True, read_only=True)
    deductions = SalaryDeductionSerializer(many=True, read_only=True)

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
