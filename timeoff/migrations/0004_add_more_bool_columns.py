from django.db import migrations, models
from django.db.models import JSONField


def backfill(apps, schema_editor):
    TimeOffConfiguration = apps.get_model("timeoff", "TimeOffConfiguration")
    db_alias = schema_editor.connection.alias

    for cfg in TimeOffConfiguration.objects.using(db_alias).all().iterator():
        global_settings = (cfg.configuration or {}).get("global_settings") or {}
        cfg.module_enabled = global_settings.get("module_enabled", True)
        cfg.allow_backdated_requests = global_settings.get("allow_backdated_requests", True)
        cfg.allow_future_dated_requests = global_settings.get("allow_future_dated_requests", True)
        cfg.allow_negative_balance = global_settings.get("allow_negative_balance", False)
        cfg.allow_overlapping_requests = global_settings.get("allow_overlapping_requests", False)
        cfg.save(
            using=db_alias,
            update_fields=[
                "module_enabled",
                "allow_backdated_requests",
                "allow_future_dated_requests",
                "allow_negative_balance",
                "allow_overlapping_requests",
            ],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("timeoff", "0003_add_columnized_timeoff_config_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="allow_backdated_requests",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="allow_future_dated_requests",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="module_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(backfill, reverse_code=migrations.RunPython.noop),
    ]
