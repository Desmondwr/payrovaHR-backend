from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS last_active_employer_id integer;"
                "CREATE INDEX IF NOT EXISTS accounts_user_last_active_employer_id "
                "ON users (last_active_employer_id);"
            ),
            reverse_sql=(
                "DROP INDEX IF EXISTS accounts_user_last_active_employer_id;"
                "ALTER TABLE users DROP COLUMN IF EXISTS last_active_employer_id;"
            ),
        ),
    ]
