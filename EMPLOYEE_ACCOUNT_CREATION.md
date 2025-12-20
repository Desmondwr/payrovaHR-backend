# Employee Account Creation Guide

## Overview
This guide covers the two methods for creating employee accounts in the HR system:
1. **Method 1**: Employer creates employee account directly
2. **Method 2**: Employee self-registration (with employer approval)

Both methods integrate with the central Employee Registry for cross-institutional duplicate detection.

---

## Architecture Context

### Multi-Tenant Structure
- **Tenant Database**: Each employer has their own database containing their Employee records
- **Central Registry**: Default database contains EmployeeRegistry for cross-institutional tracking

### Cross-Institutional Tracking
- Every employee creation checks the central EmployeeRegistry for duplicates
- National ID number is required and must be unique across all institutions
- Duplicate detection prevents employees from being registered at multiple companies simultaneously

### Employee Data Flow
```
Employee Creation → Duplicate Detection (EmployeeRegistry) → Tenant Employee Record → Sync to EmployeeRegistry
```

---

## Method 1: Employer Creates Employee Account

### Overview
The employer directly creates an employee account with full profile information. This method includes automatic duplicate detection and sends an invitation email to the employee.

### Step 1: Create Employee with Detection

**Endpoint**: `POST /api/employees/create-with-detection/`

**Purpose**: Create a new employee account with automatic duplicate detection across all institutions.

**Authentication**: Required (Employer JWT token)

**Request Headers**:
```
Authorization: Bearer <employer_access_token>
Content-Type: application/json
```

**Request Body**:
```json
{
  "email": "john.doe@company.com",
  "first_name": "John",
  "last_name": "Doe",
  "middle_name": "Michael",
  "national_id_number": "NID123456789",
  "phone_number": "+1234567890",
  "date_of_birth": "1990-05-15",
  "gender": "Male",
  "marital_status": "Single",
  "address": "789 Employee Street, City, ST 12345",
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_phone": "+1234567891",
  "employment_type": "Full-time",
  "department": 1,
  "branch": 1,
  "position": "Software Engineer",
  "hire_date": "2024-01-15",
  "salary": "75000.00",
  "work_email": "j.doe@company.com"
}
```

**Required Fields**:
- `email`: Employee's personal email (used for login)
- `first_name`: First name
- `last_name`: Last name
- `national_id_number`: National ID/SSN (required for duplicate detection)
- `phone_number`: Contact phone number
- `date_of_birth`: Birth date (YYYY-MM-DD format)
- `gender`: Gender (e.g., "Male", "Female", "Other")
- `employment_type`: Employment type (e.g., "Full-time", "Part-time", "Contract")
- `department`: Department ID (must exist in tenant database)
- `position`: Job position/title
- `hire_date`: Date of hire (YYYY-MM-DD format)

**Optional Fields**:
- `middle_name`: Middle name
- `marital_status`: Marital status
- `address`: Residential address
- `emergency_contact_name`: Emergency contact name
- `emergency_contact_phone`: Emergency contact phone
- `branch`: Branch ID (if company has multiple branches)
- `salary`: Salary amount
- `work_email`: Company email address

**Success Response** (201 Created):
```json
{
  "message": "Employee created successfully. Invitation email sent.",
  "employee": {
    "id": 1,
    "user": {
      "id": 2,
      "email": "john.doe@company.com",
      "is_employee": true,
      "is_employer": false
    },
    "employee_id": "EMP001",
    "first_name": "John",
    "last_name": "Doe",
    "middle_name": "Michael",
    "national_id_number": "NID123456789",
    "phone_number": "+1234567890",
    "date_of_birth": "1990-05-15",
    "gender": "Male",
    "marital_status": "Single",
    "address": "789 Employee Street, City, ST 12345",
    "emergency_contact_name": "Jane Doe",
    "emergency_contact_phone": "+1234567891",
    "employment_type": "Full-time",
    "department": {
      "id": 1,
      "name": "Engineering"
    },
    "branch": {
      "id": 1,
      "name": "Main Office"
    },
    "position": "Software Engineer",
    "hire_date": "2024-01-15",
    "salary": "75000.00",
    "work_email": "j.doe@company.com",
    "is_active": true,
    "profile_completed": true,
    "created_at": "2024-01-20T10:30:00Z"
  },
  "duplicate_check": {
    "duplicates_found": false,
    "checked_institutions": 15,
    "message": "No duplicates found in central registry"
  },
  "registry_sync": {
    "synced": true,
    "registry_id": 1
  }
}
```

**What Happens Behind the Scenes**:
1. Validates all required fields including national_id_number
2. Queries EmployeeRegistry (central database) for duplicates by national_id or email
3. If duplicates found at other institutions → Returns error with institution details
4. If no duplicates → Creates User account with `is_employee=True`
5. Creates Employee record in tenant database
6. Syncs employee data to EmployeeRegistry in default database
7. Sends invitation email with login instructions
8. Returns employee details with duplicate check results

**Error Responses**:

**400 Bad Request** - Validation errors:
```json
{
  "national_id_number": ["This field is required."],
  "email": ["Enter a valid email address."],
  "date_of_birth": ["Date has wrong format. Use YYYY-MM-DD."],
  "department": ["Invalid pk \"999\" - object does not exist."]
}
```

**409 Conflict** - Duplicate detected in same institution:
```json
{
  "error": "Employee with this national ID already exists in your organization",
  "duplicate": {
    "employee_id": "EMP001",
    "name": "John Doe",
    "national_id": "NID123456789",
    "institution": "Tech Solutions Inc"
  }
}
```

**409 Conflict** - Duplicate detected at another institution:
```json
{
  "error": "Duplicate employee detected at another institution",
  "message": "This employee is already registered at another company",
  "duplicates": [
    {
      "name": "John Doe",
      "national_id": "NID123456789",
      "email": "john.doe@othercompany.com",
      "institution": "Other Company Inc",
      "registered_date": "2023-11-10T08:00:00Z"
    }
  ],
  "action_required": "Contact the other institution to verify employment status before proceeding"
}
```

**401 Unauthorized** - Invalid or missing token:
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**403 Forbidden** - Not an employer:
```json
{
  "error": "Only employers can create employee accounts"
}
```

---

### Step 2: Employee Receives Invitation

After account creation, the employee receives an invitation email with:
- Welcome message
- Login credentials (email)
- Instructions to set/reset password
- Link to complete profile (if any fields are missing)

---

### Step 3: Employee First Login

**Endpoint**: `POST /api/accounts/login/`

**Request Body**:
```json
{
  "email": "john.doe@company.com",
  "password": "TemporaryPassword123"
}
```

**Success Response** (200 OK):
```json
{
  "message": "Login successful",
  "user": {
    "id": 2,
    "email": "john.doe@company.com",
    "is_employee": true,
    "is_employer": false
  },
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "profile_completed": true,
  "requires_password_change": true
}
```

---

## Method 2: Employee Self-Registration

### Overview
Employee creates their own account and waits for employer approval. This method also includes duplicate detection to prevent registration at multiple institutions.

### Step 1: Employee Self-Registration

**Endpoint**: `POST /api/employees/self-register/`

**Purpose**: Employee creates their own account with basic information.

**Authentication**: Not required

**Request Headers**:
```
Content-Type: application/json
```

**Request Body**:
```json
{
  "email": "jane.smith@email.com",
  "password": "SecurePassword123!",
  "password_confirm": "SecurePassword123!",
  "first_name": "Jane",
  "last_name": "Smith",
  "middle_name": "Elizabeth",
  "national_id_number": "NID987654321",
  "phone_number": "+1234567892",
  "date_of_birth": "1992-08-22",
  "gender": "Female",
  "address": "456 Self Street, City, ST 54321",
  "employer_code": "TECHSOL123"
}
```

**Required Fields**:
- `email`: Personal email address
- `password`: Minimum 8 characters
- `password_confirm`: Must match password
- `first_name`: First name
- `last_name`: Last name
- `national_id_number`: National ID/SSN (required for duplicate detection)
- `phone_number`: Contact phone number
- `date_of_birth`: Birth date
- `gender`: Gender
- `employer_code`: Employer's unique registration code

**Optional Fields**:
- `middle_name`: Middle name
- `address`: Residential address

**Success Response** (201 Created):
```json
{
  "message": "Registration successful. Awaiting employer approval.",
  "employee": {
    "id": 2,
    "user": {
      "id": 3,
      "email": "jane.smith@email.com",
      "is_employee": true
    },
    "employee_id": "PENDING",
    "first_name": "Jane",
    "last_name": "Smith",
    "middle_name": "Elizabeth",
    "national_id_number": "NID987654321",
    "phone_number": "+1234567892",
    "date_of_birth": "1992-08-22",
    "gender": "Female",
    "address": "456 Self Street, City, ST 54321",
    "is_active": false,
    "approval_status": "pending",
    "profile_completed": false,
    "created_at": "2024-01-20T11:00:00Z"
  },
  "duplicate_check": {
    "duplicates_found": false,
    "checked_institutions": 15,
    "message": "No duplicates found in central registry"
  },
  "next_steps": [
    "Wait for employer approval",
    "Check email for approval notification",
    "Complete profile after approval"
  ]
}
```

**What Happens Behind the Scenes**:
1. Validates employer_code and finds matching employer
2. Checks EmployeeRegistry for duplicates (same as Method 1)
3. If duplicates found → Returns error with institution details
4. If no duplicates → Creates User account with `is_employee=True`
5. Creates Employee record with `is_active=False` and `approval_status='pending'`
6. Does NOT sync to EmployeeRegistry yet (waits for approval)
7. Sends notification email to employer for approval
8. Employee cannot login until approved

**Error Responses**:

**400 Bad Request** - Invalid employer code:
```json
{
  "employer_code": ["Invalid employer code. Please check with your employer."]
}
```

**409 Conflict** - Duplicate detected:
```json
{
  "error": "Duplicate employee detected",
  "message": "You are already registered at another institution",
  "duplicate": {
    "institution": "Other Company Inc",
    "registered_date": "2023-09-05T10:00:00Z"
  },
  "action": "Contact your current employer or system administrator"
}
```

**400 Bad Request** - Already registered:
```json
{
  "email": ["Employee with this email already exists."],
  "national_id_number": ["Employee with this national ID already registered."]
}
```

---

### Step 2: Employer Reviews Pending Registrations

**Endpoint**: `GET /api/employees/pending-approvals/`

**Purpose**: List all employees waiting for approval.

**Authentication**: Required (Employer JWT token)

**Request Headers**:
```
Authorization: Bearer <employer_access_token>
```

**Success Response** (200 OK):
```json
{
  "count": 2,
  "pending_employees": [
    {
      "id": 2,
      "first_name": "Jane",
      "last_name": "Smith",
      "email": "jane.smith@email.com",
      "national_id_number": "NID987654321",
      "phone_number": "+1234567892",
      "date_of_birth": "1992-08-22",
      "registered_at": "2024-01-20T11:00:00Z",
      "approval_status": "pending"
    },
    {
      "id": 3,
      "first_name": "Bob",
      "last_name": "Johnson",
      "email": "bob.j@email.com",
      "national_id_number": "NID456789123",
      "phone_number": "+1234567893",
      "date_of_birth": "1988-12-10",
      "registered_at": "2024-01-21T09:30:00Z",
      "approval_status": "pending"
    }
  ]
}
```

---

### Step 3: Employer Approves Employee

**Endpoint**: `POST /api/employees/{employee_id}/approve/`

**Purpose**: Approve a pending employee registration and assign employment details.

**Authentication**: Required (Employer JWT token)

**Request Headers**:
```
Authorization: Bearer <employer_access_token>
Content-Type: application/json
```

**Request Body**:
```json
{
  "employment_type": "Full-time",
  "department": 1,
  "branch": 1,
  "position": "HR Manager",
  "hire_date": "2024-01-22",
  "salary": "65000.00",
  "work_email": "jane.smith@company.com"
}
```

**Required Fields**:
- `employment_type`: Type of employment
- `department`: Department ID
- `position`: Job position
- `hire_date`: Start date

**Optional Fields**:
- `branch`: Branch ID
- `salary`: Salary amount
- `work_email`: Company email

**Success Response** (200 OK):
```json
{
  "message": "Employee approved successfully",
  "employee": {
    "id": 2,
    "employee_id": "EMP002",
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane.smith@email.com",
    "national_id_number": "NID987654321",
    "employment_type": "Full-time",
    "department": {
      "id": 1,
      "name": "Human Resources"
    },
    "branch": {
      "id": 1,
      "name": "Main Office"
    },
    "position": "HR Manager",
    "hire_date": "2024-01-22",
    "salary": "65000.00",
    "work_email": "jane.smith@company.com",
    "is_active": true,
    "approval_status": "approved",
    "approved_at": "2024-01-21T14:00:00Z"
  },
  "registry_sync": {
    "synced": true,
    "registry_id": 2
  }
}
```

**What Happens Behind the Scenes**:
1. Updates Employee record with employment details
2. Sets `is_active=True` and `approval_status='approved'`
3. Generates official employee_id (e.g., "EMP002")
4. Syncs employee data to EmployeeRegistry in default database
5. Sends approval email to employee with login instructions
6. Employee can now login

**Error Response**:

**404 Not Found**:
```json
{
  "error": "Employee not found or already approved"
}
```

---

### Step 4: Employer Rejects Employee (Optional)

**Endpoint**: `POST /api/employees/{employee_id}/reject/`

**Purpose**: Reject a pending employee registration.

**Request Body**:
```json
{
  "reason": "Invalid credentials provided"
}
```

**Success Response** (200 OK):
```json
{
  "message": "Employee registration rejected",
  "reason": "Invalid credentials provided"
}
```

---

### Step 5: Employee Login After Approval

**Endpoint**: `POST /api/accounts/login/`

**Request Body**:
```json
{
  "email": "jane.smith@email.com",
  "password": "SecurePassword123!"
}
```

**Success Response** (200 OK):
```json
{
  "message": "Login successful",
  "user": {
    "id": 3,
    "email": "jane.smith@email.com",
    "is_employee": true
  },
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "profile_completed": false,
  "requires_profile_completion": true
}
```

---

## Profile Completion (Both Methods)

After account creation and approval, employees may need to complete additional profile fields.

### Check Profile Completion Status

**Endpoint**: `GET /api/employees/profile/completion-status/`

**Authentication**: Required (Employee JWT token)

**Success Response** (200 OK):
```json
{
  "profile_completed": false,
  "completion_percentage": 75,
  "missing_fields": [
    "emergency_contact_name",
    "emergency_contact_phone",
    "marital_status"
  ],
  "required_fields_missing": [
    "emergency_contact_name",
    "emergency_contact_phone"
  ],
  "optional_fields_missing": [
    "marital_status"
  ]
}
```

---

### Complete Employee Profile

**Endpoint**: `PATCH /api/employees/profile/complete/`

**Purpose**: Update employee profile with missing information.

**Authentication**: Required (Employee JWT token)

**Request Headers**:
```
Authorization: Bearer <employee_access_token>
Content-Type: application/json
```

**Request Body** (only include fields to update):
```json
{
  "middle_name": "Elizabeth",
  "marital_status": "Married",
  "address": "789 Complete Avenue, City, ST 67890",
  "emergency_contact_name": "John Smith",
  "emergency_contact_phone": "+1234567894",
  "phone_number": "+1234567895"
}
```

**Success Response** (200 OK):
```json
{
  "message": "Profile updated successfully",
  "employee": {
    "id": 2,
    "employee_id": "EMP002",
    "first_name": "Jane",
    "last_name": "Smith",
    "middle_name": "Elizabeth",
    "national_id_number": "NID987654321",
    "phone_number": "+1234567895",
    "date_of_birth": "1992-08-22",
    "gender": "Female",
    "marital_status": "Married",
    "address": "789 Complete Avenue, City, ST 67890",
    "emergency_contact_name": "John Smith",
    "emergency_contact_phone": "+1234567894",
    "profile_completed": true,
    "updated_at": "2024-01-22T10:00:00Z"
  },
  "registry_sync": {
    "synced": true,
    "updated_fields": ["middle_name", "marital_status", "address", "emergency_contact_name", "emergency_contact_phone", "phone_number"]
  }
}
```

**What Happens Behind the Scenes**:
1. Updates Employee record in tenant database
2. Recalculates profile_completed status
3. Syncs updated data to EmployeeRegistry in default database
4. Returns updated employee profile

---

## Duplicate Detection Deep Dive

### How It Works

**Query Location**: EmployeeRegistry in default database (not tenant database)

**Detection Criteria**:
1. National ID number match
2. Email address match

**Detection Scope**:
- Checks across ALL institutions in the system
- Searches central EmployeeRegistry table

### Example Detection Scenario

**Scenario**: Employee tries to register at Company B while already employed at Company A

**Request to Company B**:
```json
{
  "email": "employee@email.com",
  "national_id_number": "NID123456789",
  ...
}
```

**System Process**:
1. Query EmployeeRegistry: `SELECT * FROM employee_registry WHERE national_id_number='NID123456789' OR email='employee@email.com'`
2. Find match in Company A's record
3. Verify employee is still active at Company A (check tenant database)
4. Return duplicate error with institution details

**Response**:
```json
{
  "error": "Duplicate employee detected at another institution",
  "duplicates": [
    {
      "institution": "Company A Inc",
      "name": "John Employee",
      "national_id": "NID123456789",
      "registered_date": "2023-06-15T09:00:00Z",
      "status": "active"
    }
  ],
  "action_required": "Contact Company A to verify employment status. Concurrent employment at multiple institutions requires special approval."
}
```

---

## Synchronization to Employee Registry

### When Sync Happens

**Method 1 (Employer Creates)**:
- Immediately after employee creation (if no duplicates)

**Method 2 (Self-Registration)**:
- After employer approval (not during initial registration)

**Profile Completion**:
- After any employee profile update

### What Gets Synced

From Employee (tenant DB) to EmployeeRegistry (default DB):
- User reference
- National ID number
- First name, last name, middle name
- Email
- Phone number
- Date of birth
- Gender
- Address
- Emergency contact details
- Marital status

### Sync Error Handling

If sync fails:
```json
{
  "warning": "Employee created successfully but registry sync failed",
  "employee": { ... },
  "sync_error": "Connection to central registry temporarily unavailable",
  "retry": true
}
```

System will automatically retry sync on next employee update.

---

## Example: Python Implementation

### Method 1: Employer Creates Employee

```python
import requests

BASE_URL = "http://localhost:8000/api"
employer_token = "eyJ0eXAiOiJKV1QiLCJhbGc..."  # From employer login

headers = {
    "Authorization": f"Bearer {employer_token}",
    "Content-Type": "application/json"
}

employee_data = {
    "email": "newemployee@company.com",
    "first_name": "Alice",
    "last_name": "Johnson",
    "national_id_number": "NID555444333",
    "phone_number": "+1234567896",
    "date_of_birth": "1995-03-20",
    "gender": "Female",
    "employment_type": "Full-time",
    "department": 1,
    "position": "Data Analyst",
    "hire_date": "2024-02-01",
    "salary": "70000.00"
}

response = requests.post(
    f"{BASE_URL}/employees/create-with-detection/",
    json=employee_data,
    headers=headers
)

if response.status_code == 201:
    data = response.json()
    print(f"Employee created: {data['employee']['employee_id']}")
    print(f"Duplicate check: {data['duplicate_check']['message']}")
    print(f"Registry synced: {data['registry_sync']['synced']}")
elif response.status_code == 409:
    error = response.json()
    print(f"Duplicate detected: {error['error']}")
    if 'duplicates' in error:
        for dup in error['duplicates']:
            print(f"  - Institution: {dup['institution']}")
            print(f"  - Name: {dup['name']}")
else:
    print("Error:", response.json())
```

### Method 2: Employee Self-Registration

```python
# Step 1: Employee registers
registration_data = {
    "email": "selfregister@email.com",
    "password": "SecurePass123!",
    "password_confirm": "SecurePass123!",
    "first_name": "Bob",
    "last_name": "Williams",
    "national_id_number": "NID777888999",
    "phone_number": "+1234567897",
    "date_of_birth": "1989-11-05",
    "gender": "Male",
    "address": "123 Self Street",
    "employer_code": "TECHSOL123"
}

response = requests.post(
    f"{BASE_URL}/employees/self-register/",
    json=registration_data
)

if response.status_code == 201:
    data = response.json()
    employee_id = data['employee']['id']
    print(f"Registration successful! Status: {data['employee']['approval_status']}")
    
    # Step 2: Employer approves (using employer token)
    approval_data = {
        "employment_type": "Part-time",
        "department": 2,
        "position": "Assistant",
        "hire_date": "2024-02-05"
    }
    
    approval_response = requests.post(
        f"{BASE_URL}/employees/{employee_id}/approve/",
        json=approval_data,
        headers=headers
    )
    
    if approval_response.status_code == 200:
        approved = approval_response.json()
        print(f"Employee approved: {approved['employee']['employee_id']}")
        print(f"Registry synced: {approved['registry_sync']['synced']}")
```

---

## Comparison: Method 1 vs Method 2

| Feature | Method 1 (Employer Creates) | Method 2 (Self-Registration) |
|---------|----------------------------|------------------------------|
| **Who initiates** | Employer | Employee |
| **Authentication required** | Yes (Employer) | No (Public endpoint) |
| **Duplicate check** | Yes, before creation | Yes, before creation |
| **Immediate activation** | Yes | No (requires approval) |
| **Registry sync timing** | Immediately | After approval |
| **Profile completeness** | Can be 100% from start | Usually requires completion |
| **Use case** | Bulk onboarding, HR-managed | Self-service, open applications |
| **Approval workflow** | None | Required |
| **Employee ID generation** | Immediate | After approval |

---

## Best Practices

### For Employers

1. **Use Method 1 for bulk onboarding**: More control and immediate activation
2. **Use Method 2 for open positions**: Let candidates apply, review, then approve
3. **Verify national IDs**: Ensure accuracy before creation to prevent duplicate issues
4. **Complete all fields**: Provide as much information as possible during creation
5. **Monitor pending approvals**: Regularly check and process self-registrations

### For Employees

1. **Provide accurate information**: Especially national ID and contact details
2. **Use personal email**: Don't use company email from previous employer
3. **Complete profile promptly**: Fill in all required fields after approval
4. **Keep credentials secure**: Store password safely

### Security Considerations

1. **National ID validation**: System requires unique national IDs across all institutions
2. **Duplicate prevention**: Cannot register at multiple companies simultaneously
3. **Approval workflow**: Method 2 includes employer verification
4. **Token security**: Always use HTTPS and secure token storage
5. **Data privacy**: Employee data is isolated in tenant databases

---

## Troubleshooting

### Common Issues

**1. "This field is required: national_id_number"**
- Solution: National ID is mandatory for all employee creations
- Ensures duplicate detection works properly

**2. "Duplicate employee detected at another institution"**
- Solution: Employee is already registered elsewhere
- Action: Verify employment status with the other institution
- May require termination or transfer process

**3. "Invalid employer code"**
- Solution: Verify the employer code with your HR department
- Code format is usually uppercase (e.g., "TECHSOL123")

**4. "Department does not exist"**
- Solution: Create departments first in the system
- Use valid department ID from your tenant database

**5. "Employee registration pending approval"**
- Solution: Wait for employer to approve (Method 2 only)
- Check email for approval notification

**6. "Profile completion required"**
- Solution: Use profile completion endpoint to add missing fields
- Check completion status endpoint to see what's missing

---

## Next Steps

After successful employee creation:
1. Employee logs in with provided credentials
2. Completes profile if necessary
3. Can access employee portal features:
   - View payslips
   - Request leave
   - Update personal information
   - Access company documents

---

## Support

For additional information:
- Employer account creation: EMPLOYER_ACCOUNT_CREATION.md
- API documentation: README_API.md
- Contact technical support for assistance
