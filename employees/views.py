"""Views for employee management by employers"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.db import IntegrityError
from datetime import timedelta

from .models import (
    Department, Branch, Employee, EmployeeDocument,
    EmployeeCrossInstitutionRecord, EmployeeAuditLog,
    EmployeeInvitation, EmployeeConfiguration
)
from .serializers import (
    DepartmentSerializer, BranchSerializer,
    EmployeeListSerializer, EmployeeDetailSerializer,
    CreateEmployeeSerializer, UpdateEmployeeSerializer,
    TerminateEmployeeSerializer, EmployeeDocumentSerializer,
    CrossInstitutionRecordSerializer, EmployeeAuditLogSerializer,
    EmployeeInvitationSerializer, EmployeeSearchSerializer,
    EmployeeConfigurationSerializer, DuplicateDetectionResultSerializer,
    CreateEmployeeWithDetectionSerializer, EmployeeDocumentUploadSerializer,
    AcceptInvitationSerializer, EmployeeProfileCompletionSerializer,
    EmployeeSelfProfileSerializer, EmployeePrefillRequestSerializer,
    EmployeePrefillSerializer
)
from .utils import (
    detect_duplicate_employees, generate_employee_invitation_token,
    get_invitation_expiry_date, send_employee_invitation_email,
    create_employee_audit_log, check_required_documents,
    check_expiring_documents, get_cross_institution_summary
)
from accounts.permissions import IsEmployer, IsEmployee, IsAuthenticated


class DepartmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing departments"""
    
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = DepartmentSerializer
    
    def get_queryset(self):
        """Return departments for the employer's organization from tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        
        return Department.objects.using(tenant_db).filter(
            employer_id=self.request.user.employer_profile.id
        ).select_related('parent_department')
    
    def perform_create(self, serializer):
        """Set employer when creating department in tenant database"""
        serializer.save(employer_id=self.request.user.employer_profile.id)
    
    def perform_update(self, serializer):
        """Update department in tenant database"""
        serializer.save()
    
    def perform_destroy(self, instance):
        """Delete department from tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        
        instance.delete(using=tenant_db)


class BranchViewSet(viewsets.ModelViewSet):
    """ViewSet for managing branches"""
    
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = BranchSerializer
    
    def get_queryset(self):
        """Return branches for the employer's organization from tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        
        return Branch.objects.using(tenant_db).filter(
            employer_id=self.request.user.employer_profile.id
        )
    
    def perform_create(self, serializer):
        """Set employer when creating branch in tenant database"""
        serializer.save(employer_id=self.request.user.employer_profile.id)
    
    def perform_update(self, serializer):
        """Update branch in tenant database"""
        serializer.save()
    
    def perform_destroy(self, instance):
        """Delete branch from tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        
        instance.delete(using=tenant_db)


class EmployeeViewSet(viewsets.ModelViewSet):
    """ViewSet for managing employees"""
    
    permission_classes = [IsAuthenticated, IsEmployer]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return EmployeeListSerializer
        elif self.action == 'create':
            return CreateEmployeeWithDetectionSerializer
        elif self.action == 'update' or self.action == 'partial_update':
            return UpdateEmployeeSerializer
        elif self.action == 'terminate':
            return TerminateEmployeeSerializer
        else:
            return EmployeeDetailSerializer
    
    def get_queryset(self):
        """Return employees for the employer's organization from tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        queryset = Employee.objects.using(tenant_db).filter(
            employer_id=employer.id
        ).select_related(
            'department', 'branch', 'manager'
        ).prefetch_related('documents', 'cross_institution_records')
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(employment_status=status_filter)
        
        # Filter by department if provided
        department = self.request.query_params.get('department')
        if department:
            queryset = queryset.filter(department_id=department)
        
        # Filter by branch if provided
        branch = self.request.query_params.get('branch')
        if branch:
            queryset = queryset.filter(branch_id=branch)
        
        # Search by name or employee ID
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(employee_id__icontains=search) |
                Q(email__icontains=search)
            )
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create a new employee with duplicate detection"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            employee = serializer.save()
        except IntegrityError as e:
            error_message = str(e)
            
            # Check for specific constraint violations
            if 'employees_employer_id_employee_id' in error_message:
                return Response(
                    {
                        'error': 'Duplicate Employee ID',
                        'detail': 'An employee with this Employee ID already exists in your organization. Please use a different Employee ID or leave it empty for auto-generation.',
                        'field': 'employee_id'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            elif 'employees_employer_id_email' in error_message:
                return Response(
                    {
                        'error': 'Duplicate Email',
                        'detail': 'An employee with this email address already exists in your organization. Please use a different email address.',
                        'field': 'email'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            elif 'employees_employer_id_national_id' in error_message or 'national_id_number' in error_message:
                return Response(
                    {
                        'error': 'Duplicate National ID',
                        'detail': 'An employee with this National ID number already exists in your organization.',
                        'field': 'national_id_number'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                # Generic integrity error
                return Response(
                    {
                        'error': 'Data Integrity Error',
                        'detail': 'The employee data conflicts with existing records. Please check all fields and try again.',
                        'technical_detail': error_message
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Send invitation if requested
        if getattr(employee, '_send_invitation', False):
            tenant_db = getattr(employee, '_tenant_db', None)
            self._send_invitation(employee, tenant_db)
        
        # Send profile completion notification if required
        if getattr(employee, '_send_completion_notification', False):
            from employees.utils import send_profile_completion_notification, check_missing_fields_against_config
            from accounts.database_utils import get_tenant_database_alias
            from employees.utils import get_or_create_employee_config
            
            tenant_db = getattr(employee, '_tenant_db', None)
            if not tenant_db:
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
            
            config = get_or_create_employee_config(employee.employer_id, tenant_db)
            missing_fields_info = check_missing_fields_against_config(employee, config)
            
            send_profile_completion_notification(
                employee,
                missing_fields_info,
                request.user.employer_profile,
                tenant_db
            )
        
        # Prepare response with duplicate info if available
        response_data = EmployeeDetailSerializer(employee).data
        
        if hasattr(employee, '_duplicate_info') and employee._duplicate_info:
            duplicate_info = employee._duplicate_info
            response_data['duplicate_warning'] = {
                'message': f"Employee created successfully, but {duplicate_info['total_matches']} potential duplicate(s) detected",
                'duplicates_found': duplicate_info['duplicates_found'],
                'total_matches': duplicate_info['total_matches'],
                'same_institution': len(duplicate_info['same_institution_matches']),
                'cross_institution': len(duplicate_info['cross_institution_matches']),
            }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
    
    def _send_invitation(self, employee, tenant_db=None):
        """Helper method to send employee invitation"""
        # If tenant_db not provided, get it from employer
        if not tenant_db:
            from accounts.database_utils import get_tenant_database_alias
            from accounts.models import EmployerProfile
            try:
                employer_profile = EmployerProfile.objects.get(id=employee.employer_id)
                tenant_db = get_tenant_database_alias(employer_profile)
            except EmployerProfile.DoesNotExist:
                tenant_db = 'default'
        
        # Get configuration from tenant database
        from employees.utils import get_or_create_employee_config
        config = get_or_create_employee_config(employee.employer_id, tenant_db)
        
        # Create invitation in tenant database
        invitation = EmployeeInvitation.objects.using(tenant_db).create(
            employee=employee,
            token=generate_employee_invitation_token(),
            email=employee.email or employee.personal_email,
            expires_at=get_invitation_expiry_date(config)
        )
        
        # Update employee flags in tenant database
        employee.invitation_sent = True
        employee.invitation_sent_at = timezone.now()
        employee.save(using=tenant_db, update_fields=['invitation_sent', 'invitation_sent_at'])
        
        # Send email
        if not config or config.send_invitation_email:
            send_employee_invitation_email(employee, invitation)
        
        # Create audit log in tenant database
        create_employee_audit_log(
            employee=employee,
            action='INVITED',
            performed_by=self.request.user,
            notes=f'Invitation sent to {invitation.email}',
            request=self.request,
            tenant_db=tenant_db
        )
    
    @action(detail=True, methods=['post'])
    def send_invitation(self, request, pk=None):
        """Send or resend invitation to employee"""
        from accounts.database_utils import get_tenant_database_alias
        
        employee = self.get_object()
        
        # Get tenant database
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        # Check if employee already has a user account (use user_id not user)
        if employee.user_id:
            return Response(
                {'error': 'Employee already has a user account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if there's a pending invitation in tenant database
        pending_invitation = EmployeeInvitation.objects.using(tenant_db).filter(
            employee_id=employee.id,
            status='PENDING'
        ).first()
        
        if pending_invitation and pending_invitation.is_valid():
            return Response(
                {
                    'error': 'A valid invitation is already pending',
                    'expires_at': pending_invitation.expires_at
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Send new invitation
        self._send_invitation(employee, tenant_db)
        
        return Response(
            {'message': 'Invitation sent successfully'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """Terminate an employee"""
        employee = self.get_object()
        
        # Check if already terminated
        if employee.is_terminated:
            return Response(
                {'error': 'Employee is already terminated'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = TerminateEmployeeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get tenant database
        from accounts.database_utils import get_tenant_database_alias
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        # Validate foreign key references before saving
        # If branch_id exists but the branch doesn't exist in the database, set it to None
        if employee.branch_id:
            branch_exists = Branch.objects.using(tenant_db).filter(id=employee.branch_id).exists()
            if not branch_exists:
                employee.branch_id = None
        
        # If department_id exists but the department doesn't exist in the database, set it to None
        if employee.department_id:
            dept_exists = Department.objects.using(tenant_db).filter(id=employee.department_id).exists()
            if not dept_exists:
                employee.department_id = None
        
        # If manager_id exists but the manager doesn't exist in the database, set it to None
        if employee.manager_id:
            manager_exists = Employee.objects.using(tenant_db).filter(id=employee.manager_id).exists()
            if not manager_exists:
                employee.manager_id = None
        
        # Update employee
        employee.employment_status = 'TERMINATED'
        employee.termination_date = serializer.validated_data['termination_date']
        employee.termination_reason = serializer.validated_data['termination_reason']
        employee.save(using=tenant_db)
        
        # Create audit log
        create_employee_audit_log(
            employee=employee,
            action='TERMINATED',
            performed_by=request.user,
            changes={
                'termination_date': str(employee.termination_date),
                'termination_reason': employee.termination_reason
            },
            notes='Employee terminated',
            request=request,
            tenant_db=tenant_db
        )
        
        # Revoke system access based on configuration
        try:
            from accounts.database_utils import get_tenant_database_alias
            employer = request.user.employer_profile
            tenant_db = get_tenant_database_alias(employer)
            from employees.utils import get_or_create_employee_config
            config = get_or_create_employee_config(employee.employer_id, tenant_db)
            if config.termination_revoke_access_timing == 'IMMEDIATE' and employee.user_id:
                # Update user in main database
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=employee.user_id)
                user.is_active = False
                user.save()
        except Exception as e:
            # Log but don't fail the termination
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error revoking access during termination: {str(e)}")
        
        return Response(
            EmployeeDetailSerializer(employee).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        """Reactivate a terminated employee"""
        employee = self.get_object()
        
        # Check if employee is terminated
        if not employee.is_terminated:
            return Response(
                {'error': 'Employee is not terminated'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if reactivation is allowed
        from accounts.database_utils import get_tenant_database_alias
        from employees.utils import get_or_create_employee_config
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        config = get_or_create_employee_config(employee.employer_id, tenant_db)
        if not config.allow_employee_reactivation:
            return Response(
                {'error': 'Employee reactivation is not allowed by policy'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Reactivate employee
        employee.employment_status = 'ACTIVE'
        employee.termination_date = None
        employee.termination_reason = None
        employee.save()
        
        # Restore system access if user exists
        if employee.user:
            employee.user.is_active = True
            employee.user.save()
        
        # Create audit log
        create_employee_audit_log(
            employee=employee,
            action='UPDATED',
            performed_by=request.user,
            changes={'reactivated': True},
            notes='Employee reactivated',
            request=request,
            tenant_db=tenant_db
        )
        
        return Response(
            EmployeeDetailSerializer(employee).data,
            status=status.HTTP_200_OK
        )
    
    def perform_destroy(self, instance):
        """Delete employee from tenant database ONLY (not from default database)"""
        from accounts.database_utils import get_tenant_database_alias
        
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        employee_id = instance.id
        employee_info = {
            'employee_id': instance.employee_id,
            'name': instance.full_name,
            'email': instance.email
        }
        
        # Create audit log before deletion
        create_employee_audit_log(
            employee=instance,
            action='DELETED',
            performed_by=self.request.user,
            changes=employee_info,
            notes='Employee record deleted from employer database',
            request=self.request,
            tenant_db=tenant_db
        )
        
        # Delete ONLY from tenant database, not from default database
        # Use direct database query to ensure we only delete from tenant DB
        Employee.objects.using(tenant_db).filter(id=employee_id).delete()
    
    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        """Get all documents for an employee"""
        employee = self.get_object()
        documents = employee.documents.all()
        serializer = EmployeeDocumentSerializer(documents, many=True)
        
        # Check for missing required documents
        required_check = check_required_documents(employee)
        
        # Check for expiring documents
        expiring_check = check_expiring_documents(employee)
        
        return Response({
            'documents': serializer.data,
            'required_documents': required_check,
            'expiring_documents': {
                'expiring_soon_count': expiring_check['expiring_count'],
                'expired_count': expiring_check['expired_count']
            }
        })
    
    @action(detail=True, methods=['get'])
    def cross_institutions(self, request, pk=None):
        """Get cross-institution information for an employee"""
        employee = self.get_object()
        
        from accounts.database_utils import get_tenant_database_alias
        from employees.utils import get_or_create_employee_config
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        config = get_or_create_employee_config(employee.employer_id, tenant_db)
        
        summary = get_cross_institution_summary(employee, config)
        
        return Response(summary)
    
    @action(detail=True, methods=['get'])
    def audit_log(self, request, pk=None):
        """Get audit log for an employee"""
        employee = self.get_object()
        logs = employee.audit_logs.all()[:50]  # Last 50 entries
        serializer = EmployeeAuditLogSerializer(logs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def detect_duplicates(self, request):
        """Detect potential duplicate employees"""
        serializer = EmployeeSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        from accounts.database_utils import get_tenant_database_alias
        from employees.utils import get_or_create_employee_config
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        config = get_or_create_employee_config(employer.id, tenant_db)
        
        result = detect_duplicate_employees(
            employer=request.user.employer_profile,
            national_id=serializer.validated_data.get('national_id_number'),
            email=serializer.validated_data.get('email'),
            phone=serializer.validated_data.get('phone_number'),
            config=config
        )
        
        result_serializer = DuplicateDetectionResultSerializer(result)
        return Response(result_serializer.data)
    
    @action(detail=False, methods=['post'], url_path='prefill-existing')
    def prefill_existing(self, request):
        """Verify an existing employee and return prefill data for the creation form"""
        from accounts.models import EmployeeRegistry
        from accounts.database_utils import get_tenant_database_alias
        from employees.utils import (
            get_or_create_employee_config,
            validate_existing_employee_against_new_config
        )
        
        request_serializer = EmployeePrefillRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        
        national_id = request_serializer.validated_data.get('national_id_number')
        email = request_serializer.validated_data.get('email')
        
        query = EmployeeRegistry.objects.select_related('user')
        match = None
        
        if national_id:
            match = query.filter(national_id_number=national_id).first()
        if not match and email:
            match = query.filter(Q(user__email=email) | Q(personal_email=email)).first()
        
        if not match:
            return Response(
                {'error': 'No matching employee found in the system.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        existing_here = Employee.objects.using(tenant_db).filter(
            Q(user_id=match.user_id) | Q(national_id_number=match.national_id_number)
        ).first()
        
        # Get employer configuration to validate existing data
        config = get_or_create_employee_config(request.user.employer_profile.id, tenant_db)
        
        # Validate existing employee data against new employer's requirements
        validation_result = validate_existing_employee_against_new_config(match, config)
        
        prefill_data = {
            'user_id': match.user_id,
            'first_name': match.first_name,
            'last_name': match.last_name,
            'middle_name': match.middle_name,
            'email': match.user.email if match.user_id else (match.personal_email or ''),
            'personal_email': match.personal_email,
            'national_id_number': match.national_id_number,
            'passport_number': match.passport_number,
            'phone_number': match.phone_number,
            'alternative_phone': match.alternative_phone,
            'address': match.address,
            'city': match.city,
            'state_region': match.state_region,
            'country': match.country,
            'nationality': match.nationality,
            'gender': match.gender,
            'date_of_birth': match.date_of_birth,
        }
        
        prefill_serializer = EmployeePrefillSerializer(prefill_data)
        
        response_data = {
            'message': 'Existing employee verified. Prefill the form and choose hire details.',
            'prefill': prefill_serializer.data,
            'link_existing_user': match.user_id,
            'already_employed_here': bool(existing_here),
            'profile_validation': {
                'completion_state': validation_result['completion_state'],
                'requires_update': validation_result['requires_update'],
                'is_blocking': validation_result['is_blocking'],
                'missing_critical_fields': validation_result['missing_critical'],
                'missing_non_critical_fields': validation_result['missing_non_critical'],
            }
        }
        
        # Add warning message if fields are missing
        if validation_result['requires_update']:
            if validation_result['is_blocking']:
                response_data['warning'] = (
                    f"This employee is missing {len(validation_result['missing_critical'])} critical required field(s). "
                    "They will have limited access until their profile is completed."
                )
            else:
                response_data['info'] = (
                    f"This employee is missing {len(validation_result['missing_non_critical'])} optional field(s). "
                    "They will be notified to complete their profile."
                )
        
        return Response(response_data)


class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing employee documents"""
    
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = EmployeeDocumentSerializer
    
    def get_queryset(self):
        """Return documents for employees in employer's organization"""
        return EmployeeDocument.objects.filter(
            employee__employer=self.request.user.employer_profile
        ).select_related('employee', 'uploaded_by')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return EmployeeDocumentUploadSerializer
        return EmployeeDocumentSerializer
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Verify a document"""
        document = self.get_object()
        document.is_verified = True
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.save()
        
        return Response(
            EmployeeDocumentSerializer(document).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """Get documents expiring soon"""
        days_ahead = int(request.query_params.get('days', 30))
        expiry_threshold = timezone.now().date() + timedelta(days=days_ahead)
        
        documents = self.get_queryset().filter(
            has_expiry=True,
            expiry_date__lte=expiry_threshold,
            expiry_date__gte=timezone.now().date()
        )
        
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)


class EmployeeConfigurationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing employee configuration"""
    
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = EmployeeConfigurationSerializer
    http_method_names = ['get', 'post', 'patch', 'put']
    
    def get_queryset(self):
        """Return configuration for the employer from tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        return EmployeeConfiguration.objects.using(tenant_db).filter(
            employer_id=employer.id
        )
    
    def get_object(self):
        """Get or create configuration for employer in tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        config, created = EmployeeConfiguration.objects.using(tenant_db).get_or_create(
            employer_id=employer.id,
            defaults={
                'employee_id_prefix': 'EMP',
                'required_documents': ['RESUME', 'ID_COPY', 'CERTIFICATE'],
                'document_allowed_formats': ['pdf', 'jpg', 'jpeg', 'png', 'docx']
            }
        )
        return config
    
    def list(self, request, *args, **kwargs):
        """Return the single configuration instance"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        """Create or update configuration in tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        # Save to tenant database
        for attr, value in serializer.validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=tenant_db)
        
        return Response(serializer.data)
    
    def update(self, request, *args, **kwargs):
        """Update configuration in tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Save to tenant database
        for attr, value in serializer.validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=tenant_db)
        
        return Response(serializer.data)
    
    def partial_update(self, request, *args, **kwargs):
        """Partially update configuration in tenant database"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    @action(detail=False, methods=['post'])

    def reset_to_defaults(self, request):
        """Reset configuration to default values in tenant database"""
        from accounts.database_utils import get_tenant_database_alias
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        
        config = self.get_object()
        
        # Reset to defaults
        config.employee_id_format = 'SEQUENTIAL'
        config.employee_id_prefix = 'EMP'
        config.employee_id_starting_number = 1
        config.employee_id_padding = 3
        config.duplicate_detection_level = 'MODERATE'
        config.duplicate_action = 'WARN'
        config.required_documents = ['RESUME', 'ID_COPY', 'CERTIFICATE']
        config.document_allowed_formats = ['pdf', 'jpg', 'jpeg', 'png', 'docx']
        config.save(using=tenant_db)
        
        serializer = self.get_serializer(config)
        return Response(serializer.data)


class EmployeeInvitationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing employee invitations"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = EmployeeInvitationSerializer
    
    def get_queryset(self):
        """Return invitations for the employer's employees"""
        user = self.request.user
        
        if hasattr(user, 'employer_profile'):
            # Employer can see all invitations for their employees
            return EmployeeInvitation.objects.filter(
                employee__employer=user.employer_profile
            ).select_related('employee')
        
        # Employee can see their own invitations
        return EmployeeInvitation.objects.filter(
            email=user.email
        ).select_related('employee')
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def accept(self, request):
        """Accept an employee invitation and create user account"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        invitation = serializer.validated_data['token']
        password = serializer.validated_data['password']
        
        # Get tenant database info that was attached in the serializer
        tenant_db = getattr(invitation, '_tenant_db', None)
        employer_profile = getattr(invitation, '_employer_profile', None)
        
        if not tenant_db or not employer_profile:
            return Response(
                {'error': 'Invalid invitation state'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Query the employee from the correct tenant database using the employee relation from invitation
        # Note: invitation.employee might not be accessible due to cross-database ForeignKey
        # We need to re-fetch the invitation from the tenant database to get the employee
        try:
            # Re-fetch the invitation using token to access the employee relationship properly
            invitation_refresh = EmployeeInvitation.objects.using(tenant_db).select_related('employee').get(token=invitation.token)
            employee = invitation_refresh.employee
        except EmployeeInvitation.DoesNotExist:
            return Response(
                {'error': 'Invitation not found in tenant database'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Employee.DoesNotExist:
            return Response(
                {'error': 'Employee record not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user already exists with this email
        if employee.user_id:
            return Response(
                {'error': 'This employee already has a user account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if a user account exists with this email in main database
        try:
            user = User.objects.get(email=invitation_refresh.email)
            user.is_employee = True
            user.is_active = True
            user.profile_completed = False
            user.save(update_fields=['is_employee', 'is_active', 'profile_completed'])
            # Link existing user to employee
            employee.user_id = user.id
            employee.save(using=tenant_db)
        except User.DoesNotExist:
            # Create new user account in main database
            user = User.objects.create_user(
                email=invitation_refresh.email,
                password=password,
                is_employee=True,
                is_active=True
            )
            
            # Link user to employee in tenant database
            employee.user_id = user.id
            employee.save(using=tenant_db)
        
        # Update invitation status in tenant database
        invitation_refresh.status = 'ACCEPTED'
        invitation_refresh.accepted_at = timezone.now()
        invitation_refresh.save(using=tenant_db)
        
        # Update employee flags in tenant database
        employee.invitation_accepted = True
        employee.invitation_accepted_at = timezone.now()
        employee.save(using=tenant_db)
        
        # Check and update profile completion state
        from employees.utils import (
            check_missing_fields_against_config,
            get_or_create_employee_config,
            send_profile_completion_notification
        )
        
        config = get_or_create_employee_config(employee.employer_id, tenant_db)
        validation_result = check_missing_fields_against_config(employee, config)
        
        # Update profile completion fields
        employee.profile_completion_state = validation_result['completion_state']
        employee.profile_completion_required = validation_result['requires_update']
        employee.missing_required_fields = validation_result['missing_critical']
        employee.missing_optional_fields = validation_result['missing_non_critical']
        
        if validation_result['completion_state'] == 'COMPLETE':
            employee.profile_completed = True
            employee.profile_completed_at = timezone.now()
        
        employee.save(using=tenant_db, update_fields=[
            'profile_completion_state', 'profile_completion_required',
            'missing_required_fields', 'missing_optional_fields',
            'profile_completed', 'profile_completed_at'
        ])
        
        # Send profile completion notification if needed
        if validation_result['requires_update']:
            send_profile_completion_notification(
                employee,
                validation_result,
                employer_profile,
                tenant_db
            )
        
        # Create audit log in tenant database
        create_employee_audit_log(
            employee=employee,
            action='LINKED',
            performed_by=user,
            notes='Employee accepted invitation and linked user account',
            request=request,
            tenant_db=tenant_db
        )
        
        # Serialize the full form fields for profile completion
        from .serializers import EmployeeProfileCompletionSerializer
        employee_data = EmployeeProfileCompletionSerializer(instance=employee).data

        return Response({
            'message': 'Invitation accepted successfully.',
            'employee_data': employee_data,
            'token': invitation_refresh.token,
            'user_id': user.id,
            'email': user.email,
            'profile_completion': {
                'required': validation_result['requires_update'],
                'state': validation_result['completion_state'],
                'is_blocking': validation_result['is_blocking'],
                'missing_critical_fields': validation_result['missing_critical'],
                'missing_non_critical_fields': validation_result['missing_non_critical'],
            }
        }, status=status.HTTP_200_OK)
        

class EmployeeProfileViewSet(viewsets.GenericViewSet):
    """ViewSet for employees to manage their own profile"""
    
    permission_classes = [IsAuthenticated, IsEmployee]
    
    def get_queryset(self):
        """Get the employee record for the authenticated user"""
        from accounts.database_utils import get_tenant_database_alias
        
        user = self.request.user
        if not user.is_employee or not hasattr(user, 'employee_profile') or not user.employee_profile:
            return Employee.objects.none()
        
        # Get tenant database
        try:
            employee = user.employee_profile
            from accounts.models import EmployerProfile
            employer = EmployerProfile.objects.get(id=employee.employer_id)
            tenant_db = get_tenant_database_alias(employer)
            
            return Employee.objects.using(tenant_db).filter(user_id=user.id)
        except:
            return Employee.objects.none()
    
    @action(detail=False, methods=['get'], url_path='me')
    def get_own_profile(self, request):
        """Get authenticated employee's own profile"""
        from accounts.database_utils import get_tenant_database_alias
        from .serializers import EmployeeSelfProfileSerializer
        
        user = request.user
        
        # Check if user is an employee
        if not user.is_employee:
            return Response({
                'error': 'Only employees can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get employee record from cache or database
        try:
            # Try to get from user relationship first
            if hasattr(user, 'employee_profile') and user.employee_profile:
                employee = user.employee_profile
            else:
                # Fallback: search all tenant databases
                from accounts.models import EmployerProfile
                
                # Get all employers
                employers = EmployerProfile.objects.filter(user__is_active=True).select_related('user')
                employee = None
                
                for employer in employers:
                    tenant_db = get_tenant_database_alias(employer)
                    try:
                        employee = Employee.objects.using(tenant_db).get(user_id=user.id)
                        break
                    except Employee.DoesNotExist:
                        continue
                
                if not employee:
                    return Response({
                        'error': 'Employee record not found'
                    }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = EmployeeSelfProfileSerializer(employee)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'Failed to retrieve employee profile',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['put', 'patch'], url_path='complete-profile')
    def complete_profile(self, request):
        """Employee completes their own profile after accepting invitation"""
        from accounts.database_utils import get_tenant_database_alias
        from .serializers import EmployeeProfileCompletionSerializer
        
        user = request.user
        
        # Check if user is an employee
        if not user.is_employee:
            return Response({
                'error': 'Only employees can complete their profile'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # Get employee record
            if hasattr(user, 'employee_profile') and user.employee_profile:
                employee = user.employee_profile
                from accounts.models import EmployerProfile
                employer = EmployerProfile.objects.get(id=employee.employer_id)
                tenant_db = get_tenant_database_alias(employer)
            else:
                # Fallback: search all tenant databases
                from accounts.models import EmployerProfile
                employers = EmployerProfile.objects.filter(user__is_active=True).select_related('user')
                employee = None
                tenant_db = None
                
                for employer in employers:
                    tenant_db = get_tenant_database_alias(employer)
                    try:
                        employee = Employee.objects.using(tenant_db).get(user_id=user.id)
                        break
                    except Employee.DoesNotExist:
                        continue
                
                if not employee:
                    return Response({
                        'error': 'Employee record not found'
                    }, status=status.HTTP_404_NOT_FOUND)
            
            # Use partial update for PATCH, full update for PUT
            partial = request.method == 'PATCH'
            serializer = EmployeeProfileCompletionSerializer(
                employee, 
                data=request.data, 
                partial=partial
            )
            
            if serializer.is_valid():
                # Save to tenant database
                updated_employee = serializer.save()
                
                # Prepare update fields
                update_fields = {field: getattr(updated_employee, field) 
                                for field in serializer.validated_data.keys()}
                
                # Change employment status from PENDING to ACTIVE when profile is completed
                if updated_employee.employment_status == 'PENDING':
                    update_fields['employment_status'] = 'ACTIVE'
                    updated_employee.employment_status = 'ACTIVE'
                
                # Update in tenant database
                Employee.objects.using(tenant_db).filter(id=updated_employee.id).update(**update_fields)
                
                # Add profile_completed fields
                if not partial or ('profile_completed' in dir(updated_employee) and updated_employee.profile_completed):
                    Employee.objects.using(tenant_db).filter(id=updated_employee.id).update(
                        profile_completed=updated_employee.profile_completed,
                        profile_completed_at=updated_employee.profile_completed_at
                    )
                
                # Create audit log
                create_employee_audit_log(
                    employee=updated_employee,
                    action='PROFILE_COMPLETED' if updated_employee.profile_completed else 'PROFILE_UPDATED',
                    performed_by=user,
                    notes='Employee completed/updated their profile',
                    request=request,
                    tenant_db=tenant_db
                )
                
                # Refresh and return
                updated_employee = Employee.objects.using(tenant_db).get(id=updated_employee.id)
                from .serializers import EmployeeSelfProfileSerializer
                return Response({
                    'message': 'Profile completed successfully. You can now log in.',
                    'redirect_to': 'login',
                    'profile': EmployeeSelfProfileSerializer(updated_employee).data
                }, status=status.HTTP_200_OK)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({
                'error': 'Failed to update profile',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], url_path='complete')
    def complete_profile(self, request):
        """Handle employee profile completion"""
        from .serializers import EmployeeProfileCompletionSerializer
        
        serializer = EmployeeProfileCompletionSerializer(data=request.data)
        if serializer.is_valid():
            # Perform profile completion logic here
            return Response({
                'message': 'Profile completed successfully.'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
