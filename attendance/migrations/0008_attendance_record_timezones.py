from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0007_working_schedule_break_times"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendancerecord",
            name="check_in_timezone",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="attendancerecord",
            name="check_out_timezone",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
