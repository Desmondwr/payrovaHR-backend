"""Utility functions for employee management"""
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import secrets
from difflib import SequenceMatcher


def detect_duplicate_employees(employer, national_id=None, email=None, phone=None, 
                               first_name=None, last_name=None, date_of_birth=None,
                               config=None, exclude_employee_id=None):
    """
    Detect potential duplicate employees based on configuration settings
    Searches both EmployeeRegistry (for employees with accounts) 
    and all tenant databases (for employees without accounts)
    
    Args:
        employer: EmployerProfile instance
        national_id: National ID number
        email: Email address
        phone: Phone number
        first_name: First name
        last_name: Last name
        date_of_birth: Date of birth
        config: EmployeeConfiguration instance (optional)
        exclude_employee_id: Employee ID to exclude from search (for updates)
    
    Returns:
        dict: {
            'duplicates_found': bool,
            'matches': list of match dictionaries,
            'match_reasons': dict explaining why each is a match
        }
    """
    from employees.models import Employee, EmployeeConfiguration
    from accounts.models import EmployeeRegistry, EmployerProfile
    from accounts.database_utils import get_tenant_database_alias
    
    # Get configuration from tenant database
    if config is None:
        try:
            tenant_db = get_tenant_database_alias(employer)
            config = EmployeeConfiguration.objects.using(tenant_db).get(employer_id=employer.id)
        except EmployeeConfiguration.DoesNotExist:
            # No config, use default strict matching
            config = None
    
    all_matches = []
    match_reasons = {}
    
    # PART 1: Search central EmployeeRegistry (employees with user accounts)
    registry_query = EmployeeRegistry.objects.all()
    
    if exclude_employee_id:
        try:
            tenant_db = get_tenant_database_alias(employer)
            exclude_employee = Employee.objects.using(tenant_db).get(id=exclude_employee_id)
            if exclude_employee.user_id:
                registry_query = registry_query.exclude(user_id=exclude_employee.user_id)
        except Employee.DoesNotExist:
            pass
    
    registry_matches = []
    
    if config:
        if config.duplicate_check_national_id and national_id:
            for profile in registry_query.filter(national_id_number=national_id):
                registry_matches.append(profile)
                match_reasons[f'registry_{profile.id}'] = ['National ID match']
        
        if config.duplicate_check_email and email:
            for profile in registry_query.filter(Q(user__email=email) | Q(personal_email=email)):
                if profile not in registry_matches:
                    registry_matches.append(profile)
                    match_reasons[f'registry_{profile.id}'] = ['Email match']
                elif f'registry_{profile.id}' in match_reasons:
                    match_reasons[f'registry_{profile.id}'].append('Email match')
        
        if config.duplicate_check_phone and phone:
            for profile in registry_query.filter(Q(phone_number=phone) | Q(alternative_phone=phone)):
                if profile not in registry_matches:
                    registry_matches.append(profile)
                    match_reasons[f'registry_{profile.id}'] = ['Phone match']
                elif f'registry_{profile.id}' in match_reasons:
                    match_reasons[f'registry_{profile.id}'].append('Phone match')
    else:
        if national_id:
            registry_matches = list(registry_query.filter(national_id_number=national_id))
            for profile in registry_matches:
                match_reasons[f'registry_{profile.id}'] = ['National ID match']
    
    # PART 2: Search across all tenant databases (for employees without accounts)
    tenant_matches = []
    all_employers = EmployerProfile.objects.filter(is_active=True)
    current_tenant_db = get_tenant_database_alias(employer)
    
    for emp_profile in all_employers:
        try:
            tenant_db = get_tenant_database_alias(emp_profile)
            employee_query = Employee.objects.using(tenant_db).all()
            
            # Exclude the employee being updated
            if exclude_employee_id and tenant_db == current_tenant_db:
                employee_query = employee_query.exclude(id=exclude_employee_id)
            
            # Only search employees without user accounts (those with accounts are in registry)
            employee_query = employee_query.filter(user_id__isnull=True)
            
            if config:
                if config.duplicate_check_national_id and national_id:
                    for emp in employee_query.filter(national_id_number=national_id):
                        tenant_matches.append({
                            'employee': emp,
                            'employer_id': emp_profile.id,
                            'employer_name': emp_profile.company_name,
                            'tenant_db': tenant_db
                        })
                        match_reasons[f'tenant_{emp.id}'] = ['National ID match']
                
                if config.duplicate_check_email and email:
                    for emp in employee_query.filter(Q(email=email) | Q(personal_email=email)):
                        match_key = f'tenant_{emp.id}'
                        if not any(m['employee'].id == emp.id for m in tenant_matches):
                            tenant_matches.append({
                                'employee': emp,
                                'employer_id': emp_profile.id,
                                'employer_name': emp_profile.company_name,
                                'tenant_db': tenant_db
                            })
                            match_reasons[match_key] = ['Email match']
                        elif match_key in match_reasons:
                            match_reasons[match_key].append('Email match')
                
                if config.duplicate_check_phone and phone:
                    for emp in employee_query.filter(Q(phone_number=phone) | Q(alternative_phone=phone)):
                        match_key = f'tenant_{emp.id}'
                        if not any(m['employee'].id == emp.id for m in tenant_matches):
                            tenant_matches.append({
                                'employee': emp,
                                'employer_id': emp_profile.id,
                                'employer_name': emp_profile.company_name,
                                'tenant_db': tenant_db
                            })
                            match_reasons[match_key] = ['Phone match']
                        elif match_key in match_reasons:
                            match_reasons[match_key].append('Phone match')
            else:
                # Default: national ID only
                if national_id:
                    for emp in employee_query.filter(national_id_number=national_id):
                        tenant_matches.append({
                            'employee': emp,
                            'employer_id': emp_profile.id,
                            'employer_name': emp_profile.company_name,
                            'tenant_db': tenant_db
                        })
                        match_reasons[f'tenant_{emp.id}'] = ['National ID match']
        except Exception as e:
            # Skip this tenant if there's an error
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error searching tenant database for employer {emp_profile.id}: {str(e)}")
            continue
    
    # Categorize matches as same-institution vs cross-institution
    same_institution_matches = []
    cross_institution_matches = []
    
    # Process registry matches
    for profile in registry_matches:
        try:
            Employee.objects.using(current_tenant_db).get(user_id=profile.user_id)
            same_institution_matches.append({
                'type': 'registry',
                'data': profile,
                'employer_id': employer.id,
                'employer_name': employer.company_name
            })
        except Employee.DoesNotExist:
            cross_institution_matches.append({
                'type': 'registry',
                'data': profile,
                'employer_id': 'unknown',
                'employer_name': 'Other Institution'
            })
    
    # Process tenant matches
    for match in tenant_matches:
        if match['tenant_db'] == current_tenant_db:
            same_institution_matches.append({
                'type': 'employee',
                'data': match['employee'],
                'employer_id': match['employer_id'],
                'employer_name': match['employer_name']
            })
        else:
            cross_institution_matches.append({
                'type': 'employee',
                'data': match['employee'],
                'employer_id': match['employer_id'],
                'employer_name': match['employer_name']
            })
    
    all_matches = same_institution_matches + cross_institution_matches
    
    return {
        'duplicates_found': len(all_matches) > 0,
        'total_matches': len(all_matches),
        'same_institution_matches': same_institution_matches,
        'cross_institution_matches': cross_institution_matches,
        'match_reasons': match_reasons,
        'all_matches': all_matches
    }


def similar(a, b):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, a, b).ratio()


def generate_employee_invitation_token():
    """Generate a secure invitation token"""
    return secrets.token_urlsafe(32)


def get_invitation_expiry_date(config):
    """Get invitation expiry date based on configuration"""
    from employees.models import EmployeeConfiguration
    
    days = config.invitation_expiry_days if config else 7
    return timezone.now() + timedelta(days=days)


def send_employee_invitation_email(employee, invitation):
    """Send invitation email to employee"""
    from django.core.mail import send_mail
    from django.conf import settings
    from django.template.loader import render_to_string
    
    # Build invitation URL
    invitation_url = f"{settings.FRONTEND_URL}/accept-invitation/{invitation.token}"
    
    # Prepare context - need to fetch employer from main DB
    from accounts.models import EmployerProfile
    employer = EmployerProfile.objects.get(id=employee.employer_id)
    
    context = {
        'employee': employee,
        'employer': employer,
        'invitation_url': invitation_url,
        'expires_at': invitation.expires_at,
    }
    
    # Render email
    subject = f"Invitation to join {employer.company_name}"
    html_message = render_to_string('emails/employee_invitation.html', context)
    text_message = render_to_string('emails/employee_invitation.txt', context)
    
    # Send email
    send_mail(
        subject=subject,
        message=text_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        html_message=html_message,
        fail_silently=False,
    )


def generate_work_email(employee, config):
    """Generate work email based on configuration template"""
    if not config.auto_generate_work_email or not config.work_email_template:
        return None
    
    # Fetch employer from main database
    from accounts.models import EmployerProfile
    employer = EmployerProfile.objects.get(id=employee.employer_id)
    
    # Parse template
    template = config.work_email_template
    domain = employer.official_company_email.split('@')[1] if '@' in employer.official_company_email else 'company.com'
    
    email = template.replace('{firstname}', employee.first_name.lower())
    email = email.replace('{lastname}', employee.last_name.lower())
    email = email.replace('{domain}', domain)
    
    # Clean up (remove spaces, special chars)
    email = email.replace(' ', '').replace('_', '.')
    
    return email


def check_required_documents(employee):
    """Check if employee has uploaded all required documents"""
    from employees.models import EmployeeConfiguration, EmployeeDocument
    from accounts.database_utils import get_tenant_database_alias
    from accounts.models import EmployerProfile
    
    try:
        employer = EmployerProfile.objects.get(id=employee.employer_id)
        tenant_db = get_tenant_database_alias(employer)
        config = EmployeeConfiguration.objects.using(tenant_db).get(employer_id=employee.employer_id)
    except (EmployeeConfiguration.DoesNotExist, EmployerProfile.DoesNotExist):
        return {'missing': [], 'all_uploaded': True}
    
    required_types = config.get_required_document_types()
    
    # Get uploaded document types
    uploaded_types = employee.documents.values_list('document_type', flat=True).distinct()
    
    # Find missing documents
    missing = [doc_type for doc_type in required_types if doc_type not in uploaded_types]
    
    return {
        'required': required_types,
        'uploaded': list(uploaded_types),
        'missing': missing,
        'all_uploaded': len(missing) == 0
    }


def check_expiring_documents(employee, days_ahead=30):
    """Check for documents expiring within specified days"""
    from employees.models import EmployeeDocument
    
    expiry_threshold = timezone.now().date() + timedelta(days=days_ahead)
    
    expiring_docs = employee.documents.filter(
        has_expiry=True,
        expiry_date__lte=expiry_threshold,
        expiry_date__gte=timezone.now().date()
    )
    
    expired_docs = employee.documents.filter(
        has_expiry=True,
        expiry_date__lt=timezone.now().date()
    )
    
    return {
        'expiring_soon': list(expiring_docs),
        'expired': list(expired_docs),
        'expiring_count': expiring_docs.count(),
        'expired_count': expired_docs.count()
    }


def validate_employee_data(data, config):
    """
    Validate employee data against configuration requirements
    
    Returns:
        dict: {'valid': bool, 'errors': dict}
    """
    errors = {}
    
    # Check required fields based on configuration
    required_field_map = {
        'middle_name': 'require_middle_name',
        'profile_photo': 'require_profile_photo',
        'gender': 'require_gender',
        'date_of_birth': 'require_date_of_birth',
        'marital_status': 'require_marital_status',
        'nationality': 'require_nationality',
        'personal_email': 'require_personal_email',
        'alternative_phone': 'require_alternative_phone',
        'address': 'require_address',
        'postal_code': 'require_postal_code',
        'national_id_number': 'require_national_id',
        'passport_number': 'require_passport',
        'cnps_number': 'require_cnps_number',
        'tax_number': 'require_tax_number',
        'department': 'require_department',
        'branch': 'require_branch',
        'manager': 'require_manager',
        'probation_end_date': 'require_probation_period',
    }
    
    for field_name, config_field in required_field_map.items():
        if config.is_field_required(config_field.replace('require_', '')):
            if not data.get(field_name):
                errors[field_name] = f"{field_name.replace('_', ' ').title()} is required"
    
    # Validate bank details for active employees
    if config.require_bank_details == 'REQUIRED':
        if config.require_bank_details_active_only:
            if data.get('employment_status') == 'ACTIVE':
                if not data.get('bank_account_number'):
                    errors['bank_account_number'] = "Bank account is required for active employees"
        else:
            if not data.get('bank_account_number'):
                errors['bank_account_number'] = "Bank account is required"
    
    # Validate emergency contact
    if config.is_field_required('emergency_contact'):
        if not data.get('emergency_contact_name'):
            errors['emergency_contact_name'] = "Emergency contact name is required"
        if not data.get('emergency_contact_phone'):
            errors['emergency_contact_phone'] = "Emergency contact phone is required"
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


def create_employee_audit_log(employee, action, performed_by, changes=None, notes=None, request=None, tenant_db=None):
    """Create an audit log entry for employee actions"""
    from employees.models import EmployeeAuditLog
    
    ip_address = None
    if request:
        # Get IP address from request
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
    
    # Use tenant database if provided
    if tenant_db:
        audit_log = EmployeeAuditLog.objects.using(tenant_db).create(
            employee=employee,
            action=action,
            performed_by_id=performed_by.id if performed_by else None,
            changes=changes,
            notes=notes,
            ip_address=ip_address
        )
    else:
        audit_log = EmployeeAuditLog.objects.create(
            employee=employee,
            action=action,
            performed_by_id=performed_by.id if performed_by else None,
            changes=changes,
            notes=notes,
            ip_address=ip_address
        )
    
    return audit_log


def get_cross_institution_summary(employee, config):
    """Get summary of employee's presence in other institutions"""
    from employees.models import EmployeeCrossInstitutionRecord
    from accounts.models import EmployerProfile
    from accounts.database_utils import get_tenant_database_alias
    
    if not config:
        return {'has_other_institutions': False, 'records': []}
    
    # Get tenant database for the current employer
    try:
        current_employer = EmployerProfile.objects.get(id=employee.employer_id)
        tenant_db = get_tenant_database_alias(current_employer)
    except EmployerProfile.DoesNotExist:
        tenant_db = 'default'
    
    # Query from tenant database - no select_related since detected_employer_id is IntegerField
    records = EmployeeCrossInstitutionRecord.objects.using(tenant_db).filter(
        employee_id=employee.id
    )
    
    summary = []
    for record in records:
        # Manually fetch employer info from main database using detected_employer_id
        try:
            detected_employer = EmployerProfile.objects.get(id=record.detected_employer_id)
            employer_name = detected_employer.company_name
        except EmployerProfile.DoesNotExist:
            employer_name = 'Unknown'
        
        info = {
            'employer_id': str(record.detected_employer_id),
            'employee_id': record.detected_employee_id,
            'status': record.status,
            'consent_status': record.consent_status,
        }
        
        # Add information based on visibility level
        if config.cross_institution_visibility_level in ['BASIC', 'MODERATE', 'FULL']:
            info['company_name'] = employer_name
        
        if config.cross_institution_visibility_level in ['MODERATE', 'FULL']:
            # Would need to fetch from detected employee record
            info['employment_dates'] = {
                'detected_at': record.detected_at
            }
        
        if config.cross_institution_visibility_level == 'FULL':
            # Full details available
            info['verified'] = record.verified
            info['notes'] = record.notes
        
        summary.append(info)
    
    return {
        'has_other_institutions': records.exists(),
        'count': records.count(),
        'records': summary
    }
