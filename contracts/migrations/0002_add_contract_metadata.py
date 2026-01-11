from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='allowance',
            name='allowance_id',
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text='Optional reference to an allowance template or master list'
            ),
        ),
        migrations.AddField(
            model_name='allowance',
            name='effective_from',
            field=models.DateField(
                null=True,
                blank=True,
                help_text='Date when this allowance takes effect'
            ),
        ),
        migrations.AddField(
            model_name='deduction',
            name='deduction_id',
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text='Optional reference to a deduction template or master list'
            ),
        ),
        migrations.AddField(
            model_name='deduction',
            name='effective_from',
            field=models.DateField(
                null=True,
                blank=True,
                help_text='Date when this deduction takes effect'
            ),
        ),
        migrations.AddField(
            model_name='contractsignature',
            name='signature_method',
            field=models.CharField(
                max_length=20,
                choices=[('DOCUSIGN', 'DocuSign'), ('INTERNAL', 'Internal')],
                null=True,
                blank=True,
                help_text='Method used to obtain this signature'
            ),
        ),
        migrations.AddField(
            model_name='contractsignature',
            name='signature_audit_id',
            field=models.CharField(
                max_length=255,
                null=True,
                blank=True,
                help_text='Optional audit trail reference'
            ),
        ),
        migrations.AddField(
            model_name='contractsignature',
            name='signed_document',
            field=models.ForeignKey(
                'contracts.contractdocument',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='signatures',
                help_text='Document that was signed'
            ),
        ),
    ]
