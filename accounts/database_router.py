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
        'employeeregistry',  # Central employee registry for cross-institutional tracking
        'employeemembership',
        'permission',
        'role',
        'rolepermission',
        'employeerole',
        'userpermissionoverride',
        'auditlog',
        'notification',
        'session',
        'contenttype',
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

        # Respect the instance database when provided (e.g., related managers).
        instance = hints.get('instance')
        if instance is not None:
            instance_db = getattr(instance._state, 'db', None)
            if instance_db:
                return instance_db
        
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

        # Respect the instance database when provided (e.g., related managers).
        instance = hints.get('instance')
        if instance is not None:
            instance_db = getattr(instance._state, 'db', None)
            if instance_db:
                return instance_db
        
        # Check for tenant context in thread-local storage
        tenant_db = getattr(settings, 'CURRENT_TENANT_DB', None)
        if tenant_db:
            return tenant_db
        
        # Default database for everything else
        return 'default'
    
    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations if both objects are in the same database or app.
        Also allow relations within tenant-specific models.
        """
        # Get the database for each object
        db1 = obj1._state.db if hasattr(obj1, '_state') and obj1._state.db else None
        db2 = obj2._state.db if hasattr(obj2, '_state') and obj2._state.db else None
        
        # Get model info
        model1_name = obj1._meta.model_name.lower()
        model2_name = obj2._meta.model_name.lower()
        app1 = obj1._meta.app_label
        app2 = obj2._meta.app_label
        
        # Both models are in the default database models list
        if model1_name in self.DEFAULT_DB_MODELS and model2_name in self.DEFAULT_DB_MODELS:
            return True
        
        # Both models are from the same tenant app (e.g., employees app, contracts app)
        # Allow relations within the same app (like Employee -> Employee for manager)
        if app1 == app2 and app1 in ['employees', 'contracts', 'frontdesk', 'timeoff', 'attendance', 'treasury', 'income_expense', 'recruitment', 'communications']:
            return True
        
        # Allow relations between tenant apps (e.g., Contract -> Employee)
        if app1 in ['employees', 'contracts', 'frontdesk', 'timeoff', 'attendance', 'treasury', 'income_expense', 'recruitment', 'communications'] and app2 in ['employees', 'contracts', 'frontdesk', 'timeoff', 'attendance', 'treasury', 'income_expense', 'recruitment', 'communications']:
            return True
        
        # If both databases are explicitly set, they must match
        if db1 and db2:
            return db1 == db2
        
        # If only one database is set, check if they're in the same app
        if (db1 or db2) and app1 == app2:
            return True
        
        # Default: allow if we can't determine (will be validated at save time)
        return True
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Control which databases get migrations
        
        - Default database gets all migrations
        - Tenant databases only get app-specific migrations (not auth/admin)
        """
        # Default database gets everything
        if db == 'default':
            if app_label == 'treasury' and (model_name or '').lower() == 'treasuryconfiguration':
                return False
            if app_label == 'income_expense' and (model_name or '').lower() == 'incomeexpenseconfiguration':
                return False
            return True
        
        # Tenant databases skip auth and admin related migrations
        if db.startswith('tenant_'):
            # Never apply accounts app migrations to tenant databases (accounts models live in default DB)
            if app_label == 'accounts':
                return False
            if app_label in ['auth', 'admin', 'sessions', 'contenttypes', 'notifications']:
                # These tables should not be created in tenant databases
                return False
            
            # Allow all other app migrations
            return True
        
        return None
