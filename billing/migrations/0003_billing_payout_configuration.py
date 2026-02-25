import uuid

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_gbpay_integration"),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingPayoutConfiguration",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("is_active", models.BooleanField(default=True)),
                ("payroll_provider", models.CharField(choices=[("MANUAL", "Manual"), ("GBPAY", "GbPay")], default="MANUAL", max_length=20)),
                ("expense_provider", models.CharField(choices=[("MANUAL", "Manual"), ("GBPAY", "GbPay")], default="MANUAL", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_payout_configurations",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="billingpayoutconfiguration",
            constraint=models.UniqueConstraint(condition=Q(("is_active", True)), fields=("employer_id",), name="uniq_billing_payout_config_active_per_employer"),
        ),
        migrations.AddIndex(
            model_name="billingpayoutconfiguration",
            index=models.Index(fields=["employer_id", "is_active"], name="bill_payout_cfg_emp_act_idx"),
        ),
    ]
