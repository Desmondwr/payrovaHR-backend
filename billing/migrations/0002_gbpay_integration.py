import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payoutmethod",
            name="bank_code",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="payoutmethod",
            name="operator_code",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="payoutmethod",
            name="entity_product_uuid",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="payoutmethod",
            name="country_id",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payoutmethod",
            name="account_number_encrypted",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="payoutmethod",
            name="wallet_destination_encrypted",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="payoutmethod",
            name="verification_reference",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="payoutmethod",
            name="verification_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="billingpayout",
            name="receipt_number",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="billingpayout",
            name="receipt_file",
            field=models.FileField(blank=True, null=True, upload_to="billing/payouts/"),
        ),
        migrations.AddField(
            model_name="billingpayout",
            name="receipt_issued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="billingpaymentattempt",
            name="idempotency_key",
            field=models.CharField(blank=True, db_index=True, max_length=128, null=True),
        ),
        migrations.CreateModel(
            name="GbPayEmployerConnection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("label", models.CharField(blank=True, max_length=120)),
                ("environment", models.CharField(choices=[("SANDBOX", "Sandbox"), ("PRODUCTION", "Production")], default="PRODUCTION", max_length=20)),
                ("is_active", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive"), ("INVALID", "Invalid"), ("PENDING", "Pending")], default="INACTIVE", max_length=20)),
                ("credentials_encrypted", models.TextField()),
                ("credentials_hint", models.CharField(blank=True, max_length=120)),
                ("last_validated_at", models.DateTimeField(blank=True, null=True)),
                ("last_validation_error", models.TextField(blank=True)),
                ("last_validated_by_id", models.IntegerField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_gbpay_connections",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="GbPayTransfer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("PROCESSING", "Processing"), ("SUCCESS", "Success"), ("FAILED", "Failed"), ("CANCELED", "Canceled"), ("TIMEOUT", "Timeout")], default="PENDING", max_length=20)),
                ("provider_status", models.CharField(blank=True, max_length=40)),
                ("quote_id", models.CharField(blank=True, max_length=120)),
                ("transaction_reference", models.CharField(blank=True, max_length=120)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("status_payload", models.JSONField(blank=True, default=dict)),
                ("event_log", models.JSONField(blank=True, default=list)),
                ("failure_code", models.CharField(blank=True, max_length=60)),
                ("failure_message", models.TextField(blank=True)),
                ("poll_count", models.PositiveIntegerField(default=0)),
                ("last_polled_at", models.DateTimeField(blank=True, null=True)),
                ("next_poll_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("attempt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gbpay_transfers", to="billing.billingpaymentattempt")),
                ("payout", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gbpay_transfers", to="billing.billingpayout")),
            ],
            options={
                "db_table": "billing_gbpay_transfers",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="gbpayemployerconnection",
            constraint=models.UniqueConstraint(condition=models.Q(is_active=True), fields=("employer_id",), name="uniq_billing_gbpay_active_employer"),
        ),
        migrations.AddIndex(
            model_name="gbpayemployerconnection",
            index=models.Index(fields=["employer_id", "status"], name="billing_gbpay_employer_id_status_idx"),
        ),
        migrations.AddIndex(
            model_name="gbpaytransfer",
            index=models.Index(fields=["employer_id", "status"], name="billing_gbpay_transfer_employer_status_idx"),
        ),
        migrations.AddIndex(
            model_name="gbpaytransfer",
            index=models.Index(fields=["transaction_reference"], name="billing_gbpay_transfer_reference_idx"),
        ),
        migrations.AddIndex(
            model_name="gbpaytransfer",
            index=models.Index(fields=["next_poll_at"], name="billing_gbpay_transfer_next_poll_idx"),
        ),
        migrations.AddConstraint(
            model_name="billingpaymentattempt",
            constraint=models.UniqueConstraint(condition=models.Q(attempt_type="PAYOUT"), fields=("idempotency_key",), name="uniq_billing_payout_idempotency"),
        ),
    ]
