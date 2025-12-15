"""Custom permissions for the application"""
from rest_framework import permissions


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
