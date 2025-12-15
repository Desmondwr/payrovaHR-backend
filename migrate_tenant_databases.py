"""
Utility script to migrate tenant databases
Run this after creating migrations or to fix databases that were created without tables

Usage:
    python migrate_tenant_databases.py                    # Migrate all tenant databases
    python migrate_tenant_databases.py --employer-id 1    # Migrate specific employer
    python migrate_tenant_databases.py --check-only       # Check status without migrating
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.management import call_command
from accounts.models import EmployerProfile
from accounts.database_utils import add_tenant_database_to_settings
from django.conf import settings
import argparse


def check_database_tables(db_alias):
    """Check if database has tables"""
    from django.db import connections
    
    try:
        with connections[db_alias].cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
            """)
            count = cursor.fetchone()[0]
            return count
    except Exception as e:
        print(f"Error checking tables in {db_alias}: {e}")
        return None


def migrate_tenant_database(employer_profile, check_only=False):
    """Migrate a single tenant database"""
    if not employer_profile.database_created or not employer_profile.database_name:
        print(f"❌ Employer '{employer_profile.company_name}' has no database created")
        return False
    
    db_name = employer_profile.database_name
    alias = f"tenant_{employer_profile.id}"
    
    print(f"\n{'='*60}")
    print(f"Employer: {employer_profile.company_name}")
    print(f"Database: {db_name}")
    print(f"Alias: {alias}")
    
    # Add database to settings if not already there
    if alias not in settings.DATABASES:
        add_tenant_database_to_settings(db_name, employer_profile.id)
        print(f"✓ Added database configuration to settings")
    
    # Check current tables
    table_count = check_database_tables(alias)
    if table_count is not None:
        print(f"Current tables: {table_count}")
        
        if table_count == 0:
            print("⚠️  Database is EMPTY - no tables found!")
        else:
            print(f"✓ Database has {table_count} tables")
    
    if check_only:
        print("Check-only mode - skipping migration")
        return True
    
    # Run migrations
    try:
        print(f"Running migrations on {db_name}...")
        call_command('migrate', database=alias, verbosity=2)
        
        # Check tables again
        new_table_count = check_database_tables(alias)
        if new_table_count is not None:
            print(f"\n✓ Migration complete! Tables: {table_count} → {new_table_count}")
        else:
            print(f"\n✓ Migration complete!")
        
        return True
    except Exception as e:
        print(f"❌ Error migrating {db_name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Migrate tenant databases')
    parser.add_argument('--employer-id', type=int, help='Migrate specific employer by ID')
    parser.add_argument('--check-only', action='store_true', help='Check status without migrating')
    args = parser.parse_args()
    
    print("=" * 60)
    print("TENANT DATABASE MIGRATION UTILITY")
    print("=" * 60)
    
    # Get employers
    if args.employer_id:
        employers = EmployerProfile.objects.filter(id=args.employer_id)
        if not employers.exists():
            print(f"❌ Employer with ID {args.employer_id} not found")
            return
    else:
        employers = EmployerProfile.objects.filter(database_created=True)
    
    total = employers.count()
    print(f"\nFound {total} employer(s) with databases\n")
    
    if total == 0:
        print("No tenant databases to migrate")
        return
    
    success_count = 0
    for employer in employers:
        if migrate_tenant_database(employer, check_only=args.check_only):
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {success_count}/{total} databases processed successfully")
    print("=" * 60)


if __name__ == '__main__':
    main()
