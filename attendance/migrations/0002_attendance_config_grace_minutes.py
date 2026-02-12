from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="early_check_in_grace_minutes",
            field=models.IntegerField(
                default=0,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="attendanceconfiguration",
            name="late_check_in_grace_minutes",
            field=models.IntegerField(
                default=0,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
