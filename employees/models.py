from django.db import models
from django.contrib.auth import get_user_model
# Remove direct import to avoid cross-database foreign key issues
# from accounts.models import EmployerProfile
from django.utils import timezone
import uuid
import json

User = get_user_model()


class EmployeeConfiguration(models.Model):
    """Configuration for employee management at institution level"""
    
    # Employee ID Format Options
    ID_FORMAT_SEQUENTIAL = 'SEQUENTIAL'  # EMP-001, EMP-002, etc.
    ID_FORMAT_YEAR_BASED = 'YEAR_BASED'  # EMP-2025-001
    ID_FORMAT_BRANCH_BASED = 'BRANCH_BASED'  # YAO-001 (Yaoundé), DLA-001 (Douala)
    ID_FORMAT_DEPT_BASED = 'DEPT_BASED'  # HR-001, IT-001
    ID_FORMAT_CUSTOM = 'CUSTOM'  # Custom format defined in template
    
    ID_FORMAT_CHOICES = [
        (ID_FORMAT_SEQUENTIAL, 'Sequential (EMP-001)'),
        (ID_FORMAT_YEAR_BASED, 'Year Based (EMP-2025-001)'),
        (ID_FORMAT_BRANCH_BASED, 'Branch Based (YAO-001)'),
        (ID_FORMAT_DEPT_BASED, 'Department Based (HR-001)'),
        (ID_FORMAT_CUSTOM, 'Custom Template'),
    ]
    
    # Field Requirement Levels
    FIELD_REQUIRED = 'REQUIRED'
    FIELD_OPTIONAL = 'OPTIONAL'
    FIELD_HIDDEN = 'HIDDEN'
    
    FIELD_REQUIREMENT_CHOICES = [
        (FIELD_REQUIRED, 'Required'),
        (FIELD_OPTIONAL, 'Optional'),
        (FIELD_HIDDEN, 'Hidden'),
    ]
    
    # Duplicate Detection Levels
    DUPLICATE_STRICT = 'STRICT'  # Exact national ID match
    DUPLICATE_MODERATE = 'MODERATE'  # National ID, email, or phone
    DUPLICATE_LENIENT = 'LENIENT'  # Fuzzy name + DOB matching
    
    DUPLICATE_DETECTION_CHOICES = [
        (DUPLICATE_STRICT, 'Strict (National ID only)'),
        (DUPLICATE_MODERATE, 'Moderate (ID, email, phone)'),
        (DUPLICATE_LENIENT, 'Lenient (Fuzzy matching)'),
    ]
    
    # Duplicate Action Options
    DUPLICATE_ACTION_BLOCK = 'BLOCK'
    DUPLICATE_ACTION_WARN = 'WARN'
    DUPLICATE_ACTION_ALLOW = 'ALLOW'
    
    DUPLICATE_ACTION_CHOICES = [
        (DUPLICATE_ACTION_BLOCK, 'Block creation'),
        (DUPLICATE_ACTION_WARN, 'Warn user'),
        (DUPLICATE_ACTION_ALLOW, 'Allow with reason'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Use IntegerField instead of ForeignKey for cross-database compatibility
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    
    # ===== Employee ID Configuration =====
    employee_id_format = models.CharField(max_length=20, choices=ID_FORMAT_CHOICES, default=ID_FORMAT_SEQUENTIAL)
    employee_id_prefix = models.CharField(max_length=10, default='EMP', help_text='Prefix for employee IDs')
    employee_id_suffix = models.CharField(max_length=10, blank=True, null=True, help_text='Suffix for employee IDs')
    employee_id_starting_number = models.IntegerField(default=1, help_text='Starting sequence number')
    employee_id_padding = models.IntegerField(default=3, help_text='Number of digits (e.g., 3 = 001)')
    employee_id_include_branch = models.BooleanField(default=False, help_text='Include branch code in ID')
    employee_id_include_department = models.BooleanField(default=False, help_text='Include department code in ID')
    employee_id_include_year = models.BooleanField(default=False, help_text='Include year in ID')
    employee_id_custom_template = models.CharField(max_length=100, blank=True, null=True, 
        help_text='Custom template: {prefix}-{year}-{branch}-{number}')
    employee_id_manual_override = models.BooleanField(default=False, help_text='Allow manual employee ID entry')
    
    # ===== Required vs Optional Fields Configuration =====
    # Basic Information
    require_middle_name = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_profile_photo = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_gender = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    require_date_of_birth = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    require_marital_status = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_nationality = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    
    # Contact Information
    require_personal_email = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_alternative_phone = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_address = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    require_postal_code = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    
    # Legal Identification
    require_national_id = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    require_passport = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_cnps_number = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    require_tax_number = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    
    # Employment Details
    require_department = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    require_branch = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_manager = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    require_probation_period = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_OPTIONAL)
    
    # Payroll Information
    require_bank_details = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    require_bank_details_active_only = models.BooleanField(default=True, 
        help_text='Require bank details only for active employees')
    
    # Emergency Contact
    require_emergency_contact = models.CharField(max_length=20, choices=FIELD_REQUIREMENT_CHOICES, default=FIELD_REQUIRED)
    
    # ===== Cross-Institution Employment Rules =====
    allow_concurrent_employment = models.BooleanField(default=False, 
        help_text='Allow employees to work in multiple institutions simultaneously')
    require_employee_consent_cross_institution = models.BooleanField(default=True, 
        help_text='Require employee consent before linking to another institution')
    cross_institution_visibility_level = models.CharField(max_length=20, 
        choices=[
            ('NONE', 'No visibility'),
            ('BASIC', 'Institution name only'),
            ('MODERATE', 'Institution name and employment dates'),
            ('FULL', 'Full employment details'),
        ], default='BASIC', help_text='What information is visible about other institutions')
    
    # ===== Duplicate Detection Rules =====
    duplicate_detection_level = models.CharField(max_length=20, choices=DUPLICATE_DETECTION_CHOICES, default=DUPLICATE_MODERATE)
    duplicate_action = models.CharField(max_length=20, choices=DUPLICATE_ACTION_CHOICES, default=DUPLICATE_ACTION_WARN)
    duplicate_check_national_id = models.BooleanField(default=True, help_text='Check national ID for duplicates')
    duplicate_check_email = models.BooleanField(default=True, help_text='Check email for duplicates')
    duplicate_check_phone = models.BooleanField(default=True, help_text='Check phone for duplicates')
    duplicate_check_name_dob = models.BooleanField(default=False, help_text='Check name + DOB combination')
    
    # ===== Document Management Configuration =====
    required_documents = models.JSONField(default=list, blank=True, 
        help_text='List of required document types: ["RESUME", "ID_COPY", "CERTIFICATE"]')
    document_expiry_tracking_enabled = models.BooleanField(default=True, 
        help_text='Track document expiration dates')
    document_expiry_reminder_days = models.IntegerField(default=30, 
        help_text='Send reminder X days before document expires')
    document_max_file_size_mb = models.IntegerField(default=10, help_text='Maximum file size in MB')
    document_allowed_formats = models.JSONField(default=list, blank=True, 
        help_text='Allowed file formats: ["pdf", "jpg", "png", "docx"]')
    
    # ===== Termination Workflow Configuration =====
    require_termination_reason = models.BooleanField(default=True, help_text='Require reason when terminating employee')
    termination_approval_required = models.BooleanField(default=True, help_text='Require approval for termination')
    termination_approval_by = models.CharField(max_length=20, 
        choices=[
            ('MANAGER', 'Direct Manager'),
            ('HR', 'HR Department'),
            ('BOTH', 'Both Manager and HR'),
            ('ADMIN', 'System Admin'),
        ], default='HR', help_text='Who must approve termination')
    termination_revoke_access_timing = models.CharField(max_length=20,
        choices=[
            ('IMMEDIATE', 'Immediately'),
            ('ON_DATE', 'On termination date'),
            ('CUSTOM', 'Custom delay'),
        ], default='ON_DATE', help_text='When to revoke system access')
    termination_access_delay_days = models.IntegerField(default=0, 
        help_text='Days after termination to revoke access (if custom)')
    termination_data_retention_months = models.IntegerField(default=60, 
        help_text='Months to retain terminated employee data (0 = indefinite)')
    allow_employee_reactivation = models.BooleanField(default=True, 
        help_text='Allow reactivating terminated employees')
    
    # ===== Notification Settings =====
    send_invitation_email = models.BooleanField(default=True, help_text='Send invitation email to new employees')
    invitation_expiry_days = models.IntegerField(default=7, help_text='Days until invitation expires')
    send_welcome_email = models.BooleanField(default=True, help_text='Send welcome email when employee accepts')
    send_profile_completion_reminder = models.BooleanField(default=True, 
        help_text='Remind employees to complete their profile')
    profile_completion_reminder_days = models.IntegerField(default=3, 
        help_text='Days after invitation to send reminder')
    
    # ===== Probation Configuration =====
    default_probation_period_months = models.IntegerField(default=3, help_text='Default probation period in months')
    probation_review_required = models.BooleanField(default=True, help_text='Require probation review before confirmation')
    probation_reminder_before_end_days = models.IntegerField(default=14, 
        help_text='Days before probation ends to send reminder')
    
    # ===== System Settings =====
    auto_generate_work_email = models.BooleanField(default=False, 
        help_text='Automatically generate work email (e.g., firstname.lastname@company.com)')
    work_email_template = models.CharField(max_length=100, blank=True, null=True,
        help_text='Template: {firstname}.{lastname}@{domain}')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employee_configurations'
        verbose_name = 'Employee Configuration'
        verbose_name_plural = 'Employee Configurations'

    def __str__(self):
        return f"Employee Config - Employer ID: {self.employer_id}"
    
    def get_next_employee_id(self, branch=None, department=None, using='default'):
        """Generate next employee ID based on configuration
        
        Args:
            branch: Branch object (optional)
            department: Department object (optional)
            using: Database alias to use for queries
        """
        from employees.models import Employee
        import re
        
        # Get the highest employee number currently in use
        # Extract numbers from existing employee IDs and find the max
        existing_employees = Employee.objects.using(using).filter(
            employer_id=self.employer_id
        ).exclude(employee_id='').exclude(employee_id__isnull=True).values_list('employee_id', flat=True)
        
        max_number = 0
        for emp_id in existing_employees:
            # Extract all numbers from the employee ID
            numbers = re.findall(r'\d+', str(emp_id))
            if numbers:
                # Get the last number (usually the sequence number)
                try:
                    num = int(numbers[-1])
                    if num > max_number:
                        max_number = num
                except ValueError:
                    continue
        
        # Next number is max + 1, or starting number if no employees exist
        if max_number > 0:
            next_number = max_number + 1
        else:
            next_number = self.employee_id_starting_number
        
        # Format number with padding
        formatted_number = str(next_number).zfill(self.employee_id_padding)
        
        # Build ID based on format
        if self.employee_id_format == self.ID_FORMAT_SEQUENTIAL:
            employee_id = f"{self.employee_id_prefix}-{formatted_number}"
        
        elif self.employee_id_format == self.ID_FORMAT_YEAR_BASED:
            current_year = timezone.now().year
            employee_id = f"{self.employee_id_prefix}-{current_year}-{formatted_number}"
        
        elif self.employee_id_format == self.ID_FORMAT_BRANCH_BASED:
            branch_code = branch.code if branch else "HQ"
            employee_id = f"{branch_code}-{formatted_number}"
        
        elif self.employee_id_format == self.ID_FORMAT_DEPT_BASED:
            dept_code = department.code if department and hasattr(department, 'code') else "GEN"
            employee_id = f"{dept_code}-{formatted_number}"
        
        elif self.employee_id_format == self.ID_FORMAT_CUSTOM and self.employee_id_custom_template:
            # Parse custom template
            template = self.employee_id_custom_template
            template = template.replace('{prefix}', self.employee_id_prefix)
            template = template.replace('{year}', str(timezone.now().year))
            template = template.replace('{branch}', branch.code if branch else 'HQ')
            template = template.replace('{dept}', department.code if department and hasattr(department, 'code') else 'GEN')
            template = template.replace('{number}', formatted_number)
            employee_id = template
        else:
            employee_id = f"{self.employee_id_prefix}-{formatted_number}"
        
        # Add suffix if configured
        if self.employee_id_suffix:
            employee_id = f"{employee_id}-{self.employee_id_suffix}"
        
        return employee_id
    
    def is_field_required(self, field_name):
        """Check if a field is required"""
        field_config = getattr(self, f'require_{field_name}', None)
        return field_config == self.FIELD_REQUIRED
    
    def is_field_optional(self, field_name):
        """Check if a field is optional"""
        field_config = getattr(self, f'require_{field_name}', None)
        return field_config == self.FIELD_OPTIONAL
    
    def is_field_hidden(self, field_name):
        """Check if a field is hidden"""
        field_config = getattr(self, f'require_{field_name}', None)
        return field_config == self.FIELD_HIDDEN
    
    def get_required_document_types(self):
        """Get list of required document types"""
        if isinstance(self.required_documents, list):
            return self.required_documents
        try:
            return json.loads(self.required_documents)
        except:
            return []
    
    def get_allowed_document_formats(self):
        """Get list of allowed document formats"""
        if isinstance(self.document_allowed_formats, list):
            return self.document_allowed_formats
        try:
            return json.loads(self.document_allowed_formats)
        except:
            return ['pdf', 'jpg', 'jpeg', 'png', 'docx']


class Department(models.Model):
    """Department within an institution/company"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    branch = models.ForeignKey('Branch', on_delete=models.CASCADE, related_name='departments', 
                                null=True, blank=True, help_text='Branch this department belongs to (optional for company-wide departments)')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, help_text='Department code (e.g., HR, IT, FIN)')
    description = models.TextField(blank=True, null=True)
    parent_department = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_departments')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'departments'
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        unique_together = [['employer_id', 'name'], ['employer_id', 'code']]
        ordering = ['name']

    def __str__(self):
        branch_info = f" - {self.branch.name}" if self.branch else ""
        return f"{self.name}{branch_info} (Employer ID: {self.employer_id})"


class Branch(models.Model):
    """Branch/Location of an institution"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, help_text='Branch code/identifier')
    address = models.TextField()
    city = models.CharField(max_length=100)
    state_region = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_headquarters = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'branches'
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'
        unique_together = [['employer_id', 'code']]
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code}) - Employer ID: {self.employer_id}"


class Employee(models.Model):
    """Employee master record managed by employer"""
    
    EMPLOYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROBATION', 'Probation'),
        ('ACTIVE', 'Active'),
        ('ON_LEAVE', 'On Leave'),
        ('SUSPENDED', 'Suspended'),
        ('TERMINATED', 'Terminated'),
        ('RESIGNED', 'Resigned'),
        ('RETIRED', 'Retired'),
    ]
    
    EMPLOYMENT_TYPE_CHOICES = [
        ('FULL_TIME', 'Full Time'),
        ('PART_TIME', 'Part Time'),
        ('CONTRACT', 'Contract'),
        ('TEMPORARY', 'Temporary'),
        ('INTERN', 'Intern'),
        ('CONSULTANT', 'Consultant'),
    ]
    
    GENDER_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('OTHER', 'Other'),
        ('PREFER_NOT_TO_SAY', 'Prefer not to say'),
    ]
    
    MARITAL_STATUS_CHOICES = [
        ('SINGLE', 'Single'),
        ('MARRIED', 'Married'),
        ('DIVORCED', 'Divorced'),
        ('WIDOWED', 'Widowed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    
    # Link to user account (optional - employee may not have created account yet)
    user_id = models.IntegerField(null=True, blank=True, db_index=True, help_text='ID of the user account (from main database)')
    
    # Basic Information (core fields required by employer)
    employee_id = models.CharField(max_length=50, blank=True, help_text='Company-assigned employee ID (auto-generated if not provided)')
    first_name = models.CharField(max_length=100)  # Required by employer
    last_name = models.CharField(max_length=100)  # Required by employer
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)  # Employee completes
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)  # Employee completes
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True, null=True)
    nationality = models.CharField(max_length=100, blank=True, null=True)  # Employee completes
    profile_photo = models.ImageField(upload_to='employee_photos/', blank=True, null=True)
    
    # Contact Information
    email = models.EmailField(help_text='Work email')  # Required by employer
    personal_email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)  # Employee completes
    alternative_phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)  # Employee completes
    city = models.CharField(max_length=100, blank=True, null=True)  # Employee completes
    state_region = models.CharField(max_length=100, blank=True, null=True)  # Employee completes
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)  # Employee completes
    
    # Legal Identification (employee completes their own sensitive info)
    national_id_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)  # Employee completes
    passport_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    cnps_number = models.CharField(max_length=50, blank=True, null=True, help_text='CNPS employee number')  # Employee completes
    tax_number = models.CharField(max_length=50, blank=True, null=True, help_text='Tax identification number')
    
    # Employment Details (set by employer)
    job_title = models.CharField(max_length=255)  # Required by employer
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='direct_reports')
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES)  # Required by employer
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_STATUS_CHOICES, default='PENDING')
    hire_date = models.DateField()  # Required by employer
    probation_end_date = models.DateField(blank=True, null=True)
    termination_date = models.DateField(blank=True, null=True)
    termination_reason = models.TextField(blank=True, null=True)
    
    # Payroll Information
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_account_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Emergency Contact (employee completes)
    emergency_contact_name = models.CharField(max_length=200, blank=True, null=True)  # Employee completes
    emergency_contact_relationship = models.CharField(max_length=100, blank=True, null=True)  # Employee completes
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)  # Employee completes
    
    # System Access
    invitation_sent = models.BooleanField(default=False)
    invitation_sent_at = models.DateTimeField(null=True, blank=True)
    invitation_accepted = models.BooleanField(default=False)
    invitation_accepted_at = models.DateTimeField(null=True, blank=True)
    
    # Flags
    is_concurrent_employment = models.BooleanField(default=False, help_text='Employee works for multiple institutions')
    
    # Profile Completion Tracking
    profile_completed = models.BooleanField(default=False, help_text='Whether employee has completed their profile')
    profile_completed_at = models.DateTimeField(null=True, blank=True, help_text='When employee completed their profile')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_id = models.IntegerField(null=True, db_index=True, help_text='ID of the user who created this record')

    class Meta:
        db_table = 'employees'
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
        unique_together = [['employer_id', 'employee_id']]
        indexes = [
            models.Index(fields=['employer_id', 'employment_status']),
            models.Index(fields=['national_id_number']),
            models.Index(fields=['email']),
        ]
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
    
    @property
    def full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_active(self):
        return self.employment_status == 'ACTIVE'
    
    @property
    def is_terminated(self):
        return self.employment_status in ['TERMINATED', 'RESIGNED', 'RETIRED']


class EmployeeDocument(models.Model):
    """Documents associated with an employee"""
    
    DOCUMENT_TYPE_CHOICES = [
        ('RESUME', 'Resume/CV'),
        ('ID_COPY', 'ID Copy'),
        ('PASSPORT_COPY', 'Passport Copy'),
        ('CERTIFICATE', 'Certificate/Diploma'),
        ('CONTRACT', 'Employment Contract'),
        ('OFFER_LETTER', 'Offer Letter'),
        ('TERMINATION_LETTER', 'Termination Letter'),
        ('RECOMMENDATION', 'Recommendation Letter'),
        ('MEDICAL', 'Medical Certificate'),
        ('POLICE_CLEARANCE', 'Police Clearance'),
        ('OTHER', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='employee_documents/')
    file_size = models.IntegerField(help_text='File size in bytes')
    
    # Expiry tracking
    has_expiry = models.BooleanField(default=False, help_text='Does this document have an expiry date?')
    expiry_date = models.DateField(null=True, blank=True)
    expiry_reminder_sent = models.BooleanField(default=False)
    expiry_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    
    uploaded_by_id = models.IntegerField(null=True, db_index=True, help_text='ID of the user who uploaded this document')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Verification
    is_verified = models.BooleanField(default=False, help_text='Document verified by HR')
    verified_by_id = models.IntegerField(null=True, blank=True, db_index=True, help_text='ID of the user who verified this document')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'employee_documents'
        verbose_name = 'Employee Document'
        verbose_name_plural = 'Employee Documents'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} - {self.employee.full_name}"
    
    @property
    def is_expired(self):
        """Check if document is expired"""
        if self.has_expiry and self.expiry_date:
            return timezone.now().date() > self.expiry_date
        return False
    
    @property
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if self.has_expiry and self.expiry_date:
            delta = self.expiry_date - timezone.now().date()
            return delta.days
        return None


class EmployeeCrossInstitutionRecord(models.Model):
    """Track employees who exist in multiple institutions"""
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('TERMINATED', 'Terminated'),
        ('PENDING', 'Pending Verification'),
    ]
    
    CONSENT_STATUS_CHOICES = [
        ('PENDING', 'Pending Employee Consent'),
        ('APPROVED', 'Approved by Employee'),
        ('REJECTED', 'Rejected by Employee'),
        ('NOT_REQUIRED', 'Consent Not Required'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='cross_institution_records')
    detected_employer_id = models.IntegerField(db_index=True, help_text='ID of the other employer (from main database)')
    detected_employee_id = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    # Consent tracking
    consent_status = models.CharField(max_length=20, choices=CONSENT_STATUS_CHOICES, default='NOT_REQUIRED')
    consent_requested_at = models.DateTimeField(null=True, blank=True)
    consent_responded_at = models.DateTimeField(null=True, blank=True)
    consent_notes = models.TextField(blank=True, null=True)
    
    detected_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by_id = models.IntegerField(null=True, blank=True, db_index=True, help_text='ID of the user who verified this record')
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'employee_cross_institution_records'
        verbose_name = 'Cross-Institution Record'
        verbose_name_plural = 'Cross-Institution Records'
        ordering = ['-detected_at']

    def __str__(self):
        return f"{self.employee.full_name} at Employer ID: {self.detected_employer_id}"


class EmployeeAuditLog(models.Model):
    """Audit log for employee record changes"""
    
    ACTION_CHOICES = [
        ('CREATED', 'Created'),
        ('UPDATED', 'Updated'),
        ('TERMINATED', 'Terminated'),
        ('DELETED', 'Deleted'),
        ('INVITED', 'Invitation Sent'),
        ('LINKED', 'Linked to User Account'),
        ('CROSS_INSTITUTION_DETECTED', 'Cross-Institution Detected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    performed_by_id = models.IntegerField(null=True, db_index=True, help_text='ID of the user who performed this action')
    timestamp = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField(null=True, blank=True, help_text='JSON object describing changes')
    notes = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'employee_audit_logs'
        verbose_name = 'Employee Audit Log'
        verbose_name_plural = 'Employee Audit Logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} - {self.employee.full_name} by {self.performed_by}"


class EmployeeInvitation(models.Model):
    """Track employee invitation status"""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('EXPIRED', 'Expired'),
        ('REVOKED', 'Revoked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='invitations')
    token = models.CharField(max_length=100, unique=True, db_index=True)
    email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    sent_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by_id = models.IntegerField(null=True, blank=True, db_index=True, help_text='ID of the user who revoked this invitation')
    
    class Meta:
        db_table = 'employee_invitations'
        verbose_name = 'Employee Invitation'
        verbose_name_plural = 'Employee Invitations'
        ordering = ['-sent_at']

    def __str__(self):
        return f"Invitation for {self.employee.full_name} ({self.status})"
    
    def is_valid(self):
        from django.utils import timezone
        return self.status == 'PENDING' and timezone.now() < self.expires_at
