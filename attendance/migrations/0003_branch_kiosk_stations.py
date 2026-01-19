from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0002_branch_scoping"),
        ("employees", "0009_employee_pin_hash_employee_rfid_tag_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendanceKioskStation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True)),
                ("name", models.CharField(max_length=255)),
                ("kiosk_token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="attendance_kiosk_stations",
                        to="employees.branch",
                    ),
                ),
            ],
            options={
                "verbose_name": "Attendance Kiosk Station",
                "verbose_name_plural": "Attendance Kiosk Stations",
                "db_table": "attendance_kiosk_stations",
            },
        ),
        migrations.AddField(
            model_name="attendancerecord",
            name="kiosk_station",
            field=models.ForeignKey(
                blank=True,
                help_text="Branch kiosk station used for this record.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attendance_records",
                to="attendance.attendancekioskstation",
            ),
        ),
        migrations.AddIndex(
            model_name="attendancekioskstation",
            index=models.Index(fields=["employer_id", "branch", "is_active"], name="attendance_kiosk_station_idx"),
        ),
    ]
