from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0012_add_component_month"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE contract_allowances "
                "ADD COLUMN IF NOT EXISTS component_month varchar(10);"
            ),
            reverse_sql=(
                "ALTER TABLE contract_allowances "
                "DROP COLUMN IF EXISTS component_month;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE contract_deductions "
                "ADD COLUMN IF NOT EXISTS component_month varchar(10);"
            ),
            reverse_sql=(
                "ALTER TABLE contract_deductions "
                "DROP COLUMN IF EXISTS component_month;"
            ),
        ),
    ]

