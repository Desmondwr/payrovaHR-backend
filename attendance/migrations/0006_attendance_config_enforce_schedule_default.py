from django.db import migrations, models


def enable_schedule_check_in(apps, schema_editor):
    AttendanceConfiguration = apps.get_model("attendance", "AttendanceConfiguration")
    AttendanceConfiguration.objects.all().update(enforce_schedule_check_in=True)


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0005_attendance_config_enforce_schedule_checkin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="attendanceconfiguration",
            name="enforce_schedule_check_in",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(enable_schedule_check_in, migrations.RunPython.noop),
    ]
