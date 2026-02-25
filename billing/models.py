import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .crypto import decrypt_value, encrypt_value


def mask_mobile(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"


class FundingMethod(models.Model):
    METHOD_BANK_ACCOUNT = "BANK_ACCOUNT"
    METHOD_CARD = "CARD"
    METHOD_MOBILE_MONEY = "MOBILE_MONEY"
    METHOD_WALLET = "WALLET"
    METHOD_OTHER = "OTHER"

    METHOD_CHOICES = [
        (METHOD_BANK_ACCOUNT, "Bank Account"),
        (METHOD_CARD, "Card"),
        (METHOD_MOBILE_MONEY, "Mobile Money"),
        (METHOD_WALLET, "Wallet"),
        (METHOD_OTHER, "Other"),
    ]

    VERIFICATION_UNVERIFIED = "UNVERIFIED"
    VERIFICATION_PENDING = "PENDING"
    VERIFICATION_VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "FAILED"

    VERIFICATION_CHOICES = [
        (VERIFICATION_UNVERIFIED, "Unverified"),
        (VERIFICATION_PENDING, "Pending"),
        (VERIFICATION_VERIFIED, "Verified"),
        (VERIFICATION_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    method_type = models.CharField(max_length=30, choices=METHOD_CHOICES)
    provider = models.CharField(max_length=60, blank=True)
    label = models.CharField(max_length=120, blank=True)
    currency = models.CharField(max_length=10, default="XAF")
    country = models.CharField(max_length=2, blank=True)
    account_holder_name = models.CharField(max_length=255, blank=True)
    account_last4 = models.CharField(max_length=4, blank=True)
    bank_name = models.CharField(max_length=255, blank=True)
    mobile_number = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_CHOICES,
        default=VERIFICATION_UNVERIFIED,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    is_default_subscription = models.BooleanField(default=False)
    is_default_payroll = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_funding_methods"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employer_id"],
                condition=Q(is_default_subscription=True, is_active=True),
                name="uniq_billing_funding_default_subscription",
            ),
            models.UniqueConstraint(
                fields=["employer_id"],
                condition=Q(is_default_payroll=True, is_active=True),
                name="uniq_billing_funding_default_payroll",
            ),
        ]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
            models.Index(fields=["employer_id", "method_type"]),
        ]

    def __str__(self):
        return f"{self.method_type} ({self.employer_id})"


class BillingPayoutConfiguration(models.Model):
    PROVIDER_MANUAL = "MANUAL"
    PROVIDER_GBPAY = "GBPAY"

    PROVIDER_CHOICES = [
        (PROVIDER_MANUAL, "Manual"),
        (PROVIDER_GBPAY, "GbPay"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    is_active = models.BooleanField(default=True)
    payroll_provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_MANUAL,
    )
    expense_provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_MANUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_payout_configurations"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employer_id"],
                condition=Q(is_active=True),
                name="uniq_billing_payout_config_active_per_employer",
            ),
        ]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
        ]

    def __str__(self):
        return f"Billing Payout Config ({self.employer_id})"


class PayoutMethod(models.Model):
    METHOD_BANK_ACCOUNT = "BANK_ACCOUNT"
    METHOD_MOBILE_MONEY = "MOBILE_MONEY"
    METHOD_WALLET = "WALLET"
    METHOD_CASH = "CASH"
    METHOD_OTHER = "OTHER"

    METHOD_CHOICES = [
        (METHOD_BANK_ACCOUNT, "Bank Account"),
        (METHOD_MOBILE_MONEY, "Mobile Money"),
        (METHOD_WALLET, "Wallet"),
        (METHOD_CASH, "Cash"),
        (METHOD_OTHER, "Other"),
    ]

    VERIFICATION_CHOICES = FundingMethod.VERIFICATION_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="payout_methods",
    )
    method_type = models.CharField(max_length=30, choices=METHOD_CHOICES)
    provider = models.CharField(max_length=60, blank=True)
    label = models.CharField(max_length=120, blank=True)
    currency = models.CharField(max_length=10, default="XAF")
    country = models.CharField(max_length=2, blank=True)
    account_holder_name = models.CharField(max_length=255, blank=True)
    account_last4 = models.CharField(max_length=4, blank=True)
    bank_name = models.CharField(max_length=255, blank=True)
    bank_code = models.CharField(max_length=60, blank=True)
    operator_code = models.CharField(max_length=60, blank=True)
    entity_product_uuid = models.CharField(max_length=120, blank=True)
    country_id = models.IntegerField(null=True, blank=True)
    account_number_encrypted = models.TextField(blank=True)
    wallet_destination_encrypted = models.TextField(blank=True)
    mobile_number = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_CHOICES,
        default=FundingMethod.VERIFICATION_UNVERIFIED,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    verification_reference = models.CharField(max_length=120, blank=True)
    verification_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_payout_methods"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(is_default=True, is_active=True),
                name="uniq_billing_payout_default_employee",
            )
        ]
        indexes = [
            models.Index(fields=["employee", "is_active"]),
            models.Index(fields=["employee", "method_type"]),
        ]

    def __str__(self):
        return f"{self.method_type} ({self.employee_id})"

    def set_account_number(self, value: str):
        self.account_number_encrypted = encrypt_value(value) if value else ""
        self.account_last4 = (str(value)[-4:] if value else "")

    def get_account_number(self) -> str:
        return decrypt_value(self.account_number_encrypted)

    def set_wallet_destination(self, value: str):
        self.wallet_destination_encrypted = encrypt_value(value) if value else ""
        self.mobile_number = mask_mobile(value)

    def get_wallet_destination(self) -> str:
        return decrypt_value(self.wallet_destination_encrypted)


class BillingPlan(models.Model):
    INTERVAL_MONTHLY = "MONTHLY"
    INTERVAL_QUARTERLY = "QUARTERLY"
    INTERVAL_YEARLY = "YEARLY"

    INTERVAL_CHOICES = [
        (INTERVAL_MONTHLY, "Monthly"),
        (INTERVAL_QUARTERLY, "Quarterly"),
        (INTERVAL_YEARLY, "Yearly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES, default=INTERVAL_MONTHLY)
    interval_count = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=10, default="XAF")
    trial_days = models.PositiveIntegerField(default=0)
    tax_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_plans"
        ordering = ["-created_at"]
        unique_together = [["employer_id", "code"]]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
        ]

    def __str__(self):
        return f"{self.code} ({self.employer_id})"


class EmployerSubscription(models.Model):
    STATUS_TRIALING = "TRIALING"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_PAST_DUE = "PAST_DUE"
    STATUS_PAUSED = "PAUSED"
    STATUS_CANCELED = "CANCELED"

    STATUS_CHOICES = [
        (STATUS_TRIALING, "Trialing"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past Due"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_CANCELED, "Canceled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    plan = models.ForeignKey(
        BillingPlan,
        on_delete=models.SET_NULL,
        null=True,
        related_name="subscriptions",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIALING)
    current_period_start = models.DateField(null=True, blank=True)
    current_period_end = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True)
    billing_cycle_anchor = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    default_funding_method = models.ForeignKey(
        FundingMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_defaults",
    )
    canceled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_subscriptions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
        ]

    def __str__(self):
        return f"Subscription {self.id} ({self.employer_id})"


class BillingSequence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    key = models.CharField(max_length=20, db_index=True)
    last_number = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_sequences"
        unique_together = [["employer_id", "key"]]
        indexes = [
            models.Index(fields=["employer_id", "key"]),
        ]

    def __str__(self):
        return f"{self.employer_id}:{self.key}"


class BillingInvoice(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_ISSUED = "ISSUED"
    STATUS_PAID = "PAID"
    STATUS_VOID = "VOID"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_PAID, "Paid"),
        (STATUS_VOID, "Void"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    subscription = models.ForeignKey(
        EmployerSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    number = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    currency = models.CharField(max_length=10, default="XAF")
    subtotal = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    tax_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    pdf_file = models.FileField(upload_to="billing/invoices/", null=True, blank=True)
    is_finalized = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_invoices"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["employer_id", "number"]),
        ]

    def __str__(self):
        return f"Invoice {self.number}"

    def save(self, *args, **kwargs):
        if self.pk and self.is_finalized:
            existing = BillingInvoice.objects.using(self._state.db).filter(pk=self.pk).first()
            if existing and existing.is_finalized:
                immutable_fields = [
                    "employer_id",
                    "subscription_id",
                    "period_start",
                    "period_end",
                    "number",
                    "currency",
                    "subtotal",
                    "tax_rate",
                    "tax_amount",
                    "total_amount",
                    "issued_at",
                ]
                for field in immutable_fields:
                    if getattr(existing, field) != getattr(self, field):
                        raise ValidationError("Issued invoices are immutable.")
        super().save(*args, **kwargs)


class BillingInvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        BillingInvoice,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_invoice_lines"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["invoice"]),
        ]

    def __str__(self):
        return f"{self.description} ({self.amount})"


class BillingTransaction(models.Model):
    ROLE_EMPLOYER = "EMPLOYER"
    ROLE_EMPLOYEE = "EMPLOYEE"

    ROLE_CHOICES = [
        (ROLE_EMPLOYER, "Employer"),
        (ROLE_EMPLOYEE, "Employee"),
    ]

    DIRECTION_DEBIT = "DEBIT"
    DIRECTION_CREDIT = "CREDIT"

    DIRECTION_CHOICES = [
        (DIRECTION_DEBIT, "Debit"),
        (DIRECTION_CREDIT, "Credit"),
    ]

    CATEGORY_SUBSCRIPTION = "SUBSCRIPTION"
    CATEGORY_PAYROLL = "PAYROLL"
    CATEGORY_EXPENSE = "EXPENSE"
    CATEGORY_REFUND = "REFUND"
    CATEGORY_ADJUSTMENT = "ADJUSTMENT"

    CATEGORY_CHOICES = [
        (CATEGORY_SUBSCRIPTION, "Subscription"),
        (CATEGORY_PAYROLL, "Payroll"),
        (CATEGORY_EXPENSE, "Expense"),
        (CATEGORY_REFUND, "Refund"),
        (CATEGORY_ADJUSTMENT, "Adjustment"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_REVERSED = "REVERSED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REVERSED, "Reversed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_transactions",
    )
    account_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_EMPLOYER)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=10, default="XAF")
    description = models.TextField(blank=True)
    provider = models.CharField(max_length=60, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    invoice = models.ForeignKey(
        BillingInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    payout = models.ForeignKey(
        "BillingPayout",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    reversal_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversals",
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_transactions"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["employer_id", "account_role"]),
            models.Index(fields=["employee", "account_role"]),
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self):
        return f"{self.category} {self.amount} {self.currency}"


class BillingPayoutBatch(models.Model):
    TYPE_PAYROLL = "PAYROLL"
    TYPE_EXPENSE = "EXPENSE"

    TYPE_CHOICES = [
        (TYPE_PAYROLL, "Payroll"),
        (TYPE_EXPENSE, "Expense"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVAL_PENDING = "APPROVAL_PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVAL_PENDING, "Approval Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    batch_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    requires_approval = models.BooleanField(default=False)
    approved_by_id = models.IntegerField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="XAF")
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    planned_date = models.DateField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_by_id = models.IntegerField(null=True, blank=True)
    treasury_batch_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_payout_batches"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "batch_type"]),
            models.Index(fields=["employer_id", "status"]),
        ]

    def __str__(self):
        return f"{self.batch_type} batch {self.id}"


class BillingPayout(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_PAID = "PAID"
    STATUS_FAILED = "FAILED"
    STATUS_REVERSED = "REVERSED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REVERSED, "Reversed"),
    ]

    CATEGORY_PAYROLL = BillingTransaction.CATEGORY_PAYROLL
    CATEGORY_EXPENSE = BillingTransaction.CATEGORY_EXPENSE

    CATEGORY_CHOICES = [
        (CATEGORY_PAYROLL, "Payroll"),
        (CATEGORY_EXPENSE, "Expense"),
    ]

    LINKED_OBJECT_CHOICES = [
        ("PAYSLIP", "Payslip"),
        ("EXPENSE_CLAIM", "Expense Claim"),
        ("OTHER", "Other"),
        ("NONE", "None"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_payouts",
    )
    payout_method = models.ForeignKey(
        PayoutMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts",
    )
    batch = models.ForeignKey(
        BillingPayoutBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts",
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=10, default="XAF")
    provider = models.CharField(max_length=60, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    receipt_number = models.CharField(max_length=40, blank=True)
    receipt_file = models.FileField(upload_to="billing/payouts/", null=True, blank=True)
    receipt_issued_at = models.DateTimeField(null=True, blank=True)
    linked_object_type = models.CharField(
        max_length=30,
        choices=LINKED_OBJECT_CHOICES,
        default="NONE",
    )
    linked_object_id = models.UUIDField(null=True, blank=True)
    treasury_payment_line_id = models.UUIDField(null=True, blank=True)
    treasury_batch_id = models.UUIDField(null=True, blank=True)
    employer_transaction = models.ForeignKey(
        BillingTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employer_payouts",
    )
    employee_transaction = models.ForeignKey(
        BillingTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_payouts",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_payouts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        return f"Payout {self.id} {self.amount} {self.currency}"


class BillingPaymentAttempt(models.Model):
    TYPE_SUBSCRIPTION = "SUBSCRIPTION"
    TYPE_PAYOUT = "PAYOUT"

    TYPE_CHOICES = [
        (TYPE_SUBSCRIPTION, "Subscription Charge"),
        (TYPE_PAYOUT, "Payout"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_RETRYING = "RETRYING"
    STATUS_CANCELED = "CANCELED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_RETRYING, "Retrying"),
        (STATUS_CANCELED, "Canceled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    attempt_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    funding_method = models.ForeignKey(
        FundingMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_attempts",
    )
    payout_method = models.ForeignKey(
        PayoutMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_attempts",
    )
    invoice = models.ForeignKey(
        BillingInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_attempts",
    )
    payout = models.ForeignKey(
        BillingPayout,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_attempts",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=10, default="XAF")
    provider = models.CharField(max_length=60, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    failure_code = models.CharField(max_length=60, blank=True)
    failure_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    attempted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_payment_attempts"
        ordering = ["-attempted_at"]
        indexes = [
            models.Index(fields=["employer_id", "attempt_type"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=Q(attempt_type="PAYOUT"),
                name="uniq_billing_payout_idempotency",
            )
        ]

    def __str__(self):
        return f"{self.attempt_type} attempt {self.id}"


class BillingAuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(null=True, blank=True, db_index=True)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_audit_logs",
    )
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=64)
    meta_old = models.TextField(blank=True)
    meta_new = models.TextField(blank=True)
    actor_id = models.IntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id}"


class GbPayEmployerConnection(models.Model):
    ENV_SANDBOX = "SANDBOX"
    ENV_PRODUCTION = "PRODUCTION"

    ENV_CHOICES = [
        (ENV_SANDBOX, "Sandbox"),
        (ENV_PRODUCTION, "Production"),
    ]

    STATUS_ACTIVE = "ACTIVE"
    STATUS_INACTIVE = "INACTIVE"
    STATUS_INVALID = "INVALID"
    STATUS_PENDING = "PENDING"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
        (STATUS_INVALID, "Invalid"),
        (STATUS_PENDING, "Pending"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    label = models.CharField(max_length=120, blank=True)
    environment = models.CharField(max_length=20, choices=ENV_CHOICES, default=ENV_PRODUCTION)
    is_active = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INACTIVE)
    credentials_encrypted = models.TextField()
    credentials_hint = models.CharField(max_length=120, blank=True)
    last_validated_at = models.DateTimeField(null=True, blank=True)
    last_validation_error = models.TextField(blank=True)
    last_validated_by_id = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_gbpay_connections"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employer_id"],
                condition=Q(is_active=True),
                name="uniq_billing_gbpay_active_employer",
            )
        ]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
        ]

    def __str__(self):
        return f"GbPay ({self.employer_id})"


class GbPayTransfer(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELED = "CANCELED"
    STATUS_TIMEOUT = "TIMEOUT"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_TIMEOUT, "Timeout"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    payout = models.ForeignKey(
        BillingPayout,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gbpay_transfers",
    )
    attempt = models.ForeignKey(
        BillingPaymentAttempt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gbpay_transfers",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    provider_status = models.CharField(max_length=40, blank=True)
    quote_id = models.CharField(max_length=120, blank=True)
    transaction_reference = models.CharField(max_length=120, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    status_payload = models.JSONField(default=dict, blank=True)
    event_log = models.JSONField(default=list, blank=True)
    failure_code = models.CharField(max_length=60, blank=True)
    failure_message = models.TextField(blank=True)
    poll_count = models.PositiveIntegerField(default=0)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    next_poll_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_gbpay_transfers"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["transaction_reference"]),
            models.Index(fields=["next_poll_at"]),
        ]

    def __str__(self):
        return f"GbPay transfer {self.id}"
