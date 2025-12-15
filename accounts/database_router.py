"""
Database router for multi-tenant architecture
Routes database queries to appropriate tenant databases
"""
from django.conf import settings


class TenantDatabaseRouter:
    """
    A router to control database operations for multi-tenant architecture.
    
    - Admin and authentication models stay in the default database
    - Tenant-specific data goes to their respective databases
    """
    
    # Models that should always use the default database
    DEFAULT_DB_MODELS = [
        'user',
        'activationtoken',
        'employerprofile',
        'employeeprofile',  # Employee user profiles stay in main DB
        'session',
        'contenttype',
        'permission',
        'group',
        'logentry',
    ]
    
    def db_for_read(self, model, **hints):
        """
        Route read operations
        """
        # Always use default for auth and admin models
        if model._meta.model_name.lower() in self.DEFAULT_DB_MODELS:
            return 'default'
        
        # Check if a specific database is hinted
        if 'tenant_db' in hints:
            return hints['tenant_db']
        
        # Check for tenant context in thread-local storage
        tenant_db = getattr(settings, 'CURRENT_TENANT_DB', None)
        if tenant_db:
            return tenant_db
        
        # Default database for everything else
        return 'default'
    
    def db_for_write(self, model, **hints):
        """
        Route write operations
        """
        # Always use default for auth and admin models
        if model._meta.model_name.lower() in self.DEFAULT_DB_MODELS:
            return 'default'
        
        # Check if a specific database is hinted
        if 'tenant_db' in hints:
            return hints['tenant_db']
        
        # Check for tenant context in thread-local storage
        tenant_db = getattr(settings, 'CURRENT_TENANT_DB', None)
        if tenant_db:
            return tenant_db
        
        # Default database for everything else
        return 'default'
    
    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations if both objects are in the same database
        """
        db1 = obj1._state.db
        db2 = obj2._state.db
        
        if db1 and db2:
            return db1 == db2
        
        return None
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Control which databases get migrations
        
        - Default database gets all migrations
        - Tenant databases only get app-specific migrations (not auth/admin)
        """
        # Default database gets everything
        if db == 'default':
            return True
        
        # Tenant databases skip auth and admin related migrations
        if db.startswith('tenant_'):
            if app_label in ['auth', 'admin', 'sessions', 'contenttypes']:
                # These tables should not be created in tenant databases
                return False
            
            # Allow accounts app but only for tenant-specific models
            if app_label == 'accounts':
                if model_name and model_name.lower() in self.DEFAULT_DB_MODELS:
                    return False
            
            # Allow all other app migrations
            return True
        
        return None
