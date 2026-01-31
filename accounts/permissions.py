"""Custom permissions for the application"""
from rest_framework import permissions
from accounts.rbac import get_active_employer, user_has_permission


class IsAuthenticated(permissions.BasePermission):
    """
    Permission to only allow authenticated users.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsEmployer(permissions.BasePermission):
    """
    Permission to only allow employers.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_employer and
            hasattr(request.user, 'employer_profile')
        )


class IsEmployee(permissions.BasePermission):
    """
    Permission to only allow employees.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_employee
        )


class IsAdmin(permissions.BasePermission):
    """
    Permission to only allow admin users.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_admin
        )


class IsEmployerOwner(permissions.BasePermission):
    """
    Permission to allow employer owners or platform admins.
    """

    def has_permission(self, request, view):
        user = request.user
        return (
            user
            and user.is_authenticated
            and (
                user.is_admin
                or user.is_superuser
                or (getattr(user, "is_employer", False) and getattr(user, "is_employer_owner", False))
            )
        )


class EmployerAccessPermission(permissions.BasePermission):
    """
    Allow employer owners or employee delegates with required permissions.
    View can define `permission_map` or `required_permissions`.
    """

    def _get_required_permissions(self, view):
        permission_map = getattr(view, "permission_map", None)
        if permission_map and getattr(view, "action", None):
            return permission_map.get(view.action) or permission_map.get("*")
        return getattr(view, "required_permissions", None)

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Platform admins or employer owners
        if user.is_superuser or user.is_admin:
            return True
        if getattr(user, "employer_profile", None):
            return True

        required = self._get_required_permissions(view)
        if not required:
            return False

        employer = get_active_employer(request, require_context=False)
        if not employer:
            return False
        return user_has_permission(user, employer.id, required)


class EmployerOrEmployeeAccessPermission(permissions.BasePermission):
    """
    Allow employees for self-service endpoints; otherwise require employer access.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_employee", False) and not getattr(user, "employer_profile", None):
            return True

        return EmployerAccessPermission().has_permission(request, view)


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to allow owners to edit their own data or admins.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admins have full access
        if request.user.is_admin:
            return True
        
        # Check if the object has a user field and if it matches the request user
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # For user objects themselves
        return obj == request.user
