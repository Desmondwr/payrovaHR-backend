from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0011_contractcomponenttemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="allowance",
            name="component_month",
            field=models.CharField(
                blank=True,
                help_text="Optional fiscal month reference (e.g., 01-12)",
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="deduction",
            name="component_month",
            field=models.CharField(
                blank=True,
                help_text="Optional fiscal month reference (e.g., 01-12)",
                max_length=10,
                null=True,
            ),
        ),
    ]

