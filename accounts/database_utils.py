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
    
    # Add to DATABASES dictionary
    settings.DATABASES[alias] = {
        'ENGINE': default_db['ENGINE'],
        'NAME': db_name,
        'USER': default_db['USER'],
        'PASSWORD': default_db['PASSWORD'],
        'HOST': default_db['HOST'],
        'PORT': default_db['PORT'],
    }
    
    # Ensure the connection is available
    connections.databases[alias] = settings.DATABASES[alias]
    
    logger.info(f"Added database configuration for alias: {alias}")


def run_migrations_on_tenant_database(db_name, employer_id):
    """
    Run Django migrations on the newly created tenant database
    """
    try:
        alias = f"tenant_{employer_id}"
        
        # Run migrations
        call_command('migrate', database=alias, verbosity=0)
        
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
    if employer_profile and employer_profile.database_created:
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
