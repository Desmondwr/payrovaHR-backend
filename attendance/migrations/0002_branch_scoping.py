from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0009_employee_pin_hash_employee_rfid_tag_id_and_more"),
        ("attendance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendancelocationsite",
            name="branch",
            field=models.ForeignKey(
                blank=True,
                help_text="Branch this site belongs to (optional for global sites).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attendance_sites",
                to="employees.branch",
            ),
        ),
        migrations.AddField(
            model_name="attendanceallowedwifi",
            name="branch",
            field=models.ForeignKey(
                blank=True,
                help_text="Branch this Wi-Fi is restricted to (optional for global).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attendance_wifi_networks",
                to="employees.branch",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="attendancelocationsite",
            unique_together={("employer_id", "branch", "name")},
        ),
        migrations.RemoveConstraint(
            model_name="attendanceallowedwifi",
            name="uniq_attendance_wifi_entry",
        ),
        migrations.AddConstraint(
            model_name="attendanceallowedwifi",
            constraint=models.UniqueConstraint(
                fields=("employer_id", "branch", "ssid", "bssid"), name="uniq_attendance_wifi_entry"
            ),
        ),
        migrations.AddIndex(
            model_name="attendancelocationsite",
            index=models.Index(fields=["employer_id", "branch"], name="attendance_site_branch_idx"),
        ),
        migrations.AddIndex(
            model_name="attendanceallowedwifi",
            index=models.Index(fields=["employer_id", "branch"], name="attendance_wifi_branch_idx"),
        ),
    ]
