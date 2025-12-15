# Employer Employee Management - Quick API Reference

## Authentication
All endpoints require authentication. Include JWT token in header:
```
Authorization: Bearer <your-jwt-token>
```

## Base URL
```
/api/employees/
```

---

## Quick Start Workflow

### Step 1: Configure Employee Settings (First Time Only)
```http
GET /api/employees/configuration/
```
This will auto-create default configuration. Update as needed:
```http
PATCH /api/employees/configuration/
Content-Type: application/json

{
  "employee_id_format": "YEAR_BASED",
  "employee_id_prefix": "EMP",
  "duplicate_detection_level": "MODERATE",
  "duplicate_action": "WARN",
  "required_documents": ["RESUME", "ID_COPY"]
}
```

### Step 2: Create Departments (Optional but Recommended)
```http
POST /api/employees/departments/
Content-Type: application/json

{
  "name": "Human Resources",
  "code": "HR",
  "description": "HR Department"
}
```

### Step 3: Create Branches (Optional)
```http
POST /api/employees/branches/
Content-Type: application/json

{
  "name": "Headquarters",
  "code": "HQ",
  "address": "123 Main Street",
  "city": "Yaoundé",
  "state_region": "Centre",
  "country": "Cameroon",
  "is_headquarters": true
}
```

### Step 4: Create Employee
```http
POST /api/employees/employees/
Content-Type: application/json

{
  "first_name": "John",
  "last_name": "Doe",
  "date_of_birth": "1990-05-15",
  "gender": "MALE",
  "nationality": "Cameroonian",
  "email": "john.doe@company.com",
  "phone_number": "+237670000000",
  "national_id_number": "123456789",
  "address": "123 Street",
  "city": "Yaoundé",
  "state_region": "Centre",
  "country": "Cameroon",
  "job_title": "Software Engineer",
  "department": "dept-uuid",
  "employment_type": "FULL_TIME",
  "employment_status": "ACTIVE",
  "hire_date": "2025-01-15",
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_relationship": "Spouse",
  "emergency_contact_phone": "+237670000001",
  "send_invitation": true
}
```

**Response includes:**
- Employee details
- Duplicate warning (if any matches found)
- Generated employee ID

### Step 5: Employee Accepts Invitation
```http
POST /api/employees/invitations/accept/
Content-Type: application/json

{
  "token": "invitation-token-from-email",
  "password": "newpassword123",
  "password_confirm": "newpassword123"
}
```

---

## Common Operations

### List All Employees
```http
GET /api/employees/employees/
```

**With Filters:**
```http
GET /api/employees/employees/?status=ACTIVE
GET /api/employees/employees/?department=uuid
GET /api/employees/employees/?branch=uuid
GET /api/employees/employees/?search=john
```

### Get Employee Details
```http
GET /api/employees/employees/{employee-uuid}/
```

### Update Employee
```http
PATCH /api/employees/employees/{employee-uuid}/
Content-Type: application/json

{
  "job_title": "Senior Software Engineer",
  "email": "john.doe@newdomain.com"
}
```

### Send/Resend Invitation
```http
POST /api/employees/employees/{employee-uuid}/send_invitation/
```

### Terminate Employee
```http
POST /api/employees/employees/{employee-uuid}/terminate/
Content-Type: application/json

{
  "termination_date": "2025-12-31",
  "termination_reason": "Resignation - Better opportunity"
}
```

### Reactivate Employee
```http
POST /api/employees/employees/{employee-uuid}/reactivate/
```

### Check for Duplicates
```http
POST /api/employees/employees/detect_duplicates/
Content-Type: application/json

{
  "national_id_number": "123456789",
  "email": "test@example.com",
  "phone_number": "+237670000000"
}
```

---

## Document Management

### Get Employee Documents
```http
GET /api/employees/employees/{employee-uuid}/documents/
```

**Response includes:**
- List of documents
- Missing required documents
- Expiring documents count

### Upload Document
```http
POST /api/employees/documents/
Content-Type: multipart/form-data

{
  "employee": "employee-uuid",
  "document_type": "RESUME",
  "title": "John Doe Resume",
  "description": "Latest resume",
  "file": <file>,
  "has_expiry": false
}
```

**With Expiry:**
```http
POST /api/employees/documents/
Content-Type: multipart/form-data

{
  "employee": "employee-uuid",
  "document_type": "ID_COPY",
  "title": "National ID",
  "file": <file>,
  "has_expiry": true,
  "expiry_date": "2030-12-31"
}
```

### Verify Document (HR Only)
```http
POST /api/employees/documents/{document-uuid}/verify/
```

### Get Expiring Documents
```http
GET /api/employees/documents/expiring_soon/?days=30
```

---

## Cross-Institution Information

### Get Cross-Institution Records
```http
GET /api/employees/employees/{employee-uuid}/cross_institutions/
```

**Response:**
```json
{
  "has_other_institutions": true,
  "count": 2,
  "records": [
    {
      "employer_id": "uuid",
      "company_name": "Other Company",
      "employee_id": "OC-001",
      "status": "ACTIVE",
      "consent_status": "APPROVED"
    }
  ]
}
```

---

## Audit Log

### Get Employee Audit Log
```http
GET /api/employees/employees/{employee-uuid}/audit_log/
```

**Returns last 50 audit entries:**
```json
[
  {
    "id": "uuid",
    "action": "CREATED",
    "performed_by": "employer@example.com",
    "timestamp": "2025-01-15T10:30:00Z",
    "changes": {...},
    "notes": "Employee created",
    "ip_address": "192.168.1.1"
  }
]
```

---

## Configuration Options

### Employee ID Formats
- **SEQUENTIAL**: EMP-001, EMP-002, EMP-003
- **YEAR_BASED**: EMP-2025-001, EMP-2025-002
- **BRANCH_BASED**: YAO-001, DLA-001 (uses branch code)
- **DEPT_BASED**: HR-001, IT-001 (uses dept code)
- **CUSTOM**: Define your own template

### Field Requirements
Set each field as:
- **REQUIRED**: Must be provided
- **OPTIONAL**: Can be empty
- **HIDDEN**: Not displayed

Fields configurable:
- Basic: middle_name, profile_photo, gender, date_of_birth, marital_status, nationality
- Contact: personal_email, alternative_phone, address, postal_code
- Legal: national_id, passport, cnps_number, tax_number
- Employment: department, branch, manager, probation_period
- Payroll: bank_details
- Other: emergency_contact

### Duplicate Detection Levels
- **STRICT**: Only exact national ID match
- **MODERATE**: Match on ID, email, or phone
- **LENIENT**: Fuzzy name + DOB matching

### Duplicate Actions
- **BLOCK**: Prevent creation
- **WARN**: Show warning, allow creation
- **ALLOW**: Allow with required reason

---

## Response Formats

### Success Response
```json
{
  "id": "uuid",
  "employee_id": "EMP-2025-001",
  "first_name": "John",
  "last_name": "Doe",
  "full_name": "John Doe",
  ...
}
```

### Duplicate Warning
```json
{
  "id": "uuid",
  ...,
  "duplicate_warning": {
    "message": "Employee created successfully, but 2 potential duplicate(s) detected",
    "duplicates_found": true,
    "total_matches": 2,
    "same_institution": 0,
    "cross_institution": 2
  }
}
```

### Error Response
```json
{
  "field_name": [
    "Error message here"
  ]
}
```

### Validation Error
```json
{
  "duplicate_detected": "Duplicate employee detected. Found 1 matching records. 1 in your institution."
}
```

---

## Employment Statuses
- **ACTIVE**: Currently employed
- **PROBATION**: In probation period
- **SUSPENDED**: Temporarily suspended
- **TERMINATED**: Employment ended
- **RESIGNED**: Employee resigned
- **RETIRED**: Employee retired

## Employment Types
- **FULL_TIME**: Full-time employee
- **PART_TIME**: Part-time employee
- **CONTRACT**: Contract worker
- **TEMPORARY**: Temporary position
- **INTERN**: Internship
- **CONSULTANT**: Consultant/contractor

## Document Types
- **RESUME**: Resume/CV
- **ID_COPY**: ID card copy
- **PASSPORT_COPY**: Passport copy
- **CERTIFICATE**: Educational certificate
- **CONTRACT**: Employment contract
- **OFFER_LETTER**: Job offer letter
- **TERMINATION_LETTER**: Termination document
- **RECOMMENDATION**: Recommendation letter
- **MEDICAL**: Medical certificate
- **POLICE_CLEARANCE**: Police clearance certificate
- **OTHER**: Other documents

---

## Tips & Best Practices

1. **Always configure your institution settings first** before creating employees
2. **Use duplicate detection** before creating employees to avoid duplicates
3. **Set up departments and branches** for better organization
4. **Send invitations** to allow employees to manage their own profiles
5. **Upload required documents** as configured in your settings
6. **Track document expiry** for compliance
7. **Review audit logs** regularly for security
8. **Use filters** when listing employees for better performance
9. **Check cross-institution records** for concurrent employment tracking
10. **Configure probation periods** and reminders appropriately

---

## Common Issues & Solutions

### Issue: Employee ID not auto-generated
**Solution**: Check that `employee_id` is not included in the request, and configuration is properly set up.

### Issue: Duplicate detection not working
**Solution**: Ensure `EmployeeConfiguration` exists and `duplicate_check_*` fields are enabled.

### Issue: Invitation email not sent
**Solution**: Check email configuration in Django settings and ensure `send_invitation_email` is enabled in configuration.

### Issue: Document upload fails
**Solution**: Check file size against `document_max_file_size_mb` and format against `document_allowed_formats`.

### Issue: Cannot terminate employee
**Solution**: Verify `termination_approval_required` setting and that user has appropriate permissions.

---

## Testing Endpoints

You can test all endpoints using:
- **Postman**: Import the Postman collection
- **Insomnia**: Import the Insomnia collection
- **cURL**: Use command line
- **Python requests**: Programmatic access

Example using cURL:
```bash
curl -X GET \
  http://localhost:8000/api/employees/employees/ \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

---

For detailed documentation, see `EMPLOYER_EMPLOYEE_MANAGEMENT_GUIDE.md`
