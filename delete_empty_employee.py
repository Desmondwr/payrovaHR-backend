"""
Script to delete the employee with empty employee_id
"""
import os
import django
import psycopg2

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from accounts.models import EmployerProfile

def delete_empty_employee():
    """Delete the employee with ID 6172c211-72c5-41f6-bdae-6d6e9ec12053"""
    
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
        
        # Delete the specific employee with empty employee_id
        employee_uuid = '6172c211-72c5-41f6-bdae-6d6e9ec12053'
        cursor.execute("DELETE FROM employees WHERE id = %s", (employee_uuid,))
        deleted_count = cursor.rowcount
        conn.commit()
        
        if deleted_count > 0:
            print(f"\n✓ Deleted employee with ID {employee_uuid}")
        else:
            print(f"\n✗ Employee with ID {employee_uuid} not found")
        
        cursor.close()
        conn.close()
        
        print("\n✓ Cleanup complete! You can now try creating the employee again.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    delete_empty_employee()
