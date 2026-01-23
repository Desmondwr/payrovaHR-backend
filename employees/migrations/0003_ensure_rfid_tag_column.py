from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0002_ensure_user_account_column'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE employees
                ADD COLUMN IF NOT EXISTS rfid_tag_id varchar(100);
                CREATE INDEX IF NOT EXISTS employees_employee_rfid_tag_id
                ON employees (rfid_tag_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS employees_employee_rfid_tag_id;
                ALTER TABLE employees
                DROP COLUMN IF EXISTS rfid_tag_id;
            """,
        ),
    ]
