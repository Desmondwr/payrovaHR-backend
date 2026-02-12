from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0003_attendance_config_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="missing_checkout_cutoff_minutes",
            field=models.IntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="missing_checkout_penalty_mode",
            field=models.CharField(
                choices=[
                    ("none", "No penalty"),
                    ("full_absence", "Full absence"),
                    ("auto_refuse", "Auto-refuse record"),
                    ("fixed_minutes", "Fixed penalty minutes"),
                ],
                default="none",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="missing_checkout_penalty_minutes",
            field=models.IntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
    ]
