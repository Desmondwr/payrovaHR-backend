import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from employees.models import Branch, Employee


class TreasuryConfiguration(models.Model):
    SEQUENCE_RESET_MONTHLY = "MONTHLY"
    SEQUENCE_RESET_YEARLY = "YEARLY"
    SEQUENCE_RESET_NEVER = "NEVER"

    SEQUENCE_RESET_CHOICES = [
        (SEQUENCE_RESET_MONTHLY, "Monthly"),
        (SEQUENCE_RESET_YEARLY, "Yearly"),
        (SEQUENCE_RESET_NEVER, "Never"),
    ]

    MATCHING_LOOSE = "LOOSE"
    MATCHING_BALANCED = "BALANCED"
    MATCHING_STRICT = "STRICT"

    MATCHING_STRICTNESS_CHOICES = [
        (MATCHING_LOOSE, "Loose"),
        (MATCHING_BALANCED, "Balanced"),
        (MATCHING_STRICT, "Strict"),
    ]

    PAYMENT_METHOD_BANK_TRANSFER = "BANK_TRANSFER"
    PAYMENT_METHOD_CASH = "CASH"
    PAYMENT_METHOD_MOBILE_MONEY = "MOBILE_MONEY"
    PAYMENT_METHOD_CHEQUE = "CHEQUE"

    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_METHOD_BANK_TRANSFER, "Bank Transfer"),
        (PAYMENT_METHOD_CASH, "Cash"),
        (PAYMENT_METHOD_MOBILE_MONEY, "Mobile Money"),
        (PAYMENT_METHOD_CHEQUE, "Cheque"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        "accounts.EmployerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treasury_configurations",
        db_constraint=False,
        help_text="Institution owning this configuration (nullable for single-tenant setups).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    default_currency = models.CharField(max_length=3, default="XAF")
    enable_bank_accounts = models.BooleanField(default=True)
    enable_cash_desks = models.BooleanField(default=True)
    enable_mobile_money = models.BooleanField(default=False)
    enable_cheques = models.BooleanField(default=False)
    enable_reconciliation = models.BooleanField(default=True)

    batch_reference_format = models.CharField(max_length=100, default="PAY-{YYYY}{MM}-{SEQ}")
    transaction_reference_format = models.CharField(max_length=100, default="TRX-{YYYY}{MM}-{SEQ}")
    cash_voucher_format = models.CharField(max_length=100, default="CV-{BRANCH}-{SEQ}")
    sequence_reset_policy = models.CharField(
        max_length=10,
        choices=SEQUENCE_RESET_CHOICES,
        default=SEQUENCE_RESET_NEVER,
    )

    batch_approval_required = models.BooleanField(default=True)
    batch_approval_threshold_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("1000000.00"),
        validators=[MinValueValidator(0)],
    )
    dual_approval_required_for_payroll = models.BooleanField(default=True)
    allow_self_approval = models.BooleanField(default=False)
    cancellation_requires_approval = models.BooleanField(default=True)

    line_approval_required = models.BooleanField(default=False)
    line_approval_threshold_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("500000.00"),
        validators=[MinValueValidator(0)],
    )

    allow_edit_after_approval = models.BooleanField(default=False)

    default_salary_payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_METHOD_BANK_TRANSFER,
    )
    default_expense_payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_METHOD_CASH,
    )
    default_vendor_payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_METHOD_BANK_TRANSFER,
    )

    require_beneficiary_details_for_non_cash = models.BooleanField(default=True)
    execution_proof_required = models.BooleanField(default=False)

    enable_csv_export = models.BooleanField(default=True)
    enable_iso20022_export = models.BooleanField(default=False)
    csv_template_code = models.CharField(max_length=30, null=True, blank=True)

    require_open_session = models.BooleanField(default=True)
    allow_negative_cash_balance = models.BooleanField(default=False)

    max_cash_desk_balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("10000000.00"),
        validators=[MinValueValidator(0)],
    )
    min_balance_alert = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("1000.00"),
        validators=[MinValueValidator(0)],
    )
    cash_out_approval_threshold = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("500000.00"),
        validators=[MinValueValidator(0)],
    )
    cash_out_requires_reason = models.BooleanField(default=True)
    adjustments_require_approval = models.BooleanField(default=True)

    discrepancy_tolerance_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("2000.00"),
        validators=[MinValueValidator(0)],
    )
    auto_lock_cash_desk_on_discrepancy = models.BooleanField(default=False)

    auto_match_enabled = models.BooleanField(default=True)
    match_window_days = models.IntegerField(default=7, validators=[MinValueValidator(0)])
    auto_confirm_confidence_threshold = models.IntegerField(
        default=95,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    matching_strictness = models.CharField(
        max_length=10,
        choices=MATCHING_STRICTNESS_CHOICES,
        default=MATCHING_BALANCED,
    )
    lock_batch_until_reconciled = models.BooleanField(default=False)

    class Meta:
        db_table = "treasury_configuration"
        verbose_name = "Treasury Configuration"
        verbose_name_plural = "Treasury Configuration"
        constraints = [
            models.UniqueConstraint(
                fields=["institution"],
                condition=Q(is_active=True, institution__isnull=False),
                name="uniq_treasury_config_active_institution",
            )
        ]

    def __str__(self):
        return f"Treasury Configuration ({self.institution_id or 'single-tenant'})"


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="treasury_bank_accounts",
    )
    name = models.CharField(max_length=255)
    currency = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=64, blank=True, null=True)
    iban = models.CharField(max_length=64, blank=True, null=True)
    account_holder_name = models.CharField(max_length=255)
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    current_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "treasury_bank_accounts"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.current_balance == Decimal("0.00"):
            self.current_balance = self.opening_balance
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.bank_name})"


class CashDesk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="treasury_cash_desks",
    )
    name = models.CharField(max_length=255)
    currency = models.CharField(max_length=10)
    custodian_employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custodied_cash_desks",
    )
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    current_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "treasury_cash_desks"
        ordering = ["branch", "name"]

    def save(self, *args, **kwargs):
        if self.current_balance == Decimal("0.00"):
            self.current_balance = self.opening_balance
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.branch.name})"


class CashDeskSession(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cashdesk = models.ForeignKey(
        CashDesk,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    opened_by_id = models.IntegerField()
    opened_at = models.DateTimeField(default=timezone.now)
    opening_count_amount = models.DecimalField(max_digits=20, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    closed_by_id = models.IntegerField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closing_count_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    discrepancy_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    discrepancy_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "treasury_cashdesk_sessions"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Session {self.id} ({self.cashdesk.name})"


class TreasuryTransaction(models.Model):
    SOURCE_BANK = "BANK"
    SOURCE_CASHDESK = "CASHDESK"

    SOURCE_TYPE_CHOICES = [
        (SOURCE_BANK, "Bank Account"),
        (SOURCE_CASHDESK, "Cash Desk"),
    ]

    DIRECTION_IN = "IN"
    DIRECTION_OUT = "OUT"

    DIRECTION_CHOICES = [
        (DIRECTION_IN, "Money In"),
        (DIRECTION_OUT, "Money Out"),
    ]

    CATEGORY_CHOICES = [
        ("SALARY", "Salary"),
        ("EXPENSE", "Expense"),
        ("VENDOR", "Vendor"),
        ("TRANSFER", "Transfer"),
        ("WITHDRAWAL", "Withdrawal"),
        ("DEPOSIT", "Deposit"),
        ("ADJUSTMENT", "Adjustment"),
        ("OTHER", "Other"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVAL_PENDING = "APPROVAL_PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_POSTED = "POSTED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVAL_PENDING, "Approval Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_POSTED, "Posted"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    LINKED_OBJECT_CHOICES = [
        ("PAYMENT_LINE", "Payment Line"),
        ("PAY_RUN", "Pay Run"),
        ("EXPENSE", "Expense"),
        ("BILL", "Bill"),
        ("MANUAL", "Manual"),
        ("NONE", "None"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    source_id = models.UUIDField()
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="OTHER")
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=10)
    transaction_date = models.DateTimeField(default=timezone.now)
    reference = models.CharField(max_length=64, unique=True)
    counterparty_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by_id = models.IntegerField(null=True, blank=True)
    approved_by_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    linked_object_type = models.CharField(max_length=20, choices=LINKED_OBJECT_CHOICES, default="NONE")
    linked_object_id = models.UUIDField(null=True, blank=True)
    cashdesk_session = models.ForeignKey(
        CashDeskSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "treasury_transactions"
        ordering = ["-transaction_date"]

    def __str__(self):
        return f"{self.reference} ({self.direction} {self.amount} {self.currency})"


class PaymentBatch(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVAL_PENDING = "APPROVAL_PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_EXECUTED = "EXECUTED"
    STATUS_PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED"
    STATUS_RECONCILED = "RECONCILED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVAL_PENDING, "Approval Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_EXECUTED, "Executed"),
        (STATUS_PARTIALLY_RECONCILED, "Partially Reconciled"),
        (STATUS_RECONCILED, "Reconciled"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    PAYMENT_SOURCE_CHOICES = [
        (TreasuryTransaction.SOURCE_BANK, "Bank Account"),
        (TreasuryTransaction.SOURCE_CASHDESK, "Cash Desk"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("BANK_TRANSFER", "Bank Transfer"),
        ("CASH", "Cash"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("CHEQUE", "Cheque"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="treasury_payment_batches",
    )
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=PAYMENT_SOURCE_CHOICES)
    source_id = models.UUIDField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    planned_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10)
    created_by_id = models.IntegerField(null=True, blank=True)
    approved_by_id = models.IntegerField(null=True, blank=True)
    executed_by_id = models.IntegerField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reference_number = models.CharField(max_length=64, blank=True, null=True)

    class Meta:
        db_table = "treasury_payment_batches"
        ordering = ["-planned_date", "-created_at"]

    def recalculate_total(self):
        lines = self.lines.aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0.00")
        self.total_amount = lines
        self.save(update_fields=["total_amount"])

    def __str__(self):
        return f"{self.name} ({self.status})"


class PaymentLine(models.Model):
    PAYEE_EMPLOYEE = "EMPLOYEE"
    PAYEE_VENDOR = "VENDOR"
    PAYEE_OTHER = "OTHER"

    PAYEE_TYPE_CHOICES = [
        (PAYEE_EMPLOYEE, "Employee"),
        (PAYEE_VENDOR, "Vendor"),
        (PAYEE_OTHER, "Other"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_PAID = "PAID"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    LINKED_OBJECT_CHOICES = [
        ("PAYSLIP", "Payslip"),
        ("EXPENSE_CLAIM", "Expense Claim"),
        ("BILL", "Bill"),
        ("NONE", "None"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        PaymentBatch,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    payee_type = models.CharField(max_length=20, choices=PAYEE_TYPE_CHOICES)
    payee_id = models.UUIDField(null=True, blank=True)
    payee_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    external_reference = models.CharField(max_length=128, blank=True, null=True)
    linked_object_type = models.CharField(max_length=20, choices=LINKED_OBJECT_CHOICES, default="NONE")
    linked_object_id = models.UUIDField(null=True, blank=True)
    requires_approval = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    approved_by_id = models.IntegerField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "treasury_payment_lines"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.payee_name} ({self.amount} {self.currency})"


class BankStatement(models.Model):
    STATUS_IMPORTED = "IMPORTED"
    STATUS_READY = "READY"
    STATUS_ARCHIVED = "ARCHIVED"

    STATUS_CHOICES = [
        (STATUS_IMPORTED, "Imported"),
        (STATUS_READY, "Ready"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name="statements",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    imported_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IMPORTED)
    source_file = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "treasury_bank_statements"
        ordering = ["-period_start"]

    def __str__(self):
        return f"Statement {self.id} ({self.period_start} - {self.period_end})"


class BankStatementLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_statement = models.ForeignKey(
        BankStatement,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    txn_date = models.DateField()
    description = models.TextField(blank=True)
    amount_signed = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=10)
    reference_raw = models.CharField(max_length=128, blank=True, null=True)
    external_id = models.CharField(max_length=128, blank=True, null=True)
    matched = models.BooleanField(default=False)

    class Meta:
        db_table = "treasury_bank_statement_lines"
        ordering = ["txn_date"]

    def __str__(self):
        return f"{self.txn_date} {self.amount_signed}"


class ReconciliationMatch(models.Model):
    MATCH_TYPE_CHOICES = [
        ("PAYMENT_LINE", "Payment Line"),
        ("TREASURY_TRANSACTION", "Treasury Transaction"),
    ]

    STATUS_SUGGESTED = "SUGGESTED"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_SUGGESTED, "Suggested"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    statement_line = models.ForeignKey(
        BankStatementLine,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    match_type = models.CharField(max_length=30, choices=MATCH_TYPE_CHOICES)
    match_id = models.UUIDField()
    confidence = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUGGESTED)
    confirmed_by_id = models.IntegerField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "treasury_reconciliation_matches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Match {self.id} ({self.match_type})"
