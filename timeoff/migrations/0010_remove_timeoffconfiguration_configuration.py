from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("timeoff", "0009_recreate_timeoff_config_table"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="timeoffconfiguration",
            name="configuration",
        ),
    ]
