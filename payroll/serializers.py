from rest_framework import serializers

from contracts.models import Contract
from employees.models import Employee

from .models import (
    Advantage,
    CalculationBasis,
    CalculationBasisAdvantage,
    CalculationScale,
    Deduction,
    PayrollConfiguration,
    PayrollElement,
    Salary,
    SalaryAdvantage,
    SalaryDeduction,
    ScaleRange,
)


class PayrollConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollConfiguration
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class AdvantageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Advantage
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class CalculationScaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationScale
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class ScaleRangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScaleRange
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class DeductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deduction
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]

    def validate(self, attrs):
        is_rate = attrs.get("is_rate", getattr(self.instance, "is_rate", False))
        is_scale = attrs.get("is_scale", getattr(self.instance, "is_scale", False))
        is_base_table = attrs.get("is_base_table", getattr(self.instance, "is_base_table", False))
        methods = [is_rate, is_scale, is_base_table]
        if sum(bool(v) for v in methods) != 1:
            raise serializers.ValidationError("Select exactly one calculation method (rate, scale, or base table).")
        return attrs


class CalculationBasisSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationBasis
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class CalculationBasisAdvantageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationBasisAdvantage
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]


class PayrollElementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollElement
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "employer_id"]

    def validate(self, attrs):
        advantage = attrs.get("advantage", getattr(self.instance, "advantage", None))
        deduction = attrs.get("deduction", getattr(self.instance, "deduction", None))
        if bool(advantage) == bool(deduction):
            raise serializers.ValidationError("Element must link to either an advantage or a deduction.")
        return attrs


class SalaryAdvantageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryAdvantage
        fields = [
            "id",
            "advantage",
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
