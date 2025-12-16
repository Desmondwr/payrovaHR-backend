"""
Script to clean up invalid employee records with empty employee_id
"""
import os
import django
import psycopg2

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from accounts.models import EmployerProfile

def cleanup_invalid_employees():
    """Delete employee records with empty employee_id"""
    
    # Get the employer with ID 2
    try:
        employer = EmployerProfile.objects.get(id=2)
        print(f"Employer ID 2: {employer.company_name}")
        print(f"Database name: {employer.database_name}")
        
        # Get database connection settings
        default_db = settings.DATABASES['default']
        
        # Connect directly to the tenant database
        conn = psycopg2.connect(
            dbname=employer.database_name,
            user=default_db['USER'],
            password=default_db['PASSWORD'],
            host=default_db['HOST'],
            port=default_db['PORT']
        )
        
        cursor = conn.cursor()
        
        # Check all employees
        cursor.execute("SELECT id, employer_id, employee_id, email FROM employees")
        all_employees = cursor.fetchall()
        
        print(f"\nAll employees in database:")
        for emp in all_employees:
            print(f"  - ID: {emp[0]}, employer_id: {emp[1]}, employee_id: '{emp[2]}', email: {emp[3]}")
        
        # Check for invalid employees (empty or NULL)
        cursor.execute("SELECT id, employer_id, employee_id, email FROM employees WHERE employee_id = '' OR employee_id IS NULL")
        invalid_employees = cursor.fetchall()
        
        if invalid_employees:
            print(f"\nFound {len(invalid_employees)} invalid employee(s):")
            for emp in invalid_employees:
                print(f"  - ID: {emp[0]}, employer_id: {emp[1]}, employee_id: '{emp[2]}', email: {emp[3]}")
            
            # Delete them
            cursor.execute("DELETE FROM employees WHERE employee_id = '' OR employee_id IS NULL")
            deleted_count = cursor.rowcount
            conn.commit()
            print(f"\n✓ Deleted {deleted_count} invalid employee record(s)")
        else:
            print("\nNo invalid employees found")
        
        cursor.close()
        conn.close()
        
        print("\n✓ Cleanup complete!")
        
    except EmployerProfile.DoesNotExist:
        print("Employer with ID 2 not found")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    cleanup_invalid_employees()
