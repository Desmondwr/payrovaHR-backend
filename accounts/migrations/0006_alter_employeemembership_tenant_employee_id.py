from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_backfill_employee_memberships'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employeemembership',
            name='tenant_employee_id',
            field=models.CharField(
                max_length=64,
                null=True,
                blank=True,
                help_text='Employee PK inside the employer tenant database (supports UUIDs)',
            ),
        ),
    ]
