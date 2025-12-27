# PayrovaHR Backend

Django-based multi-tenant HR management system with advanced employee profile management and cross-employer functionality.

## 🎯 Key Features

- **Multi-Tenant Architecture**: Separate databases per employer for data isolation
- **Cross-Employer Employee Management**: Single employee can work for multiple employers
- **Smart Profile Completion**: Two-tier validation system (critical vs non-critical fields)
- **Employee Registry**: Centralized profile management across all employers
- **Automated Notifications**: Email notifications for profile completion requirements
- **Flexible Configuration**: Per-employer field requirements and validation rules
- **Duplicate Detection**: Intelligent employee duplicate detection across institutions

## 📚 New Feature: Cross-Employer Profile Completion

The system now intelligently handles scenarios where employees work for multiple employers with different profile requirements.

### Quick Links
- [Implementation Guide](PROFILE_COMPLETION_IMPLEMENTATION.md) - Comprehensive technical documentation
- [Setup Guide](PROFILE_COMPLETION_SETUP.md) - Quick setup and testing instructions
- [Visual Diagrams](PROFILE_COMPLETION_DIAGRAMS.md) - Architecture and flow diagrams
- [Deployment Checklist](DEPLOYMENT_CHECKLIST.md) - Pre/post deployment tasks
- [Implementation Summary](IMPLEMENTATION_SUMMARY.md) - Changes and features overview

### How It Works

When an employee who exists in the system joins a new employer with stricter requirements:

1. **Validation**: System checks existing profile against new employer's requirements
2. **Categorization**: Missing fields are categorized as critical (blocking) or non-critical
3. **Notification**: Employee receives clear email about what needs updating
4. **Smart Access**: Critical fields block access, non-critical fields don't
5. **Auto-Update**: Profile completion state updates automatically as employee fills fields
6. **Sync**: Changes sync to central registry, benefiting all employers

### Profile Completion States

- 🟢 **COMPLETE** - All requirements met, full access
- 🟡 **INCOMPLETE_NON_BLOCKING** - Missing optional fields, full access allowed
- 🔴 **INCOMPLETE_BLOCKING** - Missing critical fields, limited access

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- PostgreSQL (recommended for production)

### Installation

1. **Activate the virtual environment:**
   ```bash
   # Windows
   .\venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create a `.env` file in the project root:**
   ```env
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   DATABASE_URL=sqlite:///db.sqlite3
   
   # Email Configuration
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-app-password
   DEFAULT_FROM_EMAIL=HR System <noreply@yourcompany.com>
   
   # Frontend URL for email links
   FRONTEND_URL=http://localhost:3000
   ```

4. **Run migrations:**
   ```bash
   python manage.py migrate
   python manage.py migrate --database=default  # Main database
   # Tenant migrations are run automatically via migrate_tenants command
   ```

5. **Create a superuser:**
   ```bash
   python manage.py createsuperadmin
   ```

6. **Run the development server:**
   ```bash
   python manage.py runserver
   ```

The server will start at `http://127.0.0.1:8000/`

## Project Structure
## Project Structure
```
payrovaHR-backend/
├── venv/                          # Virtual environment
├── config/                        # Django project settings
│   ├── settings.py               # Main settings
│   ├── urls.py                   # URL routing
│   └── wsgi.py                   # WSGI config
├── accounts/                      # User and employer management
│   ├── models.py                 # User, EmployerProfile, EmployeeRegistry
│   ├── views.py                  # Authentication, registration
│   ├── database_router.py        # Multi-tenant routing
│   └── database_utils.py         # Tenant database utilities
├── employees/                     # Employee management
│   ├── models.py                 # Employee, Department, Branch, Configuration
│   ├── views.py                  # Employee CRUD, invitations, profile
│   ├── serializers.py            # API serializers
│   ├── utils.py                  # Validation, notifications, utilities
│   └── migrations/               # Database migrations
│       └── 0005_profile_completion_tracking.py  # New feature migration
├── templates/                     # Email and HTML templates
│   └── emails/                   # Email notification templates
│       ├── profile_completion_required.html
│       ├── profile_completion_required.txt
│       ├── employee_invitation.html
│       └── ...
├── requirements.txt               # Python dependencies
├── manage.py                     # Django management script
├── .env                          # Environment variables (create this)
├── .gitignore                    # Git ignore file
│
├── README.md                     # This file
├── PROFILE_COMPLETION_IMPLEMENTATION.md  # Feature documentation
├── PROFILE_COMPLETION_SETUP.md           # Setup guide
├── PROFILE_COMPLETION_DIAGRAMS.md        # Visual diagrams
├── DEPLOYMENT_CHECKLIST.md               # Deployment guide
└── IMPLEMENTATION_SUMMARY.md             # Changes summary
```

## API Endpoints

### Authentication & Accounts
- `POST /api/accounts/register/employer/` - Register new employer
- `POST /api/accounts/register/employee/` - Register new employee
- `POST /api/accounts/login/` - Login
- `POST /api/accounts/activate/` - Activate account

### Employees (Employer)
- `GET /api/employees/` - List all employees
- `POST /api/employees/` - Create new employee (with smart profile validation)
- `GET /api/employees/{id}/` - Get employee details
- `PATCH /api/employees/{id}/` - Update employee
- `POST /api/employees/{id}/terminate/` - Terminate employee
- `POST /api/employees/{id}/send-invitation/` - Send invitation
- `POST /api/employees/prefill-existing/` - Check existing employee (with validation)

### Invitations
- `POST /api/invitations/accept/` - Accept invitation (with profile completion check)
- `GET /api/invitations/` - List invitations

### Employee Profile (Self-Service)
- `GET /api/employee/profile/me/` - Get own profile
- `PATCH /api/employee/profile/me/` - Update own profile (auto-validates)

### Departments & Branches
- `GET /api/departments/` - List departments
- `POST /api/departments/` - Create department
- `GET /api/branches/` - List branches
- `POST /api/branches/` - Create branch

## Development

### Creating a new Django app
```bash
python manage.py startapp app_name
```

### Running tests
```bash
python manage.py test
```

### Making migrations
```bash
# For main database (accounts app)
python manage.py makemigrations accounts

# For tenant databases (employees app)
python manage.py makemigrations employees

# Apply migrations
python manage.py migrate

# Migrate all tenant databases
python manage.py migrate_tenants
```

## Multi-Tenant Commands

### Create tenant database for employer
```bash
python manage.py shell
```
```python
from accounts.models import EmployerProfile
from accounts.database_utils import create_tenant_database

employer = EmployerProfile.objects.get(id=1)
create_tenant_database(employer)
```

### Migrate all tenants
```bash
python manage.py migrate_tenants
```

## Testing the Profile Completion Feature

See [PROFILE_COMPLETION_SETUP.md](PROFILE_COMPLETION_SETUP.md) for detailed testing instructions.

Quick test:
```bash
# 1. Run migrations
python manage.py migrate employees

# 2. Create test employer
python manage.py shell
```
```python
from accounts.models import EmployerProfile
from employees.models import EmployeeConfiguration

# Configure critical fields for an employer
config = EmployeeConfiguration.objects.get(employer_id=1)
config.critical_fields = ['national_id_number', 'date_of_birth']
config.require_profile_photo = 'REQUIRED'
config.save()
```

## Environment Variables

Required in `.env`:
```env
# Django
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/payrova_hr

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=HR System <noreply@company.com>

# Frontend
FRONTEND_URL=http://localhost:3000
```

## Troubleshooting

### Profile completion not working
1. Verify migration ran: `python manage.py showmigrations employees`
2. Check configuration exists for employer
3. Review logs for validation errors

### Emails not sending
1. Check email settings in `.env`
2. Verify employee has user account
3. Check email templates exist
4. Review Django logs

### Tenant database issues
1. Ensure database was created: Check `EmployerProfile.database_created`
2. Run migrations: `python manage.py migrate_tenants`
3. Check database router configuration

## Documentation

- [Employee Account Creation](EMPLOYEE_ACCOUNT_CREATION.md)
- [Employer Account Creation](EMPLOYER_ACCOUNT_CREATION.md)  
- [Password Reset Implementation](PASSWORD_RESET_IMPLEMENTATION.md)
- [API Documentation](README_API.md)
- [User Manual](USER_MANUAL.md)
- [Insomnia API Endpoints](INSOMNIA_API_ENDPOINTS.md)

## Contributing

1. Create a feature branch
2. Make your changes
3. Write tests
4. Submit a pull request

## License

[Your License Here]

## Support

For issues or questions:
- Check the documentation files
- Review the deployment checklist
- Check Django logs
- Contact the development team
