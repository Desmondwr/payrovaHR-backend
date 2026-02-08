from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contracttemplate",
            name="file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="contract_templates/",
                help_text="Template file (DOCX, PDF, etc.)",
            ),
        ),
    ]
