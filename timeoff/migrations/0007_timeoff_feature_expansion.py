import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0007_alter_employeedocument_document_type"),
        ("timeoff", "0006_add_tenant_to_ledger"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeoffrequest",
            name="attachments",
            field=models.JSONField(blank=True, default=list, help_text="Attachment metadata (if any)"),
        ),
        migrations.AddField(
            model_name="timeoffrequest",
            name="description",
            field=models.TextField(blank=True, help_text="User-provided description/reason", null=True),
        ),
        migrations.AddField(
            model_name="timeoffrequest",
            name="from_time",
            field=models.TimeField(blank=True, help_text="For custom hours start time", null=True),
        ),
        migrations.AddField(
            model_name="timeoffrequest",
            name="half_day_period",
            field=models.CharField(
                blank=True,
                choices=[("MORNING", "Morning"), ("AFTERNOON", "Afternoon")],
                help_text="Relevant when input_type is HALF_DAY",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="timeoffrequest",
            name="input_type",
            field=models.CharField(
                choices=[("FULL_DAY", "Full Day"), ("HALF_DAY", "Half Day"), ("CUSTOM_HOURS", "Custom Hours")],
                default="FULL_DAY",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="timeoffrequest",
            name="tenant_id",
            field=models.IntegerField(blank=True, db_index=True, help_text="Tenant identifier", null=True),
        ),
        migrations.AddField(
            model_name="timeoffrequest",
            name="to_time",
            field=models.TimeField(blank=True, help_text="For custom hours end time", null=True),
        ),
        migrations.CreateModel(
            name="TimeOffAccrualPlan",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("tenant_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("name", models.CharField(max_length=255)),
                ("frequency", models.CharField(choices=[("MONTHLY", "Monthly")], default="MONTHLY", max_length=20)),
                ("amount_minutes", models.IntegerField(default=0, help_text="Minutes accrued per period")),
                (
                    "accrual_gain_time",
                    models.CharField(
                        choices=[("START", "At period start"), ("END", "At period end")],
                        default="START",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "timeoff_accrual_plans",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="TimeOffAllocation",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("tenant_id", models.IntegerField(blank=True, db_index=True, null=True, help_text="Tenant identifier")),
                ("employer_id", models.IntegerField(db_index=True, help_text="Employer/tenant identifier")),
                ("name", models.CharField(max_length=255)),
                ("leave_type_code", models.CharField(db_index=True, max_length=50)),
                (
                    "allocation_type",
                    models.CharField(
                        choices=[("REGULAR", "Regular"), ("ACCRUAL", "Accrual")],
                        default="REGULAR",
                        max_length=10,
                    ),
                ),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True)),
                (
                    "unit",
                    models.CharField(
                        blank=True, choices=[("DAYS", "Days"), ("HOURS", "Hours")], max_length=10, null=True
                    ),
                ),
                ("start_date", models.DateField()),
                ("end_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")],
                        db_index=True,
                        default="DRAFT",
                        max_length=15,
                    ),
                ),
                ("created_by", models.IntegerField(db_index=True, help_text="User ID from main DB")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "accrual_plan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="allocations",
                        to="timeoff.timeoffaccrualplan",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="time_off_allocations",
                        to="employees.employee",
                    ),
                ),
            ],
            options={
                "db_table": "timeoff_allocations",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "leave_type_code"], name="timeoff_alloc_emp_lt_idx"),
                    models.Index(fields=["status"], name="timeoff_alloc_status_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="TimeOffAllocationRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("tenant_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("leave_type_code", models.CharField(db_index=True, max_length=50)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=9)),
                ("unit", models.CharField(choices=[("DAYS", "Days"), ("HOURS", "Hours")], max_length=10)),
                ("reason", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=10,
                    ),
                ),
                ("acted_at", models.DateTimeField(blank=True, null=True)),
                ("acted_by", models.IntegerField(blank=True, help_text="Approver user id", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_off_allocation_requests",
                        to="employees.employee",
                    ),
                ),
            ],
            options={
                "db_table": "timeoff_allocation_requests",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["employer_id", "leave_type_code"], name="timeoff_allocreq_emp_lt_idx"),
                    models.Index(fields=["status"], name="timeoff_allocreq_status_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="TimeOffAllocationLine",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")],
                        db_index=True,
                        default="DRAFT",
                        max_length=15,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "allocation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="timeoff.timeoffallocation"
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_off_allocation_lines",
                        to="employees.employee",
                    ),
                ),
            ],
            options={
                "db_table": "timeoff_allocation_lines",
                "ordering": ["created_at"],
                "unique_together": {("allocation", "employee")},
            },
        ),
        migrations.CreateModel(
            name="TimeOffAccrualSubscription",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("leave_type_code", models.CharField(db_index=True, max_length=50)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField(blank=True, null=True)),
                ("last_accrual_date", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("ENDED", "Ended"), ("CANCELLED", "Cancelled")],
                        db_index=True,
                        default="ACTIVE",
                        max_length=10,
                    ),
                ),
                ("created_by", models.IntegerField(db_index=True, help_text="User ID from main DB")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "allocation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accrual_subscriptions",
                        to="timeoff.timeoffallocation",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_off_accrual_subscriptions",
                        to="employees.employee",
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscriptions",
                        to="timeoff.timeoffaccrualplan",
                    ),
                ),
            ],
            options={
                "db_table": "timeoff_accrual_subscriptions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["leave_type_code"], name="timeoff_accrual_lt_idx"),
                    models.Index(fields=["status"], name="timeoff_accrual_status_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="timeoffledgerentry",
            name="allocation",
            field=models.ForeignKey(
                blank=True,
                help_text="Linked allocation (if any)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ledger_entries",
                to="timeoff.timeoffallocation",
            ),
        ),
        migrations.AddField(
            model_name="timeoffledgerentry",
            name="allocation_request",
            field=models.ForeignKey(
                blank=True,
                help_text="Linked allocation request (if any)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ledger_entries",
                to="timeoff.timeoffallocationrequest",
            ),
        ),
    ]
