from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="employeeconfiguration",
            name="require_employee_consent_cross_institution",
        ),
    ]
