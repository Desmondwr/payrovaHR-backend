from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0003_add_contract_stage_flag"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobposition",
            name="reference_code",
            field=models.CharField(blank=True, db_index=True, max_length=60, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="level",
            field=models.CharField(
                blank=True,
                choices=[
                    ("JUNIOR", "Junior"),
                    ("MID", "Mid"),
                    ("SENIOR", "Senior"),
                    ("LEAD", "Lead"),
                    ("EXECUTIVE", "Executive"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="contract_duration",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="number_of_positions",
            field=models.PositiveIntegerField(blank=True, default=1),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="requirements",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="responsibilities",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="qualifications",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="experience_years_min",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="experience_years_max",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="skills",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="languages",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="salary_min",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="salary_max",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="salary_currency",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="salary_visibility",
            field=models.CharField(
                choices=[
                    ("PUBLIC", "Public"),
                    ("PRIVATE", "Private"),
                    ("NEGOTIABLE", "Negotiable"),
                ],
                default="PRIVATE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="jobposition",
            name="application_deadline",
            field=models.DateField(blank=True, null=True),
        ),
    ]
