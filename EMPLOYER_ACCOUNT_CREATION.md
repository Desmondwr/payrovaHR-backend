# Employer Account Creation Guide

## Overview
This guide provides complete documentation for the employer registration and account setup process. The system uses a multi-tenant architecture where each employer gets their own isolated database for their employee data.

## Architecture Context

### Database Structure
- **Default Database**: Stores user accounts, employer profiles, and central employee registry
- **Tenant Databases**: Each employer gets a dedicated database (schema) for their employee data

### Key Components
- User authentication (JWT-based)
- Employer profile management
- Automatic tenant database creation
- Database migration handling

---

## Complete Registration Flow

### Step 1: Employer Registration

**Endpoint**: `POST /api/accounts/employer/register/`

**Purpose**: Creates a new employer account with user credentials and company information. This automatically triggers tenant database creation.

**Request Headers**:
```
Content-Type: application/json
```

**Request Body**:
```json
{
  "email": "employer@company.com",
  "password": "SecurePassword123!",
  "password_confirm": "SecurePassword123!",
  "company_name": "Tech Solutions Inc",
  "business_registration_number": "BRN123456789",
  "industry": "Information Technology",
  "company_size": "50-200",
  "contact_number": "+1234567890",
  "address": "123 Business Street, Tech City, TC 12345"
}
```

**Required Fields**:
- `email`: Valid email address (used for login)
- `password`: Minimum 8 characters
- `password_confirm`: Must match password
- `company_name`: Your company/organization name
- `business_registration_number`: Official business registration number
- `industry`: Industry sector
- `company_size`: Number of employees (e.g., "1-10", "11-50", "50-200", "200+")
- `contact_number`: Contact phone number
- `address`: Complete business address

**Success Response** (201 Created):
```json
{
  "message": "Employer registered successfully. A tenant database has been created for your company.",
  "user": {
    "id": 1,
    "email": "employer@company.com",
    "is_employer": true,
    "is_employee": false,
    "is_admin": false
  },
  "employer_profile": {
    "id": 1,
    "company_name": "Tech Solutions Inc",
    "business_registration_number": "BRN123456789",
    "industry": "Information Technology",
    "company_size": "50-200",
    "contact_number": "+1234567890",
    "address": "123 Business Street, Tech City, TC 12345",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z"
  },
  "tenant_db_name": "tenant_brn123456789",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**What Happens Behind the Scenes**:
1. Creates a User account with `is_employer=True`
2. Creates an EmployerProfile linked to the user
3. Generates a unique tenant database name based on business registration number
4. Creates the tenant database schema in PostgreSQL
5. Runs all migrations on the new tenant database
6. Returns JWT access and refresh tokens for immediate login

**Error Responses**:

**400 Bad Request** - Validation errors:
```json
{
  "email": ["User with this email already exists."],
  "password": ["This password is too short. It must contain at least 8 characters."],
  "password_confirm": ["Passwords do not match."],
  "business_registration_number": ["Employer with this business registration number already exists."]
}
```

**500 Internal Server Error** - Database creation failure:
```json
{
  "error": "Failed to create tenant database",
  "details": "Database 'tenant_brn123456789' already exists"
}
```

---

### Step 2: Login (After Registration)

**Endpoint**: `POST /api/accounts/login/`

**Purpose**: Authenticate and obtain JWT tokens for API access.

**Request Body**:
```json
{
  "email": "employer@company.com",
  "password": "SecurePassword123!"
}
```

**Success Response** (200 OK):
```json
{
  "message": "Login successful",
  "user": {
    "id": 1,
    "email": "employer@company.com",
    "is_employer": true,
    "is_employee": false,
    "is_admin": false
  },
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Error Responses**:

**401 Unauthorized** - Invalid credentials:
```json
{
  "error": "Invalid credentials"
}
```

**403 Forbidden** - Account inactive:
```json
{
  "error": "Account is inactive. Please contact support."
}
```

---

### Step 3: Get Employer Profile

**Endpoint**: `GET /api/accounts/employer/profile/`

**Purpose**: Retrieve full employer profile details.

**Request Headers**:
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
Content-Type: application/json
```

**Success Response** (200 OK):
```json
{
  "id": 1,
  "user": {
    "id": 1,
    "email": "employer@company.com",
    "is_employer": true
  },
  "company_name": "Tech Solutions Inc",
  "business_registration_number": "BRN123456789",
  "industry": "Information Technology",
  "company_size": "50-200",
  "contact_number": "+1234567890",
  "address": "123 Business Street, Tech City, TC 12345",
  "is_active": true,
  "tenant_db_name": "tenant_brn123456789",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Error Responses**:

**401 Unauthorized** - Invalid or expired token:
```json
{
  "detail": "Given token not valid for any token type"
}
```

**403 Forbidden** - Not an employer:
```json
{
  "error": "Only employers can access this endpoint"
}
```

**404 Not Found** - Profile doesn't exist:
```json
{
  "error": "Employer profile not found"
}
```

---

### Step 4: Update Employer Profile

**Endpoint**: `PUT /api/accounts/employer/profile/`  
or  
**Endpoint**: `PATCH /api/accounts/employer/profile/` (for partial updates)

**Purpose**: Update employer profile information.

**Request Headers**:
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
Content-Type: application/json
```

**Request Body** (all fields optional for PATCH):
```json
{
  "company_name": "Tech Solutions International Inc",
  "industry": "Software Development",
  "company_size": "200+",
  "contact_number": "+1234567899",
  "address": "456 Innovation Boulevard, Tech City, TC 12346"
}
```

**Note**: `business_registration_number` and `tenant_db_name` cannot be updated after creation.

**Success Response** (200 OK):
```json
{
  "id": 1,
  "user": {
    "id": 1,
    "email": "employer@company.com",
    "is_employer": true
  },
  "company_name": "Tech Solutions International Inc",
  "business_registration_number": "BRN123456789",
  "industry": "Software Development",
  "company_size": "200+",
  "contact_number": "+1234567899",
  "address": "456 Innovation Boulevard, Tech City, TC 12346",
  "is_active": true,
  "tenant_db_name": "tenant_brn123456789",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-20T14:25:00Z"
}
```

---

### Step 5: Refresh Access Token

**Endpoint**: `POST /api/accounts/token/refresh/`

**Purpose**: Obtain a new access token using the refresh token when the access token expires.

**Request Body**:
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Success Response** (200 OK):
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Error Response**:

**401 Unauthorized** - Invalid refresh token:
```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

---

## Token Management

### JWT Token Structure
- **Access Token**: Valid for 60 minutes (used for API authentication)
- **Refresh Token**: Valid for 7 days (used to obtain new access tokens)

### Using Tokens in API Calls
Include the access token in the Authorization header:
```
Authorization: Bearer <access_token>
```

### Token Lifecycle
1. Register or login → Receive both access and refresh tokens
2. Use access token for all API calls
3. When access token expires (after 60 minutes) → Use refresh token to get new access token
4. When refresh token expires (after 7 days) → User must login again

---

## Example: Complete Registration Flow (Python)

```python
import requests
import json

BASE_URL = "http://localhost:8000/api"

# Step 1: Register new employer
registration_data = {
    "email": "employer@company.com",
    "password": "SecurePassword123!",
    "password_confirm": "SecurePassword123!",
    "company_name": "Tech Solutions Inc",
    "business_registration_number": "BRN123456789",
    "industry": "Information Technology",
    "company_size": "50-200",
    "contact_number": "+1234567890",
    "address": "123 Business Street, Tech City, TC 12345"
}

response = requests.post(
    f"{BASE_URL}/accounts/employer/register/",
    json=registration_data
)

if response.status_code == 201:
    data = response.json()
    print("Registration successful!")
    print(f"Company: {data['employer_profile']['company_name']}")
    print(f"Tenant DB: {data['tenant_db_name']}")
    
    # Save tokens
    access_token = data['access_token']
    refresh_token = data['refresh_token']
    
    # Step 2: Use access token to get profile
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    profile_response = requests.get(
        f"{BASE_URL}/accounts/employer/profile/",
        headers=headers
    )
    
    if profile_response.status_code == 200:
        profile = profile_response.json()
        print(f"Profile retrieved: {profile['company_name']}")
    
    # Step 3: Update profile
    update_data = {
        "contact_number": "+1234567899",
        "address": "456 New Address, Tech City, TC 12346"
    }
    
    update_response = requests.patch(
        f"{BASE_URL}/accounts/employer/profile/",
        json=update_data,
        headers=headers
    )
    
    if update_response.status_code == 200:
        updated_profile = update_response.json()
        print(f"Profile updated: {updated_profile['contact_number']}")
        
else:
    print("Registration failed:", response.json())
```

---

## Example: cURL Commands

### Register Employer
```bash
curl -X POST http://localhost:8000/api/accounts/employer/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "employer@company.com",
    "password": "SecurePassword123!",
    "password_confirm": "SecurePassword123!",
    "company_name": "Tech Solutions Inc",
    "business_registration_number": "BRN123456789",
    "industry": "Information Technology",
    "company_size": "50-200",
    "contact_number": "+1234567890",
    "address": "123 Business Street, Tech City, TC 12345"
  }'
```

### Login
```bash
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "employer@company.com",
    "password": "SecurePassword123!"
  }'
```

### Get Profile
```bash
curl -X GET http://localhost:8000/api/accounts/employer/profile/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

### Update Profile
```bash
curl -X PATCH http://localhost:8000/api/accounts/employer/profile/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "contact_number": "+1234567899",
    "address": "456 New Address, Tech City, TC 12346"
  }'
```

---

## Troubleshooting

### Common Issues

**1. "Employer with this business registration number already exists"**
- Solution: Use a unique business registration number or contact support if you believe this is an error

**2. "Failed to create tenant database"**
- Solution: Check database permissions and ensure PostgreSQL is running
- Contact system administrator

**3. "Token is invalid or expired"**
- Solution: Use refresh token to get a new access token, or login again if refresh token has expired

**4. "Only employers can access this endpoint"**
- Solution: Ensure you're logged in with an employer account, not an employee account

---

## Security Best Practices

1. **Store tokens securely**: Never expose tokens in client-side code or URLs
2. **Use HTTPS**: Always use HTTPS in production
3. **Implement token refresh**: Automatically refresh tokens before expiry
4. **Handle logout**: Clear tokens from storage on logout
5. **Validate input**: Always validate and sanitize user input on the frontend
6. **Rate limiting**: Implement rate limiting for registration and login endpoints

---

## Next Steps

After successful employer registration:
1. Configure your company settings
2. Create departments and branches
3. Start adding employees (see EMPLOYEE_ACCOUNT_CREATION.md)
4. Set up payroll configurations
5. Configure leave policies

---

## Support

For issues or questions:
- Check the API documentation: README_API.md
- Review employee creation guide: EMPLOYEE_ACCOUNT_CREATION.md
- Contact technical support
