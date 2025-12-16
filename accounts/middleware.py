"""
Middleware for multi-tenant database routing
"""
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from accounts.database_utils import get_tenant_database_alias, ensure_tenant_database_loaded
import threading

# Thread-local storage for tenant context
_thread_locals = threading.local()


def get_current_tenant_db():
    """Get the current tenant database from thread-local storage"""
    return getattr(_thread_locals, 'tenant_db', 'default')


def set_current_tenant_db(db_alias):
    """Set the current tenant database in thread-local storage"""
    _thread_locals.tenant_db = db_alias
    settings.CURRENT_TENANT_DB = db_alias


def clear_current_tenant_db():
    """Clear the tenant database context"""
    _thread_locals.tenant_db = 'default'
    settings.CURRENT_TENANT_DB = None


class TenantDatabaseMiddleware(MiddlewareMixin):
    """
    Middleware to set tenant database context based on authenticated user.
    This allows the database router to route queries to the correct tenant database.
    """
    
    def process_request(self, request):
        """Set tenant context at the start of request"""
        # Default to main database
        tenant_db = 'default'
        
        # Check if user is authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            # If user is an employer, use their tenant database
            if hasattr(request.user, 'employer_profile') and request.user.employer_profile:
                employer_profile = request.user.employer_profile
                if employer_profile.database_created:
                    # Ensure the tenant database is loaded before using it
                    tenant_db = ensure_tenant_database_loaded(employer_profile)
            
            # If user is an employee, we need to find their employer's database
            # This is done by querying the employees app for their record
            elif request.user.is_employee:
                # We'll handle this in the views where we have more context
                # For now, we'll try to determine from the request path or headers
                pass
        
        # Set the tenant context
        set_current_tenant_db(tenant_db)
        
        return None
    
    def process_response(self, request, response):
        """Clear tenant context after request"""
        clear_current_tenant_db()
        return response
    
    def process_exception(self, request, exception):
        """Clear tenant context on exception"""
        clear_current_tenant_db()
        return None
