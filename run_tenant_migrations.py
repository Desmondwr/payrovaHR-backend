"""
Script to manually run migrations on tenant databases
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.management import call_command
from django.db import connections
from accounts.models import EmployerProfile
from accounts.database_utils import add_tenant_database_to_settings

def run_tenant_migrations():
    """Run migrations on all tenant databases"""
    employers = EmployerProfile.objects.filter(database_created=True)
    
    if not employers.exists():
        print("No tenant databases found!")
        return
    
    print("=" * 80)
    print("RUNNING MIGRATIONS ON TENANT DATABASES")
    print("=" * 80)
    
    for employer in employers:
        print(f"\n{'=' * 80}")
        print(f"Employer: {employer.company_name}")
        print(f"Database: {employer.database_name}")
        print(f"{'=' * 80}\n")
        
        # Ensure database is in settings
        add_tenant_database_to_settings(employer.database_name, employer.id)
        alias = f"tenant_{employer.id}"
        
        try:
            # Run migrations for employees app
            print(f"Running migrations for 'employees' app on {alias}...")
            call_command('migrate', 'employees', database=alias, verbosity=2)
            print(f"\n✓ Successfully migrated 'employees' app")
            
        except Exception as e:
            print(f"\n✗ Error running migrations: {e}")
    
    print("\n" + "=" * 80)
    print("MIGRATION COMPLETE")
    print("=" * 80)
    print("\nRun check_tenant_db.py to verify the tables were created.")

if __name__ == "__main__":
    run_tenant_migrations()
