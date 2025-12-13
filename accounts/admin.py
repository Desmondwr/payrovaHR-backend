from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ActivationToken, EmployerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for User model"""
    
    list_display = ('email', 'is_admin', 'is_employer', 'is_active', 'profile_completed', 'two_factor_enabled', 'created_at')
    list_filter = ('is_admin', 'is_employer', 'is_active', 'profile_completed', 'two_factor_enabled', 'created_at')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_admin', 'is_employer', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Status', {'fields': ('profile_completed',)}),
        ('Two-Factor Authentication', {'fields': ('two_factor_enabled', 'two_factor_secret')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_admin', 'is_employer'),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ActivationToken)
class ActivationTokenAdmin(admin.ModelAdmin):
    """Admin interface for ActivationToken model"""
    
    list_display = ('user', 'token', 'created_at', 'expires_at', 'is_used')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__email', 'token')
    readonly_fields = ('token', 'created_at')
    ordering = ('-created_at',)


@admin.register(EmployerProfile)
class EmployerProfileAdmin(admin.ModelAdmin):
    """Admin interface for EmployerProfile model"""
    
    list_display = ('company_name', 'user', 'organization_type', 'industry_sector', 'created_at')
    list_filter = ('organization_type', 'created_at')
    search_fields = ('company_name', 'employer_name_or_group', 'user__email', 'official_company_email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Company Information', {
            'fields': ('company_name', 'employer_name_or_group', 'organization_type', 'industry_sector', 'date_of_incorporation')
        }),
        ('Contact Information', {
            'fields': ('company_location', 'physical_address', 'phone_number', 'fax_number', 'official_company_email')
        }),
        ('Legal & Registration', {
            'fields': ('rccm', 'taxpayer_identification_number', 'cnps_employer_number', 'labour_inspectorate_declaration', 'business_license')
        }),
        ('Financial Information', {
            'fields': ('bank_name', 'bank_account_number', 'bank_iban_swift')
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

