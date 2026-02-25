import uuid
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("employees", "0004_employeeconfiguration_multi_branch_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingPlan",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("code", models.CharField(max_length=60)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "interval",
                    models.CharField(
                        choices=[("MONTHLY", "Monthly"), ("QUARTERLY", "Quarterly"), ("YEARLY", "Yearly")],
                        default="MONTHLY",
                        max_length=20,
                    ),
                ),
                ("interval_count", models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])),
                ("price", models.DecimalField(decimal_places=2, max_digits=20, validators=[MinValueValidator(0)])),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("trial_days", models.PositiveIntegerField(default=0)),
                (
                    "tax_rate",
                    models.DecimalField(
                        decimal_places=4,
                        default=Decimal("0.00"),
                        max_digits=7,
                        validators=[MinValueValidator(0)],
                    ),
                ),
                ("features", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_plans",
                "ordering": ["-created_at"],
                "unique_together": {("employer_id", "code")},
                "indexes": [
                    models.Index(fields=["employer_id", "is_active"], name="billing_pl_employe_6d1aa1_idx")
                ],
            },
        ),
        migrations.CreateModel(
            name="BillingSequence",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("key", models.CharField(max_length=20, db_index=True)),
                ("last_number", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_sequences",
                "unique_together": {("employer_id", "key")},
                "indexes": [models.Index(fields=["employer_id", "key"], name="billing_se_employe_26b7c7_idx")],
            },
        ),
        migrations.CreateModel(
            name="BillingInvoice",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("period_start", models.DateField(blank=True, null=True)),
                ("period_end", models.DateField(blank=True, null=True)),
                ("number", models.CharField(max_length=40, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("ISSUED", "Issued"),
                            ("PAID", "Paid"),
                            ("VOID", "Void"),
                            ("FAILED", "Failed"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("subtotal", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                (
                    "tax_rate",
                    models.DecimalField(
                        decimal_places=4,
                        default=Decimal("0.00"),
                        max_digits=7,
                        validators=[MinValueValidator(0)],
                    ),
                ),
                ("tax_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("voided_at", models.DateTimeField(blank=True, null=True)),
                ("pdf_file", models.FileField(blank=True, null=True, upload_to="billing/invoices/")),
                ("is_finalized", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_invoices",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "status"], name="billing_in_employe_516f3b_idx"),
                    models.Index(fields=["employer_id", "number"], name="billing_in_employe_a4b4f0_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BillingInvoiceLine",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("description", models.CharField(max_length=255)),
                ("quantity", models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=12)),
                ("unit_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_items",
                        to="billing.billinginvoice",
                    ),
                ),
            ],
            options={
                "db_table": "billing_invoice_lines",
                "ordering": ["created_at"],
                "indexes": [models.Index(fields=["invoice"], name="billing_in_invoice_e457a2_idx")],
            },
        ),
        migrations.CreateModel(
            name="FundingMethod",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                (
                    "method_type",
                    models.CharField(
                        choices=[
                            ("BANK_ACCOUNT", "Bank Account"),
                            ("CARD", "Card"),
                            ("MOBILE_MONEY", "Mobile Money"),
                            ("WALLET", "Wallet"),
                            ("OTHER", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                ("provider", models.CharField(blank=True, max_length=60)),
                ("label", models.CharField(blank=True, max_length=120)),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("country", models.CharField(blank=True, max_length=2)),
                ("account_holder_name", models.CharField(blank=True, max_length=255)),
                ("account_last4", models.CharField(blank=True, max_length=4)),
                ("bank_name", models.CharField(blank=True, max_length=255)),
                ("mobile_number", models.CharField(blank=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "verification_status",
                    models.CharField(
                        choices=[
                            ("UNVERIFIED", "Unverified"),
                            ("PENDING", "Pending"),
                            ("VERIFIED", "Verified"),
                            ("FAILED", "Failed"),
                        ],
                        default="UNVERIFIED",
                        max_length=20,
                    ),
                ),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("is_default_subscription", models.BooleanField(default=False)),
                ("is_default_payroll", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_funding_methods",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "is_active"], name="billing_fu_employe_e52eb3_idx"),
                    models.Index(fields=["employer_id", "method_type"], name="billing_fu_employe_8ee402_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("is_default_subscription", True), ("is_active", True)),
                        fields=("employer_id",),
                        name="uniq_billing_funding_default_subscription",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("is_default_payroll", True), ("is_active", True)),
                        fields=("employer_id",),
                        name="uniq_billing_funding_default_payroll",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="EmployerSubscription",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("TRIALING", "Trialing"),
                            ("ACTIVE", "Active"),
                            ("PAST_DUE", "Past Due"),
                            ("PAUSED", "Paused"),
                            ("CANCELED", "Canceled"),
                        ],
                        default="TRIALING",
                        max_length=20,
                    ),
                ),
                ("current_period_start", models.DateField(blank=True, null=True)),
                ("current_period_end", models.DateField(blank=True, null=True)),
                ("next_billing_date", models.DateField(blank=True, null=True)),
                ("billing_cycle_anchor", models.DateField(blank=True, null=True)),
                ("auto_renew", models.BooleanField(default=True)),
                ("canceled_at", models.DateTimeField(blank=True, null=True)),
                ("cancel_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "default_funding_method",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subscription_defaults",
                        to="billing.fundingmethod",
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subscriptions",
                        to="billing.billingplan",
                    ),
                ),
            ],
            options={
                "db_table": "billing_subscriptions",
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["employer_id", "status"], name="billing_su_employe_63f0d6_idx")],
            },
        ),
        migrations.CreateModel(
            name="PayoutMethod",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                (
                    "method_type",
                    models.CharField(
                        choices=[
                            ("BANK_ACCOUNT", "Bank Account"),
                            ("MOBILE_MONEY", "Mobile Money"),
                            ("WALLET", "Wallet"),
                            ("CASH", "Cash"),
                            ("OTHER", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                ("provider", models.CharField(blank=True, max_length=60)),
                ("label", models.CharField(blank=True, max_length=120)),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("country", models.CharField(blank=True, max_length=2)),
                ("account_holder_name", models.CharField(blank=True, max_length=255)),
                ("account_last4", models.CharField(blank=True, max_length=4)),
                ("bank_name", models.CharField(blank=True, max_length=255)),
                ("mobile_number", models.CharField(blank=True, max_length=30)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "verification_status",
                    models.CharField(
                        choices=[
                            ("UNVERIFIED", "Unverified"),
                            ("PENDING", "Pending"),
                            ("VERIFIED", "Verified"),
                            ("FAILED", "Failed"),
                        ],
                        default="UNVERIFIED",
                        max_length=20,
                    ),
                ),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("is_default", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payout_methods",
                        to="employees.employee",
                    ),
                ),
            ],
            options={
                "db_table": "billing_payout_methods",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employee", "is_active"], name="billing_pa_employee_7f7aab_idx"),
                    models.Index(fields=["employee", "method_type"], name="billing_pa_employee_25f9ff_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("is_default", True), ("is_active", True)),
                        fields=("employee",),
                        name="uniq_billing_payout_default_employee",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="BillingTransaction",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                (
                    "account_role",
                    models.CharField(
                        choices=[("EMPLOYER", "Employer"), ("EMPLOYEE", "Employee")],
                        default="EMPLOYER",
                        max_length=20,
                    ),
                ),
                (
                    "direction",
                    models.CharField(choices=[("DEBIT", "Debit"), ("CREDIT", "Credit")], max_length=10),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("SUBSCRIPTION", "Subscription"),
                            ("PAYROLL", "Payroll"),
                            ("EXPENSE", "Expense"),
                            ("REFUND", "Refund"),
                            ("ADJUSTMENT", "Adjustment"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SUCCESS", "Success"),
                            ("FAILED", "Failed"),
                            ("REVERSED", "Reversed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=20, validators=[MinValueValidator(0)])),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("description", models.TextField(blank=True)),
                ("provider", models.CharField(blank=True, max_length=60)),
                ("provider_reference", models.CharField(blank=True, max_length=120)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="billing_transactions",
                        to="employees.employee",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="transactions",
                        to="billing.billinginvoice",
                    ),
                ),
                (
                    "reversal_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reversals",
                        to="billing.billingtransaction",
                    ),
                ),
            ],
            options={
                "db_table": "billing_transactions",
                "ordering": ["-occurred_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "account_role"], name="billing_tr_employe_1d641a_idx"),
                    models.Index(fields=["employee", "account_role"], name="billing_tr_employee_839c1a_idx"),
                    models.Index(fields=["category", "status"], name="billing_tr_category_c29da5_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BillingPayoutBatch",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                (
                    "batch_type",
                    models.CharField(choices=[("PAYROLL", "Payroll"), ("EXPENSE", "Expense")], max_length=20),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("PROCESSING", "Processing"),
                            ("COMPLETED", "Completed"),
                            ("PARTIAL", "Partial"),
                            ("FAILED", "Failed"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=20)),
                ("planned_date", models.DateField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by_id", models.IntegerField(blank=True, null=True)),
                ("treasury_batch_id", models.UUIDField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_payout_batches",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "batch_type"], name="billing_po_employe_0d3c40_idx"),
                    models.Index(fields=["employer_id", "status"], name="billing_po_employe_1ad724_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BillingPayout",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                (
                    "category",
                    models.CharField(choices=[("PAYROLL", "Payroll"), ("EXPENSE", "Expense")], max_length=20),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("PROCESSING", "Processing"),
                            ("PAID", "Paid"),
                            ("FAILED", "Failed"),
                            ("REVERSED", "Reversed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=20, validators=[MinValueValidator(0)])),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("provider", models.CharField(blank=True, max_length=60)),
                ("provider_reference", models.CharField(blank=True, max_length=120)),
                ("scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("failure_reason", models.TextField(blank=True)),
                (
                    "linked_object_type",
                    models.CharField(
                        choices=[
                            ("PAYSLIP", "Payslip"),
                            ("EXPENSE_CLAIM", "Expense Claim"),
                            ("OTHER", "Other"),
                            ("NONE", "None"),
                        ],
                        default="NONE",
                        max_length=30,
                    ),
                ),
                ("linked_object_id", models.UUIDField(blank=True, null=True)),
                ("treasury_payment_line_id", models.UUIDField(blank=True, null=True)),
                ("treasury_batch_id", models.UUIDField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "batch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payouts",
                        to="billing.billingpayoutbatch",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="billing_payouts",
                        to="employees.employee",
                    ),
                ),
                (
                    "employee_transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="employee_payouts",
                        to="billing.billingtransaction",
                    ),
                ),
                (
                    "employer_transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="employer_payouts",
                        to="billing.billingtransaction",
                    ),
                ),
                (
                    "payout_method",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payouts",
                        to="billing.payoutmethod",
                    ),
                ),
            ],
            options={
                "db_table": "billing_payouts",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "status"], name="billing_po_employe_5f3120_idx"),
                    models.Index(fields=["employee", "status"], name="billing_po_employee_e87cf2_idx"),
                    models.Index(fields=["category"], name="billing_po_category_5d8f1e_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BillingPaymentAttempt",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                (
                    "attempt_type",
                    models.CharField(
                        choices=[("SUBSCRIPTION", "Subscription Charge"), ("PAYOUT", "Payout")], max_length=20
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SUCCESS", "Success"),
                            ("FAILED", "Failed"),
                            ("RETRYING", "Retrying"),
                            ("CANCELED", "Canceled"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=20, validators=[MinValueValidator(0)])),
                ("currency", models.CharField(default="XAF", max_length=10)),
                ("provider", models.CharField(blank=True, max_length=60)),
                ("provider_reference", models.CharField(blank=True, max_length=120)),
                ("failure_code", models.CharField(blank=True, max_length=60)),
                ("failure_message", models.TextField(blank=True)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("next_retry_at", models.DateTimeField(blank=True, null=True)),
                ("attempted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "funding_method",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_attempts",
                        to="billing.fundingmethod",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_attempts",
                        to="billing.billinginvoice",
                    ),
                ),
                (
                    "payout",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_attempts",
                        to="billing.billingpayout",
                    ),
                ),
                (
                    "payout_method",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_attempts",
                        to="billing.payoutmethod",
                    ),
                ),
            ],
            options={
                "db_table": "billing_payment_attempts",
                "ordering": ["-attempted_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "attempt_type"], name="billing_pa_employe_08b1a6_idx"),
                    models.Index(fields=["status"], name="billing_pa_status_9ff992_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BillingAuditLog",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("employer_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("action", models.CharField(max_length=100)),
                ("entity_type", models.CharField(max_length=60)),
                ("entity_id", models.CharField(max_length=64)),
                ("meta_old", models.TextField(blank=True)),
                ("meta_new", models.TextField(blank=True)),
                ("actor_id", models.IntegerField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "employee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="billing_audit_logs",
                        to="employees.employee",
                    ),
                ),
            ],
            options={
                "db_table": "billing_audit_logs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "created_at"], name="billing_au_employe_80ed55_idx"),
                    models.Index(fields=["action"], name="billing_au_action_2e712b_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="billinginvoice",
            name="subscription",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoices",
                to="billing.employersubscription",
            ),
        ),
        migrations.AddField(
            model_name="billingtransaction",
            name="payout",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transactions",
                to="billing.billingpayout",
            ),
        ),
    ]
