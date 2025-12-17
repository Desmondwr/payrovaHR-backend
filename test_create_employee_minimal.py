"""
Test script to verify CreateEmployeeWithDetectionSerializer accepts minimal fields
"""
import os
import django
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from employees.serializers import CreateEmployeeWithDetectionSerializer
from unittest.mock import Mock

# Test data - minimal fields provided by employer
test_data = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "branch": "1961a46b-3799-4144-8e4f-ac5e434bd69d",
    "department": "dffccfd0-9b45-47ae-8d54-703e1888e99c",
    "job_title": "Software Developer",
    "employment_type": "FULL_TIME",
    "hire_date": "2025-01-15"
}

print("=" * 80)
print("Testing CreateEmployeeWithDetectionSerializer with minimal fields")
print("=" * 80)
print("\nTest Data:")
print(json.dumps(test_data, indent=2))

# Create mock request with employer profile
mock_request = Mock()
mock_employer = Mock()
mock_employer.id = 1
mock_request.user.employer_profile = mock_employer

# Create serializer instance with mocked context
context = {'request': mock_request}
serializer = CreateEmployeeWithDetectionSerializer(data=test_data, context=context)

print("\n" + "=" * 80)
print("Initial Validation (Field-Level):")
print("=" * 80)

try:
    # Try to validate without calling the full validate method
    # This tests if fields themselves are properly marked as optional
    from rest_framework import serializers as drf_serializers
    
    # Get the serializer fields
    fields = serializer.fields
    required_fields = [name for name, field in fields.items() if field.required]
    optional_fields = [name for name, field in fields.items() if not field.required]
    
    print(f"\nRequired fields ({len(required_fields)}):")
    for field in sorted(required_fields):
        print(f"  - {field}")
    
    print(f"\nOptional fields ({len(optional_fields)}):")
    for field in sorted(optional_fields):
        print(f"  - {field}")
    
    # Check which fields from test_data are required but missing
    provided_fields = set(test_data.keys())
    required_field_set = set(required_fields)
    missing_required = required_field_set - provided_fields
    
    print(f"\nMissing required fields ({len(missing_required)}):")
    if missing_required:
        for field in sorted(missing_required):
            print(f"  - {field}")
    else:
        print("  None (All required fields are provided)")
    
    print("\n" + "=" * 80)
    print("Summary:")
    print("=" * 80)
    
    if not missing_required:
        print("✅ PASS: All required fields are provided")
        print("✅ PASS: Fields like gender, date_of_birth, address, cnps_number, etc. are now OPTIONAL")
        print("\n📝 Note: Full validation requires database access and will be tested via API endpoint")
    else:
        print("❌ FAIL: Some required fields are missing")
        
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("=" * 80)

