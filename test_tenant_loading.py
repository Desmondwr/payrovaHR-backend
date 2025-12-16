"""
Test script to verify tenant database loading
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from accounts.models import EmployerProfile
from accounts.database_utils import load_all_tenant_databases, ensure_tenant_database_loaded

def test_tenant_loading():
    print("=" * 60)
    print("Testing Tenant Database Loading")
    print("=" * 60)
    
    # Show current databases
    print("\n1. Databases before loading:")
    print(f"   - Configured databases: {list(settings.DATABASES.keys())}")
    
    # Load tenant databases
    print("\n2. Loading tenant databases...")
    count = load_all_tenant_databases()
    print(f"   - Loaded {count} tenant database(s)")
    
    # Show databases after loading
    print("\n3. Databases after loading:")
    print(f"   - Configured databases: {list(settings.DATABASES.keys())}")
    
    # Test individual employer
    print("\n4. Testing individual employer loading:")
    try:
        employer = EmployerProfile.objects.filter(database_created=True).first()
        if employer:
            print(f"   - Employer: {employer.company_name} (ID: {employer.id})")
            print(f"   - Database name: {employer.database_name}")
            
            # Ensure loaded
            alias = ensure_tenant_database_loaded(employer)
            print(f"   - Database alias: {alias}")
            print(f"   - Alias exists in settings: {alias in settings.DATABASES}")
        else:
            print("   - No employer with database found")
    except Exception as e:
        print(f"   - Error: {e}")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == '__main__':
    test_tenant_loading()
