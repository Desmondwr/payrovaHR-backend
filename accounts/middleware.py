"""
Middleware for multi-tenant database routing
"""
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from rest_framework.exceptions import ParseError, PermissionDenied
from accounts.database_utils import (
    ensure_tenant_database_loaded,
    get_employee_tenant_db_from_membership,
)
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
        user = getattr(request, 'user', None)
        header_value = request.headers.get('x-employer-id') if hasattr(request, 'headers') else None

        # If we have an authenticated user, resolve their tenant context
        if user and user.is_authenticated:
            # Employer users go straight to their tenant DB
            if getattr(user, 'employer_profile', None):
                employer_profile = user.employer_profile
                if employer_profile.database_name:
                    tenant_db = ensure_tenant_database_loaded(employer_profile)
            # Staff/superusers can pick a tenant via the header
            elif header_value and (user.is_staff or user.is_superuser):
                try:
                    employer_id = int(header_value)
                except (TypeError, ValueError):
                    employer_id = None
                if employer_id:
                    from accounts.models import EmployerProfile

                    header_employer = EmployerProfile.objects.filter(id=employer_id).first()
                    if header_employer and header_employer.database_name:
                        tenant_db = ensure_tenant_database_loaded(header_employer)
            # Employees resolve their tenant via membership/header lookup
            elif getattr(user, 'is_employee', False):
                try:
                    tenant_alias = get_employee_tenant_db_from_membership(request)
                except (PermissionDenied, ParseError):
                    tenant_alias = None
                if tenant_alias:
                    tenant_db = tenant_alias
        
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
