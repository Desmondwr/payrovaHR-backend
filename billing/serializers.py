from django.utils import timezone
from rest_framework import serializers

from .models import (
    BillingAuditLog,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPaymentAttempt,
    BillingPayout,
    BillingPayoutBatch,
    BillingPayoutConfiguration,
    BillingPlan,
    BillingTransaction,
    EmployerSubscription,
    FundingMethod,
    GbPayEmployerConnection,
    PayoutMethod,
)
from .gbpay_ops import verify_payout_destination
from .services import set_default_funding_method, set_default_payout_method


class FundingMethodSerializer(serializers.ModelSerializer):
    set_as_default_subscription = serializers.BooleanField(write_only=True, required=False)
    set_as_default_payroll = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = FundingMethod
        fields = "__all__"
        read_only_fields = [
            "id",
            "employer_id",
            "verification_status",
            "verified_at",
            "is_default_subscription",
            "is_default_payroll",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        set_subscription = validated_data.pop("set_as_default_subscription", False)
        set_payroll = validated_data.pop("set_as_default_payroll", False)
        instance = FundingMethod.objects.using(tenant_db).create(**validated_data)
        actor_id = self.context.get("actor_id")
        if set_subscription:
            set_default_funding_method(
                instance,
                tenant_db=tenant_db,
                scope="SUBSCRIPTION",
                actor_id=actor_id,
            )
        if set_payroll:
            set_default_funding_method(
                instance,
                tenant_db=tenant_db,
                scope="PAYROLL",
                actor_id=actor_id,
            )
        return instance


class BillingPayoutConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPayoutConfiguration
        fields = [
            "id",
            "employer_id",
            "is_active",
            "payroll_provider",
            "expense_provider",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "employer_id",
            "is_active",
            "created_at",
            "updated_at",
        ]


class PayoutMethodSerializer(serializers.ModelSerializer):
    set_as_default = serializers.BooleanField(write_only=True, required=False)
    account_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    wallet_destination = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = PayoutMethod
        exclude = ["account_number_encrypted", "wallet_destination_encrypted", "verification_payload"]
        read_only_fields = [
            "id",
            "employee",
            "verification_status",
            "verified_at",
            "verification_reference",
            "is_default",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        method_type = (attrs.get("method_type") or getattr(instance, "method_type", "")).upper()
        if method_type not in [PayoutMethod.METHOD_BANK_ACCOUNT, PayoutMethod.METHOD_MOBILE_MONEY]:
            raise serializers.ValidationError("Payout method type must be BANK_ACCOUNT or MOBILE_MONEY.")

        country = attrs.get("country") or getattr(instance, "country", "")
        entity_product_uuid = attrs.get("entity_product_uuid") or getattr(instance, "entity_product_uuid", "")
        if not country:
            raise serializers.ValidationError("country is required.")
        if not entity_product_uuid:
            raise serializers.ValidationError("entity_product_uuid is required.")

        if method_type == PayoutMethod.METHOD_BANK_ACCOUNT:
            bank_code = attrs.get("bank_code") or getattr(instance, "bank_code", "")
            account_number = attrs.get("account_number")
            if not bank_code:
                raise serializers.ValidationError("bank_code is required for bank payout destinations.")
            if not account_number and not getattr(instance, "account_number_encrypted", ""):
                raise serializers.ValidationError("account_number is required for bank payout destinations.")

        if method_type == PayoutMethod.METHOD_MOBILE_MONEY:
            operator_code = attrs.get("operator_code") or getattr(instance, "operator_code", "")
            wallet_destination = attrs.get("wallet_destination")
            if not operator_code:
                raise serializers.ValidationError("operator_code is required for mobile money payout destinations.")
            if not wallet_destination and not getattr(instance, "wallet_destination_encrypted", ""):
                raise serializers.ValidationError("wallet_destination is required for mobile money payout destinations.")

        return attrs

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        set_default = validated_data.pop("set_as_default", False)
        employee = self.context.get("employee")
        if not employee:
            raise serializers.ValidationError("Employee context required.")
        account_number = validated_data.pop("account_number", None)
        wallet_destination = validated_data.pop("wallet_destination", None)

        verification = verify_payout_destination(
            tenant_db=tenant_db,
            employer_id=getattr(employee, "employer_id", None),
            method_type=validated_data.get("method_type"),
            bank_code=validated_data.get("bank_code"),
            operator_code=validated_data.get("operator_code"),
            account_number=account_number,
            wallet_destination=wallet_destination,
            country_code=validated_data.get("country"),
            entity_product_uuid=validated_data.get("entity_product_uuid"),
        )

        instance = PayoutMethod(employee=employee, **validated_data)
        instance.verification_status = PayoutMethod.VERIFICATION_VERIFIED
        instance.verified_at = timezone.now()
        instance.verification_reference = verification.get("reference") or ""
        instance.verification_payload = verification.get("payload") or {}
        if verification.get("account_name") and not instance.account_holder_name:
            instance.account_holder_name = verification.get("account_name")
        if account_number:
            instance.set_account_number(account_number)
        if wallet_destination:
            instance.set_wallet_destination(wallet_destination)
        instance.save(using=tenant_db)
        actor_id = self.context.get("actor_id")
        if set_default:
            set_default_payout_method(instance, tenant_db=tenant_db, actor_id=actor_id)
        return instance

    def update(self, instance, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        set_default = validated_data.pop("set_as_default", False)
        account_number = validated_data.pop("account_number", None)
        wallet_destination = validated_data.pop("wallet_destination", None)

        reverify = any(
            key in validated_data
            for key in ("bank_code", "operator_code", "country", "entity_product_uuid")
        ) or account_number or wallet_destination

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if account_number:
            instance.set_account_number(account_number)
        if wallet_destination:
            instance.set_wallet_destination(wallet_destination)

        if reverify:
            verification = verify_payout_destination(
                tenant_db=tenant_db,
                employer_id=getattr(instance.employee, "employer_id", None),
                method_type=instance.method_type,
                bank_code=instance.bank_code,
                operator_code=instance.operator_code,
                account_number=account_number or instance.get_account_number(),
                wallet_destination=wallet_destination or instance.get_wallet_destination(),
                country_code=instance.country,
                entity_product_uuid=instance.entity_product_uuid,
            )
            instance.verification_status = PayoutMethod.VERIFICATION_VERIFIED
            instance.verified_at = timezone.now()
            instance.verification_reference = verification.get("reference") or instance.verification_reference
            instance.verification_payload = verification.get("payload") or {}
            if verification.get("account_name") and not instance.account_holder_name:
                instance.account_holder_name = verification.get("account_name")

        instance.save(using=tenant_db)

        actor_id = self.context.get("actor_id")
        if set_default:
            set_default_payout_method(instance, tenant_db=tenant_db, actor_id=actor_id)
        return instance


class BillingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPlan
        fields = "__all__"
        read_only_fields = ["id", "employer_id", "created_at", "updated_at"]


class EmployerSubscriptionSerializer(serializers.ModelSerializer):
    plan_detail = BillingPlanSerializer(source="plan", read_only=True)

    class Meta:
        model = EmployerSubscription
        fields = "__all__"
        read_only_fields = [
            "id",
            "employer_id",
            "status",
            "current_period_start",
            "current_period_end",
            "next_billing_date",
            "billing_cycle_anchor",
            "canceled_at",
            "created_at",
            "updated_at",
        ]


class BillingInvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingInvoiceLine
        fields = "__all__"
        read_only_fields = ["id", "invoice", "created_at"]


class BillingInvoiceSerializer(serializers.ModelSerializer):
    line_items = BillingInvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = BillingInvoice
        fields = "__all__"
        read_only_fields = [
            "id",
            "employer_id",
            "number",
            "status",
            "subtotal",
            "tax_amount",
            "total_amount",
            "issued_at",
            "paid_at",
            "voided_at",
            "is_finalized",
            "created_at",
            "updated_at",
        ]


class BillingTransactionSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = BillingTransaction
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class BillingPayoutBatchSerializer(serializers.ModelSerializer):
    payout_count = serializers.IntegerField(source="payouts.count", read_only=True)

    class Meta:
        model = BillingPayoutBatch
        fields = "__all__"
        read_only_fields = [
            "id",
            "employer_id",
            "created_at",
            "updated_at",
            "total_amount",
            "requires_approval",
            "approved_by_id",
            "approved_at",
        ]


class BillingPayoutSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    payout_method_label = serializers.CharField(source="payout_method.label", read_only=True)

    class Meta:
        model = BillingPayout
        fields = "__all__"
        read_only_fields = [
            "id",
            "employer_id",
            "employer_transaction",
            "employee_transaction",
            "created_at",
            "updated_at",
        ]


class BillingPaymentAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPaymentAttempt
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class BillingAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingAuditLog
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class GbPayConnectionSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False)
    secret_key = serializers.CharField(write_only=True, required=False, allow_blank=False)
    scope = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = GbPayEmployerConnection
        fields = [
            "id",
            "employer_id",
            "label",
            "environment",
            "is_active",
            "status",
            "credentials_hint",
            "last_validated_at",
            "last_validation_error",
            "created_at",
            "updated_at",
            "api_key",
            "secret_key",
            "scope",
        ]
        read_only_fields = [
            "id",
            "employer_id",
            "is_active",
            "status",
            "credentials_hint",
            "last_validated_at",
            "last_validation_error",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        if not self.instance:
            required = ["api_key", "secret_key", "scope"]
            missing = [key for key in required if not attrs.get(key)]
            if missing:
                raise serializers.ValidationError(f"Missing GbPay credentials: {', '.join(missing)}")
        return attrs


class GbPayBatchItemSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=0.01)
    currency = serializers.CharField(required=False, allow_blank=True)
    payout_method_id = serializers.UUIDField(required=False, allow_null=True)
    linked_object_type = serializers.CharField(required=False, allow_blank=True)
    linked_object_id = serializers.UUIDField(required=False, allow_null=True)
    treasury_payment_line_id = serializers.UUIDField(required=False, allow_null=True)
    treasury_batch_id = serializers.UUIDField(required=False, allow_null=True)


class GbPayBatchCreateSerializer(serializers.Serializer):
    batch_type = serializers.ChoiceField(choices=[BillingPayoutBatch.TYPE_PAYROLL, BillingPayoutBatch.TYPE_EXPENSE])
    currency = serializers.CharField(required=False, allow_blank=True)
    planned_date = serializers.DateField(required=False)
    auto_start = serializers.BooleanField(default=False)
    items = GbPayBatchItemSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one payout item is required.")
        return value


class FundingDefaultSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=["SUBSCRIPTION", "PAYROLL"])


class PayoutDefaultSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(default=True)


class SubscriptionCreateSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    start_date = serializers.DateField(required=False)
    auto_renew = serializers.BooleanField(default=True)
    funding_method_id = serializers.UUIDField(required=False)


class InvoiceIssueSerializer(serializers.Serializer):
    issue = serializers.BooleanField(default=True)
    auto_charge = serializers.BooleanField(default=True)


class InvoicePaymentUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["PAID", "FAILED"])
    provider_reference = serializers.CharField(required=False, allow_blank=True)
    failure_reason = serializers.CharField(required=False, allow_blank=True)


class PayoutStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["PAID", "FAILED", "REVERSED"])
    provider_reference = serializers.CharField(required=False, allow_blank=True)
    failure_reason = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(required=False, allow_blank=True)


class TransactionRefundSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)
