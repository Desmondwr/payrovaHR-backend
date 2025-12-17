# Profile Completion Validation - December 17, 2025

## Overview
This update implements different validation rules for two different scenarios:
1. **Employer creating employee** - Minimal fields required
2. **Employee completing profile** - Configuration requirements enforced

## Changes Made

### 1. CreateEmployeeWithDetectionSerializer (Employer Creation)
**File:** [employees/serializers.py](employees/serializers.py) (Lines 495-650)

**Purpose:** Used when employers create new employee records

**Validation:** 
- ✅ **Minimal requirements only**
- ✅ Only 3 fields required: `first_name`, `last_name`, `email`
- ✅ All other 37 fields are optional
- ✅ Configuration validation is SKIPPED

**Required Fields:**
```python
- first_name ✓
- last_name ✓
- email ✓
```

**Optional Fields (37):**
```python
- gender, date_of_birth, address, cnps_number
- emergency_contact_name, emergency_contact_phone
- national_id_number, nationality
- And 29 more...
```

### 2. EmployeeProfileCompletionSerializer (Employee Profile Completion)
**File:** [employees/serializers.py](employees/serializers.py) (Lines 872-930)

**Purpose:** Used when employees complete their own profile after accepting invitation

**Validation:**
- ✅ **Configuration requirements ARE enforced**
- ✅ Validates against `EmployeeConfiguration` model
- ✅ Required fields based on employer's configuration settings
- ✅ Rejects incomplete data with specific error messages

**Example Validation (Based on Configuration):**

If employer has configured these as REQUIRED:
```python
{
  "require_gender": "REQUIRED",
  "require_date_of_birth": "REQUIRED",
  "require_nationality": "REQUIRED",
  "require_address": "REQUIRED",
  "require_cnps_number": "REQUIRED",
  "require_emergency_contact": "REQUIRED",
  "require_national_id": "REQUIRED",
  "require_bank_details": "REQUIRED"
}
```

Then employee MUST provide:
- ✓ gender
- ✓ date_of_birth
- ✓ nationality
- ✓ address
- ✓ national_id_number
- ✓ cnps_number
- ✓ bank_account_number
- ✓ emergency_contact_name
- ✓ emergency_contact_phone

## API Endpoints

### Employer Creates Employee (Minimal Requirements)
```
POST /api/employees/
Authorization: Bearer <employer_token>

{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "branch": "uuid-here",
  "department": "uuid-here",
  "job_title": "Software Developer",
  "employment_type": "FULL_TIME",
  "hire_date": "2025-01-15"
}
```
✅ **Response:** Success - Employee created with minimal data

### Employee Completes Profile (Configuration Enforced)
```
PUT/PATCH /api/employees/profile/complete-profile/
Authorization: Bearer <employee_token>

{
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
  "emergency_contact_relationship": "Spouse"
}
```

**If missing required fields:**
```json
{
  "success": false,
  "errors": {
    "gender": ["Gender is required"],
    "date_of_birth": ["Date Of Birth is required"],
    "nationality": ["Nationality is required"],
    "address": ["Address is required"],
    "national_id_number": ["National Id Number is required"],
    "cnps_number": ["Cnps Number is required"],
    "bank_account_number": ["Bank account is required"],
    "emergency_contact_name": ["Emergency contact name is required"],
    "emergency_contact_phone": ["Emergency contact phone is required"]
  }
}
```

**If all required fields provided:**
```json
{
  "success": true,
  "message": "Profile updated successfully",
  "profile": {
    "id": "...",
    "first_name": "John",
    "last_name": "Doe",
    "profile_completed": true,
    "profile_completed_at": "2025-12-17T10:30:00Z",
    ...
  }
}
```

## Validation Logic

### validate_employee_data() Function
**File:** [employees/utils.py](employees/utils.py) (Lines 244-305)

This function checks the `EmployeeConfiguration` model and validates data accordingly:

```python
def validate_employee_data(data, config):
    """
    Validate employee data against configuration requirements
    Returns: {'valid': bool, 'errors': dict}
    """
    errors = {}
    
    # Check each field against configuration
    if config.is_field_required('gender'):
        if not data.get('gender'):
            errors['gender'] = "Gender is required"
    
    if config.is_field_required('date_of_birth'):
        if not data.get('date_of_birth'):
            errors['date_of_birth'] = "Date Of Birth is required"
    
    # ... similar checks for all configurable fields
    
    return {'valid': len(errors) == 0, 'errors': errors}
```

## Configuration Model (EmployeeConfiguration)

**File:** [employees/models.py](employees/models.py) (Lines 12-280)

Each employer can configure which fields are:
- **REQUIRED** - Must be provided
- **OPTIONAL** - Can be provided but not required
- **HIDDEN** - Not shown in forms

Example configuration fields:
```python
require_gender = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
require_date_of_birth = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
require_nationality = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
require_address = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
require_cnps_number = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
require_national_id = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
require_emergency_contact = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
require_bank_details = CharField(choices=FIELD_REQUIREMENT_CHOICES, default='REQUIRED')
```

## Testing

### Test 1: Employer Creates Employee with Minimal Data
**File:** [test_create_employee_minimal.py](test_create_employee_minimal.py)

```bash
python test_create_employee_minimal.py
```

**Result:**
```
✅ PASS: All required fields are provided
✅ PASS: Fields like gender, date_of_birth, address, cnps_number, etc. are now OPTIONAL
```

### Test 2: Employee Completes Profile with Configuration Enforcement
**File:** [test_profile_completion_validation.py](test_profile_completion_validation.py)

```bash
python test_profile_completion_validation.py
```

**Result:**
```
✅ PASS: Validation correctly rejected incomplete data
✅ PASS: Validation correctly accepted complete data
✅ EmployeeProfileCompletionSerializer now enforces configuration requirements
```

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. EMPLOYER CREATES EMPLOYEE                                    │
│    POST /api/employees/                                         │
│    ✓ Only first_name, last_name, email required                │
│    ✓ Configuration validation SKIPPED                          │
│    ✓ Employee record created with minimal data                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         v
┌─────────────────────────────────────────────────────────────────┐
│ 2. EMPLOYEE RECEIVES INVITATION                                 │
│    ✓ Email sent with activation link                           │
│    ✓ Employee clicks link and creates account                  │
│    ✓ Login successful with profile_completed = false           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         v
┌─────────────────────────────────────────────────────────────────┐
│ 3. EMPLOYEE COMPLETES PROFILE                                   │
│    PUT/PATCH /api/employees/profile/complete-profile/          │
│    ✓ Configuration validation ENFORCED                         │
│    ✓ Required fields MUST be provided                          │
│    ✓ Validation errors if fields missing                       │
│    ✓ Profile marked as completed when all required fields set  │
└─────────────────────────────────────────────────────────────────┘
```

## Benefits

1. **Flexible Onboarding** - Employers can quickly create employee records without gathering all information upfront
2. **Data Completeness** - Employees must complete required information based on employer's requirements
3. **Compliance** - Each employer can enforce their own data requirements (e.g., CNPS mandatory in Cameroon)
4. **Better UX** - Employees see exactly what's required to complete their profile
5. **Audit Trail** - System tracks when profile is completed (`profile_completed_at`)

## Summary

✅ **Employer creates employee:** Only first_name, last_name, email required  
✅ **Employee completes profile:** All configured requirements enforced  
✅ **Different validation rules** for different use cases  
✅ **Configuration-driven** - Each employer controls their requirements  
✅ **Fully tested** with automated test scripts  
