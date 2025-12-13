# Django HR Application - Multi-Tenant Authentication & Onboarding System

A comprehensive Django-based HR application with multi-tenant support, featuring advanced authentication, 2FA, and employer onboarding system.

## Features

- ✅ Custom User Model with email-based authentication
- ✅ Multi-tenant support for HR firms and institutions
- ✅ Secure account activation flow with time-limited tokens
- ✅ JWT-based authentication with refresh tokens
- ✅ Two-Factor Authentication (2FA) using TOTP
- ✅ Comprehensive employer profile management
- ✅ Rate limiting on sensitive endpoints
- ✅ Professional email templates
- ✅ Admin management commands
- ✅ Consistent API response format

## Tech Stack

- **Django 5.2+**
- **Django REST Framework**
- **PostgreSQL**
- **JWT Authentication** (djangorestframework-simplejwt)
- **2FA Support** (pyotp, qrcode)
- **Email Backend** (django-anymail)
- **Rate Limiting** (django-ratelimit)

## Installation

### Prerequisites

- Python 3.10+
- PostgreSQL 12+
- Virtual environment

### Setup Steps

1. **Clone the repository**
```bash
cd "c:\Users\user\Documents\HR\HR Backend"
```

2. **Activate virtual environment**
```bash
.\venv\Scripts\Activate.ps1
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**

Update `.env` file with your settings:
```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Settings
DB_NAME=payrova
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432

# Email Settings
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@payrova.com

# Frontend URL
FRONTEND_URL=http://localhost:3000
```

5. **Create database**

Ensure PostgreSQL is running and create the database:
```sql
CREATE DATABASE payrova;
```

6. **Run migrations**
```bash
python manage.py makemigrations
python manage.py migrate
```

7. **Create super admin**
```bash
python manage.py createsuperadmin --email admin@payrova.com
# You'll be prompted to enter password
```

8. **Run development server**
```bash
python manage.py runserver
```

The API will be available at: `http://localhost:8000/api/`

## API Documentation

### Base URL
```
http://localhost:8000/api/
```

### Response Format

All API responses follow this consistent format:
```json
{
  "success": true,
  "message": "Operation successful",
  "data": {},
  "errors": []
}
```

---

## Authentication Endpoints

### 1. Create Employer Account (Admin Only)

**Endpoint:** `POST /api/admin/create-employer/`

**Headers:**
```
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "email": "employer@company.com"
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "Employer account created successfully. Activation email sent.",
  "data": {
    "user": {
      "id": 2,
      "email": "employer@company.com",
      "is_admin": false,
      "is_employer": true,
      "profile_completed": false,
      "two_factor_enabled": false,
      "created_at": "2025-12-13T10:30:00Z"
    },
    "activation_token": null
  },
  "errors": []
}
```

---

### 2. Activate Account

**Endpoint:** `POST /api/auth/activate/`

**Rate Limit:** 5 requests per hour per IP

**Request Body:**
```json
{
  "token": "activation_token_from_email",
  "password": "NewSecurePassword123!",
  "confirm_password": "NewSecurePassword123!"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Account activated successfully. You can now log in.",
  "data": {
    "user": {
      "id": 2,
      "email": "employer@company.com",
      "is_active": true,
      "profile_completed": false
    }
  },
  "errors": []
}
```

**Error Response (400):**
```json
{
  "success": false,
  "message": "Failed to activate account.",
  "data": {},
  "errors": {
    "token": ["Invalid activation token."],
    "confirm_password": ["Passwords do not match."]
  }
}
```

---

### 3. Login

**Endpoint:** `POST /api/auth/login/`

**Rate Limit:** 10 requests per hour per IP

**Request Body (without 2FA):**
```json
{
  "email": "employer@company.com",
  "password": "YourPassword123!"
}
```

**Request Body (with 2FA enabled):**
```json
{
  "email": "employer@company.com",
  "password": "YourPassword123!",
  "two_factor_code": "123456"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Login successful.",
  "data": {
    "user": {
      "id": 2,
      "email": "employer@company.com",
      "first_name": "",
      "last_name": "",
      "is_admin": false,
      "is_employer": true,
      "profile_completed": false,
      "two_factor_enabled": false
    },
    "tokens": {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    },
    "profile_incomplete": true
  },
  "errors": []
}
```

**Error Response (400 - 2FA Required):**
```json
{
  "success": false,
  "message": "Login failed.",
  "data": {},
  "errors": {
    "two_factor_code": ["2FA is enabled. Please provide authentication code."],
    "requires_2fa": true
  }
}
```

---

### 4. Refresh Token

**Endpoint:** `POST /api/auth/token/refresh/`

**Request Body:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response (200):**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

---

## Two-Factor Authentication (2FA) Endpoints

### 5. Setup 2FA

**Endpoint:** `POST /api/auth/2fa/setup/`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "message": "2FA setup initiated. Scan the QR code with your authenticator app.",
  "data": {
    "secret": "JBSWY3DPEHPK3PXP",
    "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
  },
  "errors": []
}
```

---

### 6. Verify and Enable 2FA

**Endpoint:** `POST /api/auth/2fa/verify/`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "verification_code": "123456"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "2FA enabled successfully.",
  "data": {
    "user": {
      "two_factor_enabled": true
    }
  },
  "errors": []
}
```

---

### 7. Disable 2FA

**Endpoint:** `POST /api/auth/2fa/disable/`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "password": "YourPassword123!"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "2FA disabled successfully.",
  "data": {
    "user": {
      "two_factor_enabled": false
    }
  },
  "errors": []
}
```

---

## Profile Endpoints

### 8. Get User Profile

**Endpoint:** `GET /api/profile/`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "success": true,
  "message": "User profile retrieved successfully.",
  "data": {
    "id": 2,
    "email": "employer@company.com",
    "first_name": "John",
    "last_name": "Doe",
    "is_employer": true,
    "profile_completed": true,
    "two_factor_enabled": false,
    "employer_profile": {
      "company_name": "Tech Corp",
      "employer_name_or_group": "Tech Group",
      "organization_type": "PRIVATE",
      "industry_sector": "Technology",
      ...
    }
  },
  "errors": []
}
```

---

### 9. Complete Employer Profile (First Login)

**Endpoint:** `POST /api/employer/profile/complete/`

**Headers:**
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "company_name": "Tech Corporation Ltd",
  "employer_name_or_group": "Tech Group",
  "organization_type": "PRIVATE",
  "industry_sector": "Technology",
  "date_of_incorporation": "2020-01-15",
  "company_location": "Douala",
  "physical_address": "123 Business Street, Akwa, Douala",
  "phone_number": "+237699123456",
  "fax_number": "+237233123456",
  "official_company_email": "contact@techcorp.cm",
  "rccm": "RC/DLA/2020/B/12345",
  "taxpayer_identification_number": "M012345678901Z",
  "cnps_employer_number": "1234567",
  "labour_inspectorate_declaration": "DIT/DLA/2020/123",
  "business_license": "P2020/12345",
  "bank_name": "Afriland First Bank",
  "bank_account_number": "10002000300040005",
  "bank_iban_swift": "CCBACMCXXXX"
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "Employer profile completed successfully.",
  "data": {
    "id": 1,
    "company_name": "Tech Corporation Ltd",
    "employer_name_or_group": "Tech Group",
    ...
  },
  "errors": []
}
```

---

### 10. Get/Update Employer Profile

**Endpoint:** `GET /api/employer/profile/`
**Endpoint:** `PUT /api/employer/profile/`
**Endpoint:** `PATCH /api/employer/profile/` (partial update)

**Headers:**
```
Authorization: Bearer <access_token>
```

**GET Response (200):**
```json
{
  "success": true,
  "message": "Employer profile retrieved successfully.",
  "data": {
    "id": 1,
    "company_name": "Tech Corporation Ltd",
    "employer_name_or_group": "Tech Group",
    "organization_type": "PRIVATE",
    "industry_sector": "Technology",
    "date_of_incorporation": "2020-01-15",
    "company_location": "Douala",
    "physical_address": "123 Business Street, Akwa, Douala",
    "phone_number": "+237699123456",
    "fax_number": "+237233123456",
    "official_company_email": "contact@techcorp.cm",
    "rccm": "RC/DLA/2020/B/12345",
    "taxpayer_identification_number": "M012345678901Z",
    "cnps_employer_number": "1234567",
    "labour_inspectorate_declaration": "DIT/DLA/2020/123",
    "business_license": "P2020/12345",
    "bank_name": "Afriland First Bank",
    "bank_account_number": "10002000300040005",
    "bank_iban_swift": "CCBACMCXXXX",
    "created_at": "2025-12-13T12:00:00Z",
    "updated_at": "2025-12-13T12:00:00Z"
  },
  "errors": []
}
```

---

## Testing the API

### Using Django Admin

1. Access admin panel: `http://localhost:8000/admin/`
2. Login with super admin credentials
3. View and manage users, activation tokens, and employer profiles

### Using cURL

**Login as admin:**
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@payrova.com", "password": "Admin@123456"}'
```

**Create employer account:**
```bash
curl -X POST http://localhost:8000/api/admin/create-employer/ \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "employer@company.com"}'
```

**Activate account:**
```bash
curl -X POST http://localhost:8000/api/auth/activate/ \
  -H "Content-Type: application/json" \
  -d '{
    "token": "activation_token_from_email",
    "password": "SecurePassword123!",
    "confirm_password": "SecurePassword123!"
  }'
```

---

## Management Commands

### Create Super Admin

```bash
python manage.py createsuperadmin --email admin@example.com --password YourPassword
```

Or without password (will prompt):
```bash
python manage.py createsuperadmin --email admin@example.com
```

---

## Security Features

- ✅ **Password Validation**: Enforces Django's password validators
- ✅ **Rate Limiting**: Protects against brute force attacks
- ✅ **Token Expiration**: Activation tokens expire after 48 hours
- ✅ **JWT Tokens**: Secure token-based authentication
- ✅ **2FA Support**: Optional TOTP-based two-factor authentication
- ✅ **CSRF Protection**: Built-in Django CSRF protection
- ✅ **HTTPS Ready**: Configured for production SSL/TLS

---

## Project Structure

```
HR Backend/
├── accounts/                       # Authentication app
│   ├── management/
│   │   └── commands/
│   │       └── createsuperadmin.py # Super admin command
│   ├── migrations/
│   ├── admin.py                   # Admin configuration
│   ├── models.py                  # User, ActivationToken, EmployerProfile
│   ├── serializers.py             # DRF serializers
│   ├── views.py                   # API views
│   ├── urls.py                    # App URLs
│   └── utils.py                   # Utility functions
├── config/                        # Project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── templates/
│   └── emails/                    # Email templates
│       ├── activation_email.html
│       └── activation_email.txt
├── .env                           # Environment variables
├── manage.py
├── requirements.txt
└── README_API.md                  # This file
```

---

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | - |
| `DEBUG` | Debug mode | `True` |
| `ALLOWED_HOSTS` | Allowed hosts | `localhost,127.0.0.1` |
| `DB_NAME` | Database name | `payrova` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | - |
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `EMAIL_BACKEND` | Email backend | `console` |
| `EMAIL_HOST` | SMTP host | `smtp.gmail.com` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_HOST_USER` | Email username | - |
| `EMAIL_HOST_PASSWORD` | Email password | - |
| `FRONTEND_URL` | Frontend URL | `http://localhost:3000` |

---

## Common Issues & Solutions

### 1. Database Connection Error
```bash
# Ensure PostgreSQL is running
# Verify database credentials in .env file
```

### 2. Email Not Sending
```bash
# For development, use console backend (default)
# Check email configuration in .env
# Ensure EMAIL_HOST_USER has app password for Gmail
```

### 3. Token Expired
```bash
# Tokens expire after 48 hours
# Admin must create a new account or resend activation
```

---

## Next Steps

1. **Frontend Integration**: Build React/Vue frontend
2. **Multi-tenancy**: Implement tenant-specific database routing
3. **Email Service**: Configure production email service (SendGrid, Mailgun)
4. **File Uploads**: Add document upload for legal documents
5. **API Testing**: Add comprehensive test suite
6. **Docker**: Containerize the application
7. **CI/CD**: Setup automated deployment pipeline

---

## Support

For issues or questions, please contact the development team.

---

## License

Proprietary - All rights reserved © 2025 Payrova HR
