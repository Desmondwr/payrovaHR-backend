from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0004_employeeconfiguration_multi_branch_enabled'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employeeconfiguration',
            name='cross_institution_visibility_level',
            field=models.CharField(choices=[('NONE', 'No visibility'), ('BASIC', 'Institution name only'), ('MODERATE', 'Institution name and employment dates'), ('FULL', 'Full employment details')], default='NONE', help_text='What information is visible about other institutions', max_length=20),
        ),
        migrations.CreateModel(
            name='EmploymentCertificateShare',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('employee_registry_id', models.IntegerField(db_index=True, help_text='EmployeeRegistry ID from main database')),
                ('employer_id', models.IntegerField(db_index=True, help_text='Employer ID that issued the certificate')),
                ('tenant_employee_id', models.CharField(blank=True, help_text='Employee ID in tenant database', max_length=64, null=True)),
                ('document_id', models.UUIDField(help_text='EmployeeDocument ID in tenant database')),
                ('token', models.CharField(db_index=True, max_length=100, unique=True)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('REVOKED', 'Revoked'), ('EXPIRED', 'Expired')], default='ACTIVE', max_length=20)),
                ('created_by_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Employment Certificate Share',
                'verbose_name_plural': 'Employment Certificate Shares',
                'db_table': 'employment_certificate_shares',
                'ordering': ['-created_at'],
            },
        ),
    ]

