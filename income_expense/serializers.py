from rest_framework import serializers

from employees.models import Employee

from .models import (
    BudgetLine,
    BudgetPlan,
    ExpenseCategory,
    ExpenseClaim,
    IncomeCategory,
    IncomeExpenseConfiguration,
    IncomeRecord,
)


class IncomeExpenseConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeExpenseConfiguration
        fields = "__all__"
        read_only_fields = [
            "id",
            "institution",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ExpenseCategorySerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return ExpenseCategory.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = ExpenseCategory
        fields = "__all__"
        read_only_fields = [
            "id",
            "institution_id",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_by_id",
        ]


class IncomeCategorySerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return IncomeCategory.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = IncomeCategory
        fields = "__all__"
        read_only_fields = [
            "id",
            "institution_id",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_by_id",
        ]


class BudgetPlanSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return BudgetPlan.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = BudgetPlan
        fields = "__all__"
        read_only_fields = [
            "id",
            "institution_id",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_by_id",
        ]


class BudgetLineSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        institution_id = self.context.get("institution_id")
        if tenant_db:
            if "budget_plan" in self.fields:
                plan_qs = BudgetPlan.objects.using(tenant_db)
                if institution_id is not None:
                    plan_qs = plan_qs.filter(institution_id=institution_id)
                self.fields["budget_plan"].queryset = plan_qs
            if "expense_category" in self.fields:
                exp_qs = ExpenseCategory.objects.using(tenant_db)
                if institution_id is not None:
                    exp_qs = exp_qs.filter(institution_id=institution_id)
                self.fields["expense_category"].queryset = exp_qs
            if "income_category" in self.fields:
                inc_qs = IncomeCategory.objects.using(tenant_db)
                if institution_id is not None:
                    inc_qs = inc_qs.filter(institution_id=institution_id)
                self.fields["income_category"].queryset = inc_qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return BudgetLine.objects.using(tenant_db).create(**validated_data)

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        category_type = attrs.get("category_type") or getattr(instance, "category_type", None)
        expense_category = attrs.get("expense_category") if "expense_category" in attrs else getattr(instance, "expense_category", None)
        income_category = attrs.get("income_category") if "income_category" in attrs else getattr(instance, "income_category", None)
        scope_type = attrs.get("scope_type") or getattr(instance, "scope_type", None)
        scope_id = attrs.get("scope_id") if "scope_id" in attrs else getattr(instance, "scope_id", None)

        if category_type == BudgetLine.CATEGORY_EXPENSE:
            if not expense_category or income_category:
                raise serializers.ValidationError("Expense category is required and income category must be empty.")
        if category_type == BudgetLine.CATEGORY_INCOME:
            if not income_category or expense_category:
                raise serializers.ValidationError("Income category is required and expense category must be empty.")

        if scope_type == IncomeExpenseConfiguration.SCOPE_COMPANY and scope_id is not None:
            raise serializers.ValidationError("Company scope must not include a scope_id.")
        if scope_type in [IncomeExpenseConfiguration.SCOPE_BRANCH, IncomeExpenseConfiguration.SCOPE_DEPARTMENT] and not scope_id:
            raise serializers.ValidationError("Branch/Department scope requires scope_id.")

        return attrs

    class Meta:
        model = BudgetLine
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_by_id",
        ]


class ExpenseClaimSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    category_name = serializers.CharField(source="expense_category.name", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        institution_id = self.context.get("institution_id")
        if tenant_db:
            if "employee" in self.fields:
                employee_qs = Employee.objects.using(tenant_db)
                if institution_id is not None:
                    employee_qs = employee_qs.filter(employer_id=institution_id)
                self.fields["employee"].queryset = employee_qs
            if "expense_category" in self.fields:
                exp_qs = ExpenseCategory.objects.using(tenant_db)
                if institution_id is not None:
                    exp_qs = exp_qs.filter(institution_id=institution_id)
                self.fields["expense_category"].queryset = exp_qs
            if "budget_line" in self.fields:
                line_qs = BudgetLine.objects.using(tenant_db)
                if institution_id is not None:
                    line_qs = line_qs.filter(budget_plan__institution_id=institution_id)
                self.fields["budget_line"].queryset = line_qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return ExpenseClaim.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = ExpenseClaim
        fields = "__all__"
        read_only_fields = [
            "id",
            "institution_id",
            "status",
            "submitted_at",
            "approved_by_id",
            "approved_at",
            "treasury_payment_line_id",
            "treasury_external_reference",
            "paid_at",
            "payment_failed",
            "payment_failed_reason",
            "budget_line",
            "budget_override_used",
            "budget_override_reason",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_by_id",
        ]


class IncomeRecordSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="income_category.name", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        institution_id = self.context.get("institution_id")
        if tenant_db:
            if "income_category" in self.fields:
                inc_qs = IncomeCategory.objects.using(tenant_db)
                if institution_id is not None:
                    inc_qs = inc_qs.filter(institution_id=institution_id)
                self.fields["income_category"].queryset = inc_qs
            if "budget_line" in self.fields:
                line_qs = BudgetLine.objects.using(tenant_db)
                if institution_id is not None:
                    line_qs = line_qs.filter(budget_plan__institution_id=institution_id)
                self.fields["budget_line"].queryset = line_qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return IncomeRecord.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = IncomeRecord
        fields = "__all__"
        read_only_fields = [
            "id",
            "institution_id",
            "status",
            "submitted_at",
            "approved_by_id",
            "approved_at",
            "received_at",
            "budget_line",
            "budget_override_used",
            "budget_override_reason",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_by_id",
        ]


class BudgetOverrideSerializer(serializers.Serializer):
    budget_override_reason = serializers.CharField(required=False, allow_blank=True)


class ExpenseRejectSerializer(serializers.Serializer):
    rejected_reason = serializers.CharField(required=False, allow_blank=True)


class ExpenseMarkPaidSerializer(serializers.Serializer):
    treasury_payment_line_id = serializers.UUIDField(required=False, allow_null=True)
    paid_at = serializers.DateTimeField(required=False, allow_null=True)


class IncomeMarkReceivedSerializer(serializers.Serializer):
    bank_statement_line_id = serializers.UUIDField(required=False, allow_null=True)
    received_at = serializers.DateTimeField(required=False, allow_null=True)


class TreasuryPaymentUpdateSerializer(serializers.Serializer):
    expense_id = serializers.UUIDField()
    treasury_payment_line_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=["PAID", "FAILED"])
    paid_at = serializers.DateTimeField(required=False, allow_null=True)
    external_reference = serializers.CharField(required=False, allow_blank=True)
