"""Utility functions for employee management"""
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import secrets
from difflib import SequenceMatcher


def get_or_create_employee_config(employer_id, tenant_db='default'):
    """
    Get or create EmployeeConfiguration for an employer.
    This ensures the config ALWAYS exists and prevents DoesNotExist errors.
    
    Args:
        employer_id: ID of the employer
        tenant_db: Database alias to use
        
    Returns:
        EmployeeConfiguration instance
    """
    from employees.models import EmployeeConfiguration
    
    config, created = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
        employer_id=employer_id,
        defaults={
            'employee_id_prefix': 'EMP',
            'employee_id_starting_number': 1,
            'employee_id_padding': 3,
            'last_employee_number': 0,
            'employee_id_format': 'SEQUENTIAL'
        }
    )
    # Ensure the instance knows which database it's from
    config._state.db = tenant_db
    return config


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
    from accounts.database_utils import get_tenant_database_alias, ensure_tenant_database_loaded
    
    # Get configuration from tenant database
    if config is None:
        from employees.models import EmployeeConfiguration
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        ensure_tenant_database_loaded(employer)
        config = get_or_create_employee_config(employer.id, tenant_db)
    
    all_matches = []
    match_reasons = {}

    # Normalize inputs for consistent matching
    import re
    normalized_national_id = national_id.strip() if isinstance(national_id, str) else national_id
    normalized_email = email.strip().lower() if isinstance(email, str) else email
    raw_phone = phone.strip() if isinstance(phone, str) else phone
    normalized_phone = re.sub(r'\D', '', raw_phone) if isinstance(raw_phone, str) else raw_phone
    phone_variants = [p for p in {raw_phone, normalized_phone} if p]
    normalized_first = first_name.strip().lower() if isinstance(first_name, str) else first_name
    normalized_last = last_name.strip().lower() if isinstance(last_name, str) else last_name
    lenient_name_match = bool(
        config and getattr(config, 'duplicate_detection_level', None) == EmployeeConfiguration.DUPLICATE_LENIENT
    )

    # Determine effective duplicate checks based on detection level and explicit toggles.
    check_national_id = bool(getattr(config, 'duplicate_check_national_id', False))
    check_email = bool(getattr(config, 'duplicate_check_email', False))
    check_phone = bool(getattr(config, 'duplicate_check_phone', False))
    check_name_dob = bool(getattr(config, 'duplicate_check_name_dob', False))

    if config:
        level = getattr(config, 'duplicate_detection_level', None)
        if level == EmployeeConfiguration.DUPLICATE_STRICT:
            check_email = False
            check_phone = False
            check_name_dob = False
        elif level == EmployeeConfiguration.DUPLICATE_MODERATE:
            check_name_dob = False

    def _normalize_name(value):
        return re.sub(r'[^a-z0-9]', '', (value or '').lower())

    def _name_matches(candidate_first, candidate_last):
        if not normalized_first or not normalized_last:
            return False
        first_norm = _normalize_name(candidate_first)
        last_norm = _normalize_name(candidate_last)
        target_first = _normalize_name(normalized_first)
        target_last = _normalize_name(normalized_last)
        if not first_norm or not last_norm:
            return False
        if lenient_name_match:
            return similar(first_norm, target_first) >= 0.85 and similar(last_norm, target_last) >= 0.85
        return first_norm == target_first and last_norm == target_last
    
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
        if check_national_id and normalized_national_id:
            for profile in registry_query.filter(national_id_number=normalized_national_id):
                registry_matches.append(profile)
                match_reasons[f'registry_{profile.id}'] = ['National ID match']
        
        if check_email and normalized_email:
            for profile in registry_query.filter(
                Q(user__email__iexact=normalized_email) | Q(personal_email__iexact=normalized_email)
            ):
                if profile not in registry_matches:
                    registry_matches.append(profile)
                    match_reasons[f'registry_{profile.id}'] = ['Email match']
                elif f'registry_{profile.id}' in match_reasons:
                    match_reasons[f'registry_{profile.id}'].append('Email match')
        
        if check_phone and phone_variants:
            for profile in registry_query.filter(
                Q(phone_number__in=phone_variants) | Q(alternative_phone__in=phone_variants)
            ):
                if profile not in registry_matches:
                    registry_matches.append(profile)
                    match_reasons[f'registry_{profile.id}'] = ['Phone match']
                elif f'registry_{profile.id}' in match_reasons:
                    match_reasons[f'registry_{profile.id}'].append('Phone match')

        if check_name_dob and normalized_first and normalized_last and date_of_birth:
            for profile in registry_query.filter(date_of_birth=date_of_birth):
                if profile in registry_matches:
                    continue
                if _name_matches(profile.first_name, profile.last_name):
                    registry_matches.append(profile)
                    match_reasons[f'registry_{profile.id}'] = ['Name + DOB match']
    else:
        if normalized_national_id:
            registry_matches = list(registry_query.filter(national_id_number=normalized_national_id))
            for profile in registry_matches:
                match_reasons[f'registry_{profile.id}'] = ['National ID match']
    
    # PART 2: Search across all tenant databases (for employees without accounts)
    tenant_matches = []
    all_employers = EmployerProfile.objects.filter(user__is_active=True).select_related('user')
    current_tenant_db = get_tenant_database_alias(employer)
    ensure_tenant_database_loaded(employer)
    
    for emp_profile in all_employers:
        try:
            tenant_db = get_tenant_database_alias(emp_profile)
            ensure_tenant_database_loaded(emp_profile)
            employee_query = Employee.objects.using(tenant_db).all()
            
            # Exclude the employee being updated
            if exclude_employee_id and tenant_db == current_tenant_db:
                employee_query = employee_query.exclude(id=exclude_employee_id)
            
            # Only search employees without user accounts (those with accounts are in registry)
            employee_query = employee_query.filter(user_id__isnull=True)
            
            if config:
                if check_national_id and normalized_national_id:
                    for emp in employee_query.filter(national_id_number=normalized_national_id):
                        tenant_matches.append({
                            'employee': emp,
                            'employer_id': emp_profile.id,
                            'employer_name': emp_profile.company_name,
                            'tenant_db': tenant_db
                        })
                        match_reasons[f'tenant_{emp.id}'] = ['National ID match']
                
                if check_email and normalized_email:
                    for emp in employee_query.filter(
                        Q(email__iexact=normalized_email) | Q(personal_email__iexact=normalized_email)
                    ):
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
                
                if check_phone and phone_variants:
                    for emp in employee_query.filter(
                        Q(phone_number__in=phone_variants) | Q(alternative_phone__in=phone_variants)
                    ):
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

                if check_name_dob and normalized_first and normalized_last and date_of_birth:
                    for emp in employee_query.filter(date_of_birth=date_of_birth):
                        match_key = f'tenant_{emp.id}'
                        if any(m['employee'].id == emp.id for m in tenant_matches):
                            continue
                        if _name_matches(emp.first_name, emp.last_name):
                            tenant_matches.append({
                                'employee': emp,
                                'employer_id': emp_profile.id,
                                'employer_name': emp_profile.company_name,
                                'tenant_db': tenant_db
                            })
                            match_reasons[match_key] = ['Name + DOB match']
            else:
                # Default: national ID only
                if normalized_national_id:
                    for emp in employee_query.filter(national_id_number=normalized_national_id):
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
    
    # Process registry matches using memberships when available
    from accounts.models import EmployeeMembership
    registry_user_ids = [profile.user_id for profile in registry_matches if getattr(profile, 'user_id', None)]
    memberships_by_user = {}
    if registry_user_ids:
        memberships = (
            EmployeeMembership.objects
            .filter(user_id__in=registry_user_ids, status=EmployeeMembership.STATUS_ACTIVE)
            .select_related('employer_profile')
        )
        for membership in memberships:
            memberships_by_user.setdefault(membership.user_id, []).append(membership)

    for profile in registry_matches:
        memberships = memberships_by_user.get(profile.user_id, [])
        if memberships:
            for membership in memberships:
                employer_profile = membership.employer_profile
                employer_id = employer_profile.id if employer_profile else None
                employer_name = employer_profile.company_name if employer_profile else 'Unknown'
                match_entry = {
                    'type': 'registry',
                    'data': profile,
                    'employer_id': employer_id,
                    'employer_name': employer_name
                }
                if employer_id == employer.id:
                    same_institution_matches.append(match_entry)
                else:
                    cross_institution_matches.append(match_entry)
        else:
            # Fallback to tenant lookup if membership not available
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
                    'employer_id': None,
                    'employer_name': 'Unknown'
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
        config = get_or_create_employee_config(employee.employer_id, tenant_db)
    except EmployerProfile.DoesNotExist:
        return {'missing': [], 'all_uploaded': True}
    
    required_types = config.get_required_document_types()
    
    # Get uploaded document types from tenant database
    uploaded_types = list(
        EmployeeDocument.objects.using(tenant_db)
        .filter(employee=employee)
        .values_list('document_type', flat=True)
        .distinct()
    )
    
    # Find missing documents
    missing = [doc_type for doc_type in required_types if doc_type not in uploaded_types]
    
    return {
        'required': required_types,
        'uploaded': uploaded_types,
        'missing': missing,
        'all_uploaded': len(missing) == 0
    }


def check_expiring_documents(employee, days_ahead=None, config=None):
    """Check for documents expiring within specified days.

    If days_ahead is not provided, use employer configuration if available.
    """
    from employees.models import EmployeeDocument
    from accounts.models import EmployerProfile
    from accounts.database_utils import get_tenant_database_alias

    tenant_db = getattr(getattr(employee, "_state", None), "db", None) or "default"

    if config is None:
        try:
            employer = EmployerProfile.objects.get(id=employee.employer_id)
            tenant_db = get_tenant_database_alias(employer)
            config = get_or_create_employee_config(employee.employer_id, tenant_db)
        except EmployerProfile.DoesNotExist:
            config = None

    if config and not config.document_expiry_tracking_enabled:
        return {
            'expiring_soon': [],
            'expired': [],
            'expiring_count': 0,
            'expired_count': 0
        }

    if days_ahead is None:
        days_ahead = config.document_expiry_reminder_days if config else 30

    expiry_threshold = timezone.now().date() + timedelta(days=days_ahead)

    expiring_docs = EmployeeDocument.objects.using(tenant_db).filter(
        employee_id=employee.id,
        has_expiry=True,
        expiry_date__lte=expiry_threshold,
        expiry_date__gte=timezone.now().date()
    )

    expired_docs = EmployeeDocument.objects.using(tenant_db).filter(
        employee_id=employee.id,
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


def validate_employee_data_strict(data, config):
    """
    Strictly validate employee data against employer's specific configuration requirements.
    Used during employee profile completion to enforce that employer's REQUIRED fields.
    
    This function ensures that fields marked as REQUIRED in the employer's configuration
    are present and valid when an employee is completing their profile for that specific employer.
    
    Args:
        data: Dictionary of employee data (merged current + update data)
        config: EmployeeConfiguration instance for the specific employer
    
    Returns:
        dict: {'valid': bool, 'errors': dict, 'employer_specific': True}
    """
    errors = {}
    
    # Map field names to their config attributes
    field_config_map = {
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
        'passport': 'require_passport',
        'cnps_number': 'require_cnps_number',
        'tax_number': 'require_tax_number',
    }
    
    # Check each field against employer's configuration
    for field_name, config_attr in field_config_map.items():
        # Get the requirement level from config
        requirement = getattr(config, config_attr, 'OPTIONAL')
        
        # If field is marked as REQUIRED, validate it's present
        if requirement == config.FIELD_REQUIRED:
            value = data.get(field_name)
            
            # Check if value is missing or empty
            is_missing = (
                value is None or 
                value == '' or 
                (isinstance(value, str) and value.strip() == '')
            )
            
            if is_missing:
                # Format field name for user-friendly error message
                field_display = field_name.replace('_', ' ').title()
                errors[field_name] = f"{field_display} is required by your employer"
    
    # Validate bank details if required by this employer
    if config.require_bank_details == config.FIELD_REQUIRED:
        if config.require_bank_details_active_only:
            # Only require for active employees
            if data.get('employment_status') == 'ACTIVE':
                if not data.get('bank_account_number') or not data.get('bank_name'):
                    if not data.get('bank_account_number'):
                        errors['bank_account_number'] = "Bank account number is required for active employees"
                    if not data.get('bank_name'):
                        errors['bank_name'] = "Bank name is required for active employees"
        else:
            # Required for all employees
            if not data.get('bank_account_number') or not data.get('bank_name'):
                if not data.get('bank_account_number'):
                    errors['bank_account_number'] = "Bank account number is required by your employer"
                if not data.get('bank_name'):
                    errors['bank_name'] = "Bank name is required by your employer"
    
    # Validate emergency contact if required by this employer
    if config.require_emergency_contact == config.FIELD_REQUIRED:
        if not data.get('emergency_contact_name'):
            errors['emergency_contact_name'] = "Emergency contact name is required by your employer"
        if not data.get('emergency_contact_phone'):
            errors['emergency_contact_phone'] = "Emergency contact phone is required by your employer"
        if not data.get('emergency_contact_relationship'):
            errors['emergency_contact_relationship'] = "Emergency contact relationship is required by your employer"
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'employer_specific': True  # Flag to indicate this is employer-specific validation
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
    from employees.models import Employee, EmployeeCrossInstitutionRecord
    from accounts.models import EmployerProfile
    from accounts.database_utils import get_tenant_database_alias, ensure_tenant_database_loaded
    import uuid

    if not config:
        return {'has_other_institutions': False, 'records': []}

    visibility = getattr(config, 'cross_institution_visibility_level', 'BASIC')
    require_consent = False  # Consent flow disabled

    # Get tenant database for the current employer
    try:
        current_employer = EmployerProfile.objects.get(id=employee.employer_id)
        ensure_tenant_database_loaded(current_employer)
        tenant_db = get_tenant_database_alias(current_employer)
    except EmployerProfile.DoesNotExist:
        tenant_db = 'default'

    # Query from tenant database - no select_related since detected_employer_id is IntegerField
    records = list(
        EmployeeCrossInstitutionRecord.objects.using(tenant_db).filter(employee_id=employee.id)
    )

    def _fetch_detected_employee(record):
        if not record.detected_employer_id or not record.detected_employee_id:
            return None
        try:
            detected_employer = EmployerProfile.objects.get(id=record.detected_employer_id)
        except EmployerProfile.DoesNotExist:
            return None
        ensure_tenant_database_loaded(detected_employer)
        detected_db = get_tenant_database_alias(detected_employer)
        detected_employee_id = str(record.detected_employee_id)

        employee_qs = Employee.objects.using(detected_db).select_related('department', 'branch')
        candidate = None
        try:
            candidate_uuid = uuid.UUID(detected_employee_id)
            candidate = employee_qs.filter(id=candidate_uuid).first()
        except (ValueError, TypeError):
            candidate = None

        if not candidate:
            candidate = employee_qs.filter(employee_id=detected_employee_id).first()

        return candidate

    if visibility == 'NONE':
        return {
            'has_other_institutions': bool(records),
            'count': len(records),
            'records': [],
            'institutions': []
        }

    summary = []
    for record in records:
        # Manually fetch employer info from main database using detected_employer_id
        try:
            detected_employer = EmployerProfile.objects.get(id=record.detected_employer_id)
            employer_name = detected_employer.company_name
        except EmployerProfile.DoesNotExist:
            employer_name = 'Unknown'

        info = {}

        if visibility in ['BASIC', 'MODERATE', 'FULL']:
            info['employer_id'] = str(record.detected_employer_id)
            info['company_name'] = employer_name

        # Flag restricted details for non-full visibility
        if visibility != 'FULL':
            info['details_restricted'] = True

        if visibility in ['MODERATE', 'FULL']:
            detected_employee = _fetch_detected_employee(record)
            if detected_employee:
                info['employment_start_date'] = detected_employee.hire_date
                info['employment_end_date'] = detected_employee.termination_date
                info['employment_dates'] = {
                    'detected_at': record.detected_at,
                    'hire_date': detected_employee.hire_date,
                    'termination_date': detected_employee.termination_date,
                }
            else:
                info['employment_dates'] = {'detected_at': record.detected_at}

        if visibility == 'FULL':
            detected_employee = _fetch_detected_employee(record)
            info.update({
                'employee_id': record.detected_employee_id,
                'status': record.status,
                'consent_status': record.consent_status,
                'verified': record.verified,
                'notes': record.notes,
            })
            if detected_employee:
                info['employment_status'] = detected_employee.employment_status
                info['employment_type'] = detected_employee.employment_type
                info['job_title'] = detected_employee.job_title
                info['department'] = (
                    detected_employee.department.name if detected_employee.department else None
                )
                info['branch'] = (
                    detected_employee.branch.name if detected_employee.branch else None
                )

        summary.append(info)

    return {
        'has_other_institutions': bool(records),
        'count': len(records),
        'records': summary,
        'institutions': summary  # Backward-compatible alias for frontend consumers
    }


def check_missing_fields_against_config(employee_data, config):
    """
    Check which fields are missing from employee data based on employer configuration.
    Distinguishes between critical (blocking) and non-critical (non-blocking) missing fields.
    
    Args:
        employee_data: dict or Employee instance with employee data
        config: EmployeeConfiguration instance
    
    Returns:
        dict: {
            'missing_critical': list of critical missing field names,
            'missing_non_critical': list of non-critical missing field names,
            'is_blocking': bool - whether critical fields are missing,
            'completion_state': str - COMPLETE, INCOMPLETE_BLOCKING, or INCOMPLETE_NON_BLOCKING
        }
    """
    from employees.models import Employee
    
    # Convert Employee instance to dict if needed
    if isinstance(employee_data, Employee):
        # Use getattr with default to avoid triggering queries for foreign keys
        data = {
            'middle_name': employee_data.middle_name,
            'profile_photo': employee_data.profile_photo,
            'gender': employee_data.gender,
            'date_of_birth': employee_data.date_of_birth,
            'marital_status': employee_data.marital_status,
            'nationality': employee_data.nationality,
            'personal_email': employee_data.personal_email,
            'alternative_phone': employee_data.alternative_phone,
            'address': employee_data.address,
            'postal_code': employee_data.postal_code,
            'national_id_number': employee_data.national_id_number,
            'passport': employee_data.passport_number,
            'cnps_number': employee_data.cnps_number,
            'tax_number': employee_data.tax_number,
            'phone_number': employee_data.phone_number,
            'city': employee_data.city,
            'state_region': employee_data.state_region,
            'country': employee_data.country,
            # Use direct field access for foreign key IDs to avoid queries
            'department': getattr(employee_data, 'department_id', None),
            'branch': getattr(employee_data, 'branch_id', None),
            'manager': getattr(employee_data, 'manager_id', None),
            'probation_end_date': employee_data.probation_end_date,
            'bank_account_number': employee_data.bank_account_number,
            'bank_name': employee_data.bank_name,
            'bank_account_name': employee_data.bank_account_name,
            'emergency_contact_name': employee_data.emergency_contact_name,
            'emergency_contact_phone': employee_data.emergency_contact_phone,
            'emergency_contact_relationship': employee_data.emergency_contact_relationship,
            'employment_status': employee_data.employment_status,
        }
    else:
        data = employee_data
    
    # Get critical fields from config (default to core identity fields if not set)
    critical_fields_list = config.critical_fields if config.critical_fields else [
        'national_id_number',
        'date_of_birth',
        'gender',
        'nationality'
    ]
    
    # Field mapping: field_name -> config attribute
    field_config_map = {
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
        'passport': 'require_passport',
        'cnps_number': 'require_cnps_number',
        'tax_number': 'require_tax_number',
        'department': 'require_department',
        'branch': 'require_branch',
        'manager': 'require_manager',
        'probation_end_date': 'require_probation_period',
        'bank_details': 'require_bank_details',
        'emergency_contact': 'require_emergency_contact',
    }
    
    missing_critical = []
    missing_non_critical = []
    
    for field_name, config_attr in field_config_map.items():
        requirement = getattr(config, config_attr, 'OPTIONAL')
        
        # Skip if field is hidden - don't track at all
        if requirement == config.FIELD_HIDDEN:
            continue
        
        # Check if field has value
        is_missing = False
        
        # Special handling for complex fields
        if field_name == 'bank_details':
            # Check if bank details are required
            if config.require_bank_details_active_only and data.get('employment_status') != 'ACTIVE':
                continue  # Not required for non-active employees
            is_missing = not (data.get('bank_account_number') and data.get('bank_name'))
        elif field_name == 'emergency_contact':
            is_missing = not (data.get('emergency_contact_name') and data.get('emergency_contact_phone'))
        else:
            # Regular field check
            value = data.get(field_name)
            is_missing = value is None or value == '' or (isinstance(value, str) and value.strip() == '')
        
        if is_missing:
            # Only add to missing lists if the field is required or optional (not hidden)
            if requirement == config.FIELD_REQUIRED:
                # Determine if this is a critical field
                if field_name in critical_fields_list:
                    missing_critical.append(field_name)
                else:
                    missing_non_critical.append(field_name)
            elif requirement == config.FIELD_OPTIONAL:
                # Optional missing fields go to non-critical
                missing_non_critical.append(field_name)
    
    # Check for missing required documents (if employee_data is an Employee instance)
    missing_documents = []
    if isinstance(employee_data, Employee):
        required_doc_types = config.get_required_document_types()
        
        # Get uploaded document types for this employee
        from employees.models import EmployeeDocument
        tenant_db = getattr(getattr(employee_data, "_state", None), "db", None) or "default"
        uploaded_doc_types = list(
            EmployeeDocument.objects.using(tenant_db).filter(employee_id=employee_data.id)
            .values_list('document_type', flat=True)
            .distinct()
        )
        
        # Find missing documents
        missing_documents = [doc_type for doc_type in required_doc_types if doc_type not in uploaded_doc_types]
    
    # Documents are always considered critical (blocking) if required
    if missing_documents:
        missing_critical.extend([f'document_{doc}' for doc in missing_documents])
    
    # Determine completion state
    if missing_critical:
        completion_state = 'INCOMPLETE_BLOCKING'
        is_blocking = True
    elif missing_non_critical:
        completion_state = 'INCOMPLETE_NON_BLOCKING'
        is_blocking = False
    else:
        completion_state = 'COMPLETE'
        is_blocking = False
    
    return {
        'missing_critical': missing_critical,
        'missing_non_critical': missing_non_critical,
        'missing_documents': missing_documents,
        'is_blocking': is_blocking,
        'completion_state': completion_state,
        'requires_update': len(missing_critical) > 0 or len(missing_non_critical) > 0
    }


def validate_existing_employee_against_new_config(employee_registry, config):
    """
    Validate if an existing employee's data from EmployeeRegistry meets
    a new employer's configuration requirements.
    
    Args:
        employee_registry: EmployeeRegistry instance
        config: EmployeeConfiguration instance for the new employer
    
    Returns:
        dict: Same as check_missing_fields_against_config
    """
    # Convert EmployeeRegistry to data dict matching Employee field names
    data = {
        'middle_name': employee_registry.middle_name,
        'profile_photo': employee_registry.profile_picture,  # Note: different field name
        'gender': employee_registry.gender,
        'date_of_birth': employee_registry.date_of_birth,
        'marital_status': employee_registry.marital_status,
        'nationality': employee_registry.nationality,
        'personal_email': employee_registry.personal_email,
        'alternative_phone': employee_registry.alternative_phone,
        'address': employee_registry.address,
        'postal_code': employee_registry.postal_code,
        'national_id_number': employee_registry.national_id_number,
        'passport': employee_registry.passport_number,
        'phone_number': employee_registry.phone_number,
        'city': employee_registry.city,
        'state_region': employee_registry.state_region,
        'country': employee_registry.country,
        'emergency_contact_name': employee_registry.emergency_contact_name,
        'emergency_contact_phone': employee_registry.emergency_contact_phone,
        'emergency_contact_relationship': employee_registry.emergency_contact_relationship,
        # These fields won't exist in registry, will be set by employer
        'cnps_number': None,
        'tax_number': None,
        'department': None,
        'branch': None,
        'manager': None,
        'probation_end_date': None,
        'bank_account_number': None,
        'bank_name': None,
        'bank_account_name': None,
        'employment_status': 'PENDING',  # Default for new hire
    }
    
    return check_missing_fields_against_config(data, config)


def send_profile_completion_notification(employee, missing_fields_info, employer, tenant_db=None):
    """
    Send email notification to employee about required profile completion.
    
    Args:
        employee: Employee instance
        missing_fields_info: dict from check_missing_fields_against_config
        employer: EmployerProfile instance
        tenant_db: tenant database alias
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.conf import settings
    
    if not employee.user_id:
        return  # Can't send email if no user account exists
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        user = User.objects.get(id=employee.user_id)
        email = user.email
    except User.DoesNotExist:
        return
    
    # Prepare context for email template
    context = {
        'employee_name': employee.full_name,
        'company_name': employer.company_name,
        'missing_critical': missing_fields_info.get('missing_critical', []),
        'missing_non_critical': missing_fields_info.get('missing_non_critical', []),
        'missing_documents': missing_fields_info.get('missing_documents', []),
        'is_blocking': missing_fields_info.get('is_blocking', False),
        'completion_url': f"{settings.FRONTEND_URL}/employee/profile/complete",
    }
    
    # Format field names for display
    def format_field_name(field):
        # Handle document fields specially
        if field.startswith('document_'):
            doc_type = field.replace('document_', '')
            return f"Document: {doc_type.replace('_', ' ').title()}"
        return field.replace('_', ' ').title()
    
    context['missing_critical_formatted'] = [format_field_name(f) for f in context['missing_critical']]
    context['missing_non_critical_formatted'] = [format_field_name(f) for f in context['missing_non_critical']]
    
    # Format document types for display
    def format_document_type(doc_type):
        from employees.models import EmployeeDocument
        # Get the human-readable name from choices
        for choice_value, choice_label in EmployeeDocument.DOCUMENT_TYPE_CHOICES:
            if choice_value == doc_type:
                return choice_label
        return doc_type.replace('_', ' ').title()
    
    context['missing_documents_formatted'] = [format_document_type(doc) for doc in context['missing_documents']]
    
    # Render email templates
    subject = f"Profile Completion Required - {employer.company_name}"
    html_message = render_to_string('emails/profile_completion_required.html', context)
    plain_message = render_to_string('emails/profile_completion_required.txt', context)
    
    # Send email
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send profile completion email to {email}: {str(e)}")

    # Also create in-app notification for the employee
    try:
        notify_employee_user(
            employee,
            title="Profile completion required",
            body=f"{employer.company_name} requires additional profile details.",
            type="ACTION",
            data={
                "event": "employees.profile_completion_required",
                "missing_critical": context.get("missing_critical", []),
                "missing_non_critical": context.get("missing_non_critical", []),
                "missing_documents": context.get("missing_documents", []),
                "is_blocking": context.get("is_blocking", False),
                "path": "/employee/profile/complete",
            },
            employer_profile=employer,
        )
    except Exception:
        pass


def send_welcome_email(employee, employer):
    """Send welcome email to employee after accepting invitation"""
    from django.core.mail import send_mail
    from django.conf import settings
    from django.template.loader import render_to_string
    
    context = {
        'employee': employee,
        'employer': employer,
        'login_url': f"{settings.FRONTEND_URL}/login",
    }
    
    subject = f"Welcome to {employer.company_name}"
    html_message = render_to_string('emails/welcome_email.html', context)
    text_message = render_to_string('emails/welcome_email.txt', context)
    
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[employee.email or employee.personal_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send welcome email to {employee.email}: {str(e)}")


def send_document_expiry_reminder(employee, document, employer, days_until_expiry):
    """Send reminder email for expiring document"""
    from django.core.mail import send_mail
    from django.conf import settings
    from django.template.loader import render_to_string
    
    context = {
        'employee': employee,
        'employer': employer,
        'document': document,
        'days_until_expiry': days_until_expiry,
        'expiry_date': document.expiry_date,
    }
    
    subject = f"Document Expiring Soon - {document.title}"
    html_message = render_to_string('emails/document_expiry_reminder.html', context)
    text_message = render_to_string('emails/document_expiry_reminder.txt', context)
    
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[employee.email or employee.personal_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send document expiry reminder to {employee.email}: {str(e)}")


def send_probation_ending_reminder(employee, employer, days_until_end):
    """Send reminder email for probation period ending"""
    from django.core.mail import send_mail
    from django.conf import settings
    from django.template.loader import render_to_string
    
    context = {
        'employee': employee,
        'employer': employer,
        'days_until_end': days_until_end,
        'probation_end_date': employee.probation_end_date,
    }
    
    subject = f"Probation Period Ending Soon - {employer.company_name}"
    html_message = render_to_string('emails/probation_ending_reminder.html', context)
    text_message = render_to_string('emails/probation_ending_reminder.txt', context)
    
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[employee.email or employee.personal_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send probation ending reminder to {employee.email}: {str(e)}")


def get_employer_notification_recipients(employer, *, exclude_user_id=None):
    """Return employer users who should receive operational notifications."""
    from accounts.models import EmployeeMembership

    recipients = {}
    if employer and getattr(employer, "user", None) and employer.user.is_active:
        recipients[employer.user.id] = employer.user

    memberships = (
        EmployeeMembership.objects.filter(
            employer_profile_id=employer.id,
            status=EmployeeMembership.STATUS_ACTIVE,
            role__in=[
                EmployeeMembership.ROLE_HR,
                EmployeeMembership.ROLE_ADMIN,
                EmployeeMembership.ROLE_MANAGER,
            ],
        )
        .select_related("user")
    )
    for membership in memberships:
        user = membership.user
        if not user or not user.is_active:
            continue
        recipients[user.id] = user

    if exclude_user_id:
        recipients.pop(exclude_user_id, None)

    return list(recipients.values())


def notify_employer_users(employer, title, body="", *, type="INFO", data=None, exclude_user_id=None):
    """Send in-app notification to employer owner/HR/manager users."""
    from accounts.notifications import create_notification

    recipients = get_employer_notification_recipients(employer, exclude_user_id=exclude_user_id)
    for user in recipients:
        create_notification(
            user=user,
            title=title,
            body=body,
            type=type,
            data=data or {},
            employer_profile=employer,
        )
    return recipients


def notify_employee_user(employee, title, body="", *, type="INFO", data=None, employer_profile=None):
    """Send in-app notification to the employee's linked user (if any)."""
    from accounts.notifications import create_notification
    from django.contrib.auth import get_user_model

    if not employee or not getattr(employee, "user_id", None):
        return None

    User = get_user_model()
    user = User.objects.filter(id=employee.user_id, is_active=True).first()
    if not user:
        return None

    return create_notification(
        user=user,
        title=title,
        body=body,
        type=type,
        data=data or {},
        employer_profile=employer_profile,
    )


def generate_consent_token():
    """Generate a secure random token for consent requests"""
    import secrets
    return secrets.token_urlsafe(32)


def check_concurrent_employment(employee_registry_id, new_employer_id, config):
    """
    Check if concurrent employment is allowed when linking employee to new employer
    
    Args:
        employee_registry_id: EmployeeRegistry ID
        new_employer_id: New employer ID to link to
        config: EmployeeConfiguration for the new employer
        
    Returns:
        dict: {'allowed': bool, 'reason': str, 'existing_employers': list}
    """
    from accounts.models import EmployeeMembership, EmployeeRegistry
    from employees.models import Employee
    from accounts.database_utils import get_tenant_database_alias
    
    existing_employers = []

    # Contract configuration is not enforced at employee creation time.
    # Employee-level configuration is the source of truth for concurrent employment here.

    # Fetch registry and memberships for this user
    try:
        registry = EmployeeRegistry.objects.get(id=employee_registry_id)
    except EmployeeRegistry.DoesNotExist:
        return {
            'allowed': True,
            'reason': 'No concurrent employment detected',
            'existing_employers': []
        }

    memberships = (
        EmployeeMembership.objects
        .filter(user_id=registry.user_id, status=EmployeeMembership.STATUS_ACTIVE)
        .select_related('employer_profile')
    )

    for membership in memberships:
        employer = membership.employer_profile
        if not employer or employer.id == new_employer_id:
            continue

        entry = {
            'employer_id': employer.id,
            'employer_name': employer.company_name,
        }

        # Try to resolve employee details for context
        if membership.tenant_employee_id:
            try:
                tenant_db = get_tenant_database_alias(employer)
                matched = Employee.objects.using(tenant_db).filter(id=membership.tenant_employee_id).only(
                    'employee_id', 'hire_date'
                ).first()
                if matched:
                    entry['employee_id'] = matched.employee_id
                    entry['hire_date'] = matched.hire_date
                else:
                    entry['employee_id'] = membership.tenant_employee_id
            except Exception:
                entry['employee_id'] = membership.tenant_employee_id

        existing_employers.append(entry)
    
    # If there are existing active employments
    if existing_employers:
        allow_concurrent = bool(config and config.allow_concurrent_employment)
        if not allow_concurrent:
            return {
                'allowed': False,
                'reason': 'Concurrent employment is not allowed by this employer',
                'existing_employers': existing_employers
            }
        return {
            'allowed': True,
            'reason': 'Concurrent employment allowed',
            'existing_employers': existing_employers
        }
    
    # No existing employments found
    return {
        'allowed': True,
        'reason': 'No concurrent employment detected',
        'existing_employers': []
    }


def create_termination_approval_request(employee, requested_by, termination_date, termination_reason, config, tenant_db):
    """
    Create a termination approval request based on configuration
    
    Args:
        employee: Employee instance
        requested_by: User who requested termination
        termination_date: Proposed termination date
        termination_reason: Reason for termination
        config: EmployeeConfiguration instance
        tenant_db: Database alias
        
    Returns:
        TerminationApproval instance or None if approval not required
    """
    from employees.models import TerminationApproval
    from django.utils import timezone
    
    if not config.termination_approval_required:
        return None
    
    # Determine what approvals are needed
    requires_manager = config.termination_approval_by in ['MANAGER', 'BOTH']
    requires_hr = config.termination_approval_by in ['HR', 'BOTH', 'ADMIN']
    
    # Create approval request in tenant database
    approval = TerminationApproval.objects.using(tenant_db).create(
        employee=employee,
        requested_by_id=requested_by.id,
        termination_date=termination_date,
        termination_reason=termination_reason,
        requires_manager_approval=requires_manager,
        requires_hr_approval=requires_hr,
        status='PENDING'
    )
    
    return approval


def revoke_employee_access(employee, config, tenant_db):
    """
    Revoke employee system access based on termination configuration
    
    Args:
        employee: Employee instance
        config: EmployeeConfiguration instance
        tenant_db: Database alias
    """
    from django.utils import timezone
    from datetime import timedelta
    
    if not employee.user_id:
        return  # No user account to revoke
    
    timing = config.termination_revoke_access_timing
    
    if timing == 'IMMEDIATE':
        # Revoke immediately
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=employee.user_id)
            user.is_active = False
            user.save()
            try:
                from accounts.models import EmployerProfile
                employer = EmployerProfile.objects.filter(id=employee.employer_id).first()
                notify_employee_user(
                    employee,
                    title="Access revoked",
                    body="Your access has been revoked due to termination.",
                    type="ALERT",
                    data={
                        "event": "employees.access_revoked",
                        "employee_id": str(employee.id),
                        "path": "/login",
                    },
                    employer_profile=employer,
                )
            except Exception:
                pass
        except User.DoesNotExist:
            pass
    
    elif timing == 'ON_DATE':
        # Will be revoked on termination date (handled by scheduled task)
        pass
    
    elif timing == 'CUSTOM':
        # Calculate revoke date
        delay_days = config.termination_access_delay_days or 0
        # Will be revoked after delay (handled by scheduled task)
        pass


def terminate_employee_contracts(
    employee,
    *,
    tenant_db,
    termination_date,
    termination_reason=None,
    performed_by=None,
):
    """
    Terminate all active/pending contracts for an employee.
    Keeps contract audit logs and notifications consistent.
    """
    if not employee:
        return 0

    try:
        from contracts.models import Contract
        from contracts.notifications import notify_terminated
    except Exception:
        return 0

    statuses = ['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE', 'APPROVED', 'PENDING_APPROVAL']
    contracts = Contract.objects.using(tenant_db).filter(
        employee=employee,
        status__in=statuses
    )
    count = 0
    for contract in contracts:
        try:
            contract.status = 'TERMINATED'
            contract.termination_date = termination_date
            if termination_reason:
                contract.termination_reason = termination_reason
            contract.final_pay_flag = True
            contract.save(using=tenant_db)
            try:
                contract.log_action(
                    performed_by,
                    'TERMINATED',
                    metadata={
                        'reason': termination_reason,
                        'termination_date': str(termination_date),
                        'source': 'employee_termination',
                    },
                )
            except Exception:
                pass
            try:
                notify_terminated(contract)
            except Exception:
                pass
            count += 1
        except Exception:
            continue
    return count

