import uuid

import frontdesk.models
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("employees", "0007_alter_employeedocument_document_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="FrontdeskStation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")),
                ("name", models.CharField(max_length=255)),
                ("kiosk_slug", models.CharField(default=frontdesk.models.generate_kiosk_slug, help_text="Stable slug used to build kiosk/QR URLs", max_length=100, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("allow_self_check_in", models.BooleanField(default=True, help_text="Allow kiosk/QR self check-in (checkout remains manual)")),
                ("kiosk_theme", models.JSONField(blank=True, default=dict, help_text="Appearance settings for the kiosk (colors, logo URL, terms text)")),
                ("terms_and_conditions", models.TextField(blank=True, help_text="Optional terms displayed on the kiosk")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="frontdesk_stations", to="employees.branch")),
            ],
            options={
                "verbose_name": "Frontdesk Station",
                "verbose_name_plural": "Frontdesk Stations",
                "db_table": "frontdesk_stations",
                "ordering": ["branch__name", "-is_active", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="Visitor",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")),
                ("full_name", models.CharField(max_length=255)),
                ("phone", models.CharField(blank=True, max_length=50, null=True)),
                ("email", models.EmailField(blank=True, max_length=254, null=True)),
                ("organization", models.CharField(blank=True, max_length=255, null=True)),
                ("id_type", models.CharField(blank=True, help_text="ID type provided (e.g., Passport, ID Card)", max_length=100, null=True)),
                ("id_number", models.CharField(blank=True, help_text="ID number captured at check-in", max_length=100, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Visitor",
                "verbose_name_plural": "Visitors",
                "db_table": "frontdesk_visitors",
            },
        ),
        migrations.CreateModel(
            name="Visit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("employer_id", models.IntegerField(db_index=True, help_text="ID of the employer (from main database)")),
                ("visit_type", models.CharField(choices=[("WALK_IN", "Walk-in"), ("PLANNED", "Planned")], default="WALK_IN", max_length=10)),
                ("status", models.CharField(choices=[("PLANNED", "Planned"), ("CHECKED_IN", "Checked In"), ("CHECKED_OUT", "Checked Out"), ("CANCELLED", "Cancelled")], default="PLANNED", max_length=12)),
                ("visit_purpose", models.CharField(blank=True, max_length=255, null=True)),
                ("planned_start", models.DateTimeField(blank=True, null=True)),
                ("planned_end", models.DateTimeField(blank=True, null=True)),
                ("check_in_time", models.DateTimeField(blank=True, null=True)),
                ("check_out_time", models.DateTimeField(blank=True, null=True)),
                ("check_in_method", models.CharField(choices=[("MANUAL", "Manual"), ("KIOSK", "Kiosk/QR")], default="MANUAL", max_length=10)),
                ("check_out_by_id", models.IntegerField(blank=True, help_text="User ID of HR/Admin who completed checkout. Visitors never self checkout.", null=True)),
                ("kiosk_session_reference", models.CharField(blank=True, help_text="Optional kiosk session/QR reference captured at check-in", max_length=100, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="frontdesk_visits", to="employees.branch")),
                ("host", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="hosted_visits", to="employees.employee")),
                ("station", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="visits", to="frontdesk.frontdeskstation")),
                ("visitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="visits", to="frontdesk.visitor")),
            ],
            options={
                "verbose_name": "Visit",
                "verbose_name_plural": "Visits",
                "db_table": "frontdesk_visits",
            },
        ),
        migrations.CreateModel(
            name="StationResponsible",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="frontdesk_responsibilities", to="employees.employee")),
                ("station", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="station_responsibles", to="frontdesk.frontdeskstation")),
            ],
            options={
                "verbose_name": "Station Responsible",
                "verbose_name_plural": "Station Responsibles",
                "db_table": "frontdesk_station_responsibles",
            },
        ),
        migrations.AddConstraint(
            model_name="frontdeskstation",
            constraint=models.UniqueConstraint(condition=Q(("is_active", True)), fields=("branch",), name="unique_active_frontdesk_station_per_branch"),
        ),
        migrations.AddIndex(
            model_name="visit",
            index=models.Index(fields=["employer_id", "branch"], name="frontdesk_v_employe_e143b0_idx"),
        ),
        migrations.AddIndex(
            model_name="visit",
            index=models.Index(fields=["employer_id", "status"], name="frontdesk_v_employe_49389e_idx"),
        ),
        migrations.AddIndex(
            model_name="visit",
            index=models.Index(fields=["employer_id", "visit_type"], name="frontdesk_v_employe_3fa635_idx"),
        ),
        migrations.AddIndex(
            model_name="visitor",
            index=models.Index(fields=["employer_id", "full_name"], name="frontdesk_v_employe_0c2bfc_idx"),
        ),
        migrations.AddIndex(
            model_name="visitor",
            index=models.Index(fields=["employer_id", "phone"], name="frontdesk_v_employe_a07e24_idx"),
        ),
        migrations.AddIndex(
            model_name="visitor",
            index=models.Index(fields=["employer_id", "email"], name="frontdesk_v_employe_ba3ab5_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="stationresponsible",
            unique_together={("station", "employee")},
        ),
    ]
