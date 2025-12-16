# Employee Creation - Frontend Integration Guide

This guide provides step-by-step instructions for frontend developers on how to implement the employee creation feature and what happens on the backend when an employer creates an employee.

## Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [API Endpoint](#api-endpoint)
- [Request Format](#request-format)
- [Response Format](#response-format)
- [Step-by-Step Process Flow](#step-by-step-process-flow)
- [Error Handling](#error-handling)
- [Advanced Features](#advanced-features)
- [Example Code](#example-code)

---

## Overview

When an employer creates an employee in the system, the following occurs:

### Phase 1: Employer Initiates Employee Creation
1. **Authentication verification** - Ensures employer is logged in with JWT token
2. **Basic data validation** - Validates minimal required fields (first_name, last_name, email, job_title, employment_type, hire_date)
3. **Duplicate detection** - Checks for potential duplicate employees (optional)
4. **Employee ID generation** - Auto-generates employee ID if not provided (e.g., EMP-001)
5. **Database record creation** - Creates employee record in employer's tenant database
6. **Invitation sent automatically** - Email invitation sent to employee (send_invitation defaults to true)
7. **Audit logging** - Logs the creation action with timestamp and performer

### Phase 2: Employee Accepts Invitation
1. **Employee receives invitation email** - Contains link with unique token
2. **Employee accepts invitation** - Submits token + password to `/api/employees/invitations/accept/`
3. **Backend creates User account** - User created in main database with `is_employee=true`
4. **Backend links User to Employee** - Sets `employee.user_id` in tenant database
5. **Invitation marked accepted** - Status updated with timestamp

### Phase 3: Employee Completes Profile
1. **Employee logs in** - Uses email and password, receives JWT token
2. **Login response includes profile status** - `employee_profile_completed: false`
3. **Frontend redirects to profile completion** - Based on profile status
4. **Employee views current profile** - GET `/api/employees/profile/me/`
5. **Employee fills remaining fields** - Personal info, contact details, emergency contact, banking
6. **Employee submits profile** - PATCH `/api/employees/profile/complete-profile/`
7. **Backend marks profile complete** - Sets `profile_completed=true`, `profile_completed_at=now()`
8. **Future logins skip redirect** - Profile shows as completed

---

## Prerequisites

### Authentication
- User must be authenticated with a valid JWT token
- User must have `IsEmployer` permission
- Token must be included in request header: `Authorization: Bearer <token>`

### Required User State
- User must have an active `employer_profile`
- Employer's tenant database must be created and accessible

---

## API Endpoint

### Create Employee

```
POST /api/employees/employees/
```

**Base URL**: `http://your-backend-domain.com/api/employees/`

**Headers Required**:
```json
{
  "Authorization": "Bearer <your_jwt_token>",
  "Content-Type": "application/json"
}
```

---

## Request Format

### Minimal Required Payload (Employer Initial Creation)

The absolute minimum fields required for employer to initiate employee creation:

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "job_title": "Software Developer",
  "employment_type": "FULL_TIME",
  "hire_date": "2025-01-15",
  "department": 1,  // Department ID (optional but recommended)
  "branch": 2       // Branch ID (optional but recommended)
  // send_invitation defaults to true automatically
}
```

**Note**: 
- Most fields are now optional during initial creation (date_of_birth, phone_number, address, national_id, etc.)
- The employee will complete these fields themselves after accepting the invitation and logging in
- `send_invitation` defaults to `true` - invitations are sent automatically unless explicitly set to `false`
- **Required fields**: first_name, last_name, email, job_title, employment_type, hire_date
- **Recommended fields**: department, branch (helps organize employees from the start)

### Complete Payload (All Available Fields)

```json
{
  // ===== BASIC INFORMATION =====
  "employee_id": "EMP-001",  // Optional - Auto-generated if not provided
  "first_name": "John",      // Required
  "last_name": "Doe",        // Required
  "middle_name": "Michael",  // Optional (depends on config)
  "date_of_birth": "1990-05-15",  // Required (depends on config)
  "gender": "MALE",          // Required (depends on config) - MALE, FEMALE, OTHER
  "marital_status": "SINGLE", // Optional (depends on config) - SINGLE, MARRIED, DIVORCED, WIDOWED
  "nationality": "Cameroonian", // Required (depends on config)
  "profile_photo": null,     // Optional - Can be a file upload URL
  
  // ===== CONTACT INFORMATION =====
  "email": "john.doe@company.com",  // Required - Work email
  "personal_email": "john@gmail.com", // Optional
  "phone_number": "+237123456789",    // Required
  "alternative_phone": "+237987654321", // Optional
  "address": "123 Main Street",       // Required (depends on config)
  "city": "Douala",                   // Optional
  "state_region": "Littoral",         // Optional
  "postal_code": "1234",              // Optional
  "country": "Cameroon",              // Optional
  
  // ===== LEGAL IDENTIFICATION =====
  "national_id_number": "123456789",  // Required (depends on config)
  "passport_number": "A12345678",     // Optional
  "cnps_number": "CNP123456789",      // Required (depends on config) - Social Security Number
  "tax_number": "TAX123456",          // Optional
  
  // ===== EMPLOYMENT DETAILS =====
  "job_title": "Software Developer",  // Required
  "department": 1,                    // Optional - Department ID (integer)
  "branch": 2,                        // Optional - Branch ID (integer)
  "manager": 5,                       // Optional - Manager's Employee ID (integer)
  "employment_type": "FULL_TIME",     // Required - FULL_TIME, PART_TIME, CONTRACT, INTERN, TEMPORARY
  "employment_status": "ACTIVE",      // Required - ACTIVE, INACTIVE, ON_LEAVE, TERMINATED, PROBATION
  "hire_date": "2025-01-15",          // Required - Format: YYYY-MM-DD
  "probation_end_date": "2025-04-15", // Optional - Format: YYYY-MM-DD
  
  // ===== PAYROLL INFORMATION =====
  "bank_name": "Bank of Africa",      // Optional (depends on config)
  "bank_account_number": "1234567890", // Optional (depends on config)
  "bank_account_name": "John Doe",    // Optional (depends on config)
  
  // ===== EMERGENCY CONTACT =====
  "emergency_contact_name": "Jane Doe",      // Required (depends on config)
  "emergency_contact_relationship": "Spouse", // Required (depends on config)
  "emergency_contact_phone": "+237999888777", // Required (depends on config)
  
  // ===== ADDITIONALtrue,            // Optional - Boolean: Send invitation email (default: true)
  "force_create": false,              // Optional - Boolean: Bypass duplicate warnings
  "link_existing_user": null,         // Optional - UUID: Link to existing user account
  "acknowledge_cross_institution": false  // Optional - Boolean: Acknowledge concurrent employment
}

**Recommended Workflow**: 
- Employer provides minimal information (name, email, job_title, hire_date, department, branch)
- `send_invitation` defaults to `true` - email sent automatically
- Employee receives email, accepts invitation, logs in
- Employee completes remaining profile fields themselves

  "acknowledge_cross_institution": false  // Optional - Boolean: Acknowledge concurrent employment
}
```

### Field Value Options

**Gender Values:**
- `"MALE"`
- `"FEMALE"`
- `"OTHER"`

**Marital Status Values:**
- `"SINGLE"`
- `"MARRIED"`
- `"DIVORCED"`
- `"WIDOWED"`

**Employment Type Values:**
- `"FULL_TIME"` - Full-time employee
- `"PART_TIME"` - Part-time employee
- `"CONTRACT"` - Contract worker
- `"INTERN"` - Intern
- `"TEMPORARY"` - Temporary worker

**Employment Status Values:**
- `"ACTIVE"` - Currently working
- `"INACTIVE"` - Not currently active
- `"ON_LEAVE"` - On leave
- `"TERMINATED"` - Employment terminated
- `"PROBATION"` - On probation period

---

## Response Format

### Success Response (201 CREATED)

When employee is created successfully:

```json
{
  "id": 1,
  "employee_id": "EMP-001",
  "first_name": "John",
  "last_name": "Doe",
  "middle_name": "Michael",
  "full_name": "John Michael Doe",
  "email": "john.doe@company.com",
  "personal_email": "john@gmail.com",
  "phone_number": "+237123456789",
  "alternative_phone": "+237987654321",
  "date_of_birth": "1990-05-15",
  "gender": "MALE",
  "marital_status": "SINGLE",
  "nationality": "Cameroonian",
  "profile_photo": null,
  
  "address": "123 Main Street",
  "city": "Douala",
  "state_region": "Littoral",
  "postal_code": "1234",
  "country": "Cameroon",
  
  "national_id_number": "123456789",
  "passport_number": "A12345678",
  "cnps_number": "CNP123456789",
  "tax_number": "TAX123456",
  
  "job_title": "Software Developer",
  "department": 1,
  "department_name": "IT Department",
  "branch": 2,
  "branch_name": "Douala Branch",
  "manager": 5,
  "manager_name": "Jane Smith",
  "employment_type": "FULL_TIME",
  "employment_status": "ACTIVE",
  "hire_date": "2025-01-15",
  "probation_end_date": "2025-04-15",
  
  "bank_name": "Bank of Africa",
  "bank_account_number": "1234567890",
  "bank_account_name": "John Doe",
  
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_relationship": "Spouse",
  "emergency_contact_phone": "+237999888777",
  
  "employer": 10,
  "user": null,
  "has_user_account": false,
  "invitation_sent": true,
  "invitation_sent_at": "2025-12-16T10:30:00Z",
  "invitation_accepted_at": null,
  "is_concurrent_employment": false,
  "cross_institution_count": 0,
  
  "profile_completed": false,
  "profile_completed_at": null,
  
  "created_at": "2025-12-16T10:30:00Z",
  "updated_at": "2025-12-16T10:30:00Z"
}
```

### Success with Duplicate Warning (201 CREATED)

When duplicates are detected but creation is allowed:

```json
{
  "id": 1,
  "employee_id": "EMP-001",
  "first_name": "John",
  // ... all employee fields ...
  
  "duplicate_warning": {
    "message": "Employee created successfully, but 2 potential duplicate(s) detected",
    "duplicates_found": true,
    "total_matches": 2,
    "same_institution": 1,
    "cross_institution": 1
  }
}
```

---

## Step-by-Step Process Flow

### What Happens on the Backend

#### Step 1: Request Reception & Authentication
```
Frontend sends POST request → Backend receives request
                           → Validates JWT token
                           → Checks user is employer
                           → Retrieves employer_profile
```

#### Step 2: Data Validation
```
Backend receives payload → Retrieves organization configuration
                        → Validates required fields
                        → Checks field-level validation
                        → Validates unique constraints (email, employee_id)
```

**Validations Performed:**
- Email is unique within the organization
- Employee ID is unique (if provided)
- Date formats are correct (YYYY-MM-DD)
- Required fields based on configuration
- Valid foreign keys (department, branch, manager exist)
- Phone number format validation
- National ID uniqueness (if configured)

#### Step 3: Duplicate Detection
```
If duplicate detection enabled → Check for matching employees
                               → Check same institution
                               → Check cross-institution
                               → Evaluate duplicate action (BLOCK/WARN/ALLOW)
```

**Duplicate Matching Criteria:**
- National ID number (exact match)
- Email address (exact match)
- Phone number (exact match)
- Name + Date of Birth combination (fuzzy match - if enabled)

**Duplicate Actions:**
- **BLOCK**: Returns 400 error, prevents creation
- **WARN**: Creates employee but includes warning in response
- **ALLOW**: Creates employee without warning

#### Step 4: Employee ID Generation
```
If employee_id not provided → Retrieve configuration
                           → Generate ID based on format
                           → Apply organization rules
                           → Ensure uniqueness
```

**ID Generation Formats:**
- **SEQUENTIAL**: `EMP-001`, `EMP-002`, `EMP-003`
- **YEAR_BASED**: `EMP-2025-001`, `EMP-2025-002`
- **BRANCH_BASED**: `DLA-001` (Douala), `YAO-001` (Yaoundé)
- **DEPT_BASED**: `HR-001`, `IT-001`, `FIN-001`
- **CUSTOM**: Custom template like `{prefix}-{year}-{branch}-{number}`

#### Step 5: Database Record Creation
```
Create employee record → Save to tenant database
                      → Set employer_id (from logged-in user)
                      → Set created_by_id (from logged-in user)
                      → Set timestamps (created_at, updated_at)
```

#### Step 6: Invitation Process (if send_invitation=true)
```
If send_invitation enabled → Generate invitation token
                          → Set expiry date (based on config)
                          → Create EmployeeInvitation record
                          → Send invitation email
                          → Update employee.invitation_sent = true
                          → Set employee.invitation_sent_at timestamp
```

**Invitation Email Contains:**
- Personalized greeting
- Organization name
- Invitation link with token (format: `/employee/accept-invitation/{token}`)
- Expiry date/time
- Instructions for accepting

**What Happens When Employee Accepts Invitation:**
1. Employee clicks invitation link → Redirected to acceptance page
2. Employee enters password (and confirms) → Submits to `/api/employees/invitations/accept/`
3. Backend creates User account in **main database** (with email and password)
4. Backend links `user_id` to employee record in **tenant database**
5. Employee can now log in and access their employee portal
6. Invitation status updated to "ACCEPTED"

#### Step 7: Audit Logging
```
Create audit log entry → Record action: "EMPLOYEE_CREATED"
                      → Record performer (employer user)
                      → Record timestamp
                      → Record IP address
                      → Store changes/notes
```

#### Step 8: Response Generation
```
Serialize employee data → Include related data (department, branch, manager)
                       → Add duplicate warnings (if any)
                       → Add computed fields
                       → Return 201 CREATED response
```

### Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend: Submit Employee Creation Form                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Authenticate Request                               │
│  - Verify JWT Token                                          │
│  - Check IsEmployer Permission                               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Load Configuration                                 │
│  - Get EmployeeConfiguration for employer                    │
│  - Determine required fields                                 │
│  - Get duplicate detection settings                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Validate Input Data                                │
│  - Check all required fields present                         │
│  - Validate field formats                                    │
│  - Check unique constraints                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Detect Duplicates                                  │
│  - Search by National ID                                     │
│  - Search by Email                                           │
│  - Search by Phone                                           │
│  - Check cross-institution                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────┴────────────┐
         │  Duplicates Found?      │
         └───────────┬────────────┘
                     │
         ┌───────────┴────────────┐
         │                        │
    YES  │                        │  NO
         │                        │
         ▼                        ▼
┌────────────────────┐   ┌────────────────────┐
│ Check Action Type  │   │ Continue Creation  │
└────────┬───────────┘   └────────┬───────────┘
         │                        │
    ┌────┴────┐                   │
    │         │                   │
  BLOCK     WARN                  │
    │         │                   │
    ▼         ▼                   │
┌───────┐ ┌───────┐              │
│Return │ │Store  │              │
│Error  │ │Warning│              │
│400    │ └───┬───┘              │
└───────┘     │                  │
              └──────────┬───────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Generate Employee ID (if not provided)             │
│  - Apply format rules                                        │
│  - Ensure uniqueness                                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Create Employee Record                             │
│  - Save to tenant database                                   │
│  - Set employer_id and created_by_id                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────┴────────────┐
         │  Send Invitation?       │
         └───────────┬────────────┘
                     │
         ┌───────────┴────────────┐
         │                        │
    YES  │                        │  NO
         │                        │
         ▼                        ▼
┌────────────────────┐   ┌────────────────────┐
│ Create Invitation  │   │ Skip Invitation    │
│ - Generate Token   │   └────────┬───────────┘
│ - Send Email       │            │
│ - Update Flags     │            │
└────────┬───────────┘            │
         │                        │
         └────────────┬───────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Create Audit Log                                   │
│  - Record action: EMPLOYEE_CREATED                           │
│  - Store metadata                                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Prepare Response                                   │
│  - Serialize employee data                                   │
│  - Include duplicate warnings (if any)                       │
│  - Add related data                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Return 201 CREATED                                 │
│  - Employee object + metadata                                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend: Handle Response                                   │
│  - Show success message                                      │
│  - Display duplicate warnings (if any)                       │
│  - Redirect to employee list/detail                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Error Handling

### Common Error Responses

#### 1. Authentication Error (401 UNAUTHORIZED)
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**Frontend Action**: Redirect to login page

---

#### 2. Permission Error (403 FORBIDDEN)
```json
{
  "detail": "You do not have permission to perform this action."
}
```

**Frontend Action**: Show error message "You must be an employer to create employees"

---

#### 3. Validation Error (400 BAD REQUEST)

**Missing Required Fields:**
```json
{
  "first_name": ["This field is required."],
  "last_name": ["This field is required."],
  "email": ["This field is required."]
}
```

**Invalid Field Format:**
```json
{
  "email": ["Enter a valid email address."],
  "date_of_birth": ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]
}
```

**Frontend Action**: Display field-specific errors next to form inputs

---

#### 4. Duplicate Employee ID (400 BAD REQUEST)
```json
{
  "error": "Duplicate Employee ID",
  "detail": "An employee with this Employee ID already exists in your organization. Please use a different Employee ID or leave it empty for auto-generation.",
  "field": "employee_id"
}
```

**Frontend Action**: 
- Highlight employee_id field
- Show error message
- Suggest removing field for auto-generation

---

#### 5. Duplicate Email (400 BAD REQUEST)
```json
{
  "error": "Duplicate Email",
  "detail": "An employee with this email address already exists in your organization. Please use a different email address.",
  "field": "email"
}
```

**Frontend Action**:
- Highlight email field
- Show error message
- Suggest checking existing employees

---

#### 6. Duplicate National ID (400 BAD REQUEST)
```json
{
  "error": "Duplicate National ID",
  "detail": "An employee with this National ID number already exists in your organization.",
  "field": "national_id_number"
}
```

**Frontend Action**:
- Highlight national_id_number field
- Show error message
- Offer to view existing employee record

---

#### 7. Duplicate Detection Block (400 BAD REQUEST)

When duplicate detection is set to BLOCK:

```json
{
  "duplicate_detected": "Duplicate employee detected. Found 2 matching records. 1 in your institution. 1 in other institutions."
}
```

**Frontend Action**:
- Show modal with duplicate details
- Offer options:
  - View duplicate records
  - Force create with `force_create: true`
  - Cancel creation

---

#### 8. Invalid Foreign Key (400 BAD REQUEST)
```json
{
  "department": ["Invalid pk \"999\" - object does not exist."]
}
```

**Frontend Action**:
- Show error: "Selected department does not exist"
- Refresh department list
- Clear invalid selection

---

#### 9. Database Integrity Error (400 BAD REQUEST)
```json
{
  "error": "Data Integrity Error",
  "detail": "The employee data conflicts with existing records. Please check all fields and try again.",
  "technical_detail": "..."
}
```

**Frontend Action**:
- Show generic error message
- Log technical details
- Suggest reviewing all fields

---

### Error Handling Best Practices

1. **Display Field-Specific Errors**
   ```javascript
   // Example: Display error next to field
   if (error.response.data.email) {
     showFieldError('email', error.response.data.email[0]);
   }
   ```

2. **Handle Multiple Errors**
   ```javascript
   // Example: Display all errors
   Object.keys(error.response.data).forEach(field => {
     showFieldError(field, error.response.data[field][0]);
   });
   ```

3. **Provide User-Friendly Messages**
   - Don't show technical error messages to users
   - Translate error codes to readable text
   - Provide actionable next steps

4. **Log Errors for Debugging**
   ```javascript
   console.error('Employee creation failed:', {
     status: error.response.status,
     data: error.response.data,
     timestamp: new Date()
   });
   ```

---

## Advanced Features

### 1. Duplicate Detection & Handling

#### Checking for Duplicates Before Creation

You can check for duplicates before submitting the form:

```
POST /api/employees/employees/detect_duplicates/
```

**Request:**
```json
{
  "national_id_number": "123456789",
  "email": "john.doe@example.com",
  "phone_number": "+237123456789"
}
```

**Response:**
```json
{
  "duplicates_found": true,
  "total_matches": 2,
  "same_institution_matches": [
    {
      "id": 10,
      "employee_id": "EMP-005",
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com",
      "job_title": "Developer"
    }
  ],
  "cross_institution_matches": [
    {
      "id": 45,
      "employee_id": "XYZ-123",
      "first_name": "John",
      "last_name": "Doe",
      "email": "john@othercompany.com",
      "job_title": "Manager"
    }
  ],
  "match_reasons": {
    "national_id": true,
    "email": false,
    "phone": true
  }
}
```

#### Force Creating Despite Duplicates

If duplicates are detected but you want to proceed:

```json
{
  "first_name": "John",
  "last_name": "Doe",
  // ... other fields ...
  "force_create": true,
  "acknowledge_cross_institution": true
}
```

---

### 2. Sending Employee Invitation

#### Option A: Send During Creation

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  // ... other fields ...
  "send_invitation": true
}
```

#### Option B: Send After Creation

```
POST /api/employees/employees/{employee_id}/send_invitation/
```

**Response:**
```json
{
  "message": "Invitation sent successfully",
  "email": "john.doe@example.com",
  "expires_at": "2025-12-23T10:30:00Z"
}
```

---

### 3. Auto-Generated vs Manual Employee ID

#### Let System Auto-Generate

```json
{
  "first_name": "John",
  // ... other fields (no employee_id) ...
}
```

System generates based on configuration (e.g., `EMP-001`)

#### Provide Custom Employee ID

```json
{
  "employee_id": "CUSTOM-2025-001",
  "first_name": "John",
  // ... other fields ...
}
```

Only allowed if configuration permits manual override.

---

### 4. Linking to Existing User Account

If the employee already has a user account in the system:

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  // ... other fields ...
  "link_existing_user": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 5. Retrieving Organization Configuration

To know which fields are required before showing the form:

```
GET /api/employees/configuration/
```

**Response:**
```json
{
  "id": "uuid-here",
  "employer": 10,
  "employee_id_format": "SEQUENTIAL",
  "employee_id_prefix": "EMP",
  "require_middle_name": "OPTIONAL",
  "require_gender": "REQUIRED",
  "require_date_of_birth": "REQUIRED",
  "require_national_id": "REQUIRED",
  "require_bank_details": "REQUIRED",
  "duplicate_detection_level": "MODERATE",
  "duplicate_action": "WARN",
  // ... other configuration fields
}
```

**Use this to:**
- Show/hide form fields
- Mark required vs optional fields
- Display appropriate validation rules

---

## Example Code

### JavaScript (Fetch API)

```javascript
// Create Employee Function
async function createEmployee(employeeData) {
  const token = localStorage.getItem('access_token'); // Get JWT token
  
  try {
    const response = await fetch('http://your-backend.com/api/employees/employees/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(employeeData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(JSON.stringify(errorData));
    }
    
    const employee = await response.json();
    console.log('Employee created successfully:', employee);
    
    // Check for duplicate warnings
    if (employee.duplicate_warning) {
      showWarningModal(employee.duplicate_warning);
    }
    
    // Redirect to employee detail page
    window.location.href = `/employees/${employee.id}`;
    
  } catch (error) {
    console.error('Error creating employee:', error);
    handleErrors(JSON.parse(error.message));
  }
}

// Example Usage
const newEmployee = {
  first_name: 'John',
  last_name: 'Doe',
  email: 'john.doe@example.com',
  job_title: 'Software Developer',
  employment_type: 'FULL_TIME',
  hire_date: '2025-01-15',
  department: 1,  // Department ID
  branch: 2,      // Branch ID
  send_invitation: true
};

createEmployee(newEmployee);
```

---

### JavaScript (Axios)

```javascript
import axios from 'axios';

// Configure axios instance
const api = axios.create({
  baseURL: 'http://your-backend.com/api',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Add auth token to requests
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Create Employee Function
async function createEmployee(employeeData) {
  try {
    const response = await api.post('/employees/employees/', employeeData);
    
    console.log('Employee created:', response.data);
    
    // Handle duplicate warning
    if (response.data.duplicate_warning) {
      alert(`Warning: ${response.data.duplicate_warning.message}`);
    }
    
    return response.data;
    
  } catch (error) {
    if (error.response) {
      // Server responded with error
      const errors = error.response.data;
      
      // Handle specific error types
      if (errors.error === 'Duplicate Employee ID') {
        alert('Employee ID already exists. Leave blank for auto-generation.');
      } else if (errors.error === 'Duplicate Email') {
        alert('This email is already in use by another employee.');
      } else {
        // Display field errors
        Object.keys(errors).forEach(field => {
          console.error(`${field}: ${errors[field]}`);
        });
      }
    } else {
      console.error('Network error:', error.message);
    }
    throw error;
  }
}

// Example: Create with duplicate check
async function createEmployeeWithDuplicateCheck(formData) {
  try {
    // Step 1: Check for duplicates first
    const duplicateCheck = await api.post('/employees/employees/detect_duplicates/', {
      national_id_number: formData.national_id_number,
      email: formData.email,
      phone_number: formData.phone_number
    });
    
    // Step 2: If duplicates found, ask user
    if (duplicateCheck.data.duplicates_found) {
      const proceed = confirm(
        `Found ${duplicateCheck.data.total_matches} potential duplicate(s). ` +
        `Do you want to continue?`
      );
      
      if (!proceed) {
        return null;
      }
      
      // Add force_create flag
      formData.force_create = true;
    }
    
    // Step 3: Create employee
    const employee = await createEmployee(formData);
    return employee;
    
  } catch (error) {
    console.error('Error in employee creation flow:', error);
    throw error;
  }
}
```

---

### React Example (with React Hook Form)

```javascript
import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import axios from 'axios';

const CreateEmployeeForm = () => {
  const { register, handleSubmit, formState: { errors }, setError } = useForm();
  const [loading, setLoading] = useState(false);
  const [duplicateWarning, setDuplicateWarning] = useState(null);

  const onSubmit = async (data) => {
    setLoading(true);
    setDuplicateWarning(null);

    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.post(
        'http://your-backend.com/api/employees/employees/',
        data,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      // Check for duplicate warning
      if (response.data.duplicate_warning) {
        setDuplicateWarning(response.data.duplicate_warning);
      }

      // Success - redirect
      alert('Employee created successfully!');
      window.location.href = `/employees/${response.data.id}`;

    } catch (error) {
      if (error.response && error.response.data) {
        const errors = error.response.data;
        
        // Set field-specific errors
        Object.keys(errors).forEach(field => {
          setError(field, {
            type: 'manual',
            message: Array.isArray(errors[field]) 
              ? errors[field][0] 
              : errors[field]
          });
        });
      } else {
        alert('An error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      {/* Duplicate Warning */}
      {duplicateWarning && (
        <div className="alert alert-warning">
          {duplicateWarning.message}
        </div>
      )}

      {/* Basic Information */}
      <div>
        <label>First Name *</label>
        <input
          {...register('first_name', { required: 'First name is required' })}
          className={errors.first_name ? 'error' : ''}
        />
        {errors.first_name && <span className="error">{errors.first_name.message}</span>}
      </div>

      <div>
        <label>Last Name *</label>
        <input
          {...register('last_name', { required: 'Last name is required' })}
          className={errors.last_name ? 'error' : ''}
        />
        {errors.last_name && <span className="error">{errors.last_name.message}</span>}
      </div>

      <div>
        <label>Email *</label>
        <input
          type="email"
          {...register('email', { 
            required: 'Email is required',
            pattern: {
              value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
              message: 'Invalid email address'
            }
          })}
          className={errors.email ? 'error' : ''}
        />
        {errors.email && <span className="error">{errors.email.message}</span>}
      </div>

      <div>
        <label>Phone Number *</label>
        <input
          {...register('phone_number', { required: 'Phone number is required' })}
          className={errors.phone_number ? 'error' : ''}
        />
        {errors.phone_number && <span className="error">{errors.phone_number.message}</span>}
      </div>

      <div>
        <label>Job Title *</label>
        <input
          {...register('job_title', { required: 'Job title is required' })}
          className={errors.job_title ? 'error' : ''}
        />
        {errors.job_title && <span className="error">{errors.job_title.message}</span>}
      </div>

      <div>
        <label>Employment Type *</label>
        <select {...register('employment_type', { required: true })}>
          <option value="">Select...</option>
          <option value="FULL_TIME">Full Time</option>
          <option value="PART_TIME">Part Time</option>
          <option value="CONTRACT">Contract</option>
          <option value="INTERN">Intern</option>
          <option value="TEMPORARY">Temporary</option>
        </select>
        {errors.employment_type && <span className="error">Employment type is required</span>}
      </div>

      <div>
        <label>Hire Date *</label>
        <input
          type="date"
          {...register('hire_date', { required: 'Hire date is required' })}
          className={errors.hire_date ? 'error' : ''}
        />
        {errors.hire_date && <span className="error">{errors.hire_date.message}</span>}
      </div>

      <div>
        <label>Department</label>
        <select {...register('department')}>
          <option value="">Select Department...</option>
          {/* Load departments from API */}
        </select>
        {errors.department && <span className="error">{errors.department.message}</span>}
      </div>

      <div>
        <label>Branch</label>
        <select {...register('branch')}>
          <option value="">Select Branch...</option>
          {/* Load branches from API */}
        </select>
        {errors.branch && <span className="error">{errors.branch.message}</span>}
      </div>

      <div>
        <label>
          <input
            type="checkbox"
            {...register('send_invitation')}
            defaultChecked
          />
          Send invitation email to employee
        </label>
      </div>

      <button type="submit" disabled={loading}>
        {loading ? 'Creating...' : 'Create Employee'}
      </button>
    </form>
  );
};

export default CreateEmployeeForm;
```

---

### Vue.js Example

```vue
<template>
  <div class="create-employee">
    <h2>Create New Employee</h2>
    
    <!-- Duplicate Warning -->
    <div v-if="duplicateWarning" class="alert alert-warning">
      {{ duplicateWarning.message }}
    </div>

    <form @submit.prevent="submitForm">
      <!-- Basic Information -->
      <div class="form-group">
        <label>First Name *</label>
        <input 
          v-model="form.first_name" 
          :class="{ 'error': errors.first_name }"
          @input="clearError('first_name')"
        />
        <span v-if="errors.first_name" class="error-message">
          {{ errors.first_name }}
        </span>
      </div>

      <div class="form-group">
        <label>Last Name *</label>
        <input 
          v-model="form.last_name"
          :class="{ 'error': errors.last_name }"
          @input="clearError('last_name')"
        />
        <span v-if="errors.last_name" class="error-message">
          {{ errors.last_name }}
        </span>
      </div>

      <div class="form-group">
        <label>Email *</label>
        <input 
          type="email"
          v-model="form.email"
          :class="{ 'error': errors.email }"
          @input="clearError('email')"
        />
        <span v-if="errors.email" class="error-message">
          {{ errors.email }}
        </span>
      </div>

      <!-- More fields... -->

      <div class="form-group">
        <label>
          <input type="checkbox" v-model="form.send_invitation" />
          Send invitation email
        </label>
      </div>
job_title: '',
        employment_type: 'FULL_TIME',
        hire_date: '',
        department: null,
        branch: null,
        send_invitation: true
      },
      departments: [],
      branches: [],
      errors: {},
      loading: false,
      duplicateWarning: null
    };
  },
  mounted() {
    this.loadDepartments();
    this.loadBranches()
export default {
  name: 'CreateEmployee',
  data() {
    return {
      form: {
        first_name: '',
        last_name: '',
        email: '',
        phone_number: '',
        job_title: '',
        employment_type: 'FULL_TIME',
        employment_status: 'ACTIVE',
        hire_date: '',
        send_invitation: false
      },
      errors: {},
      loading: false,
      duplicateWarning: null
    };
  },
  methods: {
    async submitForm() {
      this.loading = true;
      this.errors = {};
      this.duplicateWarning = null;

      try {
        const token = localStorage.getItem('access_token');
        const response = await axios.post(
          `${process.env.VUE_APP_API_URL}/employees/employees/`,
          this.form,
          {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          }
        );

        // Check for duplicate warning
        if (response.data.duplicate_warning) {
          this.duplicateWarning = response.data.duplicate_warning;
        }

        // Success
        this.$toast.success('Employee created successfully!');
        this.$router.push(`/employees/${response.data.id}`);

      } catch (error) {
        if (error.response && error.response.data) {
          const errorData = error.response.data;
          
          // Handle specific errors
          if (errorData.error) {
            this.$toast.error(errorData.detail || errorData.error);
          }
          
          // Set field errors
          Object.keys(errorData).forEach(field => {
            this.errors[field] = Array.isArray(errorData[field])
              ? errorData[field][0]
              : errorData[field];
          });
        } else {
          this.$toast.error('An error occurred. Please try again.');
        }
      } finally {
        this.loading = false;
      }
    },
    
    async loadDepartments() {
      try {
        const token = localStorage.getItem('access_token');
        const response = await axios.get(
          `${process.env.VUE_APP_API_URL}/employees/departments/`,
          {
            headers: { 'Authorization': `Bearer ${token}` }
          }
        );
        this.departments = response.data.results || response.data;
      } catch (error) {
        console.error('Error loading departments:', error);
      }
    },
    
    async loadBranches() {
      try {
        const token = localStorage.getItem('access_token');
        const response = await axios.get(
          `${process.env.VUE_APP_API_URL}/employees/branches/`,
          {
            headers: { 'Authorization': `Bearer ${token}` }
          }
        );
        this.branches = response.data.results || response.data;
      } catch (error) {
        console.error('Error loading branches:', error);
      }
    },
    
    clearError(field) {
      if (this.errors[field]) {
        delete this.errors[field];
      }
    }
  }
};
</script>

<style scoped>
.error {
  border-color: red;
}
.error-message {
  color: red;
  font-size: 0.875rem;
}
.alert-warning {
  background-color: #fff3cd;
  border: 1px solid #ffc107;
  padding: 1rem;
  margin-bottom: 1rem;
  border-radius: 0.25rem;
}
</style>
```

---

## Employee Invitation Acceptance Flow

After an employer creates an employee and sends an invitation, the employee needs to accept it to gain access to the system.

### API Endpoint for Accepting Invitation

```
POST /api/employees/invitations/accept/
```

**Note**: This endpoint has `AllowAny` permission (no authentication required)

---

### Request Format

```json
{
  "token": "the-invitation-token-from-email-link",
  "password": "SecurePassword123!",
  "password_confirm": "SecurePassword123!"
}
```

**Field Details:**
- `token` (string, required): The invitation token from the email link
- `password` (string, required): Employee's chosen password (minimum 8 characters)
- `password_confirm` (string, required): Password confirmation (must match password)

---

### Response Format

**Success Response (200 OK):**
```json
{
  "message": "Invitation accepted successfully",
  "employee": {
    "id": 1,
    "employee_id": "EMP-001",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@company.com",
    "user": 123,
    "has_user_account": true,
    // ... all employee fields
  }
}
```

**Error Responses:**

1. **Invalid Token (400 BAD REQUEST):**
```json
{
  "token": ["Invalid invitation token"]
}
```

2. **Expired Token (400 BAD REQUEST):**
```json
{
  "token": ["Invitation has expired or is no longer valid"]
}
```

3. **Password Mismatch (400 BAD REQUEST):**
```json
{
  "password_confirm": ["Passwords do not match"]
}
```

4. **Already Accepted (400 BAD REQUEST):**
```json
{
  "error": "This employee already has a user account"
}
```

---

### What Happens on the Backend

1. **Validate Invitation Token**
   - Check token exists in database
   - Verify token has not expired
   - Verify invitation status is still "PENDING"

2. **Check Existing User**
   - Check if employee already has a user account (prevents duplicate acceptance)
   - Check if a user with this email already exists in the system

3. **Create User Account** (in main database)
   - Creates new User record with:
     - Email from invitation
     - Hashed password
     - `is_employee = True`
     - `is_active = True`
   - User is created in the **main database** (for authentication)
   - If user with this email already exists, links existing user instead of creating new one

4. **Link User to Employee** (in tenant database)
   - Updates `employee.user_id` with the new user's ID
   - This creates the link between main DB user and tenant DB employee

5. **Update Invitation Status**
   - Set `invitation.status = "ACCEPTED"`
   - Set `invitation.accepted_at = current_timestamp`

6. **Update Employee Flags**
   - Set `employee.invitation_accepted = True`
   - Set `employee.invitation_accepted_at = current_timestamp`

7. **Create Audit Log**
   - Log action: "LINKED"
   - Note: "Employee accepted invitation and linked user account"

8. **Return Response**
   - Return employee details with user information

---

### Frontend Implementation Example

#### React Component for Accepting Invitation

```javascript
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

const AcceptInvitation = () => {
  const { token } = useParams(); // Get token from URL
  const navigate = useNavigate();
  
  const [formData, setFormData] = useState({
    token: token,
    password: '',
    password_confirm: ''
  });
  
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [employeeInfo, setEmployeeInfo] = useState(null);

  // Optional: Load invitation details to show employee info
  useEffect(() => {
    loadInvitationDetails();
  }, [token]);

  const loadInvitationDetails = async () => {
    try {
      // You might want an endpoint to get invitation details by token
      // For now, we'll just proceed with acceptance
    } catch (error) {
      console.error('Error loading invitation:', error);
    }
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
    // Clear error when user types
    if (errors[e.target.name]) {
      setErrors({ ...errors, [e.target.name]: null });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrors({});

    try {
      const response = await axios.post(
        'http://your-backend.com/api/employees/invitations/accept/',
        formData
      );

      alert('Invitation accepted! You can now log in.');
      
      // Redirect to login page
      navigate('/login', {
        state: { email: response.data.employee.email }
      });

    } catch (error) {
      if (error.response && error.response.data) {
        setErrors(error.response.data);
      } else {
        alert('An error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="accept-invitation-container">
      <h2>Accept Your Employment Invitation</h2>
      
      <form onSubmit={handleSubmit}>
        {errors.token && (
          <div className="alert alert-danger">{errors.token[0]}</div>
        )}
        
        {errors.error && (
          <div className="alert alert-danger">{errors.error}</div>
        )}

        <div className="form-group">
          <label>Create Password *</label>
          <input
            type="password"
            name="password"
            value={formData.password}
            onChange={handleChange}
            className={errors.password ? 'error' : ''}
            placeholder="Minimum 8 characters"
            required
          />
          {errors.password && (
            <span className="error-message">{errors.password[0]}</span>
          )}
        </div>

        <div className="form-group">
          <label>Confirm Password *</label>
          <input
            type="password"
            name="password_confirm"
            value={formData.password_confirm}
            onChange={handleChange}
            className={errors.password_confirm ? 'error' : ''}
            required
          />
          {errors.password_confirm && (
            <span className="error-message">{errors.password_confirm[0]}</span>
          )}
        </div>

        <button type="submit" disabled={loading}>
          {loading ? 'Accepting...' : 'Accept Invitation & Create Account'}
        </button>
      </form>

      <div className="info-section">
        <h4>What happens next?</h4>
        <ul>
          <li>Your user account will be created</li>
          <li>You'll be able to log in with your email and password</li>
          <li>You can access your employee portal and view your details</li>
        </ul>
      </div>
    </div>
  );
};

export default AcceptInvitation;
```

---

### Important Notes

1. **Profile Completion Workflow (NEW):**
   - **Employer**: Creates employee with minimal info (name, email, job_title, hire_date)
   - **System**: Automatically sends invitation email (send_invitation defaults to true)
   - **Employee**: Accepts invitation and sets password
   - **Employee**: Logs in → receives `employee_profile_completed: false`
   - **Frontend**: Redirects to profile completion page
   - **Employee**: Completes profile via `/api/employees/profile/complete-profile/`
   - **System**: Sets `profile_completed=true` and `profile_completed_at` timestamp

2. **Two-Database Architecture:**
   - User account stored in **main database** (for authentication)
   - Employee record stored in **tenant database** (employer-specific data)
   - The `employee.user_id` field links the two databases
   - Middleware automatically handles database routing

3. **Security Considerations:**
   - Token expires in 7 days by default
   - Employee can only view/edit their own profile
   - Employer cannot change employee's personal data after profile completion
   - All updates are logged in audit trail

---

## Employee Profile Completion Flow

After accepting the invitation and logging in, employees need to complete their profile with remaining required information.

### API Endpoints for Profile Completion

**Get Current Profile:**
```
GET /api/employees/profile/me/
```

**Complete/Update Profile (Partial Update):**
```
PATCH /api/employees/profile/complete-profile/
```

**Complete/Update Profile (Full Update):**
```
PUT /api/employees/profile/complete-profile/
```

**Headers Required**:
```json
{
  "Authorization": "Bearer <employee_jwt_token>",
  "Content-Type": "application/json"
}
```

---

### Request Format for Profile Completion

**Note**: All fields are optional - employee can complete what they can. The profile will be marked as complete when submitted.

```json
{
  // Personal Information
  "date_of_birth": "1990-05-15",
  "gender": "MALE",
  "nationality": "Cameroonian",
  "marital_status": "MARRIED",
  
  // Contact Information
  "phone_number": "+237123456789",
  "alternative_phone": "+237987654321",
  "personal_email": "john@gmail.com",
  "address": "123 Main Street",
  "city": "Douala",
  "state_region": "Littoral",
  "postal_code": "1234",
  "country": "Cameroon",
  
  // Legal Identification
  "national_id_number": "123456789",
  "passport_number": "A12345678",
  "cnps_number": "CNP123456789",
  "tax_number": "TAX123456",
  
  // Payroll Information
  "bank_name": "Bank of Africa",
  "bank_account_number": "1234567890",
  "bank_account_name": "John Doe",
  
  // Emergency Contact
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_relationship": "Spouse",
  "emergency_contact_phone": "+237999888777"
}
```

### Response Format

**Success Response (200 OK):**
```json
{
  "message": "Profile updated successfully",
  "profile": {
    "id": 1,
    "employee_id": "EMP-001",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@company.com",
    "phone_number": "+237123456789",
    "date_of_birth": "1990-05-15",
    "national_id_number": "123456789",
    "profile_completed": true,
    "profile_completed_at": "2025-12-16T14:30:00Z",
    // ... all employee fields
  }
}
```

---

### Frontend Implementation for Profile Completion

#### React Component

```javascript
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const CompleteEmployeeProfile = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    phone_number: '',
    address: '',
    city: '',
    date_of_birth: '',
    gender: '',
    nationality: '',
    national_id_number: '',
    cnps_number: '',
    emergency_contact_name: '',
    emergency_contact_relationship: '',
    emergency_contact_phone: '',
    bank_name: '',
    bank_account_number: '',
    bank_account_name: ''
  });
  
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [requiredFields, setRequiredFields] = useState([]);

  useEffect(() => {
    loadEmployeeProfile();
    loadConfiguration();
  }, []);

  const loadEmployeeProfile = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.get(
        'http://your-backend.com/api/employees/profile/me/',
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      
      // Pre-fill existing data
      setFormData({
        ...formData,
        ...response.data
      });
      
    } catch (error) {
      console.error('Error loading profile:', error);
    }
  };

  const loadConfiguration = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.get(
        'http://your-backend.com/api/employees/configuration/',
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      
      // Determine which fields are required
      const config = response.data;
      const required = [];
      
      if (config.require_phone === 'REQUIRED') required.push('phone_number');
      if (config.require_address === 'REQUIRED') required.push('address');
      if (config.require_date_of_birth === 'REQUIRED') required.push('date_of_birth');
      // ... check other fields
      
      setRequiredFields(required);
      
    } catch (error) {
      console.error('Error loading configuration:', error);
    }
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrors({});

    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.patch(
        'http://your-backend.com/api/employees/profile/complete-profile/',
        formData,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      alert('Profile completed successfully!');
      navigate('/employee/dashboard');

    } catch (error) {
      if (error.response && error.response.data) {
        setErrors(error.response.data);
      } else {
        alert('An error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="complete-profile-container">
      <h2>Complete Your Profile</h2>
      <p>Please fill in the remaining required information</p>
      
      <form onSubmit={handleSubmit}>
        {/* Contact Information */}
        <h3>Contact Information</h3>
        
        <div className="form-group">
          <label>Phone Number {requiredFields.includes('phone_number') && '*'}</label>
          <input
            type="tel"
            name="phone_number"
            value={formData.phone_number}
            onChange={handleChange}
            required={requiredFields.includes('phone_number')}
          />
          {errors.phone_number && <span className="error">{errors.phone_number[0]}</span>}
        </div>

        <div className="form-group">
          <label>Address {requiredFields.includes('address') && '*'}</label>
          <textarea
            name="address"
            value={formData.address}
            onChange={handleChange}
            required={requiredFields.includes('address')}
          />
          {errors.address && <span className="error">{errors.address[0]}</span>}
        </div>

        {/* Personal Information */}
        <h3>Personal Information</h3>
        
        <div className="form-group">
          <label>Date of Birth {requiredFields.includes('date_of_birth') && '*'}</label>
          <input
            type="date"
            name="date_of_birth"
            value={formData.date_of_birth}
            onChange={handleChange}
            required={requiredFields.includes('date_of_birth')}
          />
          {errors.date_of_birth && <span className="error">{errors.date_of_birth[0]}</span>}
        </div>

        <div className="form-group">
          <label>Gender {requiredFields.includes('gender') && '*'}</label>
          <select
            name="gender"
            value={formData.gender}
            onChange={handleChange}
            required={requiredFields.includes('gender')}
          >
            <option value="">Select...</option>
            <option value="MALE">Male</option>
            <option value="FEMALE">Female</option>
            <option value="OTHER">Other</option>
          </select>
          {errors.gender && <span className="error">{errors.gender[0]}</span>}
        </div>

        {/* Legal Identification */}
        <h3>Legal Identification</h3>
        
        <div className="form-group">
          <label>National ID Number {requiredFields.includes('national_id_number') && '*'}</label>
          <input
            type="text"
            name="national_id_number"
            value={formData.national_id_number}
            onChange={handleChange}
            required={requiredFields.includes('national_id_number')}
          />
          {errors.national_id_number && <span className="error">{errors.national_id_number[0]}</span>}
        </div>

        {/* Emergency Contact */}
        <h3>Emergency Contact</h3>
        
        <div className="form-group">
          <label>Emergency Contact Name *</label>
          <input
            type="text"
            name="emergency_contact_name"
            value={formData.emergency_contact_name}
            onChange={handleChange}
            required
          />
        </div>

        <div className="form-group">
          <label>Relationship *</label>
          <input
            type="text"
            name="emergency_contact_relationship"
            value={formData.emergency_contact_relationship}
            onChange={handleChange}
            required
          />
        </div>

        <div className="form-group">
          <label>Emergency Contact Phone *</label>
          <input
            type="tel"
            name="emergency_contact_phone"
            value={formData.emergency_contact_phone}
            onChange={handleChange}
            required
          />
        </div>

        {/* Banking Information */}
        <h3>Banking Information</h3>
        
        <div className="form-group">
          <label>Bank Name</label>
          <input
            type="text"
            name="bank_name"
            value={formData.bank_name}
            onChange={handleChange}
          />
        </div>

        <div className="form-group">
          <label>Bank Account Number</label>
          <input
            type="text"
            name="bank_account_number"
            value={formData.bank_account_number}
            onChange={handleChange}
          />
        </div>

        <button type="submit" disabled={loading}>
          {loading ? 'Saving...' : 'Complete Profile'}
        </button>
      </form>
    </div>
  );
};

export default CompleteEmployeeProfile;
```days)
   - Password must meet minimum requirements (8+ characters)
   - No authentication required for acceptance (public endpoint)

4. **After Acceptance:**
   - Employee can log in using email and password
   - Employee will have `is_employee = True` flag
   - Employee can access employee-specific endpoints
   - Employee's dashboard shows their employment details

---

## Summary Checklist

### Before Implementation
- [ ] Understand authentication requirements
- [ ] Get JWT token from login/auth endpoint
- [ ] Know which fields are required (fetch configuration)
- [ ] Understand duplicate detection rules

### During Implementation
- [ ] Include Authorization header with JWT token
- [ ] Validate form data on frontend
- [ ] Handle all possible error responses
- [ ] Display field-specific errors
- [ ] Show duplicate warnings appropriately
- [ ] Implement loading states
- [ ] Test with various data scenarios

### After Implementation
- [ ] Test successful creation flow
- [ ] Test all error scenarios
- [ ] Test duplicate detection flow
- [ ] Test invitation sending
- [ ] Test with different user permissions
- [ ] Verify audit logs are created (backend)
- [ ] Test mobile responsiveness

---

## Additional Resources

### Related Endpoints

**Employee Management (Requires Employer Authentication):**
- **List Employees**: `GET /api/employees/employees/`
- **Get Employee Detail**: `GET /api/employees/employees/{id}/`
- **Update Employee**: `PUT/PATCH /api/employees/employees/{id}/`
- **Delete Employee**: `DELETE /api/employees/employees/{id}/`
- **Terminate Employee**: `POST /api/employees/employees/{id}/terminate/`
- **Send Invitation**: `POST /api/employees/employees/{id}/send_invitation/`
- **Detect Duplicates**: `POST /api/employees/employees/detect_duplicates/`

**Employee Invitation (Public - No Authentication Required):**
- **Accept Invitation**: `POST /api/employees/invitations/accept/`
- **List Invitations**: `GET /api/employees/invitations/` (Requires authentication)

**Employee Self-Service (Requires Employee Authentication):**
- **Get Own Profile**: `GET /api/employees/profile/me/`
- **Complete Profile**: `PATCH /api/employees/profile/complete-profile/`
- **Update Profile**: `PUT /api/employees/profile/complete-profile/`

### Configuration Endpoints

- **Get Configuration**: `GET /api/employees/configuration/`
- **Update Configuration**: `PUT/PATCH /api/employees/configuration/{id}/`

### Department & Branch Endpoints

- **List Departments**: `GET /api/employees/departments/`
- **Create Department**: `POST /api/employees/departments/`
- **List Branches**: `GET /api/employees/branches/`
- **Create Branch**: `POST /api/employees/branches/`

---

## Support

For questions or issues:
1. Check API error responses for detailed information
2. Review backend logs for technical details
3. Verify authentication and permissions
4. Contact backend team with:
   - Request payload
   - Response received
   - Expected behavior
   - Steps to reproduce

---

## ✅ Multi-Tenant Database Architecture

### Implementation Status: **COMPLETE**

The system implements a **multi-tenant architecture** where:
- **Main Database** (`payrova`): Stores User accounts (authentication), EmployerProfiles
- **Tenant Databases** (`payrova_{company_name}`): Each employer has a separate database for their employees

### How It Works

1. **Tenant Context Middleware**: Automatically sets the tenant database based on the authenticated user
   - Employers: Routes to their tenant database
   - System seamlessly handles database routing

2. **Employee Creation**: 
   - Employee records are created in the **employer's tenant database**
   - Uses explicit `.using(tenant_db)` for all operations
   - Each employer's data is completely isolated

3. **Invitation Acceptance**:
   - User account created in **main database** (for authentication)
   - `user_id` linked to employee record in **tenant database**
   - Cross-database reference properly maintained

4. **Database Router**: 
   - Routes authentication models to main database
   - Routes employee models to tenant database
   - Handles all queries automatically when middleware sets context

### Database Isolation

✅ **Each employer's employee data is stored in their own database**  
✅ **Complete data isolation between employers**  
✅ **User authentication centralized in main database**  
✅ **Tenant context automatically set by middleware**

### Technical Implementation

The implementation includes:
- `TenantDatabaseMiddleware` - Sets tenant context per request
- `TenantDatabaseRouter` - Routes queries to correct database
- Explicit `.using(tenant_db)` in all employee operations
- Thread-local storage for tenant context

---

**Document Version**: 2.0  
**Last Updated**: December 16, 2025  
**API Version**: v1  
**Status**: ✅ Multi-tenant database routing fully implemented
// this is the end of the file