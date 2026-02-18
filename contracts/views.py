from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from .models import (
    Contract, ContractConfiguration, ContractTemplate, ContractTemplateVersion, SalaryScale,
    CalculationScale, ScaleRange, ContractDocument, ContractSignature
)
from .serializers import (
    ContractSerializer,
    ContractConfigurationSerializer,
    SalaryScaleSerializer,
    CalculationScaleSerializer,
    ScaleRangeSerializer,
    ContractTemplateSerializer,
    ContractTemplateVersionSerializer,
)
from .notifications import (
    notify_contract_created,
    notify_sent_for_approval,
    notify_signature_captured,
    notify_terminated,
    notify_expired,
    notify_renewed,
)
from .payroll_defaults import ensure_cameroon_default_scales
from timeoff.defaults import merge_time_off_defaults
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounts.middleware import set_current_tenant_db
from accounts.models import EmployerProfile, User
from accounts.permissions import EmployerAccessPermission, EmployerOrEmployeeAccessPermission
from accounts.rbac import get_active_employer, is_delegate_user, get_delegate_scope, apply_scope_filter
from contracts.management.commands.seed_contract_template import TYPE_BODIES, BASE_BODY
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser


class ContractViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows contracts to be viewed or edited.
    Restricted to the current user's tenant.
    """
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]
    permission_map = {
        "list": ["contracts.contract.view", "contracts.manage"],
        "retrieve": ["contracts.contract.view", "contracts.manage"],
        "create": ["contracts.contract.create", "contracts.manage"],
        "update": ["contracts.contract.update", "contracts.manage"],
        "partial_update": ["contracts.contract.update", "contracts.manage"],
        "destroy": ["contracts.contract.delete", "contracts.manage"],
        "default_template": [
            "contracts.template.view",
            "contracts.template.update",
            "contracts.manage",
        ],
        "activate": ["contracts.contract.activate", "contracts.manage"],
        "approve": ["contracts.contract.approve", "contracts.manage"],
        "send_for_approval": ["contracts.contract.send_for_approval", "contracts.manage"],
        "send_for_signature_alias": ["contracts.contract.send_for_signature", "contracts.manage"],
        "generate_document": ["contracts.contract.generate_document", "contracts.manage"],
        "sign_contract": ["contracts.contract.sign", "contracts.manage"],
        "renew": ["contracts.contract.renew", "contracts.manage"],
        "terminate": ["contracts.contract.terminate", "contracts.manage"],
        "expire": ["contracts.contract.expire", "contracts.manage"],
        "*": ["contracts.manage"],
    }

    def _set_tenant_alias(self, alias):
        """Set tenant context when we already know the DB alias."""
        try:
            set_current_tenant_db(alias)
        except Exception:
            pass

    def _set_tenant_context(self, contract):
        """
        Ensure subsequent writes route to the contract's tenant DB.
        """
        db_alias = contract._state.db or 'default'
        try:
            set_current_tenant_db(db_alias)
        except Exception:
            # If middleware setter fails, we proceed; downstream saves may fall back to default
            pass
        return db_alias
    def _is_employer_user(self, user, contract):
        """Check if the user is the employer that owns the contract"""
        if user.is_admin or user.is_superuser:
            return True
        if hasattr(user, 'employer_profile') and user.employer_profile.id == contract.employer_id:
            return True
        return is_delegate_user(user, contract.employer_id)

    def _get_role(self, user, contract):
        """Determine if user is employer or employee for this contract"""
        if contract.employee and contract.employee.user_id == user.id:
            return 'EMPLOYEE'
        if self._is_employer_user(user, contract):
            return 'EMPLOYER'
        return None

    def _get_user_signature_path(self, user_id):
        """Fetch signature path from default DB for a user id (None if missing)."""
        if not user_id:
            return None
        try:
            user_obj = User.objects.using('default').get(id=user_id)
            if user_obj.signature and user_obj.signature.name:
                return user_obj.signature.path
        except Exception:
            return None
        return None

    def get_queryset(self):
        """
        This view should return a list of all the contracts
        for the currently authenticated user's employer from tenant database.
        Also allows employees to view their own contracts.
        """
        user = self.request.user
        
        # 1. Employer Access
        employer = None
        if user.is_authenticated and getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            try:
                resolved = get_active_employer(self.request, require_context=False)
            except PermissionDenied:
                resolved = None
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved

        if employer:
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(employer)
            self._set_tenant_alias(tenant_db)
            qs = Contract.objects.using(tenant_db).filter(employer_id=employer.id)
            if is_delegate_user(user, employer.id):
                scope = get_delegate_scope(user, employer.id)
                qs = apply_scope_filter(
                    qs,
                    scope,
                    branch_field="employee__branch_id",
                    department_field="employee__department_id",
                    self_field="employee_id",
                )
            return qs
            
        # 2. Employee Access
        if user.is_authenticated and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or 'default'
            self._set_tenant_alias(tenant_db)
            return Contract.objects.using(tenant_db).filter(employee=employee)
            
        return Contract.objects.none()

    def perform_destroy(self, instance):
        """Delete contract from tenant database"""
        employer = get_active_employer(self.request, require_context=False)
        if employer and (
            getattr(self.request.user, 'employer_profile', None)
            or self.request.user.is_admin
            or self.request.user.is_superuser
            or is_delegate_user(self.request.user, employer.id)
        ):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(employer)
            instance.delete(using=tenant_db)
        else:
            instance.delete()

    def perform_create(self, serializer):
        contract = serializer.save()
        try:
            notify_contract_created(contract)
        except Exception:
            pass

    @action(detail=False, methods=['get', 'patch'], url_path='template/default')
    def default_template(self, request):
        """Get or update the default template body for the employer by contract_type (no uploads)."""
        user = request.user
        employer = get_active_employer(request, require_context=False)
        if not employer or not (
            getattr(user, 'employer_profile', None)
            or user.is_admin
            or user.is_superuser
            or is_delegate_user(user, employer.id)
        ):
            return Response({'error': 'Only employers can manage templates.'}, status=status.HTTP_403_FORBIDDEN)

        contract_type = request.query_params.get('contract_type') or request.data.get('contract_type')
        if not contract_type:
            return Response({'error': 'contract_type is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(employer)

        template = (
            ContractTemplate.objects.using(tenant_db)
            .filter(employer_id=employer.id, contract_type=contract_type, is_default=True)
            .order_by('-created_at')
            .first()
        )
        if not template and request.method.lower() == 'get':
            fallback = TYPE_BODIES.get(contract_type, BASE_BODY)
            return Response({
                'id': None,
                'contract_type': contract_type,
                'body': fallback,
                'updated_at': None,
                'template_missing': True,
            })

        # PATCH
        body = request.data.get('body')
        if not body:
            return Response({'error': 'body is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not template:
            template = ContractTemplate.objects.using(tenant_db).create(
                employer_id=employer.id,
                contract_type=contract_type,
                name=f"Default {contract_type.title().replace('_', ' ')} Template",
                body_override=body,
                is_default=True,
            )
        else:
            template.body_override = body
            template.save(using=tenant_db)
        return Response({
            'id': template.id,
            'contract_type': contract_type,
            'body': template.body_override,
            'updated_at': template.updated_at,
        })

    @action(detail=True, methods=['post'])
    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        """Activate a signed contract"""
        contract = self.get_object()
        self._set_tenant_context(contract)
        if not (request.user.is_staff or self._is_employer_user(request.user, contract)):
            return Response({'error': 'Only staff or the employer can activate contracts.'}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            contract.activate(request.user)
            return Response(self.get_serializer(contract).data)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """Approve a contract. Requires employer and employee signatures on file in default DB."""
        contract = self.get_object()
        self._set_tenant_context(contract)

        role = self._get_role(request.user, contract)
        if not (request.user.is_staff or role):
            return Response({'error': 'Only the employer or employee for this contract can approve.'}, status=status.HTTP_403_FORBIDDEN)

        # Verify signatures exist for both parties in default DB
        employee_sig = self._get_user_signature_path(getattr(contract.employee, 'user_id', None))
        employer_profile = EmployerProfile.objects.using('default').filter(id=contract.employer_id).first()
        employer_sig = self._get_user_signature_path(getattr(employer_profile, 'user_id', None))
        missing = []
        if not employee_sig:
            missing.append('employee signature')
        if not employer_sig:
            missing.append('employer signature')
        if missing:
            return Response({'error': f"Missing {' and '.join(missing)}. Please upload signatures before approval."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            contract.approve(request.user, role=role)
            return Response(self.get_serializer(contract).data)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='send-for-approval')
    def send_for_approval(self, request, pk=None):
        """Move contract to pending approval (new flow)"""
        contract = self.get_object()
        self._set_tenant_context(contract)
        if not (request.user.is_staff or self._is_employer_user(request.user, contract)):
            return Response({'error': 'Only staff or the employer can send contracts for approval.'}, status=status.HTTP_403_FORBIDDEN)

        if not contract.get_effective_config('approval_enabled', False):
            return Response({'error': 'Approval workflow is disabled by configuration.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            contract.send_for_approval(request.user)
            try:
                notify_sent_for_approval(contract)
            except Exception:
                pass
            return Response(self.get_serializer(contract).data)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='send-for-signature')
    def send_for_signature_alias(self, request, pk=None):
        """Send contract for signature (approval/signature workflow)."""
        contract = self.get_object()
        self._set_tenant_context(contract)
        if not (request.user.is_staff or self._is_employer_user(request.user, contract)):
            return Response({'error': 'Only staff or the employer can send contracts for signature.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            contract.send_for_signature(request.user)
            return Response(self.get_serializer(contract).data)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='generate-document')
    def generate_document(self, request, pk=None):
        """Generate a PDF contract document"""
        contract = self.get_object()
        
        # Optional: Allow selecting a specific template via query param or body
        # template_id = request.data.get('template_id')
        
        try:
            from .services import generate_contract_pdf
            document = generate_contract_pdf(contract)
            
            # Serialize the document object (simple representation)
            file_url = None
            if document.file:
                try:
                    file_url = request.build_absolute_uri(document.file.url)
                except Exception:
                    file_url = document.file.url
            return Response({
                'id': document.id,
                'name': document.name,
                'file_url': file_url,
                'created_at': document.created_at
            }, status=status.HTTP_201_CREATED)
            
        except ImportError as e:
            return Response({'error': 'PDF generation not available: ' + str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f"Generation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='sign')
    def sign_contract(self, request, pk=None):
        """
        Sign the contract.
        Employer signing uses the signature already saved on the user's profile.
        'document_hash' is optional.
        """
        contract = self.get_object()
        self._set_tenant_context(contract)
        user = request.user

        role = None
        if contract.employee and contract.employee.user_id == user.id:
            role = 'EMPLOYEE'
        elif hasattr(user, 'employer_profile') and user.employer_profile.id == contract.employer_id:
            role = 'EMPLOYER'

        if not role:
            return Response({'error': 'You are not authorized to sign this contract.'}, status=status.HTTP_403_FORBIDDEN)

        signature_on_file = self._get_user_signature_path(user.id)
        if role == 'EMPLOYER':
            if not signature_on_file:
                return Response(
                    {'error': 'Employer signature on file is required. Please upload your signature first.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            signature_text = 'Employer signature on file'
        else:
            signature_text = request.data.get('signature_text')
            if not signature_text:
                if signature_on_file:
                    signature_text = 'Employee signature on file'
                else:
                    return Response(
                        {'error': 'Signature text is required.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')

        db_alias = contract._state.db or 'default'
        signed_document = None
        signed_document_id = request.data.get('signed_document_id')
        if signed_document_id:
            try:
                signed_document = ContractDocument.objects.using(db_alias).get(
                    id=signed_document_id,
                    contract=contract
                )
            except ContractDocument.DoesNotExist:
                return Response(
                    {'error': 'signed_document_id must belong to this contract.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        document_hash_raw = request.data.get('document_hash')
        document_hash = f"{document_hash_raw}".strip() if document_hash_raw is not None else ''

        signature = ContractSignature.objects.using(db_alias).create(
            contract=contract,
            signer_user_id=user.id,
            signer_name=f"{user.first_name} {user.last_name}".strip() or user.email,
            role=role,
            signature_text=signature_text,
            ip_address=ip,
            user_agent=user_agent,
            signature_method=request.data.get('signature_method'),
            signature_audit_id=request.data.get('signature_audit_id'),
            signed_document=signed_document,
            document_hash=document_hash
        )

        try:
            notify_signature_captured(contract, role=role)
        except Exception:
            pass

        signatures = ContractSignature.objects.using(db_alias).filter(contract=contract)
        has_employee_sign = signatures.filter(role='EMPLOYEE').exists()
        has_employer_sign = signatures.filter(role='EMPLOYER').exists()

        if has_employee_sign and has_employer_sign and contract.status != 'SIGNED':
            contract.mark_signed(user)

        return Response({
            'status': 'signed',
            'role': role,
            'signed_at': signature.signed_at
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='renew')
    def renew(self, request, pk=None):
        """
        Renew a contract by either extending it or creating a new one.
        Expected data:
        - extend (bool): If True, extends the existing contract.
        - create_new (bool): If True, creates a new contract linked to this one.
        - new_end_date (date): Required for renewal/extension.
        """
        contract = self.get_object()
        self._set_tenant_context(contract)
        data = request.data
        
        extend = data.get('extend', False)
        create_new = data.get('create_new', False)
        new_end_date = data.get('new_end_date')
        
        if not new_end_date:
            return Response({'error': 'new_end_date is required'}, status=status.HTTP_400_BAD_REQUEST)

        if not contract.get_effective_config('auto_renew_option_available', False):
            return Response({'error': 'Renewals are disabled by configuration.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if extend and create_new:
             return Response({'error': 'Cannot extend and create new at the same time'}, status=status.HTTP_400_BAD_REQUEST)
             
        if extend:
            # 1. Extend Existing Contract
            # Create amendment for audit
            from .models import ContractAmendment
            
            # Determine DB alias
            # We are in a ViewSet method on a retrieved object, so contract._state.db should be correct
            # But let's be explicit if needed, though 'contract' is already from tenant DB.
            
            old_end_date = str(contract.end_date)
            contract.end_date = new_end_date
            contract.save()
            
            # Find next amendment number
            from django.db.models import Max
            max_num = contract.amendments.aggregate(Max('amendment_number'))['amendment_number__max']
            next_num = (max_num or 0) + 1
            
            contract.log_action(
                user=request.user,
                action='AMENDED',
                metadata={
                    'amendment_number': next_num,
                    'changed_fields': {'end_date': {'old': old_end_date, 'new': new_end_date}}
                }
            )
            
            ContractAmendment.objects.using(contract._state.db).create(
                contract=contract,
                amendment_number=next_num,
                effective_date=timezone.now().date(),
                changed_fields={'end_date': {'old': old_end_date, 'new': new_end_date}},
                created_by_id=request.user.id
            )

            try:
                notify_renewed(contract, mode='extend')
            except Exception:
                pass
            
            return Response({'status': 'extended', 'new_end_date': new_end_date})
            
        elif create_new:
            # 2. Create New Contract
            from datetime import timedelta
            new_contract = Contract(
                employer_id=contract.employer_id,
                employee=contract.employee,
                branch=contract.branch,
                department=contract.department,
                contract_type=contract.contract_type,
                start_date=contract.end_date,  # will be adjusted below if needed
                end_date=new_end_date,
                salary_scale=contract.salary_scale,
                base_salary=contract.base_salary,
                currency=contract.currency,
                pay_frequency=contract.pay_frequency,
                status='DRAFT',
                created_by=request.user.id,
                previous_contract=contract
            )
            
            # Allow overriding start_date
            if 'start_date' in data:
                new_contract.start_date = data['start_date']
            elif contract.end_date:
                try:
                    new_contract.start_date = contract.end_date + timedelta(days=1)
                except Exception:
                    new_contract.start_date = contract.end_date

            # Generate ID using configuration sequence
            db_alias = contract._state.db or 'default'
            new_contract._state.db = db_alias
            global_config, type_config = Contract.get_config_for(
                employer_id=contract.employer_id,
                contract_type=contract.contract_type,
                db_alias=db_alias
            )
            config = type_config or global_config
            if config:
                new_contract.contract_id = new_contract.generate_contract_id(config)
            else:
                import uuid
                new_contract.contract_id = f"CNT-REN-{uuid.uuid4().hex[:8].upper()}"
            
            new_contract.save(using=contract._state.db)

            try:
                notify_renewed(new_contract, mode='create_new')
            except Exception:
                pass
            
            return Response({
                'status': 'renewed',
                'new_contract_id': new_contract.id,
                'contract_display_id': new_contract.contract_id
            }, status=status.HTTP_201_CREATED)
            
        return Response({'error': 'Specify extend=true or create_new=true'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='terminate')
    def terminate(self, request, pk=None):
        """
        Terminate the contract.
        Expected data:
        - termination_date (date): Required.
        - reason (str): Optional but recommended.
        - notice_served (bool): Default False.
        """
        contract = self.get_object()
        self._set_tenant_context(contract)
        data = request.data
        
        termination_date = data.get('termination_date')
        if not termination_date:
            return Response({'error': 'termination_date is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from django.utils.dateparse import parse_date
            parsed = parse_date(str(termination_date))
            if parsed:
                termination_date = parsed
        except Exception:
            pass
            
        reason = data.get('reason')
        notice_served = data.get('notice_served', False)
        
        # Determine DB alias
        db_alias = contract._state.db or 'default'
        
        # Validation: termination date should probably be >= start_date
        # But we'll trust the input for now or could add checks.
        
        # Validate against employee termination configuration (reason/date)
        config = None
        employer_profile = None
        try:
            from employees.utils import get_or_create_employee_config, create_termination_approval_request
            from employees.serializers import TerminateEmployeeSerializer, TerminationApprovalSerializer
            from employees.utils import notify_employer_users, notify_employee_user
            employer_profile = EmployerProfile.objects.using('default').filter(id=contract.employer_id).first()
            config = get_or_create_employee_config(contract.employer_id, db_alias)
            term_serializer = TerminateEmployeeSerializer(
                data={
                    'termination_date': termination_date,
                    'termination_reason': reason,
                },
                context={'config': config},
            )
            term_serializer.is_valid(raise_exception=True)
            termination_date = term_serializer.validated_data['termination_date']
            reason = term_serializer.validated_data.get('termination_reason')
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if config and config.termination_approval_required:
            # Route through employee termination approval workflow
            approval = create_termination_approval_request(
                employee=contract.employee,
                requested_by=request.user,
                termination_date=termination_date,
                termination_reason=reason,
                config=config,
                tenant_db=db_alias,
            )

            contract.log_action(
                user=request.user,
                action='TERMINATION_REQUESTED',
                metadata={
                    'reason': reason,
                    'termination_date': str(termination_date),
                    'approval_id': str(approval.id) if approval else None,
                },
            )

            try:
                notify_employer_users(
                    employer_profile,
                    title="Termination requested",
                    body=f"Termination requested for {contract.employee.full_name}.",
                    type="ACTION",
                    data={
                        "event": "employees.termination_requested",
                        "employee_id": str(contract.employee.id),
                        "employee_number": contract.employee.employee_id,
                        "termination_date": str(termination_date),
                        "approval_id": str(approval.id) if approval else None,
                        "contract_id": str(contract.id),
                        "contract_display_id": contract.contract_id,
                        "path": f"/employer/employees/{contract.employee.id}",
                    },
                )
            except Exception:
                pass

            try:
                notify_employee_user(
                    contract.employee,
                    title="Termination requested",
                    body="A termination request has been initiated for your employment.",
                    type="ALERT",
                    data={
                        "event": "employees.termination_requested",
                        "termination_date": str(termination_date),
                        "contract_id": str(contract.id),
                        "contract_display_id": contract.contract_id,
                        "path": "/employee/profile",
                    },
                    employer_profile=employer_profile,
                )
            except Exception:
                pass

            approval_data = None
            try:
                approval_data = TerminationApprovalSerializer(approval).data if approval else None
            except Exception:
                approval_data = None

            return Response(
                {
                    'message': 'Termination request submitted for approval',
                    'approval_required': True,
                    'approval': approval_data,
                },
                status=status.HTTP_201_CREATED
            )

        # Update Contract (no approval required)
        contract.status = 'TERMINATED'
        contract.termination_date = termination_date
        contract.termination_reason = reason
        contract.notice_served = notice_served
        contract.final_pay_flag = True
        
        contract.save()
        
        contract.log_action(
            user=request.user,
            action='TERMINATED',
            metadata={'reason': reason, 'termination_date': str(termination_date)}
        )

        try:
            notify_terminated(contract)
        except Exception:
            pass
        try:
            contract._sync_employee_after_status_change('terminated', user=request.user)
        except Exception:
            pass
        
        return Response({
            'status': 'terminated',
            'termination_date': termination_date,
            'final_pay_flag': True
        })

    @action(detail=True, methods=['post'], url_path='expire')
    def expire(self, request, pk=None):
        """Expire an active contract"""
        contract = self.get_object()
        self._set_tenant_context(contract)
        if not (request.user.is_staff or self._is_employer_user(request.user, contract)):
            return Response({'error': 'Only staff or the employer can expire contracts.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            contract.expire(request.user)
            try:
                notify_expired(contract)
            except Exception:
                pass
            return Response(self.get_serializer(contract).data)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ContractAmendmentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for contract amendments.
    Nested route: /api/contracts/{contract_pk}/amendments/
    """
    from .serializers import ContractAmendmentSerializer
    serializer_class = ContractAmendmentSerializer
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["contracts.contract.view", "contracts.manage"],
        "retrieve": ["contracts.contract.view", "contracts.manage"],
        "create": ["contracts.contract.update", "contracts.manage"],
        "update": ["contracts.contract.update", "contracts.manage"],
        "partial_update": ["contracts.contract.update", "contracts.manage"],
        "destroy": ["contracts.contract.update", "contracts.manage"],
        "*": ["contracts.manage"],
    }
    
    def get_queryset(self):
        user = self.request.user
        contract_pk = self.kwargs.get('contract_pk')
        
        if not contract_pk:
            from .models import ContractAmendment
            return ContractAmendment.objects.none()
            
        # Get Tenant DB
        employer = None
        if user.is_authenticated and getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved

        if employer:
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(employer)
            
            from .models import ContractAmendment
            qs = ContractAmendment.objects.using(tenant_db).filter(
                contract__employer_id=employer.id,
                contract_id=contract_pk
            )
            return qs
        return ContractAmendment.objects.none()
        
    def perform_create(self, serializer):
        user = self.request.user
        contract_pk = self.kwargs.get('contract_pk')
        
        # Get Contract and Tenant DB
        employer = None
        if getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved

        if employer:
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(employer)
            
            # Fetch contract
            try:
                contract = Contract.objects.using(tenant_db).get(
                    id=contract_pk, 
                    employer_id=employer.id
                )
            except Contract.DoesNotExist:
                 from rest_framework.exceptions import NotFound
                 raise NotFound("Contract not found")
            
            # Determine next amendment number
            from django.db.models import Max
            from .models import ContractAmendment
            
            max_num = ContractAmendment.objects.using(tenant_db).filter(contract=contract).aggregate(Max('amendment_number'))['amendment_number__max']
            next_num = (max_num or 0) + 1
            
            serializer.save(
                contract=contract,
                amendment_number=next_num,
                created_by_id=user.id
            )
            
            # Important: Save using tenant DB? 
            # serializer.save() calls model.save()
            # We need to ensure the amendment is saved to tenant DB.
            # Workaround: manually set _state.db on instance or pass using in save?
            # ModelViewSet calls serializer.save(), which calls instance.save().
            # If instance.contract is from tenant DB, does Django inherit DB? Usually yes if relation logic holds.
            # But let's be safe.
            
            instance = serializer.instance
            if instance._state.db != tenant_db:
                 instance.save(using=tenant_db)


class ContractConfigurationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing global and per-type contract configuration.
    Global config: contract_type is null.
    Type-specific: contract_type is set.
    """
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["contracts.configuration.view", "contracts.manage"],
        "retrieve": ["contracts.configuration.view", "contracts.manage"],
        "create": ["contracts.configuration.update", "contracts.manage"],
        "update": ["contracts.configuration.update", "contracts.manage"],
        "partial_update": ["contracts.configuration.update", "contracts.manage"],
        "destroy": ["contracts.configuration.update", "contracts.manage"],
        "global_config": ["contracts.configuration.update", "contracts.manage"],
        "*": ["contracts.manage"],
    }
    serializer_class = ContractConfigurationSerializer

    def get_queryset(self):
        from accounts.database_utils import get_tenant_database_alias
        user = self.request.user
        employer = None
        if getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            tenant_db = get_tenant_database_alias(employer)
            return ContractConfiguration.objects.using(tenant_db).filter(employer_id=employer.id)
        return ContractConfiguration.objects.none()

    def perform_create(self, serializer):
        from accounts.database_utils import get_tenant_database_alias
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        serializer.save(employer_id=employer.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)
            
    def perform_update(self, serializer):
        from accounts.database_utils import get_tenant_database_alias
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
             instance.save(using=tenant_db)

    @action(detail=False, methods=['get', 'patch'], url_path='global')
    def global_config(self, request):
        """Helper to get and update the singleton-like global config"""
        from accounts.database_utils import get_tenant_database_alias
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        
        config, created = ContractConfiguration.objects.using(tenant_db).get_or_create(
            employer_id=employer.id,
            contract_type__isnull=True,
            defaults={
                'id_prefix': 'CNT',
                'id_sequence_padding': 5,
            }
        )

        # Seed time-off configuration with defaults for new tenants or empty configs.
        if created or not config.time_off_configuration:
            config.time_off_configuration = merge_time_off_defaults(config.time_off_configuration or {})
            config.save(using=tenant_db)

        if request.method == 'PATCH':
            serializer = self.get_serializer(config, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)

        serializer = self.get_serializer(config)
        return Response(serializer.data)


class SalaryScaleViewSet(viewsets.ModelViewSet):
    """API endpoint for managing salary scales."""

    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["contracts.salary_scale.view", "contracts.manage"],
        "retrieve": ["contracts.salary_scale.view", "contracts.manage"],
        "create": ["contracts.salary_scale.create", "contracts.manage"],
        "update": ["contracts.salary_scale.update", "contracts.manage"],
        "partial_update": ["contracts.salary_scale.update", "contracts.manage"],
        "destroy": ["contracts.salary_scale.delete", "contracts.manage"],
        "*": ["contracts.manage"],
    }
    serializer_class = SalaryScaleSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        employer = get_active_employer(self.request, require_context=False)
        if employer and (
            getattr(self.request.user, 'employer_profile', None)
            or self.request.user.is_admin
            or self.request.user.is_superuser
            or is_delegate_user(self.request.user, employer.id)
        ):
            from accounts.database_utils import ensure_tenant_database_loaded
            tenant_db = ensure_tenant_database_loaded(employer)
            context['tenant_db'] = tenant_db
        return context

    def get_queryset(self):
        from accounts.database_utils import get_tenant_database_alias
        user = self.request.user
        employer = None
        if getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            tenant_db = get_tenant_database_alias(employer)
            return SalaryScale.objects.using(tenant_db).filter(employer_id=employer.id)
        return SalaryScale.objects.none()

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        serializer.save(employer_id=employer.id)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        from accounts.database_utils import get_tenant_database_alias
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        instance.delete(using=tenant_db)


class CalculationScaleViewSet(viewsets.ModelViewSet):
    """API endpoint for managing calculation scales."""

    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["contracts.salary_scale.view", "contracts.manage"],
        "retrieve": ["contracts.salary_scale.view", "contracts.manage"],
        "create": ["contracts.salary_scale.create", "contracts.manage"],
        "update": ["contracts.salary_scale.update", "contracts.manage"],
        "partial_update": ["contracts.salary_scale.update", "contracts.manage"],
        "destroy": ["contracts.salary_scale.delete", "contracts.manage"],
        "*": ["contracts.manage"],
    }
    serializer_class = CalculationScaleSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        employer = get_active_employer(self.request, require_context=False)
        if employer and (
            getattr(self.request.user, 'employer_profile', None)
            or self.request.user.is_admin
            or self.request.user.is_superuser
            or is_delegate_user(self.request.user, employer.id)
        ):
            from accounts.database_utils import ensure_tenant_database_loaded
            tenant_db = ensure_tenant_database_loaded(employer)
            context['tenant_db'] = tenant_db
            context['employer_id'] = employer.id
        return context

    def get_queryset(self):
        from accounts.database_utils import get_tenant_database_alias
        user = self.request.user
        employer = None
        if getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            tenant_db = get_tenant_database_alias(employer)
            ensure_cameroon_default_scales(
                employer_id=employer.id,
                tenant_db=tenant_db,
                user_id=getattr(self.request.user, "id", None),
            )
            return CalculationScale.objects.using(tenant_db).filter(employer_id=employer.id)
        return CalculationScale.objects.none()

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        serializer.save(employer_id=employer.id, user_id=self.request.user.id)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        from accounts.database_utils import get_tenant_database_alias
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        instance.delete(using=tenant_db)


class ScaleRangeViewSet(viewsets.ModelViewSet):
    """API endpoint for managing scale ranges."""

    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["contracts.salary_scale.view", "contracts.manage"],
        "retrieve": ["contracts.salary_scale.view", "contracts.manage"],
        "create": ["contracts.salary_scale.create", "contracts.manage"],
        "update": ["contracts.salary_scale.update", "contracts.manage"],
        "partial_update": ["contracts.salary_scale.update", "contracts.manage"],
        "destroy": ["contracts.salary_scale.delete", "contracts.manage"],
        "*": ["contracts.manage"],
    }
    serializer_class = ScaleRangeSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        employer = get_active_employer(self.request, require_context=False)
        if employer and (
            getattr(self.request.user, 'employer_profile', None)
            or self.request.user.is_admin
            or self.request.user.is_superuser
            or is_delegate_user(self.request.user, employer.id)
        ):
            from accounts.database_utils import ensure_tenant_database_loaded
            tenant_db = ensure_tenant_database_loaded(employer)
            context['tenant_db'] = tenant_db
            context['employer_id'] = employer.id
        return context

    def get_queryset(self):
        from accounts.database_utils import get_tenant_database_alias
        user = self.request.user
        employer = None
        if getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if not employer:
            return ScaleRange.objects.none()

        tenant_db = get_tenant_database_alias(employer)
        ensure_cameroon_default_scales(
            employer_id=employer.id,
            tenant_db=tenant_db,
            user_id=getattr(self.request.user, "id", None),
        )
        qs = ScaleRange.objects.using(tenant_db).filter(employer_id=employer.id)
        calculation_scale_id = self.request.query_params.get('calculation_scale')
        if calculation_scale_id:
            qs = qs.filter(calculation_scale_id=calculation_scale_id)
        return qs

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        serializer.save(employer_id=employer.id, user_id=self.request.user.id)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        from accounts.database_utils import get_tenant_database_alias
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        instance.delete(using=tenant_db)


class ContractTemplateViewSet(viewsets.ModelViewSet):
    """API endpoint for managing contract templates."""

    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["contracts.template.view", "contracts.manage"],
        "retrieve": ["contracts.template.view", "contracts.manage"],
        "create": ["contracts.template.update", "contracts.manage"],
        "update": ["contracts.template.update", "contracts.manage"],
        "partial_update": ["contracts.template.update", "contracts.manage"],
        "destroy": ["contracts.template.update", "contracts.manage"],
        "*": ["contracts.manage"],
    }
    serializer_class = ContractTemplateSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_tenant_db(self):
        from accounts.database_utils import get_tenant_database_alias
        user = self.request.user
        employer = None
        if getattr(user, 'employer_profile', None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            return get_tenant_database_alias(employer), employer
        return None, None

    def _snapshot_version(self, instance, tenant_db):
        try:
            ContractTemplateVersion.objects.using(tenant_db).create(
                template=instance,
                name=instance.name,
                category=instance.category,
                version=instance.version,
                contract_type=instance.contract_type,
                body_override=instance.body_override,
                file=instance.file,
            )
        except Exception:
            pass

    def get_serializer_context(self):
        context = super().get_serializer_context()
        tenant_db, employer = self._get_tenant_db()
        if tenant_db:
            from accounts.database_utils import ensure_tenant_database_loaded
            tenant_db = ensure_tenant_database_loaded(employer)
            context['tenant_db'] = tenant_db
        return context

    def get_queryset(self):
        tenant_db, employer = self._get_tenant_db()
        if tenant_db and employer:
            qs = ContractTemplate.objects.using(tenant_db).filter(employer_id=employer.id)
            contract_type = self.request.query_params.get('contract_type')
            category = self.request.query_params.get('category')
            search = self.request.query_params.get('search')
            if contract_type:
                qs = qs.filter(contract_type=contract_type)
            if category:
                qs = qs.filter(category__iexact=category)
            if search:
                qs = qs.filter(name__icontains=search)
            return qs
        return ContractTemplate.objects.none()

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        serializer.save(employer_id=employer.id)

    def perform_update(self, serializer):
        instance = serializer.instance
        tenant_db, _ = self._get_tenant_db()
        if tenant_db and instance:
            self._snapshot_version(instance, tenant_db)
        serializer.save()

    def perform_destroy(self, instance):
        from accounts.database_utils import get_tenant_database_alias
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        instance.delete(using=tenant_db)

    @action(detail=True, methods=['get'], url_path='versions')
    def versions(self, request, pk=None):
        tenant_db, _ = self._get_tenant_db()
        if not tenant_db:
            return Response([], status=status.HTTP_200_OK)
        template = self.get_object()
        qs = ContractTemplateVersion.objects.using(tenant_db).filter(template=template)
        serializer = ContractTemplateVersionSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        tenant_db, _ = self._get_tenant_db()
        if not tenant_db:
            return Response({'error': 'Tenant context not found.'}, status=status.HTTP_400_BAD_REQUEST)

        template = self.get_object()
        version_id = request.data.get('version_id')
        if not version_id:
            return Response({'error': 'version_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        version = (
            ContractTemplateVersion.objects.using(tenant_db)
            .filter(id=version_id, template=template)
            .first()
        )
        if not version:
            return Response({'error': 'Template version not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Snapshot current state before restore
        self._snapshot_version(template, tenant_db)

        template.name = version.name
        template.category = version.category
        template.version = version.version
        template.contract_type = version.contract_type
        template.body_override = version.body_override
        if version.file:
            template.file = version.file
        else:
            template.file = None
        template.save(using=tenant_db)

        serializer = self.get_serializer(template)
        return Response(serializer.data, status=status.HTTP_200_OK)

