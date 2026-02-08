from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0003_contracttemplate_category_version"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractTemplateVersion",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("category", models.CharField(max_length=100, blank=True, null=True)),
                ("version", models.CharField(max_length=50, blank=True, null=True)),
                ("contract_type", models.CharField(max_length=20, choices=[
                    ("PERMANENT", "Permanent"),
                    ("FIXED_TERM", "Fixed-Term"),
                    ("INTERNSHIP", "Internship"),
                    ("CONSULTANT", "Consultant"),
                    ("PART_TIME", "Part-Time"),
                ])),
                ("body_override", models.TextField(blank=True, null=True)),
                ("file", models.FileField(upload_to="contract_templates/", blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("template", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="versions", to="contracts.contracttemplate")),
            ],
            options={
                "db_table": "contract_template_versions",
                "ordering": ["-created_at"],
                "verbose_name": "Contract Template Version",
                "verbose_name_plural": "Contract Template Versions",
            },
        ),
    ]
