from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0003_billing_payout_configuration"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingpayoutbatch",
            name="requires_approval",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="billingpayoutbatch",
            name="approved_by_id",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="billingpayoutbatch",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
