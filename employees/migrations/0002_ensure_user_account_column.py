from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE employees
                ADD COLUMN IF NOT EXISTS user_account_id integer;
                CREATE INDEX IF NOT EXISTS employees_employee_user_account_id
                ON employees (user_account_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS employees_employee_user_account_id;
                ALTER TABLE employees
                DROP COLUMN IF EXISTS user_account_id;
            """,
        ),
    ]
