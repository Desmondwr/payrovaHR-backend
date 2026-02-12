from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0002_attendance_config_grace_minutes"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="flag_overlaps",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="flag_missing_checkout",
            field=models.BooleanField(default=False),
        ),
    ]
