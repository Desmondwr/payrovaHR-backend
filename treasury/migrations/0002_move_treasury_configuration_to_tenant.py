from django.db import migrations, models
import django.db.models.deletion


def create_treasury_configuration_table(apps, schema_editor):
    if not schema_editor.connection.alias.startswith("tenant_"):
        return
    TreasuryConfiguration = apps.get_model("treasury", "TreasuryConfiguration")
    table_name = TreasuryConfiguration._meta.db_table
    if table_name in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(TreasuryConfiguration)


class Migration(migrations.Migration):

    dependencies = [
        ("treasury", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="treasuryconfiguration",
                    name="institution",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="Institution owning this configuration (nullable for single-tenant setups).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="treasury_configurations",
                        to="accounts.employerprofile",
                        db_constraint=False,
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(create_treasury_configuration_table, migrations.RunPython.noop),
    ]
