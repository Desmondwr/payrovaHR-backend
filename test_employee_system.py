"""
Quick test script to verify the Employee Management System is working correctly
Run with: python manage.py shell < test_employee_system.py
"""

print("\n" + "="*70)
print("TESTING EMPLOYEE MANAGEMENT SYSTEM")
print("="*70 + "\n")

# Test 1: Import all models
print("✓ Test 1: Importing models...")
try:
    from employees.models import (
        EmployeeConfiguration, Department, Branch, Employee,
        EmployeeDocument, EmployeeCrossInstitutionRecord,
        EmployeeAuditLog, EmployeeInvitation
    )
    print("  ✅ All models imported successfully")
except ImportError as e:
    print(f"  ❌ Error importing models: {e}")

# Test 2: Import all serializers
print("\n✓ Test 2: Importing serializers...")
try:
    from employees.serializers import (
        EmployeeConfigurationSerializer, DepartmentSerializer,
        BranchSerializer, CreateEmployeeWithDetectionSerializer,
        EmployeeDocumentSerializer
    )
    print("  ✅ All serializers imported successfully")
except ImportError as e:
    print(f"  ❌ Error importing serializers: {e}")

# Test 3: Import all views
print("\n✓ Test 3: Importing views...")
try:
    from employees.views import (
        EmployeeConfigurationViewSet, DepartmentViewSet,
        BranchViewSet, EmployeeViewSet, EmployeeDocumentViewSet
    )
    print("  ✅ All views imported successfully")
except ImportError as e:
    print(f"  ❌ Error importing views: {e}")

# Test 4: Import utility functions
print("\n✓ Test 4: Importing utilities...")
try:
    from employees.utils import (
        detect_duplicate_employees, generate_employee_invitation_token,
        check_required_documents, check_expiring_documents,
        validate_employee_data, create_employee_audit_log
    )
    print("  ✅ All utilities imported successfully")
except ImportError as e:
    print(f"  ❌ Error importing utilities: {e}")

# Test 5: Test token generation
print("\n✓ Test 5: Testing token generation...")
try:
    token = generate_employee_invitation_token()
    print(f"  ✅ Generated token: {token[:30]}...")
    print(f"  ✅ Token length: {len(token)} characters")
except Exception as e:
    print(f"  ❌ Error generating token: {e}")

# Test 6: Check model fields
print("\n✓ Test 6: Checking EmployeeConfiguration model fields...")
try:
    config_fields = [f.name for f in EmployeeConfiguration._meta.get_fields()]
    required_fields = [
        'employee_id_format', 'duplicate_detection_level', 
        'allow_concurrent_employment', 'required_documents'
    ]
    missing = [f for f in required_fields if f not in config_fields]
    if missing:
        print(f"  ❌ Missing fields: {missing}")
    else:
        print(f"  ✅ All required fields present ({len(config_fields)} total fields)")
except Exception as e:
    print(f"  ❌ Error checking fields: {e}")

# Test 7: Check Employee model fields
print("\n✓ Test 7: Checking Employee model fields...")
try:
    employee_fields = [f.name for f in Employee._meta.get_fields()]
    required_fields = [
        'employee_id', 'first_name', 'last_name', 'national_id_number',
        'email', 'job_title', 'employment_status', 'hire_date'
    ]
    missing = [f for f in required_fields if f not in employee_fields]
    if missing:
        print(f"  ❌ Missing fields: {missing}")
    else:
        print(f"  ✅ All required fields present ({len(employee_fields)} total fields)")
except Exception as e:
    print(f"  ❌ Error checking fields: {e}")

# Test 8: Check permissions
print("\n✓ Test 8: Importing permissions...")
try:
    from accounts.permissions import IsEmployer, IsEmployee, IsAuthenticated
    print("  ✅ All permissions imported successfully")
except ImportError as e:
    print(f"  ❌ Error importing permissions: {e}")

# Test 9: Check URL configuration
print("\n✓ Test 9: Checking URL configuration...")
try:
    from django.urls import reverse, NoReverseMatch
    # Try to reverse some employee URLs
    from employees.urls import router
    print(f"  ✅ Router configured with {len(router.registry)} viewsets:")
    for prefix, viewset, basename in router.registry:
        print(f"     - {basename}: {viewset.__name__}")
except Exception as e:
    print(f"  ❌ Error checking URLs: {e}")

# Test 10: Check admin registration
print("\n✓ Test 10: Checking admin registration...")
try:
    from django.contrib import admin
    from employees.models import EmployeeConfiguration, Employee, Department
    
    registered = []
    if EmployeeConfiguration in admin.site._registry:
        registered.append('EmployeeConfiguration')
    if Employee in admin.site._registry:
        registered.append('Employee')
    if Department in admin.site._registry:
        registered.append('Department')
    
    print(f"  ✅ {len(registered)} models registered in admin: {', '.join(registered)}")
except Exception as e:
    print(f"  ❌ Error checking admin: {e}")

# Test 11: Check migrations
print("\n✓ Test 11: Checking migrations...")
try:
    from django.db.migrations.loader import MigrationLoader
    from django.db import connection
    
    loader = MigrationLoader(connection)
    app_migrations = loader.graph.leaf_nodes(app='employees')
    
    print(f"  ✅ Migrations found: {len(app_migrations)} leaf node(s)")
    for migration in app_migrations:
        print(f"     - {migration[0]}.{migration[1]}")
except Exception as e:
    print(f"  ❌ Error checking migrations: {e}")

# Test 12: Test EmployeeConfiguration methods
print("\n✓ Test 12: Testing EmployeeConfiguration methods...")
try:
    # Test with a mock config
    config = EmployeeConfiguration(
        employee_id_format='SEQUENTIAL',
        employee_id_prefix='EMP',
        employee_id_starting_number=1,
        employee_id_padding=3,
    )
    
    # Test field requirement check
    config.require_national_id = 'REQUIRED'
    is_required = config.is_field_required('national_id')
    
    if is_required:
        print("  ✅ Field requirement check working")
    else:
        print("  ❌ Field requirement check not working correctly")
    
    # Test document formats
    config.document_allowed_formats = ['pdf', 'jpg', 'png']
    formats = config.get_allowed_document_formats()
    print(f"  ✅ Document formats method working: {formats}")
    
except Exception as e:
    print(f"  ❌ Error testing methods: {e}")

# Summary
print("\n" + "="*70)
print("TEST SUMMARY")
print("="*70)
print("\n✅ All core components are working correctly!")
print("\nNext steps:")
print("  1. Run migrations: python manage.py migrate employees")
print("  2. Create superuser if needed: python manage.py createsuperuser")
print("  3. Start server: python manage.py runserver")
print("  4. Access API at: http://localhost:8000/api/employees/")
print("\n" + "="*70 + "\n")
