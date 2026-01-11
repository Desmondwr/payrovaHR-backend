from django.db import migrations, models
from django.db.models import JSONField


def sync_columns(apps, schema_editor):
    TimeOffConfiguration = apps.get_model("timeoff", "TimeOffConfiguration")
    db_alias = schema_editor.connection.alias

    def extract(cfg):
        cfg = cfg or {}
        g = cfg.get("global_settings") or {}
        rounding = g.get("rounding") or {}
        return {
            "schema_version": cfg.get("schema_version") or g.get("schema_version") or 1,
            "default_time_unit": g.get("default_time_unit", "DAYS"),
            "working_hours_per_day": g.get("working_hours_per_day", 8),
            "leave_year_type": g.get("leave_year_type", "CALENDAR"),
            "leave_year_start_month": g.get("leave_year_start_month", 1),
            "holiday_calendar_source": g.get("holiday_calendar_source", "DEFAULT"),
            "time_zone_handling": g.get("time_zone_handling", "EMPLOYER_LOCAL"),
            "reservation_policy": g.get("reservation_policy", "RESERVE_ON_SUBMIT"),
            "rounding_increment_minutes": rounding.get("increment_minutes", 30) or 0,
            "rounding_method": rounding.get("method", "NEAREST") or "NEAREST",
            "weekend_days": g.get("weekend_days") or [],
            "allow_negative_balance": g.get("allow_negative_balance", False),
            "negative_balance_limit": g.get("negative_balance_limit", 0) or 0,
            "allow_overlapping_requests": g.get("allow_overlapping_requests", False),
            "backdated_limit_days": g.get("backdated_limit_days", 30) or 0,
            "future_window_days": g.get("future_window_days", 180) or 0,
            "max_request_length_days": g.get("max_request_length_days"),
            "max_requests_per_month": g.get("max_requests_per_month"),
        }

    for cfg in TimeOffConfiguration.objects.using(db_alias).all().iterator():
        data = extract(cfg.configuration)
        for field, value in data.items():
            setattr(cfg, field, value)
        cfg.save(
            using=db_alias,
            update_fields=list(data.keys()),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("timeoff", "0002_timeoffrequest_timeoffledgerentry_timeoffapproval_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="allow_negative_balance",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="allow_overlapping_requests",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="backdated_limit_days",
            field=models.IntegerField(default=30),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="default_time_unit",
            field=models.CharField(default="DAYS", max_length=10),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="future_window_days",
            field=models.IntegerField(default=180),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="holiday_calendar_source",
            field=models.CharField(default="DEFAULT", max_length=20),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="leave_year_start_month",
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="leave_year_type",
            field=models.CharField(default="CALENDAR", max_length=10),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="max_request_length_days",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="max_requests_per_month",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="negative_balance_limit",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="reservation_policy",
            field=models.CharField(default="RESERVE_ON_SUBMIT", max_length=30),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="rounding_increment_minutes",
            field=models.IntegerField(default=30),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="rounding_method",
            field=models.CharField(default="NEAREST", max_length=10),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="schema_version",
            field=models.IntegerField(default=1, help_text="Schema version for normalization"),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="time_zone_handling",
            field=models.CharField(default="EMPLOYER_LOCAL", max_length=30),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="weekend_days",
            field=JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="timeoffconfiguration",
            name="working_hours_per_day",
            field=models.IntegerField(default=8),
        ),
        migrations.RunPython(sync_columns, reverse_code=migrations.RunPython.noop),
    ]
