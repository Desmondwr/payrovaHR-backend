# Employee Self-Registration Feature Documentation

## Overview

The employee self-registration feature allows individuals to create their own employee accounts directly without needing admin approval or invitation. This is in addition to the existing employer invitation system.

---

## What's New

### 1. **Updated User Model**
- Added `is_employee` field to distinguish employee users
- Updated `profile_completed` field description to be generic (applies to both employers and employees)

### 2. **New EmployeeProfile Model**
Comprehensive employee profile with the following sections:

#### Personal Information
- First name, last name, middle name (optional)
- Date of birth
- Gender (Male, Female, Other, Prefer not to say)
- Marital status (Single, Married, Divorced, Widowed)
- Nationality

#### Contact Information
- Phone number (required)
- Alternative phone (optional)
- Personal email (optional)
- Full address with city, state/region, postal code, country

#### Emergency Contact
- Emergency contact name
- Relationship
- Phone number

#### Identification
- National ID number (required, unique)
- Passport number (optional, unique if provided)

#### Employment Preferences
- Desired position
- Years of experience
- Highest education level
- Skills (comma-separated list)

#### Profile Picture
- Upload capability for employee photo

---

## New API Endpoints

### 1. Employee Registration

**Endpoint:** `POST /api/auth/register/employee/`

**Rate Limit:** 5 requests per hour per IP

**Authentication:** Not required (public endpoint)

**Request Body:**
```json
{
  "email": "employee@example.com",
  "password": "SecurePassword123!",
  "confirm_password": "SecurePassword123!",
  
  "first_name": "John",
  "last_name": "Doe",
  "middle_name": "Smith",
  "date_of_birth": "1990-05-15",
  "gender": "MALE",
  "marital_status": "SINGLE",
  "nationality": "Cameroonian",
  
  "phone_number": "+237699123456",
  "alternative_phone": "+237677888999",
  "personal_email": "john.personal@email.com",
  "address": "123 Main Street, Apartment 4B",
  "city": "Douala",
  "state_region": "Littoral",
  "postal_code": "00237",
  "country": "Cameroon",
  
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_relationship": "Sister",
  "emergency_contact_phone": "+237699777888",
  
  "national_id_number": "123456789",
  "passport_number": "P1234567",
  
  "desired_position": "Software Developer",
  "years_of_experience": 3,
  "highest_education_level": "Bachelor's Degree in Computer Science",
  "skills": "Python, Django, JavaScript, React, SQL"
}
```

**Required Fields:**
- email
- password
- confirm_password
- first_name
- last_name
- date_of_birth
- gender
- marital_status
- nationality
- phone_number
- address
- city
- state_region
- country
- emergency_contact_name
- emergency_contact_relationship
- emergency_contact_phone
- national_id_number

**Optional Fields:**
- middle_name
- alternative_phone
- personal_email
- postal_code
- passport_number
- desired_position
- years_of_experience
- highest_education_level
- skills

**Success Response (201):**
```json
{
  "success": true,
  "message": "Employee account created successfully. You are now logged in.",
  "data": {
    "user": {
      "id": 3,
      "email": "employee@example.com",
      "first_name": "",
      "last_name": "",
      "is_admin": false,
      "is_employer": false,
      "is_employee": true,
      "profile_completed": true,
      "two_factor_enabled": false,
      "created_at": "2025-12-13T14:00:00Z"
    },
    "employee_profile": {
      "id": 1,
      "user": 3,
      "first_name": "John",
      "last_name": "Doe",
      "middle_name": "Smith",
      "date_of_birth": "1990-05-15",
      "gender": "MALE",
      "marital_status": "SINGLE",
      "nationality": "Cameroonian",
      "phone_number": "+237699123456",
      "alternative_phone": "+237677888999",
      "personal_email": "john.personal@email.com",
      "address": "123 Main Street, Apartment 4B",
      "city": "Douala",
      "state_region": "Littoral",
      "postal_code": "00237",
      "country": "Cameroon",
      "emergency_contact_name": "Jane Doe",
      "emergency_contact_relationship": "Sister",
      "emergency_contact_phone": "+237699777888",
      "national_id_number": "123456789",
      "passport_number": "P1234567",
      "desired_position": "Software Developer",
      "years_of_experience": 3,
      "highest_education_level": "Bachelor's Degree in Computer Science",
      "skills": "Python, Django, JavaScript, React, SQL",
      "profile_picture": null,
      "created_at": "2025-12-13T14:00:00Z",
      "updated_at": "2025-12-13T14:00:00Z"
    },
    "tokens": {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
  },
  "errors": []
}
```

**Error Response (400):**
```json
{
  "success": false,
  "message": "Failed to create employee account.",
  "data": {},
  "errors": {
    "email": ["A user with this email already exists."],
    "confirm_password": ["Passwords do not match."],
    "national_id_number": ["This national ID number is already registered."]
  }
}
```

---

### 2. Get Employee Profile

**Endpoint:** `GET /api/employee/profile/`

**Authentication:** Required (Bearer token)

**Permission:** Only employees can access

**Success Response (200):**
```json
{
  "success": true,
  "message": "Employee profile retrieved successfully.",
  "data": {
    "id": 1,
    "user": 3,
    "user_email": "employee@example.com",
    "first_name": "John",
    "last_name": "Doe",
    ...
  },
  "errors": []
}
```

---

### 3. Update Employee Profile

**Endpoint:** `PUT /api/employee/profile/` (full update)
**Endpoint:** `PATCH /api/employee/profile/` (partial update)

**Authentication:** Required (Bearer token)

**Permission:** Only employees can access

**Request Body (example partial update):**
```json
{
  "phone_number": "+237699999999",
  "address": "New Address 456",
  "skills": "Python, Django, JavaScript, React, SQL, Docker, Kubernetes"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "Employee profile updated successfully.",
  "data": {
    ...updated profile data...
  },
  "errors": []
}
```

---

### 4. Updated User Profile Endpoint

**Endpoint:** `GET /api/profile/`

Now returns employee profile if user is an employee:

```json
{
  "success": true,
  "message": "User profile retrieved successfully.",
  "data": {
    "id": 3,
    "email": "employee@example.com",
    "is_employee": true,
    "profile_completed": true,
    "employee_profile": {
      ...employee profile data...
    }
  },
  "errors": []
}
```

---

## Key Features

### 1. **Immediate Account Activation**
- Employee accounts are activated immediately upon registration
- No email confirmation required
- Automatic login after registration (JWT tokens returned)

### 2. **Profile Completion During Registration**
- All profile information collected during registration
- Profile marked as completed automatically
- No additional onboarding steps required

### 3. **Unique Identification Validation**
- National ID numbers must be unique across all employees
- Passport numbers must be unique (if provided)
- Email addresses must be unique across all users

### 4. **Secure Registration**
- Password validation using Django's password validators
- Rate limiting (5 registrations per hour per IP)
- Confirm password validation

### 5. **Auto-Login After Registration**
- JWT tokens automatically generated
- User can start using the system immediately
- No separate login step needed

---

## Differences from Employer Registration

| Feature | Employer | Employee |
|---------|----------|----------|
| Registration Method | Admin creates account | Self-registration |
| Activation | Email with token required | Immediate |
| Initial State | Inactive until activated | Active immediately |
| Profile Completion | After first login | During registration |
| Approval Required | Yes (admin creates) | No (self-service) |
| Auto-Login | No | Yes (tokens returned) |

---

## Testing the Employee Registration

### Using cURL (PowerShell):

```powershell
$body = @{
    email = "testemployee@example.com"
    password = "SecurePass123!"
    confirm_password = "SecurePass123!"
    first_name = "Test"
    last_name = "Employee"
    date_of_birth = "1995-01-01"
    gender = "MALE"
    marital_status = "SINGLE"
    nationality = "Cameroonian"
    phone_number = "+237699123456"
    address = "123 Test Street"
    city = "Douala"
    state_region = "Littoral"
    country = "Cameroon"
    emergency_contact_name = "Emergency Contact"
    emergency_contact_relationship = "Friend"
    emergency_contact_phone = "+237699999999"
    national_id_number = "TEST123456"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/register/employee/" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

### Using Postman:

1. Create new POST request
2. URL: `http://127.0.0.1:8000/api/auth/register/employee/`
3. Headers: `Content-Type: application/json`
4. Body: Raw JSON with all required fields
5. Send request
6. Tokens will be in the response

---

## Admin Panel

Employees can be viewed and managed in Django Admin:
- URL: `http://127.0.0.1:8000/admin/accounts/employeeprofile/`
- View all employee profiles
- Edit employee information
- Search by name, email, phone, or ID numbers

---

## Database Changes

### New Fields in Users Table:
- `is_employee` (boolean, default: False)
- Updated `profile_completed` (now applies to both employers and employees)

### New Table: employee_profiles
Contains all employee profile information with foreign key to users table.

---

## Security Considerations

1. **Rate Limiting:** 5 registrations per hour per IP prevents abuse
2. **Password Validation:** Strong password requirements enforced
3. **Unique Constraints:** National ID and passport numbers must be unique
4. **Input Validation:** All fields validated before saving
5. **SQL Injection Protection:** Django ORM provides protection
6. **XSS Protection:** Django templates auto-escape

---

## Next Steps (Future Enhancements)

1. **Email Verification:** Add optional email verification step
2. **Document Uploads:** Allow employees to upload ID documents, certificates
3. **Resume Upload:** PDF resume attachment
4. **Background Check:** Integration with background check services
5. **Skills Matching:** Algorithm to match employees with job openings
6. **Employee Dashboard:** Personalized dashboard for employees
7. **Job Applications:** Allow employees to apply for positions
8. **Notifications:** Email/SMS notifications for profile updates

---

## Migration Commands

Migrations have already been created and applied:
```bash
python manage.py makemigrations accounts
python manage.py migrate
```

---

## Summary

✅ Employee self-registration implemented  
✅ Comprehensive employee profile model created  
✅ API endpoints for registration and profile management  
✅ Automatic login after registration  
✅ Rate limiting and security measures in place  
✅ Admin panel integration  
✅ Database migrations completed  

**Status:** FULLY OPERATIONAL

---

**Created:** December 13, 2025
**Version:** 1.1.0
