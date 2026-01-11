from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    Contract, ContractConfiguration, ContractTemplate, SalaryScale
)
from .serializers import (
    ContractSerializer, ContractConfigurationSerializer, SalaryScaleSerializer
)
from timeoff.defaults import merge_time_off_defaults
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounts.middleware import set_current_tenant_db
from accounts.models import EmployerProfile, User
from accounts.permissions import IsEmployer
from contracts.management.commands.seed_contract_template import TYPE_BODIES, BASE_BODY

class ContractViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows contracts to be viewed or edited.
    Restricted to the current user's tenant.
    """
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]

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
        return hasattr(user, 'employer_profile') and user.employer_profile.id == contract.employer_id

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
        if user.is_authenticated and hasattr(user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(user.employer_profile)
            self._set_tenant_alias(tenant_db)
            return Contract.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
            
        # 2. Employee Access
        if user.is_authenticated and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or 'default'
            self._set_tenant_alias(tenant_db)
            return Contract.objects.using(tenant_db).filter(employee=employee)
            
        return Contract.objects.none()

    def perform_destroy(self, instance):
        """Delete contract from tenant database"""
        if hasattr(self.request.user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
            instance.delete(using=tenant_db)
        else:
            instance.delete()

    @action(detail=False, methods=['get', 'patch'], url_path='template/default')
    def default_template(self, request):
        """Get or update the default template body for the employer by contract_type (no uploads)."""
        user = request.user
        if not hasattr(user, 'employer_profile'):
            return Response({'error': 'Only employers can manage templates.'}, status=status.HTTP_403_FORBIDDEN)

        contract_type = request.query_params.get('contract_type') or request.data.get('contract_type')
        if not contract_type:
            return Response({'error': 'contract_type is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(user.employer_profile)

        template = (
            ContractTemplate.objects.using(tenant_db)
            .filter(employer_id=user.employer_profile.id, contract_type=contract_type, is_default=True)
            .order_by('-created_at')
            .first()
        )
        if not template:
            return Response({'error': 'Default template not found for this contract type.'}, status=status.HTTP_404_NOT_FOUND)

        if request.method.lower() == 'get':
            fallback = TYPE_BODIES.get(contract_type, BASE_BODY)
            return Response({
                'id': template.id,
                'contract_type': contract_type,
                'body': template.body_override or fallback,
                'updated_at': template.updated_at,
            })

        # PATCH
        body = request.data.get('body')
        if not body:
            return Response({'error': 'body is required.'}, status=status.HTTP_400_BAD_REQUEST)

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

        try:
            contract.send_for_approval(request.user)
            return Response(self.get_serializer(contract).data)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='send-for-signature')
    def send_for_signature_alias(self, request, pk=None):
        """Compatibility alias - routes to send-for-approval"""
        return self.send_for_approval(request, pk)

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
        Requires 'signature_text' in body.
        'document_hash' is optional.
        """
        contract = self.get_object()
        self._set_tenant_context(contract)
        user = request.user
        
        signature_text = request.data.get('signature_text')
        if not signature_text:
             return Response({'error': 'Signature text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Determine signer role
        role = None
        # Check if user is the employee for this contract
        # Note: 'user.employee_profile' might be cached or we need strict check
        # But contract.employee is an Employee object.
        # We need to see if request.user is linked to contract.employee
        # contract.employee.user_id should match request.user.id
        
        # We need to access contract.employee which is in tenant DB
        # self.get_object() returns contract from tenant DB, so relations should work if they are in same DB
        # But Employee -> User is loose if User is in default DB. 
        # Usually we store user_id on Employee.
        
        is_employee_signer = False
        if contract.employee and contract.employee.user_id == user.id:
            role = 'EMPLOYEE'
            is_employee_signer = True
            
        # Check if user is employer (admin/owner)
        is_employer_signer = False
        if not is_employee_signer:
            # Simple check: is this user the owner of the employer profile linked to contract?
            # contract.employer_id is just an ID.
            # We need to check if request.user.employer_profile.id == contract.employer_id
            if hasattr(user, 'employer_profile') and user.employer_profile.id == contract.employer_id:
                role = 'EMPLOYER'
                is_employer_signer = True
        
        if not role:
             return Response({'error': 'You are not authorized to sign this contract.'}, status=status.HTTP_403_FORBIDDEN)
             
        # Create Signature
        from .models import ContractSignature
        
        # Get Client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
            
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Use tenant DB for signature creation (same as contract)
        db_alias = contract._state.db or 'default'
        
        signature = ContractSignature.objects.using(db_alias).create(
            contract=contract,
            signer_user_id=user.id,
            signer_name=f"{user.first_name} {user.last_name}".strip() or user.email,
            role=role,
            signature_text=signature_text,
            ip_address=ip,
            user_agent=user_agent,
            document_hash=request.data.get('document_hash', '')
        )
        
        # Check if we should mark as SIGNED
        # Logic: If we have at least one EMPLOYEE signature AND one EMPLOYER signature
        signatures = ContractSignature.objects.using(db_alias).filter(contract=contract)
        has_employee_sign = signatures.filter(role='EMPLOYEE').exists()
        has_employer_sign = signatures.filter(role='EMPLOYER').exists()
        
        if has_employee_sign and has_employer_sign:
            if contract.status != 'SIGNED':
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
            
            return Response({'status': 'extended', 'new_end_date': new_end_date})
            
        elif create_new:
            # 2. Create New Contract
            import uuid
            new_contract = Contract(
                employer_id=contract.employer_id,
                contract_id=f"CNT-REN-{uuid.uuid4().hex[:8].upper()}", # temporary ID logic
                employee=contract.employee,
                branch=contract.branch,
                department=contract.department,
                job_position=contract.job_position,
                contract_type=contract.contract_type,
                start_date=contract.end_date, # Starts when old one ends? Or strictly provided? 
                # Ideally start_date = old_end_date + 1 day, but let's assume immediate continuation
                # For MVP let's require start_date in input or default to old end_date
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
            
            new_contract.save(using=contract._state.db)
            
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
            
        reason = data.get('reason')
        notice_served = data.get('notice_served', False)
        
        # Determine DB alias
        db_alias = contract._state.db or 'default'
        
        # Validation: termination date should probably be >= start_date
        # But we'll trust the input for now or could add checks.
        
        # Update Contract
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
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        contract_pk = self.kwargs.get('contract_pk')
        
        if not contract_pk:
            from .models import ContractAmendment
            return ContractAmendment.objects.none()
            
        # Get Tenant DB
        if user.is_authenticated and hasattr(user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(user.employer_profile)
            
            from .models import ContractAmendment
            qs = ContractAmendment.objects.using(tenant_db).filter(
                contract__employer_id=user.employer_profile.id,
                contract_id=contract_pk
            )
            return qs
        return ContractAmendment.objects.none()
        
    def perform_create(self, serializer):
        user = self.request.user
        contract_pk = self.kwargs.get('contract_pk')
        
        # Get Contract and Tenant DB
        if hasattr(user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            tenant_db = get_tenant_database_alias(user.employer_profile)
            
            # Fetch contract
            try:
                contract = Contract.objects.using(tenant_db).get(
                    id=contract_pk, 
                    employer_id=user.employer_profile.id
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
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContractConfigurationSerializer

    def get_queryset(self):
        from accounts.database_utils import get_tenant_database_alias
        user = self.request.user
        if hasattr(user, 'employer_profile'):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return ContractConfiguration.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        return ContractConfiguration.objects.none()

    def perform_create(self, serializer):
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save(employer_id=self.request.user.employer_profile.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)
            
    def perform_update(self, serializer):
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
             instance.save(using=tenant_db)

    @action(detail=False, methods=['get', 'patch'], url_path='global')
    def global_config(self, request):
        """Helper to get and update the singleton-like global config"""
        from accounts.database_utils import get_tenant_database_alias
        employer = request.user.employer_profile
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

    permission_classes = [IsEmployer]
    serializer_class = SalaryScaleSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if hasattr(self.request.user, 'employer_profile'):
            from accounts.database_utils import ensure_tenant_database_loaded
            tenant_db = ensure_tenant_database_loaded(self.request.user.employer_profile)
            context['tenant_db'] = tenant_db
        return context

    def get_queryset(self):
        from accounts.database_utils import get_tenant_database_alias
        user = self.request.user
        if hasattr(user, 'employer_profile'):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return SalaryScale.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        return SalaryScale.objects.none()

    def perform_create(self, serializer):
        serializer.save(employer_id=self.request.user.employer_profile.id)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        from accounts.database_utils import get_tenant_database_alias
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        instance.delete(using=tenant_db)

