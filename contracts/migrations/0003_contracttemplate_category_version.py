from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0002_contracttemplate_file_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="contracttemplate",
            name="category",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=100,
                help_text="Optional category label for organizing templates",
            ),
        ),
        migrations.AddField(
            model_name="contracttemplate",
            name="version",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=50,
                help_text="Optional version label (e.g., v1, 2026-02)",
            ),
        ),
    ]
