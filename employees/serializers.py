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
            'id', 'employer_id', 'name', 'code', 'description', 'parent_department',
            'parent_department_name', 'is_active', 'employee_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'employer_id', 'created_at', 'updated_at']
    
    def get_employee_count(self, obj):
        return obj.employees.count()
    
    def create(self, validated_data):
        """Create department in tenant database"""
        # Get tenant database from context
        request = self.context.get('request')
        if request and hasattr(request.user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(request.user.employer_profile)
            return Department.objects.using(tenant_db).create(**validated_data)
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update department in tenant database"""
        request = self.context.get('request')
        if request and hasattr(request.user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(request.user.employer_profile)
            
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save(using=tenant_db)
            return instance
        return super().update(instance, validated_data)


class BranchSerializer(serializers.ModelSerializer):
    """Serializer for Branch model"""
    
    employee_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Branch
        fields = [
            'id', 'employer_id', 'name', 'code', 'address', 'city',
            'state_region', 'country', 'phone_number', 'email',
            'is_headquarters', 'is_active', 'employee_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'employer_id', 'created_at', 'updated_at']
    
    def get_employee_count(self, obj):
        return obj.employees.count()
    
    def create(self, validated_data):
        """Create branch in tenant database"""
        # Get tenant database from context
        request = self.context.get('request')
        if request and hasattr(request.user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(request.user.employer_profile)
            return Branch.objects.using(tenant_db).create(**validated_data)
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update branch in tenant database"""
        request = self.context.get('request')
        if request and hasattr(request.user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(request.user.employer_profile)
            
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save(using=tenant_db)
            return instance
        return super().update(instance, validated_data)


class EmployeeListSerializer(serializers.ModelSerializer):
    """Serializer for Employee list view (minimal fields)"""
    
    department_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'first_name', 'last_name', 'full_name',
            'email', 'phone_number', 'job_title', 'department_name',
            'branch_name', 'manager_name', 'employment_status', 'employment_type',
            'hire_date', 'profile_photo', 'is_concurrent_employment'
        ]
    
    def get_department_name(self, obj):
        """Get department name from tenant database"""
        if not obj.department_id:
            return None
        
        try:
            from accounts.database_utils import get_tenant_database_alias
            request = self.context.get('request')
            if request and hasattr(request.user, 'employer_profile'):
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
                department = Department.objects.using(tenant_db).get(id=obj.department_id)
                return department.name
        except Department.DoesNotExist:
            pass
        return None
    
    def get_branch_name(self, obj):
        """Get branch name from tenant database"""
        if not obj.branch_id:
            return None
        
        try:
            from accounts.database_utils import get_tenant_database_alias
            request = self.context.get('request')
            if request and hasattr(request.user, 'employer_profile'):
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
                branch = Branch.objects.using(tenant_db).get(id=obj.branch_id)
                return branch.name
        except Branch.DoesNotExist:
            pass
        return None
    
    def get_manager_name(self, obj):
        """Get manager name from tenant database"""
        if not obj.manager_id:
            return None
        
        try:
            from accounts.database_utils import get_tenant_database_alias
            request = self.context.get('request')
            if request and hasattr(request.user, 'employer_profile'):
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
                manager = Employee.objects.using(tenant_db).get(id=obj.manager_id)
                return manager.full_name
        except Employee.DoesNotExist:
            pass
        return None


class EmployeeDetailSerializer(serializers.ModelSerializer):
    """Serializer for Employee detail view (all fields)"""
    
    department_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    has_user_account = serializers.SerializerMethodField()
    cross_institution_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'invitation_sent_at',
            'invitation_accepted_at', 'is_concurrent_employment'
        ]
    
    def get_department_name(self, obj):
        """Get department name from tenant database"""
        if not obj.department_id:
            return None
        
        try:
            from accounts.database_utils import get_tenant_database_alias
            request = self.context.get('request')
            if request and hasattr(request.user, 'employer_profile'):
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
                department = Department.objects.using(tenant_db).get(id=obj.department_id)
                return department.name
        except Department.DoesNotExist:
            pass
        return None
    
    def get_branch_name(self, obj):
        """Get branch name from tenant database"""
        if not obj.branch_id:
            return None
        
        try:
            from accounts.database_utils import get_tenant_database_alias
            request = self.context.get('request')
            if request and hasattr(request.user, 'employer_profile'):
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
                branch = Branch.objects.using(tenant_db).get(id=obj.branch_id)
                return branch.name
        except Branch.DoesNotExist:
            pass
        return None
    
    def get_manager_name(self, obj):
        """Get manager name from tenant database"""
        if not obj.manager_id:
            return None
        
        try:
            from accounts.database_utils import get_tenant_database_alias
            request = self.context.get('request')
            if request and hasattr(request.user, 'employer_profile'):
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
                manager = Employee.objects.using(tenant_db).get(id=obj.manager_id)
                return manager.full_name
        except Employee.DoesNotExist:
            pass
        return None
    
    def get_has_user_account(self, obj):
        return obj.user_id is not None
    
    def get_cross_institution_count(self, obj):
        return obj.cross_institution_records.count()


class CreateEmployeeSerializer(serializers.ModelSerializer):
    """Serializer for creating a new employee - minimal fields required by employer"""
    
    send_invitation = serializers.BooleanField(default=True, write_only=True)
    # Define as explicit UUID fields OUTSIDE of Meta.fields to prevent auto ForeignKey handling
    department = serializers.UUIDField(
        required=False, 
        allow_null=True,
        write_only=True,
        help_text='UUID of the department'
    )
    branch = serializers.UUIDField(
        required=False, 
        allow_null=True,
        write_only=True,
        help_text='UUID of the branch'
    )
    manager = serializers.UUIDField(
        required=False, 
        allow_null=True,
        write_only=True,
        help_text='UUID of the manager (another employee)'
    )
    
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
            
            # Employment Details - department, branch, manager NOT in fields (defined above)
            'job_title', 'employment_type', 'employment_status', 'hire_date',
            'probation_end_date',
            
            # Payroll Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
            
            # Additional
            'send_invitation'
        ]
        extra_kwargs = {
            'employee_id': {'required': False},  # Auto-generated if not provided
        }
    
    def validate_department(self, value):
        """Validate that department UUID exists in tenant database"""
        if value is None:
            return value
        
        request = self.context['request']
        employer_id = request.user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        # Check if department exists in tenant database
        try:
            Department.objects.using(tenant_db).get(
                id=value, employer_id=employer_id
            )
        except Department.DoesNotExist:
            raise serializers.ValidationError(
                "Department does not exist or does not belong to your organization."
            )
        return value
    
    def validate_branch(self, value):
        """Validate that branch UUID exists in tenant database"""
        if value is None:
            return value
        
        request = self.context['request']
        employer_id = request.user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        # Check if branch exists in tenant database
        try:
            Branch.objects.using(tenant_db).get(
                id=value, employer_id=employer_id
            )
        except Branch.DoesNotExist:
            raise serializers.ValidationError(
                "Branch does not exist or does not belong to your organization."
            )
        return value
    
    def validate_manager(self, value):
        """Validate that manager UUID exists in tenant database"""
        if value is None:
            return value
        
        request = self.context['request']
        employer_id = request.user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        # Check if manager exists in tenant database
        try:
            Employee.objects.using(tenant_db).get(
                id=value, employer_id=employer_id
            )
        except Employee.DoesNotExist:
            raise serializers.ValidationError(
                "Manager does not exist or does not belong to your organization."
            )
        return value
    
    def validate_employee_id(self, value):
        """Validate employee_id is unique within employer"""
        if not value:  # Allow empty, will be auto-generated - return None to trigger auto-generation
            return None
        employer_id = self.context['request'].user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.context['request'].user.employer_profile)
        
        if Employee.objects.using(tenant_db).filter(employer_id=employer_id, employee_id=value).exists():
            raise serializers.ValidationError(
                "An employee with this ID already exists in your organization."
            )
        return value
    
    def validate_email(self, value):
        """Check if email is already used by another employee in same employer"""
        employer_id = self.context['request'].user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.context['request'].user.employer_profile)
        
        if Employee.objects.using(tenant_db).filter(employer_id=employer_id, email=value).exists():
            raise serializers.ValidationError(
                "This email is already assigned to another employee."
            )
        return value
    
    def create(self, validated_data):
        send_invitation = validated_data.pop('send_invitation', False)
        request = self.context['request']
        
        # Set employer_id from logged-in user
        validated_data['employer_id'] = request.user.employer_profile.id
        validated_data['created_by_id'] = request.user.id
        
        # Get tenant database alias
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        # Extract UUID values and convert to _id fields
        department_uuid = validated_data.pop('department', None)
        branch_uuid = validated_data.pop('branch', None)
        manager_uuid = validated_data.pop('manager', None)
        
        # Set the _id fields with UUIDs
        if department_uuid:
            validated_data['department_id'] = department_uuid
        if branch_uuid:
            validated_data['branch_id'] = branch_uuid
        if manager_uuid:
            validated_data['manager_id'] = manager_uuid
        
        # Auto-generate employee_id if not provided, empty, or None
        employee_id = validated_data.get('employee_id')
        if not employee_id or employee_id is None:
            # Remove the None/empty value from validated_data
            validated_data.pop('employee_id', None)
            
            # Try to get or create configuration
            config, created = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
                employer_id=validated_data['employer_id'],
                defaults={
                    'employee_id_prefix': 'EMP',
                    'employee_id_starting_number': 1,
                    'employee_id_padding': 3,
                    'last_employee_number': 0
                }
            )
            
            # Get the actual department and branch objects for ID generation
            department_obj = None
            branch_obj = None
            
            if department_uuid:
                try:
                    department_obj = Department.objects.using(tenant_db).get(id=department_uuid)
                except Department.DoesNotExist:
                    pass
            
            if branch_uuid:
                try:
                    branch_obj = Branch.objects.using(tenant_db).get(id=branch_uuid)
                except Branch.DoesNotExist:
                    pass
            
            # Generate ID using atomic counter (thread-safe)
            validated_data['employee_id'] = config.get_next_employee_id(
                branch=branch_obj, 
                department=department_obj,
                using=tenant_db
            )
        
        # Create employee in tenant database
        employee = Employee.objects.using(tenant_db).create(**validated_data)
        
        # Store invitation flag and tenant_db for view to handle
        employee._send_invitation = send_invitation
        employee._tenant_db = tenant_db
        
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


class EmployeePrefillRequestSerializer(serializers.Serializer):
    """Input serializer to verify an existing employee before creation"""
    
    national_id_number = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    
    def validate(self, data):
        if not data.get('national_id_number') and not data.get('email'):
            raise serializers.ValidationError(
                "Provide either a national_id_number or an email to verify the employee."
            )
        return data


class EmployeePrefillSerializer(serializers.Serializer):
    """Serializer for data used to prefill the employer create form"""
    
    user_id = serializers.IntegerField(required=False, allow_null=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    middle_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    email = serializers.EmailField()
    personal_email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    national_id_number = serializers.CharField()
    passport_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    alternative_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    state_region = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    country = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)


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
    """Enhanced serializer for creating employee with duplicate detection - minimal required fields"""
    
    send_invitation = serializers.BooleanField(default=True, write_only=True)
    force_create = serializers.BooleanField(default=False, write_only=True, 
        help_text='Force create even if duplicates detected (with warn action)')
    link_existing_user = serializers.IntegerField(required=False, allow_null=True, write_only=True,
        help_text='ID of existing user account to link (from main database)')
    acknowledge_cross_institution = serializers.BooleanField(default=False, write_only=True,
        help_text='Acknowledge concurrent employment in other institutions')
    
    # Define as explicit UUID fields to prevent auto ForeignKey handling
    department = serializers.UUIDField(
        required=True, 
        allow_null=False,
        write_only=True,
        help_text='UUID of the department'
    )
    branch = serializers.UUIDField(
        required=False, 
        allow_null=True,
        write_only=True,
        help_text='UUID of the branch'
    )
    manager = serializers.UUIDField(
        required=False, 
        allow_null=True,
        write_only=True,
        help_text='UUID of the manager (another employee)'
    )
    
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
            
            # Employment Details - department, branch, manager defined above as UUIDField
            'job_title', 'employment_type', 'employment_status', 'hire_date',
            'probation_end_date', 'department', 'branch', 'manager',
            
            # Payroll Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
            
            # Additional
            'send_invitation', 'force_create', 'link_existing_user',
            'acknowledge_cross_institution'
        ]
        extra_kwargs = {
            # Make most fields optional - employers provide minimal data, employees complete their profiles
            'employee_id': {'required': False},
            'middle_name': {'required': False},
            'date_of_birth': {'required': False},
            'gender': {'required': False},
            'marital_status': {'required': False},
            'nationality': {'required': False},
            'profile_photo': {'required': False},
            'personal_email': {'required': False},
            'phone_number': {'required': False},
            'alternative_phone': {'required': False},
            'address': {'required': False},
            'city': {'required': False},
            'state_region': {'required': False},
            'postal_code': {'required': False},
            'country': {'required': False},
            'national_id_number': {'required': True},  # REQUIRED for cross-institutional tracking
            'passport_number': {'required': False},
            'cnps_number': {'required': False},
            'tax_number': {'required': False},
            'job_title': {'required': False},
            'employment_type': {'required': False},
            'employment_status': {'required': False},
            'hire_date': {'required': False},
            'probation_end_date': {'required': False},
            'bank_name': {'required': False},
            'bank_account_number': {'required': False},
            'bank_account_name': {'required': False},
            'emergency_contact_name': {'required': False},
            'emergency_contact_relationship': {'required': False},
            'emergency_contact_phone': {'required': False},
            # Employer-supplied required fields
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True},
            'job_title': {'required': True},
            'employment_type': {'required': True},
            'hire_date': {'required': True},
        }

    
    def validate_department(self, value):
        """Validate that department UUID exists in tenant database"""
        if value is None:
            return value
        
        request = self.context['request']
        employer_id = request.user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        try:
            Department.objects.using(tenant_db).get(
                id=value, employer_id=employer_id
            )
        except Department.DoesNotExist:
            raise serializers.ValidationError(
                "Department does not exist or does not belong to your organization."
            )
        return value
    
    def validate_branch(self, value):
        """Validate that branch UUID exists in tenant database"""
        if value is None:
            return value
        
        request = self.context['request']
        employer_id = request.user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        try:
            Branch.objects.using(tenant_db).get(
                id=value, employer_id=employer_id
            )
        except Branch.DoesNotExist:
            raise serializers.ValidationError(
                "Branch does not exist or does not belong to your organization."
            )
        return value
    
    def validate_manager(self, value):
        """Validate that manager UUID exists in tenant database"""
        if value is None:
            return value
        
        request = self.context['request']
        employer_id = request.user.employer_profile.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        try:
            Employee.objects.using(tenant_db).get(
                id=value, employer_id=employer_id
            )
        except Employee.DoesNotExist:
            raise serializers.ValidationError(
                "Manager does not exist or does not belong to your organization."
            )
        return value
    
    def validate_national_id_number(self, value):
        """Validate national ID number format and uniqueness within institution"""
        if not value or value.strip() == '':
            raise serializers.ValidationError("National ID number is required for cross-institutional tracking.")
        
        # Check uniqueness within the employer's institution
        request = self.context['request']
        employer = request.user.employer_profile
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
        # Check if another employee in this institution has the same national_id
        existing_query = Employee.objects.using(tenant_db).filter(
            employer_id=employer.id,
            national_id_number=value
        )
        
        # Exclude current instance if updating
        if self.instance:
            existing_query = existing_query.exclude(id=self.instance.id)
        
        if existing_query.exists():
            raise serializers.ValidationError(
                "An employee with this National ID already exists in your institution."
            )
        
        return value
    
    def validate(self, data):
        """Validate employee data against configuration"""
        from employees.utils import validate_employee_data, detect_duplicate_employees
        from accounts.database_utils import get_tenant_database_alias
        
        request = self.context['request']
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        # Get or create configuration from tenant database
        config, created = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
            employer_id=employer.id,
            defaults={
                'employee_id_prefix': 'EMP',
                'employee_id_starting_number': 1,
                'employee_id_padding': 3,
                'last_employee_number': 0
            }
        )
        
        # Skip strict validation during employer-initiated creation
        # The configuration requirements apply when employees complete their own profiles,
        # not when employers are creating initial employee records
        # Employers only need to provide minimal fields: first_name, last_name, email, job_title, etc.
        
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
        
        # Pop UUID fields and convert to _id fields
        department_uuid = validated_data.pop('department', None)
        branch_uuid = validated_data.pop('branch', None)
        manager_uuid = validated_data.pop('manager', None)
        
        if department_uuid:
            validated_data['department_id'] = department_uuid
        if branch_uuid:
            validated_data['branch_id'] = branch_uuid
        if manager_uuid:
            validated_data['manager_id'] = manager_uuid
        
        request = self.context['request']
        employer = request.user.employer_profile
        
        # Ensure baseline employment fields for employer onboarding
        validated_data.setdefault('employment_status', 'ACTIVE')
        
        # Get tenant database alias
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
        # Get configuration
        try:
            config = EmployeeConfiguration.objects.using(tenant_db).get(employer_id=employer.id)
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
            temp_employee_data = validated_data.copy()
            temp_employee_data['employer_id'] = employer.id
            temp_employee = Employee(**temp_employee_data)
            work_email = generate_work_email(temp_employee, config)
            if work_email:
                validated_data['email'] = work_email
        
        # Set employer_id and creator
        validated_data['employer_id'] = employer.id
        validated_data['created_by_id'] = request.user.id
        
        # Link existing user if provided (user is in main DB)
        if link_existing_user:
            try:
                user = User.objects.get(id=link_existing_user)
                validated_data['user_id'] = user.id
            except User.DoesNotExist:
                pass
        
        # Mark as concurrent employment if cross-institution matches found
        if duplicate_info and duplicate_info.get('cross_institution_matches'):
            validated_data['is_concurrent_employment'] = True
        
        # Create employee in tenant database
        employee = Employee.objects.using(tenant_db).create(**validated_data)
        
        # Sync to central EmployeeRegistry for cross-institutional tracking
        if employee.user_id:
            from accounts.models import EmployeeRegistry
            try:
                user = User.objects.get(id=employee.user_id)
                
                # Create or update EmployeeRegistry in main database for cross-institutional tracking
                EmployeeRegistry.objects.update_or_create(
                    user=user,
                    defaults={
                        'first_name': employee.first_name,
                        'last_name': employee.last_name,
                        'middle_name': employee.middle_name or '',
                        'date_of_birth': employee.date_of_birth if employee.date_of_birth else timezone.now().date(),
                        'gender': employee.gender or 'PREFER_NOT_TO_SAY',
                        'marital_status': employee.marital_status or 'SINGLE',
                        'nationality': employee.nationality or 'Unknown',
                        'phone_number': employee.phone_number or '0000000000',
                        'alternative_phone': employee.alternative_phone or '',
                        'personal_email': employee.personal_email or '',
                        'address': employee.address or 'Not Provided',
                        'city': employee.city or 'Unknown',
                        'state_region': employee.state_region or 'Unknown',
                        'postal_code': employee.postal_code or '',
                        'country': employee.country or 'Unknown',
                        'emergency_contact_name': employee.emergency_contact_name or 'Not Provided',
                        'emergency_contact_relationship': employee.emergency_contact_relationship or 'Unknown',
                        'emergency_contact_phone': employee.emergency_contact_phone or '0000000000',
                        'national_id_number': employee.national_id_number or '',
                        'passport_number': employee.passport_number or '',
                        'years_of_experience': 0,
                    }
                )
            except User.DoesNotExist:
                pass  # User doesn't exist, skip sync
            except Exception as e:
                # Log error but don't fail employee creation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to sync EmployeeRegistry for employee {employee.id}: {str(e)}")
        
        # Create audit log in tenant database
        create_employee_audit_log(
            employee=employee,
            action='CREATED',
            performed_by=request.user,
            notes='Employee created by employer',
            request=request,
            tenant_db=tenant_db
        )
        
        # Handle cross-institution records if detected
        if duplicate_info and duplicate_info.get('cross_institution_matches'):
            for match in duplicate_info['cross_institution_matches']:
                EmployeeCrossInstitutionRecord.objects.using(tenant_db).create(
                    employee=employee,
                    detected_employer_id=match.employer_id,
                    detected_employee_id=match.employee_id,
                    status=match.employment_status,
                    consent_status='PENDING' if config and config.require_employee_consent_cross_institution else 'NOT_REQUIRED',
                    notes=f"Detected during employee creation. Match reasons: {', '.join(duplicate_info['match_reasons'].get(str(match.id), []))}"
                )
        
        # Store flags for view to handle
        employee._send_invitation = send_invitation
        employee._duplicate_info = duplicate_info
        employee._tenant_db = tenant_db  # Store tenant DB for view to use
        
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
        from accounts.database_utils import get_tenant_database_alias
        request = self.context['request']
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        try:
            config = EmployeeConfiguration.objects.using(tenant_db).get(employer_id=employer.id)
            
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
        """Validate invitation token - search across all tenant databases"""
        from accounts.database_utils import get_tenant_database_alias
        from accounts.models import EmployerProfile
        
        # Search across all tenant databases for the invitation
        # Filter by user__is_active instead of is_active (which doesn't exist on EmployerProfile)
        employers = EmployerProfile.objects.filter(user__is_active=True).select_related('user')
        
        for employer in employers:
            try:
                tenant_db = get_tenant_database_alias(employer)
                invitation = EmployeeInvitation.objects.using(tenant_db).get(token=value)
                
                if not invitation.is_valid():
                    raise serializers.ValidationError("Invitation has expired or is no longer valid")
                
                # Attach tenant database info to the invitation object for use in the view
                invitation._tenant_db = tenant_db
                invitation._employer_profile = employer
                
                return invitation
            except EmployeeInvitation.DoesNotExist:
                continue
        
        # If we reach here, invitation was not found in any database
        raise serializers.ValidationError("Invalid invitation token")


class EmployeeProfileCompletionSerializer(serializers.ModelSerializer):
    """Serializer for employee to complete their own profile after accepting invitation"""
    
    class Meta:
        model = Employee
        fields = [
            # Personal Information to complete
            'date_of_birth', 'gender', 'nationality', 'marital_status',
            'profile_photo',
            
            # Contact Details
            'phone_number', 'alternative_phone', 'personal_email',
            'address', 'city', 'state_region', 'postal_code', 'country',
            
            # Legal Identification
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            
            # Payroll Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
        ]
        # String fields that support allow_blank
        string_fields = [
            'nationality', 'marital_status', 'phone_number', 'alternative_phone', 
            'personal_email', 'address', 'city', 'state_region', 'postal_code', 'country',
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            'bank_name', 'bank_account_number', 'bank_account_name',
            'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone'
        ]
        extra_kwargs = {
            **{field: {'required': False, 'allow_null': True, 'allow_blank': True} 
               for field in string_fields},
            **{field: {'required': False, 'allow_null': True} 
               for field in ['date_of_birth', 'gender', 'profile_photo']}
        }
    
    def validate(self, data):
        """Validate employee profile data against configuration requirements"""
        from employees.utils import validate_employee_data
        from accounts.database_utils import get_tenant_database_alias
        from accounts.models import EmployerProfile
        
        # Get the employee instance being updated
        if self.instance:
            try:
                employer = EmployerProfile.objects.get(id=self.instance.employer_id)
                tenant_db = get_tenant_database_alias(employer)
                config, created = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
                    employer_id=self.instance.employer_id,
                    defaults={
                        'employee_id_prefix': 'EMP',
                        'employee_id_starting_number': 1,
                        'employee_id_padding': 3,
                        'last_employee_number': 0
                    }
                )
            except EmployerProfile.DoesNotExist:
                config = None
            
            # Enforce configuration requirements when employee is completing profile
            if config:
                validation_result = validate_employee_data(data, config)
                if not validation_result['valid']:
                    raise serializers.ValidationError(validation_result['errors'])
        
        return data
    
    def update(self, instance, validated_data):
        """Update employee profile, mark as completed, and sync to central EmployeeProfile"""
        from django.utils import timezone
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Update all provided fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Mark profile as completed
        instance.profile_completed = True
        instance.profile_completed_at = timezone.now()
        
        instance.save()
        
        # Sync to central EmployeeRegistry
        if instance.user_id:
            from accounts.models import EmployeeRegistry
            try:
                user = User.objects.get(id=instance.user_id)
                
                # Update EmployeeRegistry if it exists
                if hasattr(user, 'employee_registry'):
                    employee_registry = user.employee_registry
                    
                    # Define field mapping (only update fields that were provided)
                    field_mapping = {
                        'date_of_birth': 'date_of_birth',
                        'gender': 'gender',
                        'nationality': 'nationality',
                        'marital_status': 'marital_status',
                        'phone_number': 'phone_number',
                        'alternative_phone': 'alternative_phone',
                        'personal_email': 'personal_email',
                        'address': 'address',
                        'city': 'city',
                        'state_region': 'state_region',
                        'postal_code': 'postal_code',
                        'country': 'country',
                        'emergency_contact_name': 'emergency_contact_name',
                        'emergency_contact_relationship': 'emergency_contact_relationship',
                        'emergency_contact_phone': 'emergency_contact_phone',
                        'national_id_number': 'national_id_number',
                        'passport_number': 'passport_number',
                    }
                    
                    # Sync only fields that were updated
                    for employee_field, profile_field in field_mapping.items():
                        if employee_field in validated_data:
                            value = validated_data[employee_field]
                            # Handle empty values for required fields in EmployeeProfile
                            if value is None or value == '':
                                if employee_field in ['date_of_birth']:
                                    continue  # Skip empty dates
                                elif employee_field == 'gender':
                                    value = 'PREFER_NOT_TO_SAY'
                                elif employee_field == 'marital_status':
                                    value = 'SINGLE'
                                elif employee_field in ['nationality', 'city', 'state_region', 'country', 
                                                       'emergency_contact_relationship']:
                                    value = 'Unknown'
                                elif employee_field in ['phone_number', 'emergency_contact_phone']:
                                    value = '0000000000'
                                elif employee_field in ['address', 'emergency_contact_name']:
                                    value = 'Not Provided'
                            setattr(employee_registry, profile_field, value)
                    
                    # Save to central database
                    employee_registry.save()
            except User.DoesNotExist:
                pass  # User doesn't exist, skip sync
            except Exception as e:
                # Log error but don't fail profile completion
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to sync EmployeeRegistry for employee {instance.id}: {str(e)}")
        
        return instance


class EmployeeSelfProfileSerializer(serializers.ModelSerializer):
    """Read-only serializer for employees to view their own profile"""
    
    department_name = serializers.CharField(source='department.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    manager_name = serializers.CharField(source='manager.full_name', read_only=True)
    employer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'first_name', 'last_name', 'middle_name', 'full_name',
            'date_of_birth', 'gender', 'nationality', 'marital_status', 'profile_photo',
            'email', 'personal_email', 'phone_number', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            'job_title', 'department_name', 'branch_name', 'manager_name',
            'employment_type', 'employment_status', 'hire_date', 'probation_end_date',
            'bank_name', 'bank_account_number', 'bank_account_name',
            'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone',
            'profile_completed', 'profile_completed_at',
            'employer_name', 'created_at', 'updated_at'
        ]
        read_only_fields = '__all__'
    
    def get_employer_name(self, obj):
        from accounts.models import EmployerProfile
        try:
            employer = EmployerProfile.objects.get(id=obj.employer_id)
            return employer.company_name
        except EmployerProfile.DoesNotExist:
            return None

