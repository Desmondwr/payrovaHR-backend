# PayrovaHR Backend - API Endpoints for Insomnia Testing

## Base URL
```
http://127.0.0.1:8000
```

---

## 🔐 ADMIN ENDPOINTS

### 1. Create Employer Account
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/admin/create-employer/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ADMIN_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "email": "employer@company.com"
}
```

---

### 2. List All Employers
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/admin/employers/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ADMIN_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 3. Enable/Disable Employer Account
**Endpoint:** `PATCH`
```
http://127.0.0.1:8000/api/admin/employers/1/status/
```
*Replace `1` with the actual employer ID*

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ADMIN_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "is_active": true
}
```
*Set to `false` to disable the employer account*

---

## 🔑 AUTHENTICATION ENDPOINTS (All Users)

### 4. Activate Account (Employer)
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/activate/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "token": "activation-token-from-email",
  "password": "SecurePassword@123",
  "confirm_password": "SecurePassword@123"
}
```

---

### 5. Login
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/login/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body (Without 2FA):**
```json
{
  "email": "admin@payrova.com",
  "password": "Admin@123456"
}
```

**Body (With 2FA):**
```json
{
  "email": "employer@company.com",
  "password": "SecurePassword@123",
  "two_factor_code": "123456"
}
```

---

### 6. Refresh Token
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/token/refresh/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "refresh": "YOUR_REFRESH_TOKEN"
}
```

---

### 7. Request Password Reset
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/password-reset/request/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Password reset code sent to your email. Code expires in 5 minutes.",
  "data": {
    "email": "user@example.com"
  },
  "errors": []
}
```

---

### 8. Verify Reset Code and Reset Password
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/password-reset/verify/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "email": "user@example.com",
  "code": "123456",
  "password": "NewPassword@123",
  "confirm_password": "NewPassword@123"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Password reset successfully. You can now login with your new password.",
  "data": {},
  "errors": []
}
```

**Response (Invalid Code):**
```json
{
  "success": false,
  "message": "Invalid verification code.",
  "data": {},
  "errors": []
}
```

**Response (Expired Code):**
```json
{
  "success": false,
  "message": "Code has expired. Please request a new one.",
  "data": {},
  "errors": []
}
```

---

### 9. Resend Password Reset Code
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/password-reset/resend/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "New password reset code sent to your email. Code expires in 5 minutes.",
  "data": {
    "email": "user@example.com"
  },
  "errors": []
}
```

---

### 10. Change Password (Authenticated Users)
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/change-password/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "old_password": "CurrentPassword@123",
  "new_password": "NewPassword@456",
  "confirm_new_password": "NewPassword@456"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Password changed successfully. Please login with your new password.",
  "data": {
    "user": {
      "email": "user@example.com",
      "is_admin": false,
      "is_employer": true,
      "is_employee": false
    }
  },
  "errors": []
}
```

**Response (Incorrect Current Password):**
```json
{
  "success": false,
  "message": "Validation failed.",
  "data": {},
  "errors": {
    "old_password": ["Current password is incorrect."]
  }
}
```

**Response (Passwords Don't Match):**
```json
{
  "success": false,
  "message": "Validation failed.",
  "data": {},
  "errors": {
    "confirm_new_password": ["New passwords do not match."]
  }
}
```

**Response (Same as Current Password):**
```json
{
  "success": false,
  "message": "Validation failed.",
  "data": {},
  "errors": {
    "new_password": ["New password must be different from current password."]
  }
}
```

---

### 11. Register Employee (Self-Registration)
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/register/employee/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "email": "employee@example.com",
  "password": "EmployeePass@123",
  "confirm_password": "EmployeePass@123",
  "first_name": "John",
  "last_name": "Doe",
  "date_of_birth": "1990-05-15",
  "phone_number": "+237670000000",
  "national_id_number": "123456789"
}
```

---

## 🔒 TWO-FACTOR AUTHENTICATION (2FA) ENDPOINTS

### 8. Setup 2FA
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/2fa/setup/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ACCESS_TOKEN"
}
```

**Body:** None (Empty JSON object)
```json
{}
```

---

### 9. Verify and Enable 2FA
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/2fa/verify/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "code": "123456"
}
```

---

### 10. Disable 2FA
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/auth/2fa/disable/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "password": "YourCurrentPassword@123"
}
```

---

## 👤 USER PROFILE ENDPOINTS (All Authenticated Users)

### 11. Get Current User Profile
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/profile/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

## 🏢 EMPLOYER PROFILE ENDPOINTS

### 12. Get Employer Profile
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employer/profile/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 13. Update Employer Profile
**Endpoint:** `PUT` or `PATCH`
```
http://127.0.0.1:8000/api/employer/profile/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body (PATCH - Partial Update):**
```json
{
  "company_name": "Updated Company Name",
  "phone_number": "+237699000000"
}
```

**Body (PUT - Full Update):**
```json
{
  "company_name": "My Company Ltd",
  "business_type": "Technology",
  "registration_number": "RC123456",
  "tax_id": "TAX987654",
  "address": "123 Business Street",
  "city": "Douala",
  "state_region": "Littoral",
  "country": "Cameroon",
  "phone_number": "+237699000000",
  "website": "https://mycompany.com",
  "number_of_employees": 50,
  "industry": "IT Services"
}
```

---

### 14. Complete Employer Profile (First Time)
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employer/profile/complete/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "company_name": "My Company Ltd",
  "business_type": "Technology",
  "registration_number": "RC123456",
  "tax_id": "TAX987654",
  "address": "123 Business Street",
  "city": "Douala",
  "state_region": "Littoral",
  "country": "Cameroon",
  "phone_number": "+237699000000",
  "website": "https://mycompany.com",
  "number_of_employees": 50,
  "industry": "IT Services"
}
```

---

## 👨‍💼 EMPLOYEE REGISTRY ENDPOINTS (For Self-Registered Employees)

### 15. Get Employee Registry Profile
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employee/registry/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYEE_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 16. Update Employee Registry Profile
**Endpoint:** `PUT` or `PATCH`
```
http://127.0.0.1:8000/api/employee/registry/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYEE_ACCESS_TOKEN"
}
```

**Body (PATCH - Partial Update):**
```json
{
  "phone_number": "+237670123456",
  "address": "456 New Address"
}
```

---

## 🏗️ DEPARTMENT MANAGEMENT (Employer Only)

### 17. List All Departments
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/departments/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 18. Create Department
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/departments/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "name": "Engineering",
  "code": "ENG",
  "description": "Engineering Department",
  "parent_department": null,
  "is_active": true
}
```

---

### 19. Get Single Department
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/departments/{department_id}/
```
*Replace `{department_id}` with actual UUID*

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 20. Update Department
**Endpoint:** `PUT` or `PATCH`
```
http://127.0.0.1:8000/api/employees/departments/{department_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "name": "Software Engineering",
  "description": "Updated description"
}
```

---

### 21. Delete Department
**Endpoint:** `DELETE`
```
http://127.0.0.1:8000/api/employees/departments/{department_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None

---

## 🏢 BRANCH MANAGEMENT (Employer Only)

### 22. List All Branches
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/branches/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 23. Create Branch
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/branches/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "name": "Douala Office",
  "code": "DLA",
  "address": "123 Main Street",
  "city": "Douala",
  "state_region": "Littoral",
  "country": "Cameroon",
  "phone_number": "+237699111111",
  "email": "douala@company.com",
  "is_headquarters": true,
  "is_active": true
}
```

---

### 24. Get Single Branch
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/branches/{branch_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 25. Update Branch
**Endpoint:** `PUT` or `PATCH`
```
http://127.0.0.1:8000/api/employees/branches/{branch_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "phone_number": "+237699222222",
  "email": "douala.updated@company.com"
}
```

---

### 26. Delete Branch
**Endpoint:** `DELETE`
```
http://127.0.0.1:8000/api/employees/branches/{branch_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None

---

## 👥 EMPLOYEE MANAGEMENT (Employer Only)

### 27. List All Employees
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/employees/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

**Query Parameters (Optional):**
```
?status=ACTIVE
?department=department-uuid
?branch=branch-uuid
?search=john
```

---

### 28. Create Employee
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/employees/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body (Minimal):**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@company.com",
  "phone_number": "+237670123456",
  "job_title": "Software Developer",
  "employment_type": "FULL_TIME",
  "employment_status": "ACTIVE",
  "hire_date": "2024-01-15",
  "national_id_number": "123456789",
  "send_invitation": true
}
```

**Body (Complete):**
```json
{
  "employee_id": "EMP001",
  "first_name": "John",
  "last_name": "Doe",
  "middle_name": "Michael",
  "date_of_birth": "1990-05-15",
  "gender": "MALE",
  "marital_status": "SINGLE",
  "nationality": "Cameroonian",
  "email": "john.doe@company.com",
  "personal_email": "john.personal@gmail.com",
  "phone_number": "+237670123456",
  "alternative_phone": "+237699123456",
  "address": "123 Main Street",
  "city": "Douala",
  "state_region": "Littoral",
  "postal_code": "12345",
  "country": "Cameroon",
  "national_id_number": "123456789",
  "passport_number": "P123456",
  "cnps_number": "CNPS123456",
  "tax_number": "TAX123456",
  "department": "department-uuid",
  "branch": "branch-uuid",
  "manager": "manager-employee-uuid",
  "job_title": "Software Developer",
  "employment_type": "FULL_TIME",
  "employment_status": "ACTIVE",
  "hire_date": "2024-01-15",
  "probation_end_date": "2024-04-15",
  "bank_name": "ABC Bank",
  "bank_account_number": "1234567890",
  "bank_account_name": "John Doe",
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_relationship": "Spouse",
  "emergency_contact_phone": "+237670999999",
  "send_invitation": true
}
```

---

### 29. Get Single Employee
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 30. Update Employee
**Endpoint:** `PUT` or `PATCH`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "job_title": "Senior Software Developer",
  "phone_number": "+237670999888"
}
```

---

### 31. Delete Employee
**Endpoint:** `DELETE`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None

---

### 32. Send/Resend Employee Invitation
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/send_invitation/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (Empty JSON object)
```json
{}
```

---

### 33. Terminate Employee
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/terminate/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "termination_date": "2024-12-31",
  "termination_reason": "RESIGNATION"
}
```

*Possible termination reasons: RESIGNATION, TERMINATION, LAYOFF, RETIREMENT, CONTRACT_END, OTHER*

---

### 34. Reactivate Employee
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/reactivate/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (Empty JSON object)
```json
{}
```

---

### 35. Get Employee Documents
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/documents/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 36. Get Employee Cross-Institution Records
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/cross_institutions/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 37. Get Employee Audit Log
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/employees/{employee_id}/audit_log/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 38. Detect Duplicate Employees
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/employees/detect_duplicates/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "national_id_number": "123456789",
  "email": "john.doe@example.com",
  "phone_number": "+237670123456"
}
```

---

## 📄 EMPLOYEE DOCUMENT MANAGEMENT (Employer Only)

### 39. List All Employee Documents
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/documents/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 40. Upload Employee Document
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/documents/
```

**Headers:**
```json
{
  "Content-Type": "multipart/form-data",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body (Form Data):**
```
employee: employee-uuid
document_type: RESUME
document_file: [FILE]
description: Employee Resume
has_expiry: false
```

*Document types: RESUME, ID_COPY, CERTIFICATE, CONTRACT, DIPLOMA, PHOTO, OTHER*

---

### 41. Get Single Document
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/documents/{document_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 42. Update Document
**Endpoint:** `PUT` or `PATCH`
```
http://127.0.0.1:8000/api/employees/documents/{document_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "description": "Updated description",
  "has_expiry": true,
  "expiry_date": "2025-12-31"
}
```

---

### 43. Delete Document
**Endpoint:** `DELETE`
```
http://127.0.0.1:8000/api/employees/documents/{document_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None

---

### 44. Verify Document
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/documents/{document_id}/verify/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (Empty JSON object)
```json
{}
```

---

### 45. Get Expiring Documents
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/documents/expiring_soon/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

**Query Parameters (Optional):**
```
?days=30
```

---

## ⚙️ EMPLOYEE CONFIGURATION (Employer Only)

### 46. Get Employee Configuration
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/configuration/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 47. Create/Update Employee Configuration
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/configuration/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "employee_id_format": "SEQUENTIAL",
  "employee_id_prefix": "EMP",
  "employee_id_starting_number": 1,
  "employee_id_padding": 3,
  "duplicate_detection_level": "MODERATE",
  "duplicate_action": "WARN",
  "allow_concurrent_employment": true,
  "required_documents": ["RESUME", "ID_COPY", "CERTIFICATE"],
  "document_allowed_formats": ["pdf", "jpg", "jpeg", "png", "docx"],
  "document_max_size_mb": 10,
  "send_invitation_email": true,
  "invitation_expiry_days": 7,
  "allow_employee_self_update": true,
  "termination_revoke_access_timing": "IMMEDIATE",
  "allow_employee_reactivation": true
}
```

---

### 48. Update Configuration (PATCH)
**Endpoint:** `PATCH`
```
http://127.0.0.1:8000/api/employees/configuration/{config_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "employee_id_prefix": "STAFF",
  "duplicate_detection_level": "STRICT"
}
```

---

### 49. Reset Configuration to Defaults
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/configuration/reset_to_defaults/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (Empty JSON object)
```json
{}
```

---

## 📧 EMPLOYEE INVITATIONS (Employer View)

### 50. List All Invitations
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/invitations/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 51. Get Single Invitation
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/invitations/{invitation_id}/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYER_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 52. Accept Employee Invitation (Public - No Auth Required)
**Endpoint:** `POST`
```
http://127.0.0.1:8000/api/employees/invitations/accept/
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "token": "invitation-token-from-email",
  "password": "EmployeePassword@123",
  "confirm_password": "EmployeePassword@123"
}
```

---

## 👤 EMPLOYEE SELF-PROFILE MANAGEMENT (Employee Only)

### 53. Get Own Employee Profile
**Endpoint:** `GET`
```
http://127.0.0.1:8000/api/employees/profile/me/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYEE_ACCESS_TOKEN"
}
```

**Body:** None (GET request)

---

### 54. Complete Employee Profile (First Time)
**Endpoint:** `PUT` or `PATCH`
```
http://127.0.0.1:8000/api/employees/profile/complete-profile/
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_EMPLOYEE_ACCESS_TOKEN"
}
```

**Body:**
```json
{
  "personal_email": "john.personal@gmail.com",
  "phone_number": "+237670123456",
  "address": "123 Home Street",
  "city": "Douala",
  "state_region": "Littoral",
  "country": "Cameroon",
  "emergency_contact_name": "Jane Doe",
  "emergency_contact_relationship": "Spouse",
  "emergency_contact_phone": "+237670999999",
  "bank_name": "ABC Bank",
  "bank_account_number": "1234567890",
  "bank_account_name": "John Doe"
}
```

---

##  NOTES

### Authentication Headers
- For endpoints requiring authentication, include the JWT access token in the Authorization header
- Format: `Bearer YOUR_ACCESS_TOKEN`
- Get the access token from the login endpoint response

### Token Refresh
- When your access token expires, use the refresh token endpoint (#6) to get a new access token
- Store both access and refresh tokens securely

### User Roles
- **Admin**: Can create and manage employer accounts
- **Employer**: Can manage departments, branches, employees, documents, and configurations
- **Employee**: Can view and update their own profile

### Common Status Codes
- `200 OK`: Request successful
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Authentication required or token expired
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

### Query Parameters for Employee List
- `status`: Filter by employment status (ACTIVE, INACTIVE, TERMINATED, etc.)
- `department`: Filter by department UUID
- `branch`: Filter by branch UUID
- `search`: Search by name, email, or employee ID

### Testing Flow Recommendations

**1. Admin Flow:**
```
1. Login as admin (#5)
2. Create employer (#1)
3. List employers (#2)
4. Enable/disable employer (#3)
```

**2. Employer Flow:**
```
1. Activate account (#4)
2. Login (#5)
3. Complete profile (#14)
4. Create departments (#18)
5. Create branches (#23)
6. Create employees (#28)
7. Manage employee documents (#40)
8. Configure settings (#47)
```

**3. Employee Flow:**
```
1. Accept invitation (#52)
2. Login (#5)
3. Get own profile (#53)
4. Complete profile (#54)
```

---

## 🔄 TESTING TIPS

1. **Start with Admin**: Create an admin user via Django command, then test admin endpoints
2. **Create Test Employer**: Use admin endpoints to create a test employer account
3. **Use Environments**: Set up Insomnia environments for base URL and tokens
4. **Save Tokens**: Store access and refresh tokens as environment variables
5. **Test in Order**: Follow the natural flow (admin → employer → employee)
6. **Check IDs**: Copy UUIDs from responses to use in subsequent requests
7. **File Uploads**: Use multipart/form-data for document uploads (#40)

---

**Last Updated:** December 20, 2025
**API Version:** 1.0
**Base URL:** http://127.0.0.1:8000
