"""
Script to check if tenant database has employee tables
"""
import os
import sys
import django
import psycopg2

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from accounts.models import EmployerProfile

def check_database_tables(db_name):
    """Check what tables exist in a database"""
    try:
        default_db = settings.DATABASES['default']
        conn = psycopg2.connect(
            dbname=db_name,
            user=default_db['USER'],
            password=default_db['PASSWORD'],
            host=default_db['HOST'],
            port=default_db['PORT']
        )
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """)
        
        tables = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [table[0] for table in tables]
        
    except Exception as e:
        print(f"Error checking tables: {e}")
        return []

def main():
    print("=" * 80)
    print("CHECKING TENANT DATABASES")
    print("=" * 80)
    
    # Get all employers with databases
    employers = EmployerProfile.objects.filter(database_created=True)
    
    if not employers.exists():
        print("\nNo tenant databases found!")
        print("\nTo create a tenant database:")
        print("1. Complete the employer profile via POST /api/accounts/employer/profile/complete/")
        return
    
    for employer in employers:
        print(f"\n{'=' * 80}")
        print(f"Employer: {employer.company_name}")
        print(f"Database: {employer.database_name}")
        print(f"Created: {employer.database_created_at}")
        print(f"{'=' * 80}")
        
        tables = check_database_tables(employer.database_name)
        
        if tables:
            print(f"\nFound {len(tables)} tables:")
            print("-" * 40)
            
            # Categorize tables
            employee_tables = [t for t in tables if 'employee' in t.lower()]
            django_tables = [t for t in tables if t.startswith('django_')]
            other_tables = [t for t in tables if t not in employee_tables and t not in django_tables]
            
            if employee_tables:
                print("\n✓ Employee-related tables:")
                for table in employee_tables:
                    print(f"  - {table}")
            else:
                print("\n✗ No employee tables found!")
            
            if django_tables:
                print("\n  Django system tables:")
                for table in django_tables:
                    print(f"  - {table}")
            
            if other_tables:
                print("\n  Other tables:")
                for table in other_tables:
                    print(f"  - {table}")
        else:
            print("\n✗ Database is empty or cannot be accessed!")
    
    # Check main database for comparison
    print(f"\n{'=' * 80}")
    print("MAIN DATABASE (for comparison)")
    print(f"{'=' * 80}")
    main_db_name = settings.DATABASES['default']['NAME']
    tables = check_database_tables(main_db_name)
    employee_tables = [t for t in tables if 'employee' in t.lower()]
    
    if employee_tables:
        print("\nEmployee-related tables in MAIN database:")
        for table in employee_tables:
            print(f"  - {table}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
