from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0004_attendance_config_missing_checkout_penalties"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="enforce_schedule_check_in",
            field=models.BooleanField(default=False),
        ),
    ]
