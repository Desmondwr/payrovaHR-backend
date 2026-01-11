from django.db import migrations, models


def backfill_tenant(apps, schema_editor):
    TimeOffConfiguration = apps.get_model("timeoff", "TimeOffConfiguration")
    db_alias = schema_editor.connection.alias
    for cfg in TimeOffConfiguration.objects.using(db_alias).all().iterator():
        if cfg.tenant_id is None:
            cfg.tenant_id = cfg.employer_id
            cfg.save(using=db_alias, update_fields=["tenant_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("timeoff", "0004_add_more_bool_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="tenant_id",
            field=models.IntegerField(
                blank=True,
                null=True,
                db_index=True,
                help_text="Alias for employer_id to support tenant-aware queries",
            ),
        ),
        migrations.RunPython(backfill_tenant, reverse_code=migrations.RunPython.noop),
    ]
