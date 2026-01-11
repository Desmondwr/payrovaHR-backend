from django.contrib import admin
from .models import Contract, Allowance, Deduction, ContractConfiguration, SalaryScale

class AllowanceInline(admin.TabularInline):
    model = Allowance
    extra = 1

class DeductionInline(admin.TabularInline):
    model = Deduction
    extra = 1

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('contract_id', 'employee', 'employer_id', 
                    'contract_type', 'start_date', 'end_date', 'status', 'base_salary')
    list_filter = ('employer_id', 'status', 'contract_type', 
                   'pay_frequency')
    search_fields = ('contract_id', 'employee__first_name', 
                     'employee__last_name', 'employee__email')
    readonly_fields = ('created_at', 'updated_at', 'created_by')
    fieldsets = (
        ('Identification', {
            'fields': ('contract_id', 'employer_id', 'employee')
        }),
        ('Organization', {
            'fields': ('branch', 'department')
        }),
        ('Contract Details', {
            'fields': ('contract_type', 'status', 'start_date', 'end_date')
        }),
        ('Compensation', {
            'fields': ('salary_scale', 'base_salary', 'currency', 'pay_frequency')
        }),
        ('Audit Info', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [AllowanceInline, DeductionInline]

from .models import ContractTemplate

@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'contract_type', 'employer_id', 'is_default', 'created_at')
    list_filter = ('contract_type', 'is_default', 'employer_id')
    search_fields = ('name',)

@admin.register(ContractConfiguration)
class ContractConfigurationAdmin(admin.ModelAdmin):
    list_display = ('employer_id', 'contract_type', 'id_prefix', 'approval_enabled', 'signature_required', 'created_at')
    list_filter = ('contract_type', 'approval_enabled', 'signature_required')
    search_fields = ('employer_id',)


@admin.register(SalaryScale)
class SalaryScaleAdmin(admin.ModelAdmin):
    list_display = ('salary_category', 'echelon', 'amount', 'status', 'employer_id', 'created_at')
    list_filter = ('status', 'employer_id')
    search_fields = ('salary_category', 'echelon')
