import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q


class PayrollConfiguration(models.Model):
    ROUND_HALF_UP = "HALF_UP"
    ROUND_DOWN = "DOWN"
    ROUND_UP = "UP"

    ROUNDING_CHOICES = [
        (ROUND_HALF_UP, "Half up"),
        (ROUND_DOWN, "Down"),
        (ROUND_UP, "Up"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    is_active = models.BooleanField(default=True)
    module_enabled = models.BooleanField(default=True)
    default_currency = models.CharField(max_length=10, default="XAF")

    rounding_scale = models.IntegerField(
        default=0,
        help_text="Number of decimal places for money rounding.",
    )
    rounding_mode = models.CharField(
        max_length=10,
        choices=ROUNDING_CHOICES,
        default=ROUND_HALF_UP,
    )

    pit_gross_salary_percentage_mode = models.BooleanField(default=False)
    pit_gross_salary_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    professional_expense_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    max_professional_expense_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_exempt_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    irpp_withholding_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("62000.00"),
        help_text="Monthly taxable gross threshold below which IRPP withholding is not applied.",
    )
    cac_rate_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="CAC rate as a percentage of IRPP amount.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_configurations"
        verbose_name = "Payroll Configuration"
        verbose_name_plural = "Payroll Configurations"
        constraints = [
            models.UniqueConstraint(
                fields=["employer_id"],
                condition=Q(is_active=True),
                name="uniq_payroll_config_active_per_employer",
            )
        ]

    def __str__(self):
        return f"Payroll Config ({self.employer_id})"


class CalculationBasis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_calculation_bases"
        verbose_name = "Calculation Basis"
        verbose_name_plural = "Calculation Bases"
        unique_together = [["employer_id", "code"]]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
        ]

    def __str__(self):
        return self.code


class CalculationBasisAdvantage(models.Model):
    """
    Basis membership rows.
    Uses existing contract allowances instead of introducing a new Advantage table.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    basis = models.ForeignKey(
        CalculationBasis,
        on_delete=models.CASCADE,
        related_name="allowance_links",
    )
    allowance = models.ForeignKey(
        "contracts.Allowance",
        on_delete=models.CASCADE,
        related_name="basis_links",
        null=True,
        blank=True,
        help_text="Optional direct link to an allowance.",
    )
    allowance_code = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional code-based mapping when allowance rows differ per contract.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_basis_advantages"
        verbose_name = "Calculation Basis Advantage"
        verbose_name_plural = "Calculation Basis Advantages"
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(allowance__isnull=False) & Q(allowance_code__isnull=True))
                    | (Q(allowance__isnull=True) & Q(allowance_code__isnull=False))
                ),
                name="payroll_basis_advantage_single_mapping",
            ),
            models.UniqueConstraint(
                fields=["employer_id", "basis", "allowance"],
                condition=Q(allowance__isnull=False),
                name="uniq_payroll_basis_allowance_link",
            ),
            models.UniqueConstraint(
                fields=["employer_id", "basis", "allowance_code"],
                condition=Q(allowance_code__isnull=False),
                name="uniq_payroll_basis_allowance_code_link",
            ),
        ]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
        ]

    def __str__(self):
        target = self.allowance_code or getattr(self.allowance, "code", None) or self.allowance_id
        return f"{self.basis.code} -> {target}"


class Salary(models.Model):
    STATUS_SIMULATED = "SIMULATED"
    STATUS_GENERATED = "GENERATED"
    STATUS_VALIDATED = "VALIDATED"
    STATUS_ARCHIVED = "ARCHIVED"

    STATUS_CHOICES = [
        (STATUS_SIMULATED, "Simulated"),
        (STATUS_GENERATED, "Generated"),
        (STATUS_VALIDATED, "Validated"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="salaries",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="salaries",
    )
    year = models.IntegerField()
    month = models.IntegerField()
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_SIMULATED,
    )

    base_salary = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    gross_salary = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    taxable_gross_salary = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    irpp_taxable_gross_salary = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    contribution_base_af_pv = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    contribution_base_at = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    total_advantages = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    total_employee_deductions = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    total_employer_deductions = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    net_salary = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))

    leave_days = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    absence_days = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_salaries"
        verbose_name = "Salary"
        verbose_name_plural = "Salaries"
        unique_together = [["employer_id", "contract", "year", "month"]]
        indexes = [
            models.Index(fields=["employer_id", "year", "month"]),
            models.Index(fields=["employee", "year", "month"]),
        ]

    def __str__(self):
        return f"Salary {self.contract_id} {self.month:02d}/{self.year}"


class SalaryAdvantage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    salary = models.ForeignKey(
        Salary,
        on_delete=models.CASCADE,
        related_name="advantages",
    )
    allowance = models.ForeignKey(
        "contracts.Allowance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    base = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_salary_advantages"
        verbose_name = "Salary Advantage"
        verbose_name_plural = "Salary Advantages"
        indexes = [
            models.Index(fields=["employer_id", "salary"]),
        ]

    def __str__(self):
        return f"{self.code} {self.amount}"


class SalaryDeduction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    salary = models.ForeignKey(
        Salary,
        on_delete=models.CASCADE,
        related_name="deductions",
    )
    deduction = models.ForeignKey(
        "contracts.Deduction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    base_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    is_employee = models.BooleanField(default=True)
    is_employer = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_salary_deductions"
        verbose_name = "Salary Deduction"
        verbose_name_plural = "Salary Deductions"
        indexes = [
            models.Index(fields=["employer_id", "salary"]),
        ]

    def __str__(self):
        return f"{self.code} {self.amount}"
