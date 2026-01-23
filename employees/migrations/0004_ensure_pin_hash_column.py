from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0003_ensure_rfid_tag_column'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE employees
                ADD COLUMN IF NOT EXISTS pin_hash varchar(128);
                CREATE INDEX IF NOT EXISTS employees_employee_pin_hash
                ON employees (pin_hash);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS employees_employee_pin_hash;
                ALTER TABLE employees
                DROP COLUMN IF EXISTS pin_hash;
            """,
        ),
    ]
