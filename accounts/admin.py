from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    ActivationToken,
    EmployerProfile,
    EmployeeRegistry,
    Permission,
    Role,
    RolePermission,
    EmployeeRole,
    UserPermissionOverride,
    AuditLog,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for User model"""
    
    list_display = ('email', 'is_admin', 'is_employer', 'is_employer_owner', 'is_employee', 'is_active', 'profile_completed', 'two_factor_enabled', 'created_at')
    list_filter = ('is_admin', 'is_employer', 'is_employer_owner', 'is_employee', 'is_active', 'profile_completed', 'two_factor_enabled', 'created_at')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_admin', 'is_employer', 'is_employer_owner', 'is_employee', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Status', {'fields': ('profile_completed',)}),
        ('Two-Factor Authentication', {'fields': ('two_factor_enabled', 'two_factor_secret')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_admin', 'is_employer', 'is_employee'),
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


@admin.register(EmployeeRegistry)
class EmployeeRegistryAdmin(admin.ModelAdmin):
    """Admin interface for EmployeeRegistry model"""
    
    list_display = ('first_name', 'last_name', 'user', 'phone_number', 'national_id_number', 'created_at')
    list_filter = ('gender', 'marital_status', 'created_at')
    search_fields = ('first_name', 'last_name', 'user__email', 'phone_number', 'national_id_number', 'passport_number')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'middle_name', 'date_of_birth', 'gender', 'marital_status', 'nationality')
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'alternative_phone', 'personal_email', 'address', 'city', 'state_region', 'postal_code', 'country')
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone')
        }),
        ('Identification', {
            'fields': ('national_id_number', 'passport_number')
        }),
        ('Employment Information', {
            'fields': ('desired_position', 'years_of_experience', 'highest_education_level', 'skills')
        }),
        ('Profile Picture', {
            'fields': ('profile_picture',)
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "resource", "action", "scope", "is_active")
    list_filter = ("module", "action", "scope", "is_active")
    search_fields = ("code", "description")
    ordering = ("module", "resource", "action", "scope")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "employer", "is_active", "is_system_role")
    list_filter = ("is_active", "is_system_role")
    search_fields = ("name", "employer__company_name")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")
    search_fields = ("role__name", "permission__code")


@admin.register(EmployeeRole)
class EmployeeRoleAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "role", "employer", "scope_type", "scope_id")
    list_filter = ("scope_type", "employer")
    search_fields = ("employee_id", "role__name")


@admin.register(UserPermissionOverride)
class UserPermissionOverrideAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "effect", "employer")
    list_filter = ("effect", "employer")
    search_fields = ("user__email", "permission__code")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "entity_type", "entity_id", "employer", "created_at")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_id", "action")

