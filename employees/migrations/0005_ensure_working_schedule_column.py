from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0004_ensure_pin_hash_column'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE employees
                ADD COLUMN IF NOT EXISTS working_schedule_id uuid;
                CREATE INDEX IF NOT EXISTS employees_employee_working_schedule_id
                ON employees (working_schedule_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS employees_employee_working_schedule_id;
                ALTER TABLE employees
                DROP COLUMN IF EXISTS working_schedule_id;
            """,
        ),
    ]
