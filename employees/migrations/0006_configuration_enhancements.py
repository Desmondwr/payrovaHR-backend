# Generated migration file for new configuration features

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0005_profile_completion_tracking'),
    ]

    operations = [
        # Add last_reminder_sent_at field to Employee model
        migrations.AddField(
            model_name='employee',
            name='last_reminder_sent_at',
            field=models.DateTimeField(blank=True, null=True, help_text='Last time a reminder email was sent'),
        ),
        
        # Create TerminationApproval model
        migrations.CreateModel(
            name='TerminationApproval',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('requested_by_id', models.IntegerField(db_index=True, help_text='ID of the user who requested termination')),
                ('termination_date', models.DateField()),
                ('termination_reason', models.TextField()),
                ('status', models.CharField(choices=[('PENDING', 'Pending Approval'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=20)),
                ('requires_manager_approval', models.BooleanField(default=False)),
                ('manager_approved', models.BooleanField(default=False)),
                ('manager_approved_by_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('manager_approved_at', models.DateTimeField(blank=True, null=True)),
                ('requires_hr_approval', models.BooleanField(default=False)),
                ('hr_approved', models.BooleanField(default=False)),
                ('hr_approved_by_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('hr_approved_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_reason', models.TextField(blank=True, null=True)),
                ('rejected_by_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='termination_approvals', to='employees.employee')),
            ],
            options={
                'verbose_name': 'Termination Approval',
                'verbose_name_plural': 'Termination Approvals',
                'db_table': 'termination_approvals',
                'ordering': ['-created_at'],
            },
        ),
        
        # Create CrossInstitutionConsent model
        migrations.CreateModel(
            name='CrossInstitutionConsent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('employee_registry_id', models.IntegerField(db_index=True, help_text='EmployeeRegistry ID from main database')),
                ('source_employer_id', models.IntegerField(db_index=True, help_text='Current employer ID')),
                ('target_employer_id', models.IntegerField(db_index=True, help_text='New employer requesting to link')),
                ('target_employer_name', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('PENDING', 'Pending Consent'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='PENDING', max_length=20)),
                ('consent_token', models.CharField(db_index=True, max_length=100, unique=True)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Cross-Institution Consent',
                'verbose_name_plural': 'Cross-Institution Consents',
                'db_table': 'cross_institution_consents',
                'ordering': ['-requested_at'],
            },
        ),
        
        # Add new action choices to EmployeeAuditLog
        migrations.AlterField(
            model_name='employeeauditlog',
            name='action',
            field=models.CharField(
                choices=[
                    ('CREATED', 'Created'),
                    ('UPDATED', 'Updated'),
                    ('TERMINATED', 'Terminated'),
                    ('DELETED', 'Deleted'),
                    ('INVITED', 'Invitation Sent'),
                    ('LINKED', 'Linked to User Account'),
                    ('CROSS_INSTITUTION_DETECTED', 'Cross-Institution Detected'),
                    ('TERMINATION_REQUESTED', 'Termination Requested'),
                    ('TERMINATION_APPROVED', 'Termination Approved'),
                    ('TERMINATION_REJECTED', 'Termination Rejected'),
                ],
                max_length=50
            ),
        ),
    ]
