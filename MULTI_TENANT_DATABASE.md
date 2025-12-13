# Multi-Tenant Database Architecture

## Overview
The HR application now supports **automatic tenant database creation** for each employer. When an employer completes their profile, a dedicated PostgreSQL database is automatically created for their organization.

## Architecture

### Database Structure
- **Default Database (`payrova`)**: Stores all authentication data, user accounts, employer profiles, and activation tokens
- **Tenant Databases (`payrova_[company_name]`)**: Each employer gets a separate database for their employees and company-specific data

### How It Works

1. **Admin Creates Employer Account**
   - Employer user created in default database
   - Activation email sent

2. **Employer Activates Account**
   - Sets password
   - Account activated in default database

3. **Employer Completes Profile** ⭐ (Database Creation Trigger)
   - When employer submits profile completion
   - System automatically:
     - Sanitizes company name to create database name (e.g., "Tech Corporation Ltd" → `payrova_tech_corporation_ltd`)
     - Creates new PostgreSQL database
     - Runs all migrations on new database
     - Updates employer profile with database info
     - Returns success with database name

4. **Future Operations**
   - Employer's employees and data stored in their tenant database
   - Authentication still happens in default database
   - Database router handles query routing automatically

## Key Components

### 1. EmployerProfile Model (Updated)
```python
# New fields added:
database_name = CharField()           # Name of tenant database
database_created = BooleanField()     # Whether DB exists
database_created_at = DateTimeField() # When DB was created
```

### 2. Database Utilities (`accounts/database_utils.py`)
- `create_tenant_database()` - Creates new PostgreSQL database and runs migrations
- `sanitize_database_name()` - Converts company name to safe DB name
- `database_exists()` - Checks if database already exists
- `delete_tenant_database()` - Removes tenant database (admin use only)

### 3. Database Router (`accounts/database_router.py`)
Routes queries to appropriate databases:
- Auth models → default database
- Tenant-specific data → tenant database
- Controls migration targets

### 4. Updated Views
**CompleteEmployerProfileView** now:
- Creates employer profile
- Automatically creates tenant database
- Returns database creation status

## API Response Example

```json
{
  "success": true,
  "message": "Employer profile completed successfully. Tenant database 'payrova_tech_corporation_ltd' created.",
  "data": {
    "profile": {
      "company_name": "Tech Corporation Ltd",
      "database_name": "payrova_tech_corporation_ltd",
      "database_created": true,
      "database_created_at": "2025-12-13T15:30:45.123456Z",
      ...
    },
    "database_created": true,
    "database_name": "payrova_tech_corporation_ltd"
  }
}
```

## Database Naming Convention

Company names are sanitized:
- Converted to lowercase
- Spaces → underscores
- Special characters removed
- Prefixed with `payrova_`
- Limited to 50 characters
- Made unique with counter if needed

Examples:
- "Tech Corporation Ltd" → `payrova_tech_corporation_ltd`
- "ABC Company" → `payrova_abc_company`
- "Company #1!" → `payrova_company_1`

## Configuration

### Settings Updates
```python
# Database router enabled
DATABASE_ROUTERS = ['accounts.database_router.TenantDatabaseRouter']

# Thread-local storage for tenant context
CURRENT_TENANT_DB = None
```

## Testing the Flow

### 1. Admin Login
```bash
POST /api/auth/login/
{
  "email": "admin@payrova.com",
  "password": "Admin@123456"
}
```

### 2. Create Employer
```bash
POST /api/admin/create-employer/
Authorization: Bearer {admin_token}
{
  "email": "employer@techcorp.com"
}
```

### 3. Check Console for Activation Token
The activation email will be displayed in the Django console.

### 4. Activate Employer Account
```bash
POST /api/auth/activate/
{
  "token": "{activation_token}",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!"
}
```

### 5. Login as Employer
```bash
POST /api/auth/login/
{
  "email": "employer@techcorp.com",
  "password": "SecurePass123!"
}
```

### 6. Complete Profile (This Creates Database!)
```bash
POST /api/employer/profile/complete/
Authorization: Bearer {employer_token}
{
  "company_name": "Tech Corporation Ltd",
  "employer_name_or_group": "Tech Group",
  "organization_type": "PRIVATE",
  "industry_sector": "Technology",
  "date_of_incorporation": "2020-01-15",
  "company_location": "Douala",
  "physical_address": "123 Business Street",
  "phone_number": "+237699123456",
  "official_company_email": "contact@techcorp.cm",
  "rccm": "RC/DLA/2020/B/12345",
  "taxpayer_identification_number": "M012345678901Z",
  "cnps_employer_number": "1234567",
  "labour_inspectorate_declaration": "DIT/DLA/2020/123",
  "business_license": "P2020/12345",
  "bank_name": "Afriland First Bank",
  "bank_account_number": "10002000300040005"
}
```

**Expected Result:**
- Employer profile created ✅
- New database `payrova_tech_corporation_ltd` created ✅
- All tables migrated to new database ✅
- Response includes database name and creation status ✅

### 7. Verify Database Creation

Check PostgreSQL:
```sql
SELECT datname FROM pg_database WHERE datname LIKE 'payrova_%';
```

## Troubleshooting

### Database Creation Fails
- Check PostgreSQL user has `CREATEDB` privilege
- Verify database connection settings
- Check logs for specific error messages

### Migration Errors
- Ensure default database is fully migrated first
- Check database router configuration
- Verify PostgreSQL version compatibility

## Security Considerations

1. **PostgreSQL Permissions**: Database user needs `CREATEDB` privilege
2. **Database Isolation**: Each employer's data is completely isolated
3. **Access Control**: Router ensures queries go to correct database
4. **Naming**: Sanitization prevents SQL injection through database names

## Future Enhancements

- Database connection pooling for tenant databases
- Automated backup scheduling per tenant
- Database size monitoring and alerts
- Multi-region database support
- Tenant database archival/deletion workflows
