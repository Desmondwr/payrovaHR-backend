from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_signature'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='last_active_employer_id',
            field=models.IntegerField(
                blank=True,
                null=True,
                db_index=True,
                help_text='EmployerProfile ID most recently used by the user',
            ),
        ),
        migrations.CreateModel(
            name='EmployeeMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('INVITED', 'Invited'), ('ACTIVE', 'Active'), ('TERMINATED', 'Terminated')], default='INVITED', max_length=20)),
                ('role', models.CharField(blank=True, choices=[('EMPLOYEE', 'Employee'), ('MANAGER', 'Manager'), ('HR', 'HR'), ('ADMIN', 'Admin')], help_text='Optional role label', max_length=30, null=True)),
                ('permissions', models.JSONField(blank=True, help_text='Optional per-employer permissions', null=True)),
                ('tenant_employee_id', models.IntegerField(blank=True, help_text='Employee PK inside the employer tenant database', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('employer_profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='employee_memberships', to='accounts.employerprofile')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'employee_memberships',
                'verbose_name': 'Employee Membership',
                'verbose_name_plural': 'Employee Memberships',
                'unique_together': {('user', 'employer_profile')},
            },
        ),
        migrations.AddIndex(
            model_name='employeemembership',
            index=models.Index(fields=['user', 'status'], name='employee_m_user_id_c2b68d_idx'),
        ),
        migrations.AddIndex(
            model_name='employeemembership',
            index=models.Index(fields=['employer_profile', 'status'], name='employee_m_employe_69ea07_idx'),
        ),
    ]
