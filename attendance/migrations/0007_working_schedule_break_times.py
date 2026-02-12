from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0006_attendance_config_enforce_schedule_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="workingscheduleday",
            name="break_start_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workingscheduleday",
            name="break_end_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="attendancerecord",
            name="break_reminder_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
