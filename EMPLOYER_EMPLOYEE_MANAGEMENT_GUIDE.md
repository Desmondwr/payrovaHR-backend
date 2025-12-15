# Employer Employee Management System Documentation

## Overview

This comprehensive employee management system allows employers to create, manage, and invite employees to their institution. It includes advanced features like duplicate detection, cross-institution employment tracking, configurable employee ID generation, document management, and much more.

## Key Features Implemented

### 1. **Employee Configuration System** (`EmployeeConfiguration` Model)
A highly configurable system that allows each institution to customize how employee management works for their organization.

#### Employee ID Format Configuration
- **Sequential Format**: EMP-001, EMP-002, etc.
- **Year-Based**: EMP-2025-001
- **Branch-Based**: YAO-001 (Yaoundé), DLA-001 (Douala)
- **Department-Based**: HR-001, IT-001
- **Custom Template**: Fully customizable with placeholders

**Configuration Options:**
- Prefix and suffix
- Starting number
- Padding (number of digits)
- Include branch/department/year codes
- Manual override capability

#### Field Requirement Configuration
Employers can configure which fields are:
- **Required**: Must be filled
- **Optional**: Can be left empty
- **Hidden**: Not shown in forms

Configurable fields include:
- Basic Info: middle_name, profile_photo, gender, date_of_birth, marital_status, nationality
- Contact: personal_email, alternative_phone, address, postal_code
- Legal: national_id, passport, cnps_number, tax_number
- Employment: department, branch, manager, probation_period
- Payroll: bank_details (with option to require only for active employees)
- Emergency contact information

#### Cross-Institution Employment Rules
- **Allow Concurrent Employment**: Control if employees can work in multiple institutions
- **Employee Consent Required**: Require employee consent before linking to another institution
- **Visibility Levels**:
  - None: No visibility of other institutions
  - Basic: Institution name only
  - Moderate: Institution name and employment dates
  - Full: Full employment details

#### Duplicate Detection Rules
**Detection Levels:**
- **Strict**: Exact national ID match only
- **Moderate**: National ID, email, or phone matching
- **Lenient**: Fuzzy name + date of birth matching

**Action on Duplicate:**
- **Block**: Prevent creation completely
- **Warn**: Show warning but allow creation
- **Allow with Reason**: Allow but require reason

**Criteria Checked:**
- National ID number
- Email address
- Phone number
- Name + Date of birth combination (fuzzy matching)

#### Document Management Configuration
- **Required Documents**: List of required document types
- **Expiry Tracking**: Enable/disable document expiration tracking
- **Reminder Days**: Days before expiry to send reminder
- **File Size Limit**: Maximum file size in MB
- **Allowed Formats**: List of permitted file formats (pdf, jpg, png, docx, etc.)

#### Termination Workflow Configuration
- **Require Reason**: Make termination reason mandatory
- **Approval Required**: Require approval before termination
- **Approval By**: Manager, HR, Both, or Admin
- **Access Revocation Timing**:
  - Immediate
  - On termination date
  - Custom delay (specify days)
- **Data Retention**: Months to retain terminated employee data
- **Allow Reactivation**: Enable/disable employee reactivation

#### Notification Settings
- **Send Invitation Email**: Automatically send invitation emails
- **Invitation Expiry**: Days until invitation expires
- **Welcome Email**: Send email when employee accepts invitation
- **Profile Completion Reminder**: Remind employees to complete profile
- **Reminder Timing**: Days after invitation to send reminder

#### Probation Configuration
- **Default Period**: Default probation period in months
- **Review Required**: Require probation review before confirmation
- **Reminder Days**: Days before probation ends to send reminder

#### System Settings
- **Auto-Generate Work Email**: Automatically create work emails
- **Email Template**: Template for work email generation (e.g., {firstname}.{lastname}@{domain})

---

### 2. **Enhanced Employee Model**
Comprehensive employee profile with all necessary sections:

#### Basic Information
- Employee ID (auto-generated or manual)
- First, middle, last name
- Date of birth
- Gender
- Marital status
- Nationality
- Profile photo

#### Contact Information
- Work email
- Personal email
- Primary phone
- Alternative phone
- Full address (address, city, state/region, postal code, country)

#### Legal Identification
- National ID number (indexed for fast searching)
- Passport number
- CNPS number (social security)
- Tax number

#### Employment Details
- Job title
- Department (with hierarchical structure)
- Branch/Location
- Direct manager
- Employment type (Full-time, Part-time, Contract, etc.)
- Employment status (Active, Probation, Terminated, etc.)
- Hire date
- Probation end date
- Termination date and reason

#### Payroll Information
- Bank name
- Bank account number
- Bank account holder name

#### Emergency Contact
- Contact name
- Relationship
- Phone number

#### System Access
- Linked user account
- Invitation status
- Concurrent employment flag

---

### 3. **Employee Invitation System** (`EmployeeInvitation` Model)

When an employer creates an employee, they can optionally send an invitation:

**Invitation Flow:**
1. Employer creates employee record
2. System generates secure invitation token
3. Invitation email sent with link
4. Employee clicks link and accepts invitation
5. Employee creates account or links existing account
6. System links user account to employee record

**Invitation Features:**
- Secure token generation (URL-safe)
- Configurable expiry period
- Status tracking (Pending, Accepted, Expired, Revoked)
- Email templates (HTML and plain text)
- Automatic account linkage on acceptance

---

### 4. **Cross-Institution Detection & Linking**

**Automatic Detection:**
When creating an employee, the system automatically searches for:
- Existing employees with same national ID
- Same email address
- Same phone number
- Similar name + date of birth combination

**Detection Results Include:**
- Same institution matches
- Cross-institution matches (employees in other companies)
- Match reasons (why each was flagged)
- Employment status in other institutions

**Handling Options:**
1. **Block Creation**: Prevent duplicate if policy requires
2. **Warn User**: Show warning but allow creation
3. **Link to Institution**: Create new employment contract under current institution
4. **Request Employee Consent**: Send notification to employee for approval

**Cross-Institution Record** (`EmployeeCrossInstitutionRecord`):
- Tracks employee presence in multiple institutions
- Consent status (Pending, Approved, Rejected, Not Required)
- Verification status
- Audit trail with timestamps

---

### 5. **Document Management** (`EmployeeDocument` Model)

**Document Types Supported:**
- Resume/CV
- ID Copy
- Passport Copy
- Certificates/Diplomas
- Employment Contracts
- Offer Letters
- Termination Letters
- Recommendation Letters
- Medical Certificates
- Police Clearance
- Other custom types

**Document Features:**
- File upload with size validation
- Format validation (configurable)
- Expiry date tracking
- Expiry reminders
- Document verification by HR
- Upload history tracking

**Document Checks:**
- Required documents checklist
- Missing documents report
- Expiring soon alerts
- Expired documents list

---

### 6. **Audit Logging** (`EmployeeAuditLog` Model)

Complete audit trail for all employee actions:
- Employee created
- Profile updated
- Terminated
- Deleted
- Invitation sent
- Account linked
- Cross-institution detected

**Audit Log Includes:**
- Action type
- Performer (who made the change)
- Timestamp
- Changes made (JSON format)
- Notes
- IP address

---

### 7. **Department & Branch Management**

**Department Model:**
- Hierarchical structure (parent-child relationships)
- Department codes
- Active/inactive status
- Employee count tracking

**Branch Model:**
- Branch code
- Full address information
- Headquarters designation
- Contact information
- Employee count tracking

---

## API Endpoints

### Employee Configuration
- `GET /api/employees/configuration/` - Get current configuration
- `POST /api/employees/configuration/` - Create/Update configuration
- `PATCH /api/employees/configuration/` - Partial update
- `POST /api/employees/configuration/reset_to_defaults/` - Reset to defaults

### Department Management
- `GET /api/employees/departments/` - List all departments
- `POST /api/employees/departments/` - Create department
- `GET /api/employees/departments/{id}/` - Get department details
- `PATCH /api/employees/departments/{id}/` - Update department
- `DELETE /api/employees/departments/{id}/` - Delete department

### Branch Management
- `GET /api/employees/branches/` - List all branches
- `POST /api/employees/branches/` - Create branch
- `GET /api/employees/branches/{id}/` - Get branch details
- `PATCH /api/employees/branches/{id}/` - Update branch
- `DELETE /api/employees/branches/{id}/` - Delete branch

### Employee Management
- `GET /api/employees/employees/` - List employees (with filters)
- `POST /api/employees/employees/` - Create new employee
- `GET /api/employees/employees/{id}/` - Get employee details
- `PATCH /api/employees/employees/{id}/` - Update employee
- `DELETE /api/employees/employees/{id}/` - Delete employee
- `POST /api/employees/employees/{id}/send_invitation/` - Send/resend invitation
- `POST /api/employees/employees/{id}/terminate/` - Terminate employee
- `POST /api/employees/employees/{id}/reactivate/` - Reactivate terminated employee
- `GET /api/employees/employees/{id}/documents/` - Get employee documents
- `GET /api/employees/employees/{id}/cross_institutions/` - Get cross-institution info
- `GET /api/employees/employees/{id}/audit_log/` - Get audit log
- `POST /api/employees/employees/detect_duplicates/` - Detect duplicate employees

#### Query Parameters for Employee List:
- `?status=ACTIVE` - Filter by employment status
- `?department={department_id}` - Filter by department
- `?branch={branch_id}` - Filter by branch
- `?search={query}` - Search by name, email, or employee ID

### Document Management
- `GET /api/employees/documents/` - List documents
- `POST /api/employees/documents/` - Upload document
- `GET /api/employees/documents/{id}/` - Get document
- `DELETE /api/employees/documents/{id}/` - Delete document
- `POST /api/employees/documents/{id}/verify/` - Verify document
- `GET /api/employees/documents/expiring_soon/?days=30` - Get expiring documents

### Invitation Management
- `GET /api/employees/invitations/` - List invitations
- `GET /api/employees/invitations/{id}/` - Get invitation details
- `POST /api/employees/invitations/accept/` - Accept invitation (public endpoint)

---

## Utility Functions

Located in `employees/utils.py`:

### `detect_duplicate_employees()`
Searches for potential duplicate employees based on configuration settings.

**Parameters:**
- employer, national_id, email, phone, first_name, last_name, date_of_birth, config

**Returns:**
- duplicates_found (bool)
- same_institution_matches (list)
- cross_institution_matches (list)
- match_reasons (dict)

### `generate_employee_invitation_token()`
Generates secure URL-safe token for invitations.

### `send_employee_invitation_email()`
Sends invitation email using configured templates.

### `check_required_documents()`
Checks if employee has uploaded all required documents.

**Returns:**
- required (list)
- uploaded (list)
- missing (list)
- all_uploaded (bool)

### `check_expiring_documents()`
Checks for documents expiring soon or already expired.

**Returns:**
- expiring_soon (list)
- expired (list)
- expiring_count (int)
- expired_count (int)

### `validate_employee_data()`
Validates employee data against configuration requirements.

**Returns:**
- valid (bool)
- errors (dict)

### `create_employee_audit_log()`
Creates audit log entry for employee actions.

### `get_cross_institution_summary()`
Gets summary of employee's presence in other institutions with appropriate visibility level.

---

## Email Templates

### Employee Invitation Email
Located in `templates/emails/employee_invitation.html` and `.txt`

**Includes:**
- Company branding
- Employee details (ID, position, department, branch, start date)
- Invitation link with expiry
- Welcome message
- Instructions

---

## Permissions

Custom permissions in `accounts/permissions.py`:

- **IsAuthenticated**: User must be authenticated
- **IsEmployer**: User must be an employer with profile
- **IsEmployee**: User must be an employee
- **IsAdmin**: User must be a system admin
- **IsOwnerOrAdmin**: User must own the resource or be admin

---

## Usage Examples

### 1. Create Employee with Auto-Generated ID

```json
POST /api/employees/employees/
{
  "first_name": "John",
  "last_name": "Doe",
  "date_of_birth": "1990-05-15",
  "gender": "MALE",
  "nationality": "Cameroonian",
  "email": "john.doe@company.com",
  "phone_number": "+237670000000",
  "national_id_number": "123456789",
  "address": "123 Main St",
  "city": "Yaoundé",
  "state_region": "Centre",
  "country": "Cameroon",
  "job_title": "Software Engineer",
  "department": "dept-uuid-here",
  "employment_type": "FULL_TIME",
  "hire_date": "2025-01-15",
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_relationship": "Spouse",
  "emergency_contact_phone": "+237670000001",
  "send_invitation": true
}
```

### 2. Check for Duplicates Before Creating

```json
POST /api/employees/employees/detect_duplicates/
{
  "national_id_number": "123456789",
  "email": "john.doe@company.com",
  "phone_number": "+237670000000"
}
```

### 3. Configure Employee Management

```json
PATCH /api/employees/configuration/
{
  "employee_id_format": "YEAR_BASED",
  "employee_id_prefix": "EMP",
  "employee_id_starting_number": 1,
  "duplicate_detection_level": "MODERATE",
  "duplicate_action": "WARN",
  "allow_concurrent_employment": true,
  "required_documents": ["RESUME", "ID_COPY", "CERTIFICATE"],
  "document_max_file_size_mb": 10,
  "document_allowed_formats": ["pdf", "jpg", "png", "docx"]
}
```

### 4. Accept Employee Invitation

```json
POST /api/employees/invitations/accept/
{
  "token": "invitation-token-here",
  "password": "securepassword123",
  "password_confirm": "securepassword123"
}
```

---

## Database Schema

All models use UUID primary keys for security. Key indexes created for:
- Employee national_id_number
- Employee email
- Employer + employment_status combination

---

## Next Steps

1. **Run Migrations**: `python manage.py migrate employees`
2. **Create Employee Configuration**: Through admin or API
3. **Set Up Departments and Branches**: Before adding employees
4. **Configure Email Settings**: In Django settings for invitation emails
5. **Test Employee Creation Flow**: Create test employee with invitation

---

## Notes

- All employee data respects the institution's configuration
- Cross-institution detection works across all employers in the system
- Audit logs are automatically created for all major actions
- Document expiry tracking requires scheduled tasks (implement with Celery)
- Email sending requires proper SMTP or email service configuration

---

## Security Features

1. **Secure Invitation Tokens**: URL-safe tokens using secrets module
2. **Permission-Based Access**: All endpoints protected with appropriate permissions
3. **Audit Trail**: Complete logging of all actions
4. **IP Address Tracking**: Records IP for audit purposes
5. **Data Validation**: Comprehensive validation before saving
6. **File Upload Security**: Size and format validation

---

This system provides a complete, production-ready employee management solution for multi-institution HR systems with advanced features for duplicate detection, cross-institution employment tracking, and highly configurable workflows.
