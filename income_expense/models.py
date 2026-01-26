import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from employees.models import Employee


class AuditBase(models.Model):
    created_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    approved_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteBase(AuditBase):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by_id = models.IntegerField(null=True, blank=True)

    class Meta:
        abstract = True


class IncomeExpenseConfiguration(AuditBase):
    BUDGET_CONTROL_OFF = "OFF"
    BUDGET_CONTROL_WARN = "WARN"
    BUDGET_CONTROL_BLOCK = "BLOCK"

    BUDGET_CONTROL_CHOICES = [
        (BUDGET_CONTROL_OFF, "Off"),
        (BUDGET_CONTROL_WARN, "Warn"),
        (BUDGET_CONTROL_BLOCK, "Block"),
    ]

    PERIOD_MONTHLY = "MONTHLY"
    PERIOD_QUARTERLY = "QUARTERLY"
    PERIOD_YEARLY = "YEARLY"

    PERIOD_CHOICES = [
        (PERIOD_MONTHLY, "Monthly"),
        (PERIOD_QUARTERLY, "Quarterly"),
        (PERIOD_YEARLY, "Yearly"),
    ]

    SCOPE_COMPANY = "COMPANY"
    SCOPE_BRANCH = "BRANCH"
    SCOPE_DEPARTMENT = "DEPARTMENT"

    SCOPE_CHOICES = [
        (SCOPE_COMPANY, "Company"),
        (SCOPE_BRANCH, "Branch"),
        (SCOPE_DEPARTMENT, "Department"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        "accounts.EmployerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="income_expense_configurations",
        db_constraint=False,
        help_text="Institution owning this configuration (nullable for single-tenant setups).",
    )
    is_active = models.BooleanField(default=True)

    default_currency = models.CharField(max_length=3, default="XAF")
    enable_income = models.BooleanField(default=True)
    enable_expenses = models.BooleanField(default=True)
    enable_budgets = models.BooleanField(default=True)

    expense_require_attachment = models.BooleanField(default=False)
    expense_require_notes = models.BooleanField(default=True)
    expense_allow_backdate = models.BooleanField(default=True)
    expense_max_backdate_days = models.IntegerField(default=30)

    expense_approval_required = models.BooleanField(default=True)
    expense_approval_threshold_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    expense_allow_self_approval = models.BooleanField(default=False)
    expense_cancel_requires_approval = models.BooleanField(default=True)
    expense_allow_edit_after_approval = models.BooleanField(default=False)

    income_allow_manual_entry = models.BooleanField(default=True)
    income_require_attachment = models.BooleanField(default=False)
    income_require_notes = models.BooleanField(default=False)
    income_approval_required = models.BooleanField(default=False)
    income_approval_threshold_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )

    budget_control_mode = models.CharField(
        max_length=10,
        choices=BUDGET_CONTROL_CHOICES,
        default=BUDGET_CONTROL_WARN,
    )
    budget_periodicity = models.CharField(
        max_length=10,
        choices=PERIOD_CHOICES,
        default=PERIOD_MONTHLY,
    )
    budget_scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_DEPARTMENT,
    )
    budget_enforce_on_submit = models.BooleanField(default=True)
    budget_enforce_on_approval = models.BooleanField(default=True)
    budget_allow_override = models.BooleanField(default=True)
    budget_override_requires_reason = models.BooleanField(default=True)

    push_approved_expenses_to_treasury = models.BooleanField(default=True)
    push_approved_vendor_bills_to_treasury = models.BooleanField(default=True)
    auto_mark_paid_from_treasury = models.BooleanField(default=True)

    class Meta:
        db_table = "income_expense_configuration"
        verbose_name = "Income & Expense Configuration"
        verbose_name_plural = "Income & Expense Configuration"
        constraints = [
            models.UniqueConstraint(
                fields=["institution"],
                condition=Q(is_active=True, institution__isnull=False),
                name="uniq_income_expense_config_active_institution",
            )
        ]

    def __str__(self):
        return f"IncomeExpense Configuration ({self.institution_id or 'single-tenant'})"


class ExpenseCategory(SoftDeleteBase):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "expense_category"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class IncomeCategory(SoftDeleteBase):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "income_category"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class BudgetPlan(SoftDeleteBase):
    STATUS_DRAFT = "DRAFT"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    ]

    PERIOD_CHOICES = IncomeExpenseConfiguration.PERIOD_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    periodicity = models.CharField(max_length=10, choices=PERIOD_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta:
        db_table = "budget_plan"
        ordering = ["-start_date", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.status})"


class BudgetLine(SoftDeleteBase):
    SCOPE_CHOICES = IncomeExpenseConfiguration.SCOPE_CHOICES

    CATEGORY_EXPENSE = "EXPENSE"
    CATEGORY_INCOME = "INCOME"

    CATEGORY_CHOICES = [
        (CATEGORY_EXPENSE, "Expense"),
        (CATEGORY_INCOME, "Income"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget_plan = models.ForeignKey(
        BudgetPlan,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    scope_id = models.UUIDField(null=True, blank=True)
    category_type = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    expense_category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_lines",
    )
    income_category = models.ForeignKey(
        IncomeCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_lines",
    )
    currency = models.CharField(max_length=3)
    allocated_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    consumed_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    reserved_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "budget_line"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(category_type="EXPENSE", expense_category__isnull=False, income_category__isnull=True)
                    | Q(category_type="INCOME", income_category__isnull=False, expense_category__isnull=True)
                ),
                name="budget_line_category_match",
            ),
            models.CheckConstraint(
                check=(
                    Q(scope_type=IncomeExpenseConfiguration.SCOPE_COMPANY, scope_id__isnull=True)
                    | Q(scope_type__in=[IncomeExpenseConfiguration.SCOPE_BRANCH, IncomeExpenseConfiguration.SCOPE_DEPARTMENT], scope_id__isnull=False)
                ),
                name="budget_line_scope_match",
            ),
        ]

    def __str__(self):
        return f"{self.budget_plan_id} {self.category_type} {self.allocated_amount}"


class ExpenseClaim(SoftDeleteBase):
    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVAL_PENDING = "APPROVAL_PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_PAID = "PAID"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVAL_PENDING, "Approval Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_PAID, "Paid"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.IntegerField(db_index=True)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_claims",
    )
    expense_category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_claims",
    )
    title = models.CharField(max_length=255)
    notes = models.TextField(null=True, blank=True)
    expense_date = models.DateField()
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3)
    attachment = models.FileField(upload_to="income_expense/expenses/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(null=True, blank=True)

    treasury_payment_line_id = models.UUIDField(null=True, blank=True)
    treasury_external_reference = models.CharField(max_length=128, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_failed = models.BooleanField(default=False)
    payment_failed_reason = models.TextField(null=True, blank=True)

    budget_line = models.ForeignKey(
        BudgetLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_claims",
    )
    budget_override_used = models.BooleanField(default=False)
    budget_override_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "expense_claim"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"

    def mark_approval_pending(self):
        self.status = self.STATUS_APPROVAL_PENDING
        self.submitted_at = timezone.now()

    def mark_approved(self):
        self.status = self.STATUS_APPROVED
        self.approved_at = timezone.now()

    def mark_rejected(self, reason: str = ""):
        self.status = self.STATUS_REJECTED
        self.rejected_reason = reason or ""

    def mark_cancelled(self):
        self.status = self.STATUS_CANCELLED

    def mark_paid(self, paid_at=None):
        self.status = self.STATUS_PAID
        self.paid_at = paid_at or timezone.now()
        self.payment_failed = False
        self.payment_failed_reason = ""


class IncomeRecord(SoftDeleteBase):
    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVAL_PENDING = "APPROVAL_PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_RECEIVED = "RECEIVED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVAL_PENDING, "Approval Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.IntegerField(db_index=True)
    income_category = models.ForeignKey(
        IncomeCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="income_records",
    )
    title = models.CharField(max_length=255)
    notes = models.TextField(null=True, blank=True)
    income_date = models.DateField()
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3)
    attachment = models.FileField(upload_to="income_expense/income/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(null=True, blank=True)

    bank_statement_line_id = models.UUIDField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    budget_line = models.ForeignKey(
        BudgetLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="income_records",
    )
    budget_override_used = models.BooleanField(default=False)
    budget_override_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "income_record"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"

    def mark_submitted(self):
        self.status = self.STATUS_APPROVAL_PENDING
        self.submitted_at = timezone.now()

    def mark_approved(self):
        self.status = self.STATUS_APPROVED
        self.approved_at = timezone.now()

    def mark_rejected(self, reason: str = ""):
        self.status = self.STATUS_REJECTED
        self.rejected_reason = reason or ""

    def mark_received(self, received_at=None):
        self.status = self.STATUS_RECEIVED
        self.received_at = received_at or timezone.now()
