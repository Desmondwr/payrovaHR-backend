from rest_framework import serializers

from employees.models import Branch, Employee

from .models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    CashDesk,
    CashDeskSession,
    PaymentBatch,
    PaymentLine,
    ReconciliationMatch,
    TreasuryConfiguration,
)


class TreasuryConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryConfiguration
        fields = [
            "id",
            "institution",
            "is_active",
            "created_at",
            "updated_at",
            "default_currency",
            "enable_bank_accounts",
            "enable_cash_desks",
            "enable_mobile_money",
            "enable_cheques",
            "enable_reconciliation",
            "batch_reference_format",
            "transaction_reference_format",
            "cash_voucher_format",
            "sequence_reset_policy",
            "batch_approval_required",
            "batch_approval_threshold_amount",
            "dual_approval_required_for_payroll",
            "allow_self_approval",
            "cancellation_requires_approval",
            "line_approval_required",
            "line_approval_threshold_amount",
            "allow_edit_after_approval",
            "default_salary_payment_method",
            "default_expense_payment_method",
            "default_vendor_payment_method",
            "require_beneficiary_details_for_non_cash",
            "execution_proof_required",
            "enable_csv_export",
            "enable_iso20022_export",
            "csv_template_code",
            "require_open_session",
            "allow_negative_cash_balance",
            "max_cash_desk_balance",
            "min_balance_alert",
            "cash_out_approval_threshold",
            "cash_out_requires_reason",
            "adjustments_require_approval",
            "discrepancy_tolerance_amount",
            "auto_lock_cash_desk_on_discrepancy",
            "auto_match_enabled",
            "match_window_days",
            "auto_confirm_confidence_threshold",
            "matching_strictness",
            "lock_batch_until_reconciled",
        ]
        read_only_fields = [
            "id",
            "institution",
            "is_active",
            "created_at",
            "updated_at",
        ]


class BankAccountSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        employer_id = self.context.get("employer_id")
        if "branch" in self.fields and tenant_db:
            qs = Branch.objects.using(tenant_db)
            if employer_id is not None:
                qs = qs.filter(employer_id=employer_id)
            self.fields["branch"].queryset = qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return BankAccount.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = BankAccount
        fields = "__all__"
        read_only_fields = ["id", "employer_id", "created_at", "updated_at"]


class CashDeskSerializer(serializers.ModelSerializer):
    current_session_id = serializers.SerializerMethodField()
    current_session = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        employer_id = self.context.get("employer_id")
        if tenant_db:
            if "branch" in self.fields:
                branch_qs = Branch.objects.using(tenant_db)
                if employer_id is not None:
                    branch_qs = branch_qs.filter(employer_id=employer_id)
                self.fields["branch"].queryset = branch_qs
            if "custodian_employee" in self.fields:
                employee_qs = Employee.objects.using(tenant_db)
                if employer_id is not None:
                    employee_qs = employee_qs.filter(employer_id=employer_id)
                self.fields["custodian_employee"].queryset = employee_qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return CashDesk.objects.using(tenant_db).create(**validated_data)

    def _get_current_session(self, obj):
        if hasattr(obj, "_current_session_cache"):
            return obj._current_session_cache
        session = obj.sessions.filter(status=CashDeskSession.STATUS_OPEN).order_by("-opened_at").first()
        obj._current_session_cache = session
        return session

    def get_current_session_id(self, obj):
        session = self._get_current_session(obj)
        return str(session.id) if session else None

    def get_current_session(self, obj):
        session = self._get_current_session(obj)
        if not session:
            return None
        return CashDeskSessionSerializer(session).data

    class Meta:
        model = CashDesk
        fields = "__all__"
        read_only_fields = ["id", "employer_id", "created_at", "updated_at"]


class CashDeskSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashDeskSession
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class PaymentBatchSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        employer_id = self.context.get("employer_id")
        if "branch" in self.fields and tenant_db:
            qs = Branch.objects.using(tenant_db)
            if employer_id is not None:
                qs = qs.filter(employer_id=employer_id)
            self.fields["branch"].queryset = qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return PaymentBatch.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = PaymentBatch
        fields = "__all__"
        read_only_fields = [
            "id",
            "employer_id",
            "total_amount",
            "created_at",
            "updated_at",
        ]


class PaymentLineSerializer(serializers.ModelSerializer):
    batch_name = serializers.CharField(source="batch.name", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        employer_id = self.context.get("employer_id")
        if "batch" in self.fields and tenant_db:
            qs = PaymentBatch.objects.using(tenant_db)
            if employer_id is not None:
                qs = qs.filter(employer_id=employer_id)
            self.fields["batch"].queryset = qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return PaymentLine.objects.using(tenant_db).create(**validated_data)

    class Meta:
        model = PaymentLine
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class BankStatementSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True)
    bank_account_number = serializers.CharField(source="bank_account.account_number", read_only=True)
    bank_account_bank_name = serializers.CharField(source="bank_account.bank_name", read_only=True)
    bank_account_currency = serializers.CharField(source="bank_account.currency", read_only=True)
    statement_name = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        employer_id = self.context.get("employer_id")
        if "bank_account" in self.fields and tenant_db:
            qs = BankAccount.objects.using(tenant_db)
            if employer_id is not None:
                qs = qs.filter(employer_id=employer_id)
            self.fields["bank_account"].queryset = qs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        return BankStatement.objects.using(tenant_db).create(**validated_data)

    def get_statement_name(self, obj):
        bank_name = ""
        if getattr(obj, "bank_account", None):
            bank_name = obj.bank_account.name
        if bank_name:
            return f"{bank_name} {obj.period_start} - {obj.period_end}"
        return f"{obj.period_start} - {obj.period_end}"

    class Meta:
        model = BankStatement
        fields = "__all__"
        read_only_fields = ["id", "employer_id", "imported_at"]


class BankStatementLineMatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationMatch
        fields = [
            "id",
            "match_type",
            "match_id",
            "confidence",
            "status",
            "confirmed_by_id",
            "confirmed_at",
            "rejected_reason",
            "created_at",
        ]
        read_only_fields = fields


class BankStatementLineSerializer(serializers.ModelSerializer):
    matches = BankStatementLineMatchSerializer(many=True, read_only=True)
    matches_count = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        if "bank_statement" in self.fields and tenant_db:
            self.fields["bank_statement"].queryset = BankStatement.objects.using(tenant_db)

    def get_matches_count(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", {})
        if "matches" in cache:
            return len(cache["matches"])
        return obj.matches.count()

    class Meta:
        model = BankStatementLine
        fields = "__all__"
        read_only_fields = ["id"]


class ReconciliationMatchSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self.context.get("tenant_db")
        if "statement_line" in self.fields and tenant_db:
            self.fields["statement_line"].queryset = BankStatementLine.objects.using(tenant_db)

    class Meta:
        model = ReconciliationMatch
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class BankAccountWithdrawSerializer(serializers.Serializer):
    cashdesk_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class CashDeskSessionOpenSerializer(serializers.Serializer):
    opening_count_amount = serializers.DecimalField(max_digits=20, decimal_places=2)


class CashDeskSessionCloseSerializer(serializers.Serializer):
    closing_count_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    discrepancy_note = serializers.CharField(required=False, allow_blank=True)


class CashDeskOperationSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    category = serializers.CharField(max_length=20)
    notes = serializers.CharField(required=False, allow_blank=True)


class CashDeskTransferSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    bank_account_id = serializers.UUIDField()
    reference = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class PaymentLineStatusUpdateSerializer(serializers.Serializer):
    external_reference = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class BankStatementLineInputSerializer(serializers.Serializer):
    txn_date = serializers.DateField()
    description = serializers.CharField(required=False, allow_blank=True)
    amount_signed = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=10)
    reference_raw = serializers.CharField(required=False, allow_blank=True)
    external_id = serializers.CharField(required=False, allow_blank=True)


class BankStatementImportSerializer(serializers.Serializer):
    bank_account_id = serializers.UUIDField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    lines = BankStatementLineInputSerializer(many=True)


class ReconciliationActionSerializer(serializers.Serializer):
    match_id = serializers.UUIDField()
    rejected_reason = serializers.CharField(required=False, allow_blank=True)
