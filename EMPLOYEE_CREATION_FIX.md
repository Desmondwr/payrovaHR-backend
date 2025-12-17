# Employee Creation Fix - December 17, 2025

## Problem
When an employer tried to create an employee with minimal fields:

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "branch": "1961a46b-3799-4144-8e4f-ac5e434bd69d",
  "department": "dffccfd0-9b45-47ae-8d54-703e1888e99c",
  "job_title": "Software Developer",
  "employment_type": "FULL_TIME",
  "hire_date": "2025-01-15"
}
```

They received validation errors requiring many fields that should be optional:
- gender
- date_of_birth
- address
- cnps_number
- emergency_contact_name
- emergency_contact_phone
- national_id_number
- nationality

## Root Cause
The `CreateEmployeeWithDetectionSerializer` was enforcing field requirements from the `EmployeeConfiguration` model during employer-initiated employee creation. This was incorrect because:

1. The configuration requirements should apply when **employees complete their own profiles**, not when employers create initial employee records
2. Employers should only need to provide minimal fields to create an employee record
3. The employee can then complete their full profile later

## Solution

### Changes Made

#### 1. Updated `CreateEmployeeWithDetectionSerializer` in [employees/serializers.py](employees/serializers.py)

**Removed strict validation** (Line ~633):
```python
# BEFORE
if config:
    validation_result = validate_employee_data(data, config)
    if not validation_result['valid']:
        raise serializers.ValidationError(validation_result['errors'])

# AFTER
# Skip strict validation during employer-initiated creation
# The configuration requirements apply when employees complete their own profiles,
# not when employers are creating initial employee records
# Employers only need to provide minimal fields: first_name, last_name, email, job_title, etc.
```

**Added extra_kwargs to make fields optional** (Line ~558):
```python
extra_kwargs = {
    # Make most fields optional - employers provide minimal data, employees complete their profiles
    'employee_id': {'required': False},
    'middle_name': {'required': False},
    'date_of_birth': {'required': False},
    'gender': {'required': False},
    'marital_status': {'required': False},
    'nationality': {'required': False},
    'profile_photo': {'required': False},
    'personal_email': {'required': False},
    'phone_number': {'required': False},
    'alternative_phone': {'required': False},
    'address': {'required': False},
    'city': {'required': False},
    'state_region': {'required': False},
    'postal_code': {'required': False},
    'country': {'required': False},
    'national_id_number': {'required': False},
    'passport_number': {'required': False},
    'cnps_number': {'required': False},
    'tax_number': {'required': False},
    'job_title': {'required': False},
    'employment_type': {'required': False},
    'employment_status': {'required': False},
    'hire_date': {'required': False},
    'probation_end_date': {'required': False},
    'bank_name': {'required': False},
    'bank_account_number': {'required': False},
    'bank_account_name': {'required': False},
    'emergency_contact_name': {'required': False},
    'emergency_contact_relationship': {'required': False},
    'emergency_contact_phone': {'required': False},
}
```

### Result

After the fix, the serializer now:

**Required Fields (Only 3):**
- ✅ `first_name`
- ✅ `last_name`
- ✅ `email`

**Optional Fields (37):**
All other fields including the ones that were causing errors:
- ✅ `gender` (now optional)
- ✅ `date_of_birth` (now optional)
- ✅ `address` (now optional)
- ✅ `cnps_number` (now optional)
- ✅ `emergency_contact_name` (now optional)
- ✅ `emergency_contact_phone` (now optional)
- ✅ `national_id_number` (now optional)
- ✅ `nationality` (now optional)
- And 29 more fields...

## Testing

Created test script [test_create_employee_minimal.py](test_create_employee_minimal.py) which confirms:
- ✅ Only 3 fields are required (first_name, last_name, email)
- ✅ All 37 other fields are optional
- ✅ Employers can create employees with minimal information

## Next Steps

When you test the API endpoint again with the same JSON payload, it should now:
1. ✅ Accept the employee creation request
2. ✅ Create the employee with only the provided fields
3. ✅ Return success response
4. ✅ Allow the employee to complete their profile later

## Notes

- The `EmployeeConfiguration` validation is still in place but only applies when employees complete their own profiles
- Duplicate detection is still active and will warn/block based on configuration
- All business logic for auto-generating employee IDs, work emails, etc. remains intact
