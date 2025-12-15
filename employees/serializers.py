from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Department, Branch, Employee, EmployeeDocument,
    EmployeeCrossInstitutionRecord, EmployeeAuditLog, EmployeeInvitation,
    EmployeeConfiguration
)
from accounts.models import EmployerProfile

User = get_user_model()


class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department model"""
    
    parent_department_name = serializers.CharField(source='parent_department.name', read_only=True)
    employee_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = [
            'id', 'employer', 'name', 'code', 'description', 'parent_department',
            'parent_department_name', 'is_active', 'employee_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_employee_count(self, obj):
        return obj.employees.count()


class BranchSerializer(serializers.ModelSerializer):
    """Serializer for Branch model"""
    
    employee_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Branch
        fields = [
            'id', 'employer', 'name', 'code', 'address', 'city',
            'state_region', 'country', 'phone_number', 'email',
            'is_headquarters', 'is_active', 'employee_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_employee_count(self, obj):
        return obj.employees.count()


class EmployeeListSerializer(serializers.ModelSerializer):
    """Serializer for Employee list view (minimal fields)"""
    
    department_name = serializers.CharField(source='department.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    manager_name = serializers.CharField(source='manager.full_name', read_only=True)
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'first_name', 'last_name', 'full_name',
            'email', 'phone_number', 'job_title', 'department_name',
            'branch_name', 'employment_status', 'employment_type',
            'hire_date', 'profile_photo', 'is_concurrent_employment'
        ]


class EmployeeDetailSerializer(serializers.ModelSerializer):
    """Serializer for Employee detail view (all fields)"""
    
    department_name = serializers.CharField(source='department.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    manager_name = serializers.CharField(source='manager.full_name', read_only=True)
    employer_name = serializers.CharField(source='employer.company_name', read_only=True)
    has_user_account = serializers.SerializerMethodField()
    cross_institution_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'invitation_sent_at',
            'invitation_accepted_at', 'is_concurrent_employment'
        ]
    
    def get_has_user_account(self, obj):
        return obj.user is not None
    
    def get_cross_institution_count(self, obj):
        return obj.cross_institution_records.count()


class CreateEmployeeSerializer(serializers.ModelSerializer):
    """Serializer for creating a new employee"""
    
    send_invitation = serializers.BooleanField(default=False, write_only=True)
    
    class Meta:
        model = Employee
        fields = [
            # Basic Information
            'employee_id', 'first_name', 'last_name', 'middle_name',
            'date_of_birth', 'gender', 'marital_status', 'nationality',
            
            # Contact Information
            'email', 'personal_email', 'phone_number', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            
            # Legal Identification
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            
            # Employment Details
            'job_title', 'department', 'branch', 'manager',
            'employment_type', 'employment_status', 'hire_date',
            'probation_end_date',
            
            # Payroll Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
            
            # Additional
            'send_invitation'
        ]
    
    def validate_employee_id(self, value):
        """Validate employee_id is unique within employer"""
        employer = self.context['request'].user.employer_profile
        if Employee.objects.filter(employer=employer, employee_id=value).exists():
            raise serializers.ValidationError(
                "An employee with this ID already exists in your organization."
            )
        return value
    
    def validate_email(self, value):
        """Check if email is already used by another employee in same employer"""
        employer = self.context['request'].user.employer_profile
        if Employee.objects.filter(employer=employer, email=value).exists():
            raise serializers.ValidationError(
                "This email is already assigned to another employee."
            )
        return value
    
    def create(self, validated_data):
        send_invitation = validated_data.pop('send_invitation', False)
        request = self.context['request']
        
        # Set employer from logged-in user
        validated_data['employer'] = request.user.employer_profile
        validated_data['created_by'] = request.user
        
        employee = Employee.objects.create(**validated_data)
        
        # Store invitation flag for view to handle
        employee._send_invitation = send_invitation
        
        return employee


class UpdateEmployeeSerializer(serializers.ModelSerializer):
    """Serializer for updating employee information"""
    
    class Meta:
        model = Employee
        fields = [
            # Basic Information
            'first_name', 'last_name', 'middle_name', 'date_of_birth',
            'gender', 'marital_status', 'nationality', 'profile_photo',
            
            # Contact Information
            'email', 'personal_email', 'phone_number', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            
            # Legal Identification
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            
            # Employment Details
            'job_title', 'department', 'branch', 'manager',
            'employment_type', 'employment_status', 'probation_end_date',
            
            # Payroll Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
        ]


class TerminateEmployeeSerializer(serializers.Serializer):
    """Serializer for employee termination"""
    
    termination_date = serializers.DateField()
    termination_reason = serializers.CharField(required=True)
    
    def validate_termination_date(self, value):
        from django.utils import timezone
        if value > timezone.now().date():
            raise serializers.ValidationError(
                "Termination date cannot be in the future."
            )
        return value


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    """Serializer for Employee Documents"""
    
    uploaded_by_name = serializers.CharField(source='uploaded_by.email', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    
    class Meta:
        model = EmployeeDocument
        fields = [
            'id', 'employee', 'employee_name', 'document_type', 'title',
            'description', 'file', 'file_size', 'uploaded_by',
            'uploaded_by_name', 'uploaded_at'
        ]
        read_only_fields = ['id', 'uploaded_by', 'uploaded_at', 'file_size']


class CrossInstitutionRecordSerializer(serializers.ModelSerializer):
    """Serializer for Cross-Institution Records"""
    
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    detected_employer_name = serializers.CharField(source='detected_employer.company_name', read_only=True)
    
    class Meta:
        model = EmployeeCrossInstitutionRecord
        fields = [
            'id', 'employee', 'employee_name', 'detected_employer',
            'detected_employer_name', 'detected_employee_id', 'status',
            'detected_at', 'verified', 'verified_at', 'notes'
        ]
        read_only_fields = ['id', 'detected_at']


class EmployeeAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for Employee Audit Logs"""
    
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    performed_by_email = serializers.CharField(source='performed_by.email', read_only=True)
    
    class Meta:
        model = EmployeeAuditLog
        fields = [
            'id', 'employee', 'employee_name', 'action', 'performed_by',
            'performed_by_email', 'timestamp', 'changes', 'notes', 'ip_address'
        ]
        read_only_fields = '__all__'


class EmployeeInvitationSerializer(serializers.ModelSerializer):
    """Serializer for Employee Invitations"""
    
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    
    class Meta:
        model = EmployeeInvitation
        fields = [
            'id', 'employee', 'employee_name', 'email', 'status',
            'sent_at', 'expires_at', 'accepted_at'
        ]
        read_only_fields = [
            'id', 'token', 'status', 'sent_at', 'expires_at', 'accepted_at'
        ]


class EmployeeSearchSerializer(serializers.Serializer):
    """Serializer for employee search/detection across institutions"""
    
    national_id_number = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if not any([data.get('national_id_number'), data.get('email'), data.get('phone_number')]):
            raise serializers.ValidationError(
                "At least one search criterion must be provided."
            )
        return data


class EmployeeConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for Employee Configuration"""
    
    employer_name = serializers.CharField(source='employer.company_name', read_only=True)
    
    class Meta:
        model = EmployeeConfiguration
        fields = '__all__'
        read_only_fields = ['id', 'employer', 'created_at', 'updated_at']


class DuplicateDetectionResultSerializer(serializers.Serializer):
    """Serializer for duplicate detection results"""
    
    duplicates_found = serializers.BooleanField()
    total_matches = serializers.IntegerField()
    same_institution_matches = EmployeeListSerializer(many=True)
    cross_institution_matches = EmployeeListSerializer(many=True)
    match_reasons = serializers.DictField()


class CreateEmployeeWithDetectionSerializer(serializers.ModelSerializer):
    """Enhanced serializer for creating employee with duplicate detection"""
    
    send_invitation = serializers.BooleanField(default=False, write_only=True)
    force_create = serializers.BooleanField(default=False, write_only=True, 
        help_text='Force create even if duplicates detected (with warn action)')
    link_existing_user = serializers.UUIDField(required=False, allow_null=True, write_only=True,
        help_text='UUID of existing user account to link')
    acknowledge_cross_institution = serializers.BooleanField(default=False, write_only=True,
        help_text='Acknowledge concurrent employment in other institutions')
    
    class Meta:
        model = Employee
        fields = [
            # Basic Information
            'employee_id', 'first_name', 'last_name', 'middle_name',
            'date_of_birth', 'gender', 'marital_status', 'nationality',
            'profile_photo',
            
            # Contact Information
            'email', 'personal_email', 'phone_number', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            
            # Legal Identification
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            
            # Employment Details
            'job_title', 'department', 'branch', 'manager',
            'employment_type', 'employment_status', 'hire_date',
            'probation_end_date',
            
            # Payroll Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
            
            # Additional
            'send_invitation', 'force_create', 'link_existing_user',
            'acknowledge_cross_institution'
        ]
    
    def validate(self, data):
        """Validate employee data against configuration"""
        from employees.utils import validate_employee_data, detect_duplicate_employees
        
        request = self.context['request']
        employer = request.user.employer_profile
        
        # Get configuration
        try:
            config = EmployeeConfiguration.objects.get(employer=employer)
        except EmployeeConfiguration.DoesNotExist:
            config = None
        
        # Validate required fields based on configuration
        if config:
            validation_result = validate_employee_data(data, config)
            if not validation_result['valid']:
                raise serializers.ValidationError(validation_result['errors'])
        
        # Detect duplicates
        force_create = data.get('force_create', False)
        if not force_create:
            duplicate_result = detect_duplicate_employees(
                employer=employer,
                national_id=data.get('national_id_number'),
                email=data.get('email'),
                phone=data.get('phone_number'),
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                date_of_birth=data.get('date_of_birth'),
                config=config
            )
            
            if duplicate_result['duplicates_found']:
                # Check duplicate action from config
                if config and config.duplicate_action == 'BLOCK':
                    error_msg = f"Duplicate employee detected. Found {duplicate_result['total_matches']} matching records."
                    if duplicate_result['same_institution_matches']:
                        error_msg += f" {len(duplicate_result['same_institution_matches'])} in your institution."
                    if duplicate_result['cross_institution_matches']:
                        error_msg += f" {len(duplicate_result['cross_institution_matches'])} in other institutions."
                    raise serializers.ValidationError({'duplicate_detected': error_msg})
                
                elif not config or config.duplicate_action == 'WARN':
                    # Store duplicate info for response but allow creation
                    data['_duplicate_info'] = duplicate_result
        
        return data
    
    def create(self, validated_data):
        from employees.utils import create_employee_audit_log
        
        send_invitation = validated_data.pop('send_invitation', False)
        force_create = validated_data.pop('force_create', False)
        link_existing_user = validated_data.pop('link_existing_user', None)
        acknowledge_cross_institution = validated_data.pop('acknowledge_cross_institution', False)
        duplicate_info = validated_data.pop('_duplicate_info', None)
        
        request = self.context['request']
        employer = request.user.employer_profile
        
        # Get configuration
        try:
            config = EmployeeConfiguration.objects.get(employer=employer)
        except EmployeeConfiguration.DoesNotExist:
            config = None
        
        # Auto-generate employee ID if not provided and configured
        if not validated_data.get('employee_id') and config:
            validated_data['employee_id'] = config.get_next_employee_id(
                branch=validated_data.get('branch'),
                department=validated_data.get('department')
            )
        
        # Auto-generate work email if configured
        if config and config.auto_generate_work_email and not validated_data.get('email'):
            from employees.utils import generate_work_email
            # Create temporary employee object for email generation
            temp_employee = Employee(**validated_data, employer=employer)
            work_email = generate_work_email(temp_employee, config)
            if work_email:
                validated_data['email'] = work_email
        
        # Set employer and creator
        validated_data['employer'] = employer
        validated_data['created_by'] = request.user
        
        # Link existing user if provided
        if link_existing_user:
            try:
                user = User.objects.get(id=link_existing_user)
                validated_data['user'] = user
            except User.DoesNotExist:
                pass
        
        # Mark as concurrent employment if cross-institution matches found
        if duplicate_info and duplicate_info.get('cross_institution_matches'):
            validated_data['is_concurrent_employment'] = True
        
        # Create employee
        employee = Employee.objects.create(**validated_data)
        
        # Create audit log
        create_employee_audit_log(
            employee=employee,
            action='CREATED',
            performed_by=request.user,
            notes='Employee created by employer',
            request=request
        )
        
        # Handle cross-institution records if detected
        if duplicate_info and duplicate_info.get('cross_institution_matches'):
            for match in duplicate_info['cross_institution_matches']:
                EmployeeCrossInstitutionRecord.objects.create(
                    employee=employee,
                    detected_employer=match.employer,
                    detected_employee_id=match.employee_id,
                    status=match.employment_status,
                    consent_status='PENDING' if config and config.require_employee_consent_cross_institution else 'NOT_REQUIRED',
                    notes=f"Detected during employee creation. Match reasons: {', '.join(duplicate_info['match_reasons'].get(match.id, []))}"
                )
        
        # Store flags for view to handle
        employee._send_invitation = send_invitation
        employee._duplicate_info = duplicate_info
        
        return employee


class EmployeeDocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading employee documents"""
    
    class Meta:
        model = EmployeeDocument
        fields = [
            'employee', 'document_type', 'title', 'description', 'file',
            'has_expiry', 'expiry_date'
        ]
    
    def validate_file(self, value):
        """Validate file size and format based on configuration"""
        request = self.context['request']
        employer = request.user.employer_profile
        
        try:
            config = EmployeeConfiguration.objects.get(employer=employer)
            
            # Check file size
            max_size_bytes = config.document_max_file_size_mb * 1024 * 1024
            if value.size > max_size_bytes:
                raise serializers.ValidationError(
                    f"File size exceeds maximum allowed size of {config.document_max_file_size_mb}MB"
                )
            
            # Check file format
            allowed_formats = config.get_allowed_document_formats()
            file_ext = value.name.split('.')[-1].lower()
            if allowed_formats and file_ext not in allowed_formats:
                raise serializers.ValidationError(
                    f"File format '.{file_ext}' is not allowed. Allowed formats: {', '.join(allowed_formats)}"
                )
        except EmployeeConfiguration.DoesNotExist:
            # No config, apply default limits
            max_size_bytes = 10 * 1024 * 1024  # 10MB default
            if value.size > max_size_bytes:
                raise serializers.ValidationError("File size exceeds 10MB limit")
        
        return value
    
    def create(self, validated_data):
        validated_data['uploaded_by'] = self.context['request'].user
        validated_data['file_size'] = validated_data['file'].size
        return super().create(validated_data)


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting employee invitation"""
    
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': "Passwords do not match"})
        return data
    
    def validate_token(self, value):
        """Validate invitation token"""
        try:
            invitation = EmployeeInvitation.objects.get(token=value)
            if not invitation.is_valid():
                raise serializers.ValidationError("Invitation has expired or is no longer valid")
            return invitation
        except EmployeeInvitation.DoesNotExist:
            raise serializers.ValidationError("Invalid invitation token")

