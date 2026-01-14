from django.db import migrations


def add_missing_signed_document_column(apps, schema_editor):
    """
    Ensure the signed_document_id column exists on contract_signatures.
    Some databases were created before the field was added to the initial migration,
    so we add it manually if it's missing.
    """
    ContractSignature = apps.get_model('contracts', 'ContractSignature')
    table_name = ContractSignature._meta.db_table
    column_name = 'signed_document_id'

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = %s
            """,
            [table_name, column_name],
        )
        if cursor.fetchone():
            return

    field = ContractSignature._meta.get_field('signed_document')
    schema_editor.add_field(ContractSignature, field)


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_missing_signed_document_column, migrations.RunPython.noop),
    ]
