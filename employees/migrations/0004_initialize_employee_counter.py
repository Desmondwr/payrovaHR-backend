# Generated migration to initialize last_employee_number for existing configurations

from django.db import migrations
import re


def initialize_counters(apps, schema_editor):
    """Initialize last_employee_number for existing EmployeeConfiguration records"""
    EmployeeConfiguration = apps.get_model('employees', 'EmployeeConfiguration')
    Employee = apps.get_model('employees', 'Employee')
    
    # Get the database alias being used
    db_alias = schema_editor.connection.alias
    
    for config in EmployeeConfiguration.objects.using(db_alias).all():
        # Find the highest employee number for this employer
        existing_employees = Employee.objects.using(db_alias).filter(
            employer_id=config.employer_id
        ).exclude(employee_id='').exclude(employee_id__isnull=True).values_list('employee_id', flat=True)
        
        max_number = 0
        for emp_id in existing_employees:
            # Extract all numbers from the employee ID
            numbers = re.findall(r'\d+', str(emp_id))
            if numbers:
                # Get the last number (usually the sequence number)
                try:
                    num = int(numbers[-1])
                    if num > max_number:
                        max_number = num
                except ValueError:
                    continue
        
        # Set last_employee_number to the max found (or 0 if no employees)
        config.last_employee_number = max_number
        config.save(using=db_alias)


def reverse_initialization(apps, schema_editor):
    """Reverse migration - reset counters to 0"""
    EmployeeConfiguration = apps.get_model('employees', 'EmployeeConfiguration')
    db_alias = schema_editor.connection.alias
    
    EmployeeConfiguration.objects.using(db_alias).update(last_employee_number=0)


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0003_employeeconfiguration_last_employee_number'),
    ]

    operations = [
        migrations.RunPython(initialize_counters, reverse_initialization),
    ]
