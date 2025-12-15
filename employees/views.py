"""Views for employee management by employers"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
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
    AcceptInvitationSerializer
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
        """Return departments for the employer's organization"""
        return Department.objects.filter(
            employer=self.request.user.employer_profile
        ).select_related('parent_department')
    
    def perform_create(self, serializer):
        """Set employer when creating department"""
        serializer.save(employer=self.request.user.employer_profile)


class BranchViewSet(viewsets.ModelViewSet):
    """ViewSet for managing branches"""
    
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = BranchSerializer
    
    def get_queryset(self):
        """Return branches for the employer's organization"""
        return Branch.objects.filter(
            employer=self.request.user.employer_profile
        )
    
    def perform_create(self, serializer):
        """Set employer when creating branch"""
        serializer.save(employer=self.request.user.employer_profile)


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
        """Return employees for the employer's organization"""
        queryset = Employee.objects.filter(
            employer=self.request.user.employer_profile
        ).select_related(
            'department', 'branch', 'manager', 'employer', 'user'
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
        
        employee = serializer.save()
        
        # Send invitation if requested
        if getattr(employee, '_send_invitation', False):
            self._send_invitation(employee)
        
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
    
    def _send_invitation(self, employee):
        """Helper method to send employee invitation"""
        # Get configuration
        try:
            config = EmployeeConfiguration.objects.get(employer=employee.employer)
        except EmployeeConfiguration.DoesNotExist:
            config = None
        
        # Create invitation
        invitation = EmployeeInvitation.objects.create(
            employee=employee,
            token=generate_employee_invitation_token(),
            email=employee.email or employee.personal_email,
            expires_at=get_invitation_expiry_date(config)
        )
        
        # Update employee flags
        employee.invitation_sent = True
        employee.invitation_sent_at = timezone.now()
        employee.save(update_fields=['invitation_sent', 'invitation_sent_at'])
        
        # Send email
        if not config or config.send_invitation_email:
            send_employee_invitation_email(employee, invitation)
        
        # Create audit log
        create_employee_audit_log(
            employee=employee,
            action='INVITED',
            performed_by=self.request.user,
            notes=f'Invitation sent to {invitation.email}',
            request=self.request
        )
    
    @action(detail=True, methods=['post'])
    def send_invitation(self, request, pk=None):
        """Send or resend invitation to employee"""
        employee = self.get_object()
        
        # Check if employee already has a user account
        if employee.user:
            return Response(
                {'error': 'Employee already has a user account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if there's a pending invitation
        pending_invitation = employee.invitations.filter(status='PENDING').first()
        if pending_invitation and pending_invitation.is_valid():
            return Response(
                {
                    'error': 'A valid invitation is already pending',
                    'expires_at': pending_invitation.expires_at
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Send new invitation
        self._send_invitation(employee)
        
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
        
        # Update employee
        employee.employment_status = 'TERMINATED'
        employee.termination_date = serializer.validated_data['termination_date']
        employee.termination_reason = serializer.validated_data['termination_reason']
        employee.save()
        
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
            request=request
        )
        
        # Revoke system access based on configuration
        try:
            config = EmployeeConfiguration.objects.get(employer=employee.employer)
            if config.termination_revoke_access_timing == 'IMMEDIATE' and employee.user:
                employee.user.is_active = False
                employee.user.save()
        except EmployeeConfiguration.DoesNotExist:
            pass
        
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
        try:
            config = EmployeeConfiguration.objects.get(employer=employee.employer)
            if not config.allow_employee_reactivation:
                return Response(
                    {'error': 'Employee reactivation is not allowed by policy'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except EmployeeConfiguration.DoesNotExist:
            pass
        
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
            request=request
        )
        
        return Response(
            EmployeeDetailSerializer(employee).data,
            status=status.HTTP_200_OK
        )
    
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
        
        try:
            config = EmployeeConfiguration.objects.get(employer=employee.employer)
        except EmployeeConfiguration.DoesNotExist:
            config = None
        
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
        
        try:
            config = EmployeeConfiguration.objects.get(employer=request.user.employer_profile)
        except EmployeeConfiguration.DoesNotExist:
            config = None
        
        result = detect_duplicate_employees(
            employer=request.user.employer_profile,
            national_id=serializer.validated_data.get('national_id_number'),
            email=serializer.validated_data.get('email'),
            phone=serializer.validated_data.get('phone_number'),
            config=config
        )
        
        result_serializer = DuplicateDetectionResultSerializer(result)
        return Response(result_serializer.data)


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
        """Return configuration for the employer"""
        return EmployeeConfiguration.objects.filter(
            employer=self.request.user.employer_profile
        )
    
    def get_object(self):
        """Get or create configuration for employer"""
        config, created = EmployeeConfiguration.objects.get_or_create(
            employer=self.request.user.employer_profile,
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
        """Create or update configuration"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def reset_to_defaults(self, request):
        """Reset configuration to default values"""
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
        config.save()
        
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
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        invitation = serializer.validated_data['token']
        password = serializer.validated_data['password']
        
        # Check if user already exists with this email
        employee = invitation.employee
        if employee.user:
            return Response(
                {'error': 'This employee already has a user account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if a user account exists with this email
        try:
            user = User.objects.get(email=invitation.email)
            # Link existing user to employee
            employee.user = user
            employee.save()
        except User.DoesNotExist:
            # Create new user account
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            user = User.objects.create_user(
                email=invitation.email,
                password=password,
                is_employee=True,
                is_active=True
            )
            
            # Link user to employee
            employee.user = user
            employee.save()
        
        # Update invitation status
        invitation.status = 'ACCEPTED'
        invitation.accepted_at = timezone.now()
        invitation.save()
        
        # Update employee flags
        employee.invitation_accepted = True
        employee.invitation_accepted_at = timezone.now()
        employee.save()
        
        # Create audit log
        create_employee_audit_log(
            employee=employee,
            action='LINKED',
            performed_by=user,
            notes='Employee accepted invitation and linked user account',
            request=request
        )
        
        return Response({
            'message': 'Invitation accepted successfully',
            'employee': EmployeeDetailSerializer(employee).data
        }, status=status.HTTP_200_OK)
