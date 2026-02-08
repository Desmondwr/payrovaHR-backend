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

    rounding_scale = models.IntegerField(default=0, help_text="Number of decimal places for money rounding.")
    rounding_mode = models.CharField(max_length=10, choices=ROUNDING_CHOICES, default=ROUND_HALF_UP)

    pit_gross_salary_percentage_mode = models.BooleanField(default=False)
    pit_gross_salary_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))

    professional_expense_rate = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    max_professional_expense_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_exempt_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

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


class Advantage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    sys_code = models.CharField(max_length=50, blank=True, null=True)
    is_manual = models.BooleanField(default=False)
    is_taxable = models.BooleanField(default=True)
    is_contributory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_advantages"
        verbose_name = "Advantage"
        verbose_name_plural = "Advantages"
        unique_together = [["employer_id", "code"]]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
            models.Index(fields=["employer_id", "sys_code"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class CalculationScale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_scales"
        verbose_name = "Calculation Scale"
        verbose_name_plural = "Calculation Scales"
        unique_together = [["employer_id", "code"]]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ScaleRange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    scale = models.ForeignKey(
        CalculationScale,
        on_delete=models.CASCADE,
        related_name="ranges",
    )
    range_min = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    range_max = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    coefficient = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    indice = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    base_threshold = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    position = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_scale_ranges"
        verbose_name = "Scale Range"
        verbose_name_plural = "Scale Ranges"
        unique_together = [["scale", "position"]]
        indexes = [
            models.Index(fields=["employer_id", "scale"]),
        ]

    def __str__(self):
        return f"{self.scale.code} #{self.position}"


class Deduction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    sys_code = models.CharField(max_length=50, blank=True, null=True)
    is_employee = models.BooleanField(default=True)
    is_employer = models.BooleanField(default=False)
    is_count = models.BooleanField(default=True)
    calculation_basis_code = models.CharField(max_length=50, blank=True, null=True)
    employee_rate = models.DecimalField(max_digits=7, decimal_places=4, blank=True, null=True)
    employer_rate = models.DecimalField(max_digits=7, decimal_places=4, blank=True, null=True)
    scale = models.ForeignKey(
        CalculationScale,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="deductions",
    )
    is_rate = models.BooleanField(default=False)
    is_scale = models.BooleanField(default=False)
    is_base_table = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_deductions"
        verbose_name = "Deduction"
        verbose_name_plural = "Deductions"
        unique_together = [["employer_id", "code"]]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
            models.Index(fields=["employer_id", "sys_code"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


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
        return f"{self.code}"


class CalculationBasisAdvantage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    basis = models.ForeignKey(
        CalculationBasis,
        on_delete=models.CASCADE,
        related_name="advantage_links",
    )
    advantage = models.ForeignKey(
        Advantage,
        on_delete=models.CASCADE,
        related_name="basis_links",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_basis_advantages"
        verbose_name = "Calculation Basis Advantage"
        verbose_name_plural = "Calculation Basis Advantages"
        unique_together = [["employer_id", "basis", "advantage"]]

    def __str__(self):
        return f"{self.basis.code} -> {self.advantage.code}"


class PayrollElement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="payroll_elements",
    )
    advantage = models.ForeignKey(
        Advantage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elements",
    )
    deduction = models.ForeignKey(
        Deduction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elements",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    month = models.CharField(max_length=2, default="__")
    year = models.CharField(max_length=4, default="__")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_elements"
        verbose_name = "Payroll Element"
        verbose_name_plural = "Payroll Elements"
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(advantage__isnull=False) & Q(deduction__isnull=True))
                    | (Q(advantage__isnull=True) & Q(deduction__isnull=False))
                ),
                name="payroll_element_single_target",
            )
        ]
        indexes = [
            models.Index(fields=["employer_id", "contract"]),
        ]

    def __str__(self):
        target = self.advantage.code if self.advantage_id else self.deduction.code
        return f"{self.contract_id} -> {target}"


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
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_SIMULATED)

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
        return f"Salary {self.contract_id} {self.month}/{self.year}"


class SalaryAdvantage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    salary = models.ForeignKey(Salary, on_delete=models.CASCADE, related_name="advantages")
    advantage = models.ForeignKey(Advantage, on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(max_length=50)
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
    salary = models.ForeignKey(Salary, on_delete=models.CASCADE, related_name="deductions")
    deduction = models.ForeignKey(Deduction, on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(max_length=50)
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
