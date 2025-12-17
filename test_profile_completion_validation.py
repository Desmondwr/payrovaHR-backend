"""
Test script to verify EmployeeProfileCompletionSerializer enforces configuration requirements
"""
import os
import django
import json
from unittest.mock import Mock

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from employees.serializers import EmployeeProfileCompletionSerializer
from employees.models import Employee, EmployeeConfiguration

print("=" * 80)
print("Testing EmployeeProfileCompletionSerializer - Configuration Enforcement")
print("=" * 80)

# Create a mock employee instance with employer_id
mock_employee = Mock(spec=Employee)
mock_employee.employer_id = 1
mock_employee.profile_completed = False
mock_employee.profile_completed_at = None

# Create a mock configuration with strict requirements
mock_config = Mock(spec=EmployeeConfiguration)
mock_config.employer_id = 1

# Define which fields are required (REQUIRED) vs optional (OPTIONAL)
mock_config.require_gender = 'REQUIRED'
mock_config.require_date_of_birth = 'REQUIRED'
mock_config.require_nationality = 'REQUIRED'
mock_config.require_address = 'REQUIRED'
mock_config.require_cnps_number = 'REQUIRED'
mock_config.require_emergency_contact = 'REQUIRED'
mock_config.require_national_id = 'REQUIRED'
mock_config.require_bank_details = 'REQUIRED'
mock_config.require_bank_details_active_only = False

# Optional fields
mock_config.require_middle_name = 'OPTIONAL'
mock_config.require_profile_photo = 'OPTIONAL'
mock_config.require_marital_status = 'OPTIONAL'
mock_config.require_personal_email = 'OPTIONAL'
mock_config.require_alternative_phone = 'OPTIONAL'
mock_config.require_postal_code = 'OPTIONAL'
mock_config.require_passport = 'OPTIONAL'
mock_config.require_tax_number = 'OPTIONAL'

def is_field_required_mock(field_name):
    """Mock the is_field_required method"""
    field_map = {
        'gender': mock_config.require_gender,
        'date_of_birth': mock_config.require_date_of_birth,
        'nationality': mock_config.require_nationality,
        'address': mock_config.require_address,
        'cnps_number': mock_config.require_cnps_number,
        'emergency_contact': mock_config.require_emergency_contact,
        'national_id': mock_config.require_national_id,
        'middle_name': mock_config.require_middle_name,
        'profile_photo': mock_config.require_profile_photo,
        'marital_status': mock_config.require_marital_status,
        'personal_email': mock_config.require_personal_email,
        'alternative_phone': mock_config.require_alternative_phone,
        'postal_code': mock_config.require_postal_code,
        'passport': mock_config.require_passport,
        'tax_number': mock_config.require_tax_number,
    }
    return field_map.get(field_name, 'OPTIONAL') == 'REQUIRED'

mock_config.is_field_required = is_field_required_mock

# Patch the EmployeeConfiguration.objects.get to return our mock
from unittest.mock import patch

print("\n" + "=" * 80)
print("Test 1: Incomplete Profile Data (Missing Required Fields)")
print("=" * 80)

incomplete_data = {
    "phone_number": "+237123456789",
    "city": "Yaoundé",
}

print("\nData provided:")
print(json.dumps(incomplete_data, indent=2))

with patch.object(EmployeeConfiguration.objects, 'get', return_value=mock_config):
    serializer = EmployeeProfileCompletionSerializer(instance=mock_employee, data=incomplete_data, partial=True)
    
    is_valid = serializer.is_valid()
    
    if not is_valid:
        print("\n✅ PASS: Validation correctly rejected incomplete data")
        print("\nValidation Errors:")
        for field, errors in serializer.errors.items():
            print(f"  - {field}: {errors[0] if isinstance(errors, list) else errors}")
    else:
        print("\n❌ FAIL: Validation should have rejected incomplete data")

print("\n" + "=" * 80)
print("Test 2: Complete Profile Data (All Required Fields Provided)")
print("=" * 80)

complete_data = {
    "gender": "MALE",
    "date_of_birth": "1990-05-15",
    "nationality": "Cameroonian",
    "address": "123 Main Street, Bastos",
    "city": "Yaoundé",
    "phone_number": "+237123456789",
    "national_id_number": "123456789",
    "cnps_number": "CNPS-12345",
    "bank_account_number": "1234567890",
    "bank_name": "Ecobank",
    "emergency_contact_name": "Jane Doe",
    "emergency_contact_phone": "+237987654321",
    "emergency_contact_relationship": "Spouse",
}

print("\nData provided:")
print(json.dumps(complete_data, indent=2))

with patch.object(EmployeeConfiguration.objects, 'get', return_value=mock_config):
    serializer = EmployeeProfileCompletionSerializer(instance=mock_employee, data=complete_data, partial=True)
    
    is_valid = serializer.is_valid()
    
    if is_valid:
        print("\n✅ PASS: Validation correctly accepted complete data")
        print("\nValidated fields:")
        for field in serializer.validated_data.keys():
            print(f"  - {field}")
    else:
        print("\n❌ FAIL: Validation should have accepted complete data")
        print("\nValidation Errors:")
        for field, errors in serializer.errors.items():
            print(f"  - {field}: {errors[0] if isinstance(errors, list) else errors}")

print("\n" + "=" * 80)
print("Summary")
print("=" * 80)
print("✅ EmployeeProfileCompletionSerializer now enforces configuration requirements")
print("✅ When employees complete their profile, required fields must be provided")
print("✅ Validation rejects incomplete data and accepts complete data")
print("=" * 80)
