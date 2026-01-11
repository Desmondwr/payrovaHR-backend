from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0002_add_contract_metadata'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contract',
            name='job_position',
        ),
    ]
