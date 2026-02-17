"""
Utility functions for multi-tenant database management
"""
import re
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def sanitize_database_name(company_name):
    """
    Create a safe database name from company name
    - Converts to lowercase
    - Removes special characters
    - Replaces spaces with underscores
    - Limits length to 50 characters
    """
    # Convert to lowercase and replace spaces with underscores
    db_name = company_name.lower().replace(' ', '_')
    
    # Remove any characters that aren't alphanumeric or underscore
    db_name = re.sub(r'[^a-z0-9_]', '', db_name)
    
    # Ensure it starts with a letter (PostgreSQL requirement)
    if db_name and not db_name[0].isalpha():
        db_name = 'tenant_' + db_name
    
    # Limit length and add prefix
    db_name = f"payrova_{db_name[:40]}"
    
    return db_name


def create_tenant_database(employer_profile):
    """
    Create a new PostgreSQL database for the employer tenant
    Returns: (success: bool, database_name: str, error_message: str)
    """
    try:
        # Generate database name from company name
        db_name = sanitize_database_name(employer_profile.company_name)
        
        # Ensure unique database name
        counter = 1
        original_db_name = db_name
        while database_exists(db_name):
            db_name = f"{original_db_name}_{counter}"
            counter += 1
        
        # Get default database configuration
        default_db = settings.DATABASES['default']
        
        # Connect to PostgreSQL to create new database
        conn = psycopg2.connect(
            dbname='postgres',  # Connect to default postgres database
            user=default_db['USER'],
            password=default_db['PASSWORD'],
            host=default_db['HOST'],
            port=default_db['PORT']
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Create the database
        cursor.execute(f'CREATE DATABASE {db_name}')
        cursor.close()
        conn.close()
        
        logger.info(f"Successfully created database: {db_name}")
        
        # Add database to Django connections
        add_tenant_database_to_settings(db_name, employer_profile.id)
        
        # Run migrations on the new database
        run_migrations_on_tenant_database(db_name, employer_profile.id)
        
        # Update employer profile
        employer_profile.database_name = db_name
        employer_profile.database_created = True
        employer_profile.database_created_at = timezone.now()
        employer_profile.save(update_fields=['database_name', 'database_created', 'database_created_at'])
        
        return True, db_name, None
        
    except psycopg2.Error as e:
        error_msg = f"PostgreSQL error creating database: {str(e)}"
        logger.error(error_msg)
        return False, None, error_msg
        
    except Exception as e:
        error_msg = f"Error creating tenant database: {str(e)}"
        logger.error(error_msg)
        return False, None, error_msg


def database_exists(db_name):
    """
    Check if a database exists in PostgreSQL
    """
    try:
        default_db = settings.DATABASES['default']
        conn = psycopg2.connect(
            dbname='postgres',
            user=default_db['USER'],
            password=default_db['PASSWORD'],
            host=default_db['HOST'],
            port=default_db['PORT']
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,)
        )
        exists = cursor.fetchone() is not None
        
        cursor.close()
        conn.close()
        
        return exists
        
    except Exception as e:
        logger.error(f"Error checking database existence: {str(e)}")
        return False


def add_tenant_database_to_settings(db_name, employer_id):
    """
    Dynamically add tenant database configuration to Django settings
    """
    alias = f"tenant_{employer_id}"
    default_db = settings.DATABASES['default']
    
    # Create a copy of the default database configuration
    tenant_db_config = default_db.copy()
    
    # Override the NAME with the tenant database name
    tenant_db_config['NAME'] = db_name
    
    settings.DATABASES[alias] = tenant_db_config
    
    # Ensure the connection is available
    connections.databases[alias] = settings.DATABASES[alias]
    
    logger.info(f"Added database configuration for alias: {alias}")


def run_migrations_on_tenant_database(db_name, employer_id):
    """
    Run Django migrations on the newly created tenant database
    """
    try:
        alias = f"tenant_{employer_id}"
        
        # Run migrations for tenant-specific apps
        call_command('migrate', 'employees', database=alias, verbosity=2)
        call_command('migrate', 'contracts', database=alias, verbosity=2)
        call_command('migrate', 'payroll', database=alias, verbosity=2)
        call_command('migrate', 'timeoff', database=alias, verbosity=2)
        call_command('migrate', 'frontdesk', database=alias, verbosity=2)
        call_command('migrate', 'attendance', database=alias, verbosity=2)
        call_command('migrate', 'treasury', database=alias, verbosity=2)
        call_command('migrate', 'income_expense', database=alias, verbosity=2)
        call_command('migrate', 'recruitment', database=alias, verbosity=2)
        
        logger.info(f"Successfully ran migrations on database: {db_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error running migrations on {db_name}: {str(e)}")
        return False


def get_tenant_database_alias(employer_profile):
    """
    Get the database alias for an employer's tenant database
    Returns 'default' if no tenant database exists
    """
    if employer_profile and employer_profile.database_name:
        return f"tenant_{employer_profile.id}"
    return 'default'


def delete_tenant_database(employer_profile):
    """
    Delete a tenant database (use with caution!)
    This is for testing or when removing an employer
    """
    try:
        if not employer_profile.database_name:
            return False, "No database to delete"
        
        db_name = employer_profile.database_name
        default_db = settings.DATABASES['default']
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            dbname='postgres',
            user=default_db['USER'],
            password=default_db['PASSWORD'],
            host=default_db['HOST'],
            port=default_db['PORT']
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Terminate all connections to the database
        cursor.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{db_name}'
            AND pid <> pg_backend_pid()
        """)
        
        # Drop the database
        cursor.execute(f'DROP DATABASE IF EXISTS {db_name}')
        cursor.close()
        conn.close()
        
        # Update employer profile
        employer_profile.database_name = None
        employer_profile.database_created = False
        employer_profile.database_created_at = None
        employer_profile.save(update_fields=['database_name', 'database_created', 'database_created_at'])
        
        logger.info(f"Successfully deleted database: {db_name}")
        return True, None
        
    except Exception as e:
        error_msg = f"Error deleting tenant database: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def load_all_tenant_databases():
    """
    Load all existing tenant databases into Django settings.
    This should be called on application startup to ensure all
    tenant database connections are available.
    """
    try:
        # Import here to avoid circular imports
        from accounts.models import EmployerProfile
        
        # Get all employers with created databases
        employer_profiles = EmployerProfile.objects.filter(
            database_created=True,
            database_name__isnull=False
        )
        
        loaded_count = 0
        for employer in employer_profiles:
            alias = f"tenant_{employer.id}"
            
            # Skip if already loaded
            if alias in settings.DATABASES:
                continue
            
            # Add to settings
            default_db = settings.DATABASES['default']
            tenant_db_config = default_db.copy()
            tenant_db_config['NAME'] = employer.database_name
            
            settings.DATABASES[alias] = tenant_db_config
            connections.databases[alias] = settings.DATABASES[alias]
            
            loaded_count += 1
            logger.info(f"Loaded tenant database: {alias} ({employer.database_name})")
        
        logger.info(f"Successfully loaded {loaded_count} tenant database(s)")
        return loaded_count
        
    except Exception as e:
        logger.error(f"Error loading tenant databases: {str(e)}")
        return 0


def ensure_tenant_database_loaded(employer_profile):
    """
    Ensure a specific tenant database is loaded into Django settings.
    Returns the database alias.
    """
    if not employer_profile or not employer_profile.database_name:
        return 'default'
    
    alias = f"tenant_{employer_profile.id}"
    
    # Check if already loaded
    if alias not in settings.DATABASES:
        # Load it now
        default_db = settings.DATABASES['default']
        tenant_db_config = default_db.copy()
        tenant_db_config['NAME'] = employer_profile.database_name
        
        settings.DATABASES[alias] = tenant_db_config
        connections.databases[alias] = settings.DATABASES[alias]
        
        logger.info(f"Dynamically loaded tenant database: {alias} ({employer_profile.database_name})")
    
    return alias


def get_employee_tenant_db_from_membership(request, require_context=None):
    """
    Resolve tenant database alias for an authenticated employee based on membership.
    
    Priority:
    1) Explicit employer context via header X-Employer-Id (preferred) or ?employer_id= query param
    2) last_active_employer_id stored on the user (if present)
    3) Legacy fallback to request.user.employee_profile when feature flag is disabled
    """
    from accounts.models import EmployeeMembership, EmployerProfile  # Imported locally to avoid circular imports
    from rest_framework.exceptions import PermissionDenied, ParseError

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    require_context = (
        require_context
        if require_context is not None
        else getattr(settings, 'REQUIRE_EMPLOYER_CONTEXT_FOR_EMPLOYEE_ENDPOINTS', False)
    )

    employer_id = None
    header_value = request.headers.get('X-Employer-Id') if hasattr(request, 'headers') else None
    query_params = getattr(request, 'query_params', None) or getattr(request, 'GET', {})
    query_value = query_params.get('employer_id') if query_params is not None else None

    raw_employer_id = header_value or query_value
    if raw_employer_id:
        try:
            employer_id = int(raw_employer_id)
        except (TypeError, ValueError):
            raise ParseError("Invalid employer id provided.")

    membership = None
    employer_profile = None

    if employer_id is not None:
        membership = EmployeeMembership.objects.filter(
            user_id=user.id,
            employer_profile_id=employer_id,
        ).select_related('employer_profile').first()
        if not membership:
            raise PermissionDenied("You do not have access to the requested employer.")
        if membership.status != EmployeeMembership.STATUS_ACTIVE:
            raise PermissionDenied("Your membership with this employer is not active.")
        employer_profile = membership.employer_profile
    else:
        # Allow implicit resolution only when the feature flag is disabled
        if require_context:
            raise ParseError("Employer context is required for this operation.")

        # Prefer the last_active_employer_id marker if we have it
        if getattr(user, 'last_active_employer_id', None):
            membership = EmployeeMembership.objects.filter(
                user_id=user.id,
                employer_profile_id=user.last_active_employer_id,
                status=EmployeeMembership.STATUS_ACTIVE,
            ).select_related('employer_profile').first()
            if membership:
                employer_profile = membership.employer_profile

        # Legacy fallback to old single-employer resolution
        if not employer_profile:
            employee = getattr(user, 'employee_profile', None)
            if employee and getattr(employee, 'employer_id', None):
                employer_profile = EmployerProfile.objects.filter(id=employee.employer_id).first()

    if not employer_profile:
        return None

    alias = get_tenant_database_alias(employer_profile)
    ensure_tenant_database_loaded(employer_profile)
    return alias
