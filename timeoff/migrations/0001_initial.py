from django.db import migrations, models
import uuid
import timeoff.defaults


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TimeOffConfiguration",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "employer_id",
                    models.IntegerField(db_index=True, help_text="ID of the employer (from main database)"),
                ),
                (
                    "configuration",
                    models.JSONField(
                        blank=True,
                        default=timeoff.defaults.get_time_off_defaults,
                        help_text="Time off configuration payload (global + leave types)",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Time Off Configuration",
                "verbose_name_plural": "Time Off Configurations",
                "db_table": "timeoff_configurations",
                "ordering": ["-created_at"],
                "unique_together": {("employer_id",)},
            },
        ),
    ]
