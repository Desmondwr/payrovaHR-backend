# Generated migration for Option 4 implementation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0004_initialize_employee_counter'),
    ]

    operations = [
        # Add new profile completion tracking fields to Employee model
        migrations.AddField(
            model_name='employee',
            name='profile_completion_required',
            field=models.BooleanField(default=False, help_text='Whether employee needs to complete profile based on employer config'),
        ),
        migrations.AddField(
            model_name='employee',
            name='profile_completion_state',
            field=models.CharField(
                choices=[
                    ('COMPLETE', 'Complete - All requirements met'),
                    ('INCOMPLETE_BLOCKING', 'Incomplete - Missing critical fields, limited access'),
                    ('INCOMPLETE_NON_BLOCKING', 'Incomplete - Missing optional fields, full access')
                ],
                default='INCOMPLETE_NON_BLOCKING',
                help_text='Current profile completion state',
                max_length=30
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='missing_required_fields',
            field=models.JSONField(blank=True, default=list, help_text='List of missing required fields per employer config'),
        ),
        migrations.AddField(
            model_name='employee',
            name='missing_optional_fields',
            field=models.JSONField(blank=True, default=list, help_text='List of missing optional fields per employer config'),
        ),
        
        # Add critical fields configuration to EmployeeConfiguration model
        migrations.AddField(
            model_name='employeeconfiguration',
            name='critical_fields',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of field names that are critical/blocking: ["national_id_number", "date_of_birth"]'
            ),
        ),
    ]
