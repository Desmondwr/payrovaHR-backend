from rest_framework import serializers
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import (
    Department, Branch, Employee, EmployeeDocument,
    EmployeeCrossInstitutionRecord, EmployeeAuditLog, EmployeeInvitation,
    EmployeeConfiguration, TerminationApproval, CrossInstitutionConsent
)
from accounts.models import EmployerProfile, EmployeeMembership

User = get_user_model()


class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department model"""
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.none(),
        required=False,
        allow_null=True
    )
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    parent_department_name = serializers.CharField(source='parent_department.name', read_only=True)
    employee_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = [
            'id', 'employer_id', 'name', 'code', 'description', 'branch',
            'branch_name', 'parent_department', 'parent_department_name',
            'is_active', 'employee_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'employer_id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request.user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(request.user.employer_profile)
            self.fields['branch'].queryset = Branch.objects.using(tenant_db).filter(
                employer_id=request.user.employer_profile.id
            )
            if 'parent_department' in self.fields:
                self.fields['parent_department'].queryset = Department.objects.using(tenant_db).filter(
                    employer_id=request.user.employer_profile.id
                )
    
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
            'email', 'phone_number', 'job_title', 'department', 'department_name',
            'branch', 'branch_name', 'manager_name', 'employment_status',
            'employment_type', 'hire_date', 'profile_photo', 'is_concurrent_employment'
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
    documents = serializers.SerializerMethodField()
    
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
    
    def get_documents(self, obj):
        """Get all documents for this employee"""
        documents = obj.documents.all()
        return EmployeeDocumentSerializer(documents, many=True, context=self.context).data


class CreateEmployeeSerializer(serializers.ModelSerializer):
    """Serializer for creating a new employee - minimal fields required by employer"""
    
    send_invitation = serializers.BooleanField(default=True, write_only=True)
    pin_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
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
            'employee_id', 'badge_id', 'pin_code', 'first_name', 'last_name', 'middle_name',
            'date_of_birth', 'gender', 'marital_status', 'nationality',
            
            # Contact Information
            'email', 'personal_email', 'phone_number', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            
            # Legal Identification
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            
            # Employment Details - department, branch, manager NOT in fields (defined above)
            'job_title', 'employment_type', 'employment_status', 'hire_date',
            'probation_end_date',
            
            # Compensation Information
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
        if not value:
            return value
        
        request = self.context['request']
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        employer_id = employer.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
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
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        employer_id = employer.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
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
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        employer_id = employer.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
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
    
    def validate(self, data):
        """Validate that all required fields per employer configuration are provided"""
        from employees.utils import validate_employee_data_strict
        from employees.models import EmployeeConfiguration
        from accounts.database_utils import get_tenant_database_alias
        from django.core.exceptions import ValidationError as DjangoValidationError
        
        request = self.context['request']
        employer_id = request.user.employer_profile.id
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        # Get or create employer configuration
        config, created = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
            employer_id=employer_id
        )
        
        # Validate data against employer configuration
        try:
            validation_result = validate_employee_data_strict(data, config)

            if not validation_result.get('valid', True):
                employer_name = request.user.employer_profile.company_name
                raise serializers.ValidationError({
                    **validation_result.get('errors', {}),
                    '_info': f'These fields are required by {employer_name}'
                })
        except DjangoValidationError as e:
            raise serializers.ValidationError({'non_field_errors': [str(e)]})
        
        return data
    
    def create(self, validated_data):
        send_invitation = validated_data.pop('send_invitation', False)
        pin_code = validated_data.pop('pin_code', None)
        request = self.context['request']
        
        # Set employer_id from logged-in user
        validated_data['employer_id'] = request.user.employer_profile.id
        validated_data['created_by_id'] = request.user.id
        
        # Get tenant database alias
        from accounts.database_utils import get_tenant_database_alias
        from employees.utils import get_or_create_employee_config
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        
        # Ensure EmployeeConfiguration exists using helper function
        config = get_or_create_employee_config(validated_data['employer_id'], tenant_db)
        
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
            
            # Use the configuration's method to generate ID (atomic and thread-safe)
            validated_data['employee_id'] = config.get_next_employee_id(
                branch=branch_obj,
                department=department_obj,
                using=tenant_db
            )
        
        # Check if this is linking an existing employee (user_id provided)
        # If so, validate their existing data against config and set completion state
        if 'user_id' in validated_data and validated_data['user_id']:
            from accounts.models import EmployeeRegistry
            from employees.utils import check_missing_fields_against_config
            
            try:
                # Get existing employee registry data
                employee_registry = EmployeeRegistry.objects.get(user_id=validated_data['user_id'])
                
                # Validate against new employer's config
                validation_result = check_missing_fields_against_config(validated_data, config)
                
                # Set profile completion fields based on validation
                validated_data['profile_completion_state'] = validation_result['completion_state']
                validated_data['profile_completion_required'] = validation_result['requires_update']
                validated_data['missing_required_fields'] = validation_result['missing_critical']
                validated_data['missing_optional_fields'] = validation_result['missing_non_critical']
                
                # If profile is complete, mark it as such
                if validation_result['completion_state'] == 'COMPLETE':
                    validated_data['profile_completed'] = True
                    validated_data['profile_completed_at'] = timezone.now()
                else:
                    validated_data['profile_completed'] = False
                    validated_data['profile_completed_at'] = None
                
            except EmployeeRegistry.DoesNotExist:
                # No registry exists, profile needs completion
                validated_data['profile_completion_required'] = True
                validated_data['profile_completion_state'] = 'INCOMPLETE_BLOCKING'
        else:
            # Only auto-create/link a user when we are not sending an invitation
            if not send_invitation:
                email = validated_data.get('email')
                if email:
                    user, _ = User.objects.get_or_create(
                        email=email,
                        defaults={
                            'is_employee': True,
                            'is_active': True,
                        },
                    )
                    validated_data['user_id'] = user.id
        
        # Create employee in tenant database
        employee = Employee.objects.using(tenant_db).create(**validated_data)

        # Evaluate profile completion state based on configuration
        from employees.utils import check_missing_fields_against_config
        completion_result = check_missing_fields_against_config(employee, config)
        employee.profile_completion_state = completion_result['completion_state']
        employee.profile_completion_required = completion_result['requires_update']
        employee.missing_required_fields = completion_result['missing_critical']
        employee.missing_optional_fields = completion_result['missing_non_critical']

        if completion_result['completion_state'] == 'COMPLETE':
            employee.profile_completed = True
            employee.profile_completed_at = timezone.now()
        else:
            employee.profile_completed = False
            employee.profile_completed_at = None

        employee.save(using=tenant_db, update_fields=[
            'profile_completion_state',
            'profile_completion_required',
            'missing_required_fields',
            'missing_optional_fields',
            'profile_completed',
            'profile_completed_at',
        ])

        if completion_result['requires_update'] and config.send_profile_completion_reminder:
            employee._send_completion_notification = True
        if pin_code:
            employee.set_pin_code(pin_code)
            employee.save(using=tenant_db, update_fields=["pin_code_hash"])

        # Create or refresh global membership mapping when a user is linked
        if employee.user_id:
            status_val = EmployeeMembership.STATUS_ACTIVE if employee.employment_status == 'ACTIVE' else EmployeeMembership.STATUS_INVITED
            EmployeeMembership.objects.using('default').update_or_create(
                user_id=employee.user_id,
                employer_profile=request.user.employer_profile,
                defaults={
                    'status': status_val,
                    'tenant_employee_id': employee.id,
                },
            )
            # Seed last_active_employer_id once for convenience
            User.objects.filter(id=employee.user_id, last_active_employer_id__isnull=True).update(
                last_active_employer_id=request.user.employer_profile.id
            )
        
        # Store invitation flag and tenant_db for view to handle
        employee._send_invitation = send_invitation
        employee._tenant_db = tenant_db
        
        # Store whether profile completion notification should be sent
        if validated_data.get('profile_completion_required', False):
            employee._send_completion_notification = True
        
        return employee


class UpdateEmployeeSerializer(serializers.ModelSerializer):
    """Serializer for updating employee information"""

    pin_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = Employee
        fields = [
            # Basic Information
            'first_name', 'last_name', 'middle_name', 'date_of_birth',
            'gender', 'marital_status', 'nationality', 'profile_photo',
            'badge_id', 'pin_code',
            
            # Contact Information
            'email', 'personal_email', 'phone_number', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            
            # Legal Identification
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            
            # Employment Details
            'job_title', 'department', 'branch', 'manager',
            'employment_type', 'employment_status', 'probation_end_date',
            
            # Compensation Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
        ]
    
    def update(self, instance, validated_data):
        """Update employee with validation of foreign key references"""
        from accounts.database_utils import get_tenant_database_alias
        
        # Get tenant database from context
        request = self.context.get('request')
        if request:
            from accounts.rbac import get_active_employer
            employer = get_active_employer(request, require_context=True)
            tenant_db = get_tenant_database_alias(employer)
            pin_code = validated_data.pop("pin_code", None)
            
            # Before updating, validate and clean up any invalid foreign key references
            # This prevents IntegrityError for existing invalid references
            if instance.branch_id:
                branch_exists = Branch.objects.using(tenant_db).filter(id=instance.branch_id).exists()
                if not branch_exists:
                    instance.branch_id = None
            
            if instance.department_id:
                dept_exists = Department.objects.using(tenant_db).filter(id=instance.department_id).exists()
                if not dept_exists:
                    instance.department_id = None
            
            if instance.manager_id:
                manager_exists = Employee.objects.using(tenant_db).filter(id=instance.manager_id).exists()
                if not manager_exists:
                    instance.manager_id = None
            
            # Update instance with validated data
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            if pin_code:
                instance.set_pin_code(pin_code)
            
            instance.save(using=tenant_db)
            return instance
        
        return super().update(instance, validated_data)


class AttendanceCredentialsSerializer(serializers.Serializer):
    """Serializer for assigning attendance identifiers and schedule to an employee."""

    badge_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    rfid_tag_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    pin_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    working_schedule_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_working_schedule_id(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if not request or not hasattr(request.user, "employer_profile"):
            return value
        from accounts.database_utils import get_tenant_database_alias
        from attendance.models import WorkingSchedule

        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        exists = WorkingSchedule.objects.using(tenant_db).filter(
            id=value, employer_id=request.user.employer_profile.id
        ).exists()
        if not exists:
            raise serializers.ValidationError("Working schedule not found for this employer.")
        return value

    def validate(self, attrs):
        if not any(
            key in attrs and attrs.get(key) not in [None, ""]
            for key in ("badge_id", "rfid_tag_id", "pin_code", "working_schedule_id")
        ):
            raise serializers.ValidationError("Provide at least one attendance credential to update.")
        return attrs


class TerminateEmployeeSerializer(serializers.Serializer):
    """Serializer for employee termination"""
    
    termination_date = serializers.DateField()
    termination_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate_termination_date(self, value):
        from django.utils import timezone
        if value > timezone.now().date():
            raise serializers.ValidationError(
                "Termination date cannot be in the future."
            )
        return value

    def validate(self, attrs):
        config = self.context.get('config')
        if config and config.require_termination_reason:
            reason = attrs.get('termination_reason')
            if not reason or (isinstance(reason, str) and reason.strip() == ''):
                raise serializers.ValidationError({
                    'termination_reason': 'Termination reason is required by configuration.'
                })
        return attrs


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    """Serializer for Employee Documents"""
    
    uploaded_by_name = serializers.SerializerMethodField()
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    
    class Meta:
        model = EmployeeDocument
        fields = [
            'id', 'employee', 'employee_name', 'document_type', 'title',
            'description', 'file', 'file_size', 'uploaded_by_id',
            'uploaded_by_name', 'uploaded_at', 'has_expiry', 'expiry_date',
            'is_verified', 'verified_by_id', 'verified_at'
        ]
        read_only_fields = ['id', 'uploaded_by_id', 'uploaded_at', 'file_size']
    
    def get_uploaded_by_name(self, obj):
        """Get the name/email of the user who uploaded this document"""
        if not obj.uploaded_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=obj.uploaded_by_id)
            return user.email
        except:
            return None
    
    def validate_file(self, value):
        """Validate file size and format based on employer configuration"""
        request = self.context.get('request')
        if not request:
            return value
        
        # Get employer configuration
        from accounts.rbac import get_active_employer
        from accounts.database_utils import get_tenant_database_alias
        from employees.utils import get_or_create_employee_config

        employer = None
        try:
            employer = get_active_employer(request, require_context=False)
        except Exception:
            employer = None

        if not employer:
            return value

        tenant_db = get_tenant_database_alias(employer)
        config = get_or_create_employee_config(employer.id, tenant_db)
        
        # Validate file size
        max_size_mb = config.document_max_file_size_mb
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"File size exceeds maximum allowed size of {max_size_mb}MB. "
                f"Your file is {value.size / (1024 * 1024):.2f}MB."
            )
        
        # Validate file format
        allowed_formats = config.get_allowed_document_formats()
        if allowed_formats:
            file_extension = value.name.split('.')[-1].lower()
            normalized_formats = [fmt.lower() for fmt in allowed_formats]
            if file_extension not in normalized_formats:
                raise serializers.ValidationError(
                    f"File format '.{file_extension}' is not allowed. "
                    f"Allowed formats: {', '.join(allowed_formats)}"
                )
        
        return value


class CrossInstitutionRecordSerializer(serializers.ModelSerializer):
    """Serializer for Cross-Institution Records"""
    
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    detected_employer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = EmployeeCrossInstitutionRecord
        fields = [
            'id', 'employee', 'employee_name', 'detected_employer_id',
            'detected_employer_name', 'detected_employee_id', 'status',
            'consent_status', 'consent_requested_at', 'consent_responded_at',
            'consent_notes', 'detected_at', 'verified', 'verified_at', 'notes'
        ]
        read_only_fields = [
            'id', 'detected_at', 'consent_requested_at',
            'consent_responded_at', 'verified_at'
        ]

    def get_detected_employer_name(self, obj):
        from accounts.models import EmployerProfile
        try:
            employer = EmployerProfile.objects.get(id=obj.detected_employer_id)
            return employer.company_name
        except EmployerProfile.DoesNotExist:
            return None


class EmployeeAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for Employee Audit Logs"""
    
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    performed_by_email = serializers.SerializerMethodField()
    
    class Meta:
        model = EmployeeAuditLog
        fields = [
            'id', 'employee', 'employee_name', 'action', 'performed_by_id',
            'performed_by_email', 'timestamp', 'changes', 'notes', 'ip_address'
        ]
        read_only_fields = ['id', 'timestamp']
    
    def get_performed_by_email(self, obj):
        """Get the email of the user who performed this action"""
        if not obj.performed_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=obj.performed_by_id)
            return user.email
        except:
            return None


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
    
    employer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = EmployeeConfiguration
        fields = '__all__'
        read_only_fields = ['id', 'employer_id', 'created_at', 'updated_at']

    def get_employer_name(self, obj):
        from accounts.models import EmployerProfile
        try:
            employer = EmployerProfile.objects.get(id=obj.employer_id)
            return employer.company_name
        except EmployerProfile.DoesNotExist:
            return None


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
    user_id = serializers.IntegerField(required=False, allow_null=True, write_only=True,
        help_text='Explicit user account ID to link (from main database)')
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
            
            # Compensation Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
            
            # Additional
            'send_invitation', 'force_create', 'link_existing_user', 'user_id',
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
            'user_id': {'required': False},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if not request:
            return

        try:
            from accounts.rbac import get_active_employer
            from accounts.database_utils import get_tenant_database_alias
            from employees.utils import get_or_create_employee_config
            employer = get_active_employer(request, require_context=True)
            tenant_db = get_tenant_database_alias(employer)
            config = get_or_create_employee_config(employer.id, tenant_db)
        except Exception:
            return

        def apply_requirement(field_name, requirement):
            field = self.fields.get(field_name)
            if not field:
                return
            if requirement == config.FIELD_REQUIRED:
                field.required = True
                field.allow_null = False
                if hasattr(field, 'allow_blank'):
                    field.allow_blank = False
            else:
                field.required = False
                field.allow_null = True
                if hasattr(field, 'allow_blank'):
                    field.allow_blank = True

        apply_requirement('department', config.require_department)
        apply_requirement('branch', config.require_branch)
        apply_requirement('manager', config.require_manager)
        apply_requirement('probation_end_date', config.require_probation_period)
        apply_requirement('national_id_number', config.require_national_id)

        # Allow email to be optional when auto-generation is enabled
        if config.auto_generate_work_email and 'email' in self.fields:
            self.fields['email'].required = False
            if hasattr(self.fields['email'], 'allow_blank'):
                self.fields['email'].allow_blank = True

    def validate_department(self, value):
        """Validate that department UUID exists in tenant database"""
        if value is None:
            return value
        
        request = self.context['request']
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        employer_id = employer.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
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
        if not value:
            return value
        
        request = self.context['request']
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        employer_id = employer.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
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
        if not value:
            return value
        
        request = self.context['request']
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        employer_id = employer.id
        
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)
        
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
        if not value or (isinstance(value, str) and value.strip() == ''):
            # Respect configuration if national ID is optional/hidden
            request = self.context.get('request')
            try:
                from accounts.rbac import get_active_employer
                from accounts.database_utils import get_tenant_database_alias
                from employees.utils import get_or_create_employee_config
                employer = get_active_employer(request, require_context=True)
                tenant_db = get_tenant_database_alias(employer)
                config = get_or_create_employee_config(employer.id, tenant_db)
                if config and config.require_national_id != config.FIELD_REQUIRED:
                    return value
            except Exception:
                pass
            raise serializers.ValidationError("National ID number is required for cross-institutional tracking.")
        
        # Check uniqueness within the employer's institution
        request = self.context['request']
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        
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
            existing = existing_query.only(
                'id',
                'employee_id',
                'first_name',
                'last_name',
                'employment_status',
                'branch_id',
                'department_id',
            ).first()
            details = None
            if existing:
                details = {
                    'id': str(existing.id),
                    'employee_id': existing.employee_id,
                    'name': f"{existing.first_name} {existing.last_name}",
                    'status': existing.employment_status,
                    'branch_id': existing.branch_id,
                    'department_id': existing.department_id,
                }
            raise serializers.ValidationError({
                'national_id_number': "An employee with this National ID already exists in your institution.",
                'existing_employee': details
            })
        
        return value
    
    def validate(self, data):
        """Validate employee data against configuration"""
        from employees.utils import validate_employee_data, detect_duplicate_employees, get_or_create_employee_config, check_concurrent_employment
        from accounts.database_utils import get_tenant_database_alias
        
        request = self.context['request']
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        
        # Get or create configuration using helper function
        config = get_or_create_employee_config(employer.id, tenant_db)

        # Enforce manual employee ID override setting
        if data.get('employee_id') and config and not config.employee_id_manual_override:
            raise serializers.ValidationError({
                'employee_id': 'Manual employee ID entry is disabled by configuration.'
            })
        
        # Skip strict validation during employer-initiated creation
        # The configuration requirements apply when employees complete their own profiles,
        # not when employers are creating initial employee records
        # Employers only need to provide minimal fields: first_name, last_name, email, job_title, etc.
        
        # Check for concurrent employment if linking existing user
        link_existing_user = data.get('link_existing_user')
        if link_existing_user:
            from accounts.models import EmployeeRegistry
            try:
                registry = EmployeeRegistry.objects.get(user_id=link_existing_user)
                concurrent_check = check_concurrent_employment(registry.id, employer.id, config)
                
                if not concurrent_check['allowed']:
                    raise serializers.ValidationError({
                        'concurrent_employment': concurrent_check['reason'],
                        'existing_employers': concurrent_check['existing_employers']
                    })
                
            except EmployeeRegistry.DoesNotExist:
                pass  # No registry, no concurrent employment check needed
        
        # Detect duplicates (always), then apply policy gates before respecting force_create
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

        if duplicate_result.get('duplicates_found'):
            same_matches = duplicate_result.get('same_institution_matches') or []
            cross_matches = duplicate_result.get('cross_institution_matches') or []
            if cross_matches:
                existing_employers = []
                for match in cross_matches:
                    entry = {
                        'employer_id': match.get('employer_id'),
                        'employer_name': match.get('employer_name'),
                    }
                    data_obj = match.get('data')
                    if isinstance(data_obj, dict):
                        entry['employee_id'] = data_obj.get('employee_id') or data_obj.get('id')
                    else:
                        entry['employee_id'] = getattr(data_obj, 'employee_id', None) or getattr(data_obj, 'id', None)
                    existing_employers.append(entry)

                # Contract-level gating for multi-institution employment
                contract_blocks_multi = False
                try:
                    from contracts.models import ContractConfiguration
                    contract_config = ContractConfiguration.objects.using(tenant_db).filter(
                        employer_id=employer.id,
                        contract_type__isnull=True
                    ).first()
                    contract_blocks_multi = bool(
                        contract_config and not contract_config.allow_multi_institution_employment
                    )
                except Exception:
                    contract_blocks_multi = False

                # Employee configuration can override contract-level default
                if contract_blocks_multi and not (config and config.allow_concurrent_employment):
                    try:
                        from accounts.notifications import create_notification
                        create_notification(
                            user=request.user,
                            title="Concurrent employment blocked",
                            body="Employee creation blocked due to contract configuration.",
                            type="ALERT",
                            data={
                                "event": "employees.concurrent_employment_blocked",
                                "reason": "contract_policy",
                                "existing_employers": existing_employers,
                            },
                            employer_profile=employer,
                        )
                    except Exception:
                        pass
                    raise serializers.ValidationError({
                        'concurrent_employment': 'Concurrent employment is not allowed by contract configuration',
                        'existing_employers': existing_employers,
                        'concurrent_employment_detected': True,
                    })

                if config and not config.allow_concurrent_employment:
                    try:
                        from accounts.notifications import create_notification
                        create_notification(
                            user=request.user,
                            title="Concurrent employment blocked",
                            body="Employee creation blocked by employer policy.",
                            type="ALERT",
                            data={
                                "event": "employees.concurrent_employment_blocked",
                                "reason": "employer_policy",
                                "existing_employers": existing_employers,
                            },
                            employer_profile=employer,
                        )
                    except Exception:
                        pass
                    raise serializers.ValidationError({
                        'concurrent_employment': 'Concurrent employment is not allowed by this employer',
                        'existing_employers': existing_employers,
                        'concurrent_employment_detected': True,
                    })

                # Consent flow disabled: do not require employee consent to proceed.

            # Check duplicate action from config (skip if force_create)
            force_create = data.get('force_create', False)
            if not force_create:
                if config and config.duplicate_action == 'BLOCK':
                    # Always block if duplicates exist within the same institution
                    if same_matches:
                        error_msg = f"Duplicate employee detected. Found {duplicate_result['total_matches']} matching records."
                        if same_matches:
                            error_msg += f" {len(same_matches)} in your institution."
                        if cross_matches:
                            error_msg += f" {len(cross_matches)} in other institutions."
                        raise serializers.ValidationError({'duplicate_detected': error_msg})

                    # If duplicates are only cross-institution and concurrent employment is allowed,
                    # treat as a warning so creation can proceed.
                    if cross_matches:
                        data['_duplicate_info'] = duplicate_result
                elif not config or config.duplicate_action in ['WARN', 'ALLOW']:
                    # Store duplicate info for response but allow creation
                    data['_duplicate_info'] = duplicate_result
        
        return data
    
    def create(self, validated_data):
        from employees.utils import create_employee_audit_log
        
        send_invitation = validated_data.pop('send_invitation', False)
        force_create = validated_data.pop('force_create', False)
        link_existing_user = validated_data.pop('link_existing_user', None)
        explicit_user_id = validated_data.pop('user_id', None)
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
        from accounts.rbac import get_active_employer
        employer = get_active_employer(request, require_context=True)
        
        # Ensure baseline employment fields for employer onboarding
        validated_data.setdefault('employment_status', 'ACTIVE')
        
        # Get tenant database alias
        from accounts.database_utils import get_tenant_database_alias
        from employees.utils import get_or_create_employee_config
        tenant_db = get_tenant_database_alias(employer)
        
        # Get configuration
        config = get_or_create_employee_config(employer.id, tenant_db)

        # Respect configuration for invitation sending
        if not config.send_invitation_email:
            send_invitation = False
        
        # Auto-generate employee ID if not provided and configured
        if not validated_data.get('employee_id'):
            department_obj = None
            branch_obj = None
            if department_uuid:
                try:
                    department_obj = Department.objects.using(tenant_db).get(id=department_uuid)
                except Department.DoesNotExist:
                    department_obj = None
            if branch_uuid:
                try:
                    branch_obj = Branch.objects.using(tenant_db).get(id=branch_uuid)
                except Branch.DoesNotExist:
                    branch_obj = None

            validated_data['employee_id'] = config.get_next_employee_id(
                branch=branch_obj,
                department=department_obj,
                using=tenant_db
            )

        # Set probation end date using default configuration if not provided
        if not validated_data.get('probation_end_date') and config.default_probation_period_months:
            if config.require_probation_period != config.FIELD_HIDDEN:
                hire_date = validated_data.get('hire_date')
                if hire_date:
                    import calendar
                    months = int(config.default_probation_period_months)
                    year = hire_date.year + (hire_date.month - 1 + months) // 12
                    month = (hire_date.month - 1 + months) % 12 + 1
                    day = min(hire_date.day, calendar.monthrange(year, month)[1])
                    validated_data['probation_end_date'] = hire_date.replace(
                        year=year,
                        month=month,
                        day=day
                    )
        
        # Auto-generate work email if configured
        if config.auto_generate_work_email and not validated_data.get('email'):
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
        chosen_user_id = explicit_user_id or link_existing_user
        if chosen_user_id:
            try:
                user = User.objects.get(id=chosen_user_id)
                validated_data['user_id'] = user.id
            except User.DoesNotExist:
                pass
        elif not validated_data.get('user_id') and not send_invitation:
            # Auto-create/link by email only when not sending invitation
            email = validated_data.get('email')
            if email:
                user, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'is_employee': True,
                        'is_active': True,
                    },
                )
                validated_data['user_id'] = user.id
        
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

            # Create or refresh global membership mapping
            status_val = EmployeeMembership.STATUS_ACTIVE if employee.employment_status == 'ACTIVE' else EmployeeMembership.STATUS_INVITED
            EmployeeMembership.objects.using('default').update_or_create(
                user_id=employee.user_id,
                employer_profile=employer,
                defaults={
                    'status': status_val,
                    'tenant_employee_id': employee.id,
                },
            )
            User.objects.filter(id=employee.user_id, last_active_employer_id__isnull=True).update(
                last_active_employer_id=employer.id
            )

            # Consent flow disabled: do not create consent requests.
        
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
                raw_employer_id = match.get('employer_id')
                employer_id = None
                if isinstance(raw_employer_id, int):
                    employer_id = raw_employer_id
                else:
                    try:
                        if raw_employer_id is not None and str(raw_employer_id).isdigit():
                            employer_id = int(raw_employer_id)
                    except (TypeError, ValueError):
                        employer_id = None
                if not employer_id:
                    continue
                data = match.get('data')
                detected_employee_id = None
                status_val = 'PENDING'

                if isinstance(data, dict):
                    detected_employee_id = data.get('id') or data.get('employee_id')
                    status_val = data.get('employment_status', status_val)
                else:
                    detected_employee_id = getattr(data, 'id', None) or getattr(data, 'employee_id', None)
                    status_val = getattr(data, 'employment_status', status_val)

                match_key = None
                if isinstance(data, dict):
                    match_key = data.get('id') or data.get('employee_id')
                else:
                    match_key = getattr(data, 'id', None) or getattr(data, 'pk', None)

                # Resolve match reasons with fallback for registry/tenant prefixes
                reason_key = str(match_key)
                reasons = duplicate_info['match_reasons'].get(reason_key)
                if not reasons:
                    reason_prefix = 'registry_' if match.get('type') == 'registry' else 'tenant_'
                    reasons = duplicate_info['match_reasons'].get(f"{reason_prefix}{match_key}", [])

                EmployeeCrossInstitutionRecord.objects.using(tenant_db).create(
                    employee=employee,
                    detected_employer_id=employer_id,
                    detected_employee_id=str(detected_employee_id) if detected_employee_id is not None else '',
                    status=status_val or 'PENDING',
                    consent_status='NOT_REQUIRED',
                    consent_requested_at=None,
                    notes=f"Detected during employee creation. Match reasons: {', '.join(reasons or [])}"
                )
        
        # Store flags for view to handle
        employee._send_invitation = send_invitation
        employee._duplicate_info = duplicate_info
        employee._tenant_db = tenant_db  # Store tenant DB for view to use
        
        return employee


class EmployeeDocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading employee documents"""
    
    # Accept 'name' as an alias for 'title' for frontend compatibility
    name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = EmployeeDocument
        fields = [
            'employee', 'document_type', 'title', 'name', 'description', 'file',
            'has_expiry', 'expiry_date'
        ]
        extra_kwargs = {
            'employee': {'required': True},
            'title': {'required': False}  # Make title optional since we accept 'name' too
        }
    
    def validate(self, data):
        """Ensure either 'title' or 'name' is provided"""
        # If 'name' is provided but not 'title', use 'name' as 'title'
        if 'name' in data and data['name']:
            data['title'] = data.pop('name')
        elif 'title' not in data or not data['title']:
            # If neither is provided, use filename or document type as title
            if 'file' in data:
                data['title'] = data['file'].name
            elif 'document_type' in data:
                # Use document type as fallback title
                doc_type = data['document_type']
                # Convert to readable format
                data['title'] = doc_type.replace('_', ' ').title()
            else:
                raise serializers.ValidationError({
                    'title': 'Either title or name field is required'
                })
        else:
            # Remove 'name' if 'title' was provided
            data.pop('name', None)
        
        return data
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove default queryset validation for employee field
        # Accept any UUID and validate it in validate_employee method
        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.none()
            
            # Make employee field optional for employees (they upload for themselves)
            request = self.context.get('request')
            if request and request.user.is_employee:
                self.fields['employee'].required = False
    
    def validate_employee(self, value):
        """Validate that employee exists in the tenant database and belongs to employer"""
        from accounts.database_utils import get_tenant_database_alias
        from accounts.rbac import get_active_employer
        
        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("Request context is required")
        
        user = request.user
        
        # If employee is uploading for themselves
        if user.is_employee:
            # If employee field is not provided, use the logged-in employee
            if not value:
                # Get employee from context (set in get_serializer_context)
                employee = self.context.get('employee')
                if not employee:
                    raise serializers.ValidationError("Employee record not found")
                return employee
            else:
                # Employee provided an employee ID - must be their own
                tenant_db = self.context.get('tenant_db')
                employee_id = value.id if hasattr(value, 'id') else value
                
                # Verify it's their own employee record
                try:
                    employee = Employee.objects.using(tenant_db).get(id=employee_id, user_id=user.id)
                    return employee
                except Employee.DoesNotExist:
                    raise serializers.ValidationError("You can only upload documents for yourself")
        
        # Employer or delegate uploading for an employee
        employer = None
        try:
            employer = get_active_employer(request, require_context=False)
        except Exception:
            employer = None

        if not employer:
            raise serializers.ValidationError("User must be an employer")

        tenant_db = self.context.get('tenant_db')
        
        if not tenant_db:
            tenant_db = get_tenant_database_alias(employer)
        
        # Get employee ID - handle both UUID string and Employee instance
        employee_id = value.id if hasattr(value, 'id') else value
        
        # Check if employee exists in tenant database and belongs to this employer
        try:
            employee = Employee.objects.using(tenant_db).get(
                id=employee_id,
                employer_id=employer.id
            )
            # Return the employee instance for use in create()
            return employee
        except Employee.DoesNotExist:
            raise serializers.ValidationError(
                f"Employee does not exist in your organization"
            )
    
    def validate_file(self, value):
        """Validate file size and format based on configuration"""
        from accounts.database_utils import get_tenant_database_alias
        from accounts.rbac import get_active_employer
        from employees.utils import get_or_create_employee_config
        
        request = self.context['request']
        user = request.user
        tenant_db = self.context.get('tenant_db')
        
        # Get employer_id based on user type
        employer_id = None
        if hasattr(user, 'employer_profile') and user.employer_profile:
            employer_id = user.employer_profile.id
            if not tenant_db:
                tenant_db = get_tenant_database_alias(user.employer_profile)
        else:
            try:
                active_employer = get_active_employer(request, require_context=False)
            except Exception:
                active_employer = None
            if active_employer:
                employer_id = active_employer.id
                if not tenant_db:
                    tenant_db = get_tenant_database_alias(active_employer)

        if not employer_id and user.is_employee:
            # Get employee to find employer_id
            employee = self.context.get('employee')
            if employee:
                employer_id = employee.employer_id
                if not tenant_db:
                    try:
                        from accounts.models import EmployerProfile
                        employer_profile = EmployerProfile.objects.get(id=employee.employer_id)
                        tenant_db = get_tenant_database_alias(employer_profile)
                    except Exception:
                        tenant_db = tenant_db or None
            else:
                # Skip validation if we can't determine employer
                return value
        elif not employer_id:
            return value
        
        # Get or create configuration using helper function
        tenant_db = tenant_db or 'default'
        config = get_or_create_employee_config(employer_id, tenant_db)
            
        # Check file size
        max_size_bytes = config.document_max_file_size_mb * 1024 * 1024
        if value.size > max_size_bytes:
            raise serializers.ValidationError(
                f"File size exceeds maximum allowed size of {config.document_max_file_size_mb}MB"
            )
            
        # Check file format
        allowed_formats = config.get_allowed_document_formats()
        file_ext = value.name.split('.')[-1].lower()
        normalized_formats = [fmt.lower() for fmt in allowed_formats] if allowed_formats else []
        if normalized_formats and file_ext not in normalized_formats:
            raise serializers.ValidationError(
                f"File format '.{file_ext}' is not allowed. Allowed formats: {', '.join(allowed_formats)}"
            )
        
        return value
    
    def create(self, validated_data):
        """Create document in tenant database"""
        # Pop the 'using' argument if it exists
        tenant_db = validated_data.pop('using', None)
        
        # The employee field is now an Employee instance from validate_employee
        employee = validated_data['employee']
        validated_data['employee_id'] = employee.id
        
        validated_data['uploaded_by_id'] = self.context['request'].user.id
        validated_data['file_size'] = validated_data['file'].size
        
        # Get tenant_db from context if not provided
        if not tenant_db:
            tenant_db = self.context.get('tenant_db')
        
        # Save to tenant database
        if tenant_db:
            # Remove employee object and use employee_id instead
            validated_data.pop('employee')
            return EmployeeDocument.objects.using(tenant_db).create(**validated_data)
        
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
            'profile_photo', 'middle_name',
            
            # Contact Details
            'phone_number', 'alternative_phone', 'personal_email',
            'address', 'city', 'state_region', 'postal_code', 'country',
            
            # Legal Identification
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            
            # Compensation Information
            'bank_name', 'bank_account_number', 'bank_account_name',
            
            # Emergency Contact
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone',
        ]
        # Explicitly make these fields read-only - employees cannot change their assignment
        read_only_fields = [
            'employee_id', 'first_name', 'last_name', 'email',
            'department', 'branch', 'manager', 'job_title', 'employment_type',
            'employment_status', 'hire_date', 'probation_end_date',
            'employer_id', 'user_id', 'created_by_id'
        ]
        # String fields that support allow_blank
        string_fields = [
            'nationality', 'marital_status', 'phone_number', 'alternative_phone', 
            'personal_email', 'address', 'city', 'state_region', 'postal_code', 'country',
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            'bank_name', 'bank_account_number', 'bank_account_name',
            'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone',
            'middle_name'
        ]
        extra_kwargs = {
            **{field: {'required': False, 'allow_null': True, 'allow_blank': True} 
               for field in string_fields},
            **{field: {'required': False, 'allow_null': True} 
               for field in ['date_of_birth', 'gender', 'profile_photo']}
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Dynamically remove hidden fields based on employer configuration
        if self.instance:
            from accounts.database_utils import get_tenant_database_alias
            from accounts.models import EmployerProfile
            
            try:
                employer = EmployerProfile.objects.get(id=self.instance.employer_id)
                tenant_db = self.context.get('tenant_db') or get_tenant_database_alias(employer)
                config, _ = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
                    employer_id=self.instance.employer_id
                )
                
                # Map serializer fields to configuration attributes
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
                    'passport_number': 'require_passport',
                    'cnps_number': 'require_cnps_number',
                    'tax_number': 'require_tax_number',
                }
                
                # Remove hidden fields
                for field_name, config_attr in field_config_map.items():
                    requirement = getattr(config, config_attr, 'OPTIONAL')
                    if requirement == 'HIDDEN' and field_name in self.fields:
                        self.fields.pop(field_name)
                
            except (EmployerProfile.DoesNotExist, Exception):
                pass
    
    def validate(self, data):
        """Validate employee profile data against employer's specific configuration requirements"""
        from employees.utils import validate_employee_data_strict
        from accounts.database_utils import get_tenant_database_alias
        from accounts.models import EmployerProfile
        
        # Get the employee instance being updated
        if self.instance:
            # Get tenant_db from context if available
            tenant_db = self.context.get('tenant_db')
            
            try:
                employer = EmployerProfile.objects.get(id=self.instance.employer_id)
                if not tenant_db:
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
            
            # Strictly enforce THIS employer's configuration requirements
            # Fields marked as REQUIRED in config must be provided during profile completion
            if config:
                # Merge existing instance data with update data for validation
                # Only include fields that the employee can update
                merged_data = {
                    'middle_name': data.get('middle_name', self.instance.middle_name),
                    'profile_photo': data.get('profile_photo', self.instance.profile_photo),
                    'gender': data.get('gender', self.instance.gender),
                    'date_of_birth': data.get('date_of_birth', self.instance.date_of_birth),
                    'marital_status': data.get('marital_status', self.instance.marital_status),
                    'nationality': data.get('nationality', self.instance.nationality),
                    'personal_email': data.get('personal_email', self.instance.personal_email),
                    'alternative_phone': data.get('alternative_phone', self.instance.alternative_phone),
                    'address': data.get('address', self.instance.address),
                    'postal_code': data.get('postal_code', self.instance.postal_code),
                    'national_id_number': data.get('national_id_number', self.instance.national_id_number),
                    'passport': data.get('passport_number', self.instance.passport_number),
                    'cnps_number': data.get('cnps_number', self.instance.cnps_number),
                    'tax_number': data.get('tax_number', self.instance.tax_number),
                    'phone_number': data.get('phone_number', self.instance.phone_number),
                    'city': data.get('city', self.instance.city),
                    'state_region': data.get('state_region', self.instance.state_region),
                    'country': data.get('country', self.instance.country),
                    'bank_account_number': data.get('bank_account_number', self.instance.bank_account_number),
                    'bank_name': data.get('bank_name', self.instance.bank_name),
                    'bank_account_name': data.get('bank_account_name', self.instance.bank_account_name),
                    'emergency_contact_name': data.get('emergency_contact_name', self.instance.emergency_contact_name),
                    'emergency_contact_phone': data.get('emergency_contact_phone', self.instance.emergency_contact_phone),
                    'emergency_contact_relationship': data.get('emergency_contact_relationship', self.instance.emergency_contact_relationship),
                    'employment_status': self.instance.employment_status,
                }
                
                # Validate against this employer's specific requirements
                validation_result = validate_employee_data_strict(merged_data, config)
                if not validation_result['valid']:
                    # Raise validation error with employer-specific field requirements
                    raise serializers.ValidationError({
                        **validation_result['errors'],
                        '_info': f'These fields are required by {employer.company_name}'
                    })
        
        return data
        
    
    def update(self, instance, validated_data):
        """Update employee profile, check completion state, and sync to central EmployeeRegistry"""
        from django.utils import timezone
        from django.contrib.auth import get_user_model
        from employees.utils import check_missing_fields_against_config, get_or_create_employee_config
        from accounts.database_utils import get_tenant_database_alias
        from accounts.models import EmployerProfile
        
        User = get_user_model()
        
        # Get tenant database from context
        tenant_db = self.context.get('tenant_db')
        
        # Track which fields are being updated
        update_fields = list(validated_data.keys())
        
        # Update all provided fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Re-validate profile completion state after update
        try:
            employer = EmployerProfile.objects.get(id=instance.employer_id)
            if not tenant_db:
                tenant_db = get_tenant_database_alias(employer)
            config = get_or_create_employee_config(instance.employer_id, tenant_db)
            
            # Check what fields are still missing after this update
            validation_result = check_missing_fields_against_config(instance, config)
            
            # Update completion state
            instance.profile_completion_state = validation_result['completion_state']
            instance.profile_completion_required = validation_result['requires_update']
            instance.missing_required_fields = validation_result['missing_critical']
            instance.missing_optional_fields = validation_result['missing_non_critical']
            
            # Add these fields to the update list
            update_fields.extend([
                'profile_completion_state', 'profile_completion_required',
                'missing_required_fields', 'missing_optional_fields'
            ])
            
            # Mark as completed if all requirements met
            if validation_result['completion_state'] == 'COMPLETE':
                instance.profile_completed = True
                instance.profile_completed_at = timezone.now()
                update_fields.extend(['profile_completed', 'profile_completed_at'])
            else:
                instance.profile_completed = False
                instance.profile_completed_at = None
                update_fields.extend(['profile_completed', 'profile_completed_at'])
                
        except EmployerProfile.DoesNotExist:
            # Fallback: mark as completed if we can't validate
            instance.profile_completed = True
            instance.profile_completed_at = timezone.now()
            update_fields.extend(['profile_completed', 'profile_completed_at'])
        
        # Save only the fields that were actually updated to the correct database
        if tenant_db:
            instance.save(using=tenant_db, update_fields=update_fields)
        else:
            instance.save(update_fields=update_fields)
        
        # Sync to central EmployeeRegistry
        if instance.user_id:
            from accounts.models import EmployeeRegistry
            try:
                user = User.objects.get(id=instance.user_id)
                
                # Update EmployeeRegistry if it exists, create if it doesn't
                employee_registry, created = EmployeeRegistry.objects.get_or_create(
                    user=user,
                    defaults={
                        'first_name': instance.first_name,
                        'last_name': instance.last_name,
                        'middle_name': instance.middle_name or '',
                        'date_of_birth': instance.date_of_birth or timezone.now().date(),
                        'gender': instance.gender or 'PREFER_NOT_TO_SAY',
                        'marital_status': instance.marital_status or 'SINGLE',
                        'nationality': instance.nationality or 'Unknown',
                        'phone_number': instance.phone_number or '0000000000',
                        'address': instance.address or 'Not Provided',
                        'city': instance.city or 'Unknown',
                        'state_region': instance.state_region or 'Unknown',
                        'country': instance.country or 'Unknown',
                        'emergency_contact_name': instance.emergency_contact_name or 'Not Provided',
                        'emergency_contact_relationship': instance.emergency_contact_relationship or 'Unknown',
                        'emergency_contact_phone': instance.emergency_contact_phone or '0000000000',
                        'national_id_number': instance.national_id_number or '',
                    }
                )
                
                if not created:
                    # Update existing registry
                    # Define field mapping (only update fields that were provided)
                    field_mapping = {
                        'first_name': 'first_name',
                        'last_name': 'last_name',
                        'middle_name': 'middle_name',
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
                            # Handle empty values for required fields in EmployeeRegistry
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
                    
                    # Sync profile photo if updated
                    if 'profile_photo' in validated_data and validated_data['profile_photo']:
                        employee_registry.profile_picture = validated_data['profile_photo']
                    
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
    
    department_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    employer_name = serializers.SerializerMethodField()
    missing_documents = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'first_name', 'last_name', 'middle_name', 'full_name',
            'date_of_birth', 'gender', 'nationality', 'marital_status', 'profile_photo',
            'email', 'personal_email', 'phone_number', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            'job_title', 'department', 'department_name', 'branch', 'branch_name', 
            'manager', 'manager_name',
            'employment_type', 'employment_status', 'hire_date', 'probation_end_date',
            'bank_name', 'bank_account_number', 'bank_account_name',
            'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone',
            'profile_completed', 'profile_completed_at', 'profile_completion_state',
            'profile_completion_required', 'missing_required_fields', 'missing_optional_fields',
            'missing_documents', 'documents', 'employer_name', 'created_at', 'updated_at'
        ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Dynamically remove hidden fields based on employer configuration
        if self.instance:
            from accounts.database_utils import get_tenant_database_alias
            from accounts.models import EmployerProfile
            
            try:
                employer = EmployerProfile.objects.get(id=self.instance.employer_id)
                tenant_db = self.context.get('tenant_db') or get_tenant_database_alias(employer)
                config, _ = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
                    employer_id=self.instance.employer_id
                )
                
                # Map serializer fields to configuration attributes
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
                    'passport_number': 'require_passport',
                    'cnps_number': 'require_cnps_number',
                    'tax_number': 'require_tax_number',
                }
                
                # Remove hidden fields
                for field_name, config_attr in field_config_map.items():
                    requirement = getattr(config, config_attr, 'OPTIONAL')
                    if requirement == 'HIDDEN' and field_name in self.fields:
                        self.fields.pop(field_name)
                
            except (EmployerProfile.DoesNotExist, Exception):
                pass
    
    def get_department_name(self, obj):
        """Get department name safely"""
        if obj.department:
            return obj.department.name
        return None
    
    def get_branch_name(self, obj):
        """Get branch name safely"""
        if obj.branch:
            return obj.branch.name
        return None
    
    def get_manager_name(self, obj):
        """Get manager name safely"""
        if obj.manager:
            return obj.manager.full_name
        return None
    
    def get_employer_name(self, obj):
        from accounts.models import EmployerProfile
        try:
            employer = EmployerProfile.objects.get(id=obj.employer_id)
            return employer.company_name
        except EmployerProfile.DoesNotExist:
            return None
    
    def get_missing_documents(self, obj):
        """Get list of missing required documents"""
        from employees.utils import check_required_documents
        try:
            result = check_required_documents(obj)
            return result.get('missing', [])
        except Exception:
            return []
    
    def get_documents(self, obj):
        """Get all documents for this employee"""
        documents = obj.documents.all()
        return EmployeeDocumentSerializer(documents, many=True, context=self.context).data


class TerminationApprovalSerializer(serializers.ModelSerializer):
    """Serializer for Termination Approval"""
    
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    requested_by_email = serializers.SerializerMethodField()
    approval_status = serializers.SerializerMethodField()
    
    class Meta:
        model = TerminationApproval
        fields = [
            'id', 'employee', 'employee_name', 'requested_by_id', 'requested_by_email',
            'termination_date', 'termination_reason', 'status', 'approval_status',
            'requires_manager_approval', 'manager_approved', 'manager_approved_by_id', 'manager_approved_at',
            'requires_hr_approval', 'hr_approved', 'hr_approved_by_id', 'hr_approved_at',
            'rejection_reason', 'rejected_by_id', 'rejected_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'status']
    
    def get_requested_by_email(self, obj):
        try:
            user = User.objects.get(id=obj.requested_by_id)
            return user.email
        except User.DoesNotExist:
            return None
    
    def get_approval_status(self, obj):
        """Get detailed approval status"""
        status = {
            'fully_approved': obj.is_fully_approved(),
            'pending_approvals': []
        }
        
        if obj.requires_manager_approval and not obj.manager_approved:
            status['pending_approvals'].append('manager')
        if obj.requires_hr_approval and not obj.hr_approved:
            status['pending_approvals'].append('hr')
        
        return status


class ApproveTerminationSerializer(serializers.Serializer):
    """Serializer for approving termination"""
    
    approval_type = serializers.ChoiceField(choices=['manager', 'hr'], required=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class RejectTerminationSerializer(serializers.Serializer):
    """Serializer for rejecting termination"""
    
    rejection_reason = serializers.CharField(required=True)


class RequestTerminationSerializer(serializers.Serializer):
    """Serializer for requesting employee termination with approval workflow"""
    
    termination_date = serializers.DateField()
    termination_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate_termination_date(self, value):
        from django.utils import timezone
        if value > timezone.now().date():
            raise serializers.ValidationError(
                "Termination date cannot be in the future."
            )
        return value

    def validate(self, attrs):
        config = self.context.get('config')
        if config and config.require_termination_reason:
            reason = attrs.get('termination_reason')
            if not reason or (isinstance(reason, str) and reason.strip() == ''):
                raise serializers.ValidationError({
                    'termination_reason': 'Termination reason is required by configuration.'
                })
        return attrs


class CrossInstitutionConsentSerializer(serializers.ModelSerializer):
    """Serializer for Cross-Institution Consent"""
    source_employer_name = serializers.SerializerMethodField()

    class Meta:
        model = CrossInstitutionConsent
        fields = [
            'id', 'employee_registry_id', 'source_employer_id', 'target_employer_id',
            'source_employer_name', 'target_employer_name', 'status', 'consent_token',
            'requested_at', 'expires_at', 'responded_at', 'notes'
        ]
        read_only_fields = ['id', 'consent_token', 'requested_at', 'responded_at']

    def get_source_employer_name(self, obj):
        from accounts.models import EmployerProfile
        try:
            employer = EmployerProfile.objects.get(id=obj.source_employer_id)
            return employer.company_name
        except EmployerProfile.DoesNotExist:
            return None


class RespondConsentSerializer(serializers.Serializer):
    """Serializer for responding to cross-institution consent"""
    
    response = serializers.ChoiceField(choices=['approve', 'reject'], required=True)
    notes = serializers.CharField(required=False, allow_blank=True)


