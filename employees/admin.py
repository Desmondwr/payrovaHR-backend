from django.contrib import admin
from .models import (
    Department, Branch, Employee, EmployeeDocument,
    EmployeeCrossInstitutionRecord, EmployeeAuditLog, EmployeeInvitation,
    EmployeeConfiguration
)


@admin.register(EmployeeConfiguration)
class EmployeeConfigurationAdmin(admin.ModelAdmin):
    list_display = ['employer', 'employee_id_format', 'duplicate_detection_level', 'allow_concurrent_employment']
    list_filter = ['employee_id_format', 'duplicate_detection_level', 'allow_concurrent_employment']
    search_fields = ['employer__company_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Employer', {
            'fields': ('id', 'employer')
        }),
        ('Employee ID Configuration', {
            'fields': ('employee_id_format', 'employee_id_prefix', 'employee_id_suffix',
                      'employee_id_starting_number', 'employee_id_padding',
                      'employee_id_include_branch', 'employee_id_include_department',
                      'employee_id_include_year', 'employee_id_custom_template',
                      'employee_id_manual_override')
        }),
        ('Required Fields - Basic Info', {
            'fields': ('require_middle_name', 'require_profile_photo', 'require_gender',
                      'require_date_of_birth', 'require_marital_status', 'require_nationality')
        }),
        ('Required Fields - Contact', {
            'fields': ('require_personal_email', 'require_alternative_phone',
                      'require_address', 'require_postal_code')
        }),
        ('Required Fields - Legal', {
            'fields': ('require_national_id', 'require_passport', 'require_cnps_number',
                      'require_tax_number')
        }),
        ('Required Fields - Employment', {
            'fields': ('require_department', 'require_branch', 'require_manager',
                      'require_probation_period')
        }),
        ('Required Fields - Other', {
            'fields': ('require_bank_details', 'require_bank_details_active_only',
                      'require_emergency_contact')
        }),
        ('Cross-Institution Rules', {
            'fields': ('allow_concurrent_employment', 'require_employee_consent_cross_institution',
                      'cross_institution_visibility_level')
        }),
        ('Duplicate Detection', {
            'fields': ('duplicate_detection_level', 'duplicate_action',
                      'duplicate_check_national_id', 'duplicate_check_email',
                      'duplicate_check_phone', 'duplicate_check_name_dob')
        }),
        ('Document Management', {
            'fields': ('required_documents', 'document_expiry_tracking_enabled',
                      'document_expiry_reminder_days', 'document_max_file_size_mb',
                      'document_allowed_formats')
        }),
        ('Termination Workflow', {
            'fields': ('require_termination_reason', 'termination_approval_required',
                      'termination_approval_by', 'termination_revoke_access_timing',
                      'termination_access_delay_days', 'termination_data_retention_months',
                      'allow_employee_reactivation')
        }),
        ('Notifications', {
            'fields': ('send_invitation_email', 'invitation_expiry_days',
                      'send_welcome_email', 'send_profile_completion_reminder',
                      'profile_completion_reminder_days')
        }),
        ('Probation', {
            'fields': ('default_probation_period_months', 'probation_review_required',
                      'probation_reminder_before_end_days')
        }),
        ('System Settings', {
            'fields': ('auto_generate_work_email', 'work_email_template')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'employer', 'parent_department', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'code', 'employer__company_name']
    ordering = ['employer', 'name']


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'employer', 'city', 'is_headquarters', 'is_active']
    list_filter = ['is_headquarters', 'is_active', 'country']
    search_fields = ['name', 'code', 'employer__company_name', 'city']
    ordering = ['employer', 'name']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'full_name', 'job_title', 'employer', 'employment_status', 'hire_date']
    list_filter = ['employment_status', 'employment_type', 'gender', 'is_concurrent_employment']
    search_fields = ['employee_id', 'first_name', 'last_name', 'email', 'national_id_number']
    readonly_fields = ['id', 'created_at', 'updated_at', 'invitation_sent_at', 'invitation_accepted_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'employer', 'employee_id', 'first_name', 'middle_name', 'last_name',
                      'date_of_birth', 'gender', 'marital_status', 'nationality', 'profile_photo')
        }),
        ('Contact Information', {
            'fields': ('email', 'personal_email', 'phone_number', 'alternative_phone',
                      'address', 'city', 'state_region', 'postal_code', 'country')
        }),
        ('Legal Identification', {
            'fields': ('national_id_number', 'passport_number', 'cnps_number', 'tax_number')
        }),
        ('Employment Details', {
            'fields': ('job_title', 'department', 'branch', 'manager', 'employment_type',
                      'employment_status', 'hire_date', 'probation_end_date',
                      'termination_date', 'termination_reason')
        }),
        ('Payroll Information', {
            'fields': ('bank_name', 'bank_account_number', 'bank_account_name')
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone')
        }),
        ('System Access', {
            'fields': ('user', 'invitation_sent', 'invitation_sent_at', 'invitation_accepted',
                      'invitation_accepted_at', 'is_concurrent_employment')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'created_by')
        }),
    )


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'employee', 'document_type', 'has_expiry', 'expiry_date', 'is_verified', 'uploaded_by', 'uploaded_at']
    list_filter = ['document_type', 'has_expiry', 'is_verified', 'uploaded_at']
    search_fields = ['title', 'employee__first_name', 'employee__last_name']
    readonly_fields = ['file_size', 'uploaded_at', 'verified_at']
    ordering = ['-uploaded_at']


@admin.register(EmployeeCrossInstitutionRecord)
class EmployeeCrossInstitutionRecordAdmin(admin.ModelAdmin):
    list_display = ['employee', 'detected_employer', 'status', 'consent_status', 'verified', 'detected_at']
    list_filter = ['status', 'consent_status', 'verified', 'detected_at']
    search_fields = ['employee__first_name', 'employee__last_name', 'detected_employer__company_name']
    readonly_fields = ['detected_at', 'consent_requested_at', 'consent_responded_at']
    ordering = ['-detected_at']


@admin.register(EmployeeAuditLog)
class EmployeeAuditLogAdmin(admin.ModelAdmin):
    list_display = ['employee', 'action', 'performed_by', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['employee__first_name', 'employee__last_name', 'performed_by__email']
    readonly_fields = ['id', 'employee', 'action', 'performed_by', 'timestamp', 'changes', 'notes', 'ip_address']
    ordering = ['-timestamp']


@admin.register(EmployeeInvitation)
class EmployeeInvitationAdmin(admin.ModelAdmin):
    list_display = ['employee', 'email', 'status', 'sent_at', 'expires_at']
    list_filter = ['status', 'sent_at']
    search_fields = ['employee__first_name', 'employee__last_name', 'email']
    readonly_fields = ['id', 'token', 'sent_at', 'accepted_at']
    ordering = ['-sent_at']
