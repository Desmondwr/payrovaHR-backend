"""
Check employer users and their database status
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User, EmployerProfile

print("=" * 60)
print("Checking Employer Users and Database Status")
print("=" * 60)

users = User.objects.filter(is_employer=True)
print(f"\nTotal employer users: {users.count()}")

for u in users:
    print(f"\nUser ID: {u.id}")
    print(f"  Email: {u.email}")
    
    try:
        if hasattr(u, 'employer_profile') and u.employer_profile:
            emp = u.employer_profile
            print(f"  Has Profile: Yes")
            print(f"  Company: {emp.company_name}")
            print(f"  Profile ID: {emp.id}")
            print(f"  Database Created: {emp.database_created}")
            print(f"  Database Name: {emp.database_name}")
        else:
            print(f"  Has Profile: No")
    except Exception as e:
        print(f"  Error checking profile: {e}")

print("\n" + "=" * 60)
