from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0008_attendance_record_timezones"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendancerecord",
            name="break_ending_soon_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="attendancerecord",
            name="break_end_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
