from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0005_employment_certificate_share_and_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeecrossinstitutionrecord',
            name='consent_scopes',
            field=models.JSONField(blank=True, default=list, help_text='Approved consent scopes for this cross-institution record'),
        ),
        migrations.AddField(
            model_name='crossinstitutionconsent',
            name='requested_scopes',
            field=models.JSONField(blank=True, default=list, help_text='Requested consent scopes for this employer'),
        ),
        migrations.AddField(
            model_name='crossinstitutionconsent',
            name='approved_scopes',
            field=models.JSONField(blank=True, default=list, help_text='Approved consent scopes granted by the employee'),
        ),
    ]
