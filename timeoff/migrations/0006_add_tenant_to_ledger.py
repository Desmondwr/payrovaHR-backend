from django.db import migrations, models


def backfill(apps, schema_editor):
    TimeOffLedgerEntry = apps.get_model("timeoff", "TimeOffLedgerEntry")
    db_alias = schema_editor.connection.alias
    for entry in TimeOffLedgerEntry.objects.using(db_alias).filter(tenant_id__isnull=True).iterator():
        entry.tenant_id = entry.employer_id
        entry.save(using=db_alias, update_fields=["tenant_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("timeoff", "0005_add_tenant_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeoffledgerentry",
            name="tenant_id",
            field=models.IntegerField(
                blank=True,
                null=True,
                db_index=True,
                help_text="Alias for employer/tenant identifier to simplify lookups",
            ),
        ),
        migrations.RunPython(backfill, reverse_code=migrations.RunPython.noop),
    ]
