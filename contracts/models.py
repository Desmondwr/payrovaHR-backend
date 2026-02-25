from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from .notifications import notify_sent_for_signature, notify_signed, notify_activated
from django.core.exceptions import ValidationError
import uuid
from decimal import Decimal
from datetime import timedelta
from .configuration_defaults import SIGNATURE_METHOD_CHOICES

User = get_user_model()


class Contract(models.Model):
    """Employee contract model - tenant-aware"""
    
    CONTRACT_TYPE_CHOICES = [
        ('PERMANENT', 'Permanent'),
        ('FIXED_TERM', 'Fixed-Term'),
        ('INTERNSHIP', 'Internship'),
        ('CONSULTANT', 'Consultant'),
        ('PART_TIME', 'Part-Time'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('PENDING_SIGNATURE', 'Pending Signature'),
        ('SIGNED', 'Signed'),
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('TERMINATED', 'Terminated'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    PAY_FREQUENCY_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('BI_WEEKLY', 'Bi-Weekly'),
        ('WEEKLY', 'Weekly'),
        ('DAILY', 'Daily'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Multitenancy support
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    
    # Contract identification
    contract_id = models.CharField(
        max_length=50,
        unique=True,
        help_text='Unique contract identifier (auto-generated or manual)'
    )
    
    # Employee relationship (tenant-aware ForeignKey)
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='contracts',
        help_text='Employee this contract belongs to'
    )
    
    
    # Organizational structure (nullable)
    branch = models.ForeignKey(
        'employees.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contracts',
        help_text='Branch where employee works'
    )
    
    department = models.ForeignKey(
        'employees.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contracts',
        help_text='Department where employee works'
    )

    # Contract details
    contract_type = models.CharField(
        max_length=20,
        choices=CONTRACT_TYPE_CHOICES,
        help_text='Type of employment contract'
    )
    
    start_date = models.DateField(
        help_text='Contract start date'
    )
    
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text='Contract end date (nullable for permanent contracts)'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
        help_text='Current status of the contract'
    )
    
    # Compensation details
    salary_scale = models.ForeignKey(
        'SalaryScale',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contracts',
        help_text='Salary scale for this contract'
    )

    base_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Base salary amount'
    )
    
    currency = models.CharField(
        max_length=3,
        default='XAF',
        help_text='Currency code (e.g., XAF, USD, EUR)'
    )
    
    pay_frequency = models.CharField(
        max_length=20,
        choices=PAY_FREQUENCY_CHOICES,
        default='MONTHLY',
        help_text='Payment frequency'
    )
    
    previous_contract = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='renewals',
        help_text='Previous contract if this is a renewal'
    )

    # Termination details
    termination_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date when the contract was terminated'
    )
    
    termination_reason = models.TextField(
        null=True,
        blank=True,
        help_text='Reason for termination'
    )
    
    notice_served = models.BooleanField(
        default=False,
        help_text='Whether the required notice period was served'
    )
    
    final_pay_flag = models.BooleanField(
        default=False,
        help_text='Flag to trigger final compensation calculation'
    )

    # Audit fields
    created_by = models.IntegerField(
        db_index=True,
        help_text='ID of the user who created this contract (from main database)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contracts'
        verbose_name = 'Contract'
        verbose_name_plural = 'Contracts'
        unique_together = [['employer_id', 'contract_id']]
        indexes = [
            models.Index(fields=['employer_id', 'status']),
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.contract_id} - {self.employee.full_name if self.employee else 'Unknown'}"
    
    @property
    def is_active(self):
        """Check if contract is currently active"""
        return self.status == 'ACTIVE'
    
    @property
    def is_expired(self):
        """Check if contract has expired"""
        if self.end_date:
            grace_days = self.get_effective_config('expiry_grace_period_days', 0) or 0
            cutoff_date = self.end_date + timedelta(days=grace_days)
            if timezone.now().date() > cutoff_date:
                return True
        return self.status == 'EXPIRED'
    
    @property
    def is_permanent(self):
        """Check if this is a permanent contract"""
        return self.contract_type == 'PERMANENT'
    
    @property
    def duration_days(self):
        """Calculate contract duration in days"""
        if not self.end_date:
            return None  # Permanent contract
        return (self.end_date - self.start_date).days
    
    @property
    def remaining_days(self):
        """Calculate remaining days until contract end"""
        if not self.end_date:
            return None  # Permanent contract
        today = timezone.now().date()
        grace_days = self.get_effective_config('expiry_grace_period_days', 0) or 0
        cutoff_date = self.end_date + timedelta(days=grace_days)
        if today > cutoff_date:
            return 0  # Expired
        return (cutoff_date - today).days
    
    @classmethod
    def get_config_for(cls, employer_id, contract_type=None, db_alias='default'):
        """
        Fetch the global and type-specific configurations for an employer.
        Returns a tuple of (global_config, type_config).
        """
        if not employer_id:
            return None, None

        type_config = None
        if contract_type:
            type_config = ContractConfiguration.objects.using(db_alias).filter(
                employer_id=employer_id, 
                contract_type=contract_type
            ).first()

        global_config = ContractConfiguration.objects.using(db_alias).filter(
            employer_id=employer_id, 
            contract_type__isnull=True
        ).first()

        return global_config, type_config

    @classmethod
    def get_effective_config_value(cls, employer_id, contract_type, field_name, default=None, db_alias='default'):
        """
        Retrieve a configuration value, checking type-specific first, then global.
        """
        global_config, type_config = cls.get_config_for(employer_id, contract_type, db_alias)
        if type_config and getattr(type_config, field_name) is not None:
            return getattr(type_config, field_name)
        
        if global_config and getattr(global_config, field_name) is not None:
            return getattr(global_config, field_name)
            
        return default

    def get_config(self, get_global=True):
        """
        Retrieve contract configuration for the employer.
        If get_global=True, returns the global configuration (contract_type is null).
        Otherwise returns the type-specific configuration for self.contract_type.
        """
        db_alias = self._state.db or 'default'
        global_config, type_config = Contract.get_config_for(
            employer_id=self.employer_id,
            contract_type=self.contract_type,
            db_alias=db_alias
        )
        return global_config if get_global else type_config

    def get_effective_config(self, field_name, default=None):
        """
        Retrieve a configuration value, checking type-specific first, then global.
        """
        db_alias = self._state.db or 'default'
        return Contract.get_effective_config_value(
            employer_id=self.employer_id,
            contract_type=self.contract_type,
            field_name=field_name,
            default=default,
            db_alias=db_alias
        )

    def get_approval_requirements(self):
        """
        Determine if this contract must follow the approval workflow and why.
        Returns (required: bool, reasons: list[str]).
        """
        approval_enabled = self.get_effective_config('approval_enabled', False)
        reasons = []

        if not approval_enabled:
            return False, reasons

        if self.get_effective_config('requires_approval', False):
            reasons.append('requires_approval')

        base_salary = getattr(self, 'base_salary', None)
        max_without = self.get_effective_config('max_salary_without_approval')
        if base_salary is not None and max_without is not None and base_salary > max_without:
            reasons.append('base_salary_above_threshold')

        salary_thresholds = self.get_effective_config('salary_thresholds', {}) or {}
        if base_salary is not None:
            for level, threshold in salary_thresholds.items():
                try:
                    if base_salary > Decimal(str(threshold)):
                        reasons.append(f'above_{level}_threshold')
                except Exception:
                    continue

        return bool(reasons), reasons

    def signature_required(self):
        """
        Resolve whether signatures are required for this contract based on configuration.
        """
        value = self.get_effective_config('requires_signature', None)
        if value is None:
            value = self.get_effective_config('signature_required', True)
        return value

    def _should_auto_expire(self):
        """Check whether the contract should auto-expire based on config and dates."""
        if self.contract_type != 'FIXED_TERM' or not self.end_date:
            return False

        auto_expire = self.get_effective_config('auto_expire_fixed_term', False)
        if not auto_expire:
            return False

        grace_days = self.get_effective_config('expiry_grace_period_days', 0) or 0
        cutoff_date = self.end_date + timedelta(days=grace_days)
        return timezone.now().date() > cutoff_date

    def _apply_auto_expiry_if_needed(self):
        """Adjust status to EXPIRED if auto-expiry rules say so."""
        if self.status in ['TERMINATED', 'CANCELLED', 'EXPIRED']:
            return

        if self._should_auto_expire() and self.status in ['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE', 'APPROVED']:
            self.status = 'EXPIRED'
            self._auto_expired = True

    def generate_contract_id(self, config=None):
        """Auto-generate contract ID based on configuration"""
        if not config:
            db_alias = self._state.db or 'default'
            global_config, type_config = Contract.get_config_for(
                employer_id=self.employer_id,
                contract_type=self.contract_type,
                db_alias=db_alias
            )
            config = type_config or global_config
        if not config:
            return None

        from django.db.models import F
        from django.db import transaction

        db_alias = self._state.db or 'default'
        now = timezone.now()

        def _resolve_institution_code():
            """Best-effort institution code for ID generation."""
            code = None
            try:
                from accounts.models import EmployerProfile
                employer = EmployerProfile.objects.using('default').filter(id=self.employer_id).only('slug').first()
                code = getattr(employer, 'slug', None)
            except Exception:
                code = None

            if not code:
                code = str(self.employer_id)

            cleaned = ''.join(ch for ch in str(code).upper() if ch.isalnum())
            return cleaned[:8] if len(cleaned) > 8 else cleaned

        with transaction.atomic(using=db_alias):
            config_qs = ContractConfiguration.objects.using(db_alias).select_for_update().filter(id=config.id)
            config = config_qs.first()
            if not config:
                return None

            if config.id_reset_sequence_yearly:
                contract_qs = Contract.objects.using(db_alias).filter(employer_id=self.employer_id)
                if config.contract_type:
                    contract_qs = contract_qs.filter(contract_type=config.contract_type)
                if not contract_qs.filter(created_at__year=now.year).exists():
                    config_qs.update(last_sequence_number=0, updated_at=now)
                    config.refresh_from_db(using=db_alias)

            config_qs.update(last_sequence_number=F('last_sequence_number') + 1, updated_at=now)
            config.refresh_from_db(using=db_alias)
            seq = config.last_sequence_number

        padding = max(1, int(config.id_sequence_padding or 1))
        formatted_seq = str(seq).zfill(padding)

        prefix = (config.id_prefix or '').strip()
        year = ''
        if config.id_year_format == 'YYYY':
            year = str(now.year)
        elif config.id_year_format == 'YY':
            year = str(now.year)[2:]

        parts = []
        if prefix:
            parts.append(prefix)
        if config.id_include_institution_code:
            parts.append(_resolve_institution_code())
        if year:
            parts.append(year)
        parts.append(formatted_seq)
        return "-".join([part for part in parts if part])

    def clean(self):
        """Validate contract data against configurations"""
        from django.core.exceptions import ValidationError
        errors = {}
        
        # 1. Type specific logic (using effective config)
        end_date_required = self.get_effective_config('end_date_required', True)
        if end_date_required and not self.end_date and self.contract_type != 'PERMANENT':
            errors['end_date'] = 'End date is required for this contract type.'
        
        if self.contract_type == 'PERMANENT' and self.end_date:
            errors['end_date'] = 'Permanent contracts should not have an end date.'

        # 2. Date Rules
        today = timezone.now().date()
        max_backdate = self.get_effective_config('max_backdate_days')
        allow_future = self.get_effective_config('allow_future_contracts')
        min_fixed_duration = self.get_effective_config('min_fixed_term_duration_days')

        if self.start_date:
            if max_backdate is not None:
                days_diff = (today - self.start_date).days
                if days_diff > max_backdate:
                    errors['start_date'] = f'Contract cannot be backdated more than {max_backdate} days.'
            
            if allow_future is not None and not allow_future and self.start_date > today:
                errors['start_date'] = 'Future contracts are not allowed.'
        
        if self.start_date and self.end_date:
            if min_fixed_duration is not None and self.contract_type == 'FIXED_TERM':
                duration = (self.end_date - self.start_date).days
                if duration < min_fixed_duration:
                     errors['end_date'] = f'Minimum duration for fixed-term contracts is {min_fixed_duration} days.'
            
            if self.end_date <= self.start_date:
                 errors['end_date'] = 'End date must be after start date.'

        # 2c. Probation end date should fit within contract duration
        probation_must_end = self.get_effective_config('probation_must_end_before_contract', False)
        if probation_must_end and self.end_date and self.employee_id:
            try:
                probation_end = getattr(self.employee, 'probation_end_date', None)
            except Exception:
                probation_end = None
            if probation_end and probation_end > self.end_date:
                errors['end_date'] = 'Probation end date must be on or before the contract end date.'

        # 2b. Concurrent contract rules
        allow_concurrent = self.get_effective_config('allow_concurrent_contracts_same_inst', False)
        constrained_statuses = ['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE']
        if (
            not allow_concurrent
            and self.employee_id
            and self.start_date
            and self.status in constrained_statuses
        ):
            db_alias = self._state.db or 'default'
            existing_contracts = Contract.objects.using(db_alias).filter(
                employee=self.employee,
                status__in=constrained_statuses
            )
            if self.pk:
                existing_contracts = existing_contracts.exclude(id=self.pk)

            for existing in existing_contracts:
                exist_start = existing.start_date
                exist_end = existing.end_date

                if self.end_date and exist_end:
                    if self.start_date <= exist_end and self.end_date >= exist_start:
                        errors['start_date'] = f'Overlapping contract exists: {existing.contract_id} ({exist_start} - {exist_end})'
                        break
                elif not exist_end:
                    if self.end_date:
                        if self.end_date >= exist_start:
                            errors['start_date'] = f'Overlapping permanent contract exists: {existing.contract_id} (Starts {exist_start})'
                            break
                    else:
                        errors['start_date'] = f'Employee already has a permanent contract: {existing.contract_id}'
                        break
                elif not self.end_date and exist_end and self.start_date <= exist_end:
                    errors['start_date'] = f'Cannot start permanent contract during existing contract: {existing.contract_id}'
                    break

        # 3. Compensation Rules
        require_gross_gt_zero = self.get_effective_config('require_gross_salary_gt_zero')
        min_wage = self.get_effective_config('min_wage')

        if require_gross_gt_zero is not None and require_gross_gt_zero:
            gross_value = None
            if self.pk:
                try:
                    gross_value = self.gross_salary
                except Exception:
                    gross_value = None
            if gross_value is None:
                gross_value = self.base_salary or Decimal('0')
            if gross_value <= 0:
                errors['base_salary'] = 'Gross salary must be greater than zero.'
            
        if min_wage is not None and self.base_salary and self.base_salary < min_wage:
            errors['base_salary'] = f'Base salary must be at least the minimum wage ({min_wage}).'

        salary_scale_enforcement = self.get_effective_config('salary_scale_enforcement', 'WARNING')
        allow_salary_override = self.get_effective_config('allow_salary_override', True)

        if salary_scale_enforcement == 'STRICT' and not self.salary_scale:
            errors['salary_scale'] = 'Salary scale is required by configuration.'

        if self.salary_scale and allow_salary_override is not None and not allow_salary_override:
            if self.base_salary is not None and self.base_salary != self.salary_scale.amount:
                errors['base_salary'] = 'Base salary must match the selected salary scale when overrides are disabled.'

        # 4. Allowance Rules
        if self.pk:
            allow_pct = self.get_effective_config('allow_percentage_allowances')
            max_pct = self.get_effective_config('max_allowance_percentage')
            allow_duplicate_allowances = self.get_effective_config('allow_duplicate_allowances', False)
            duplicate_names = set()

            if allow_pct is not None and not allow_pct:
                if self.allowances.all().filter(type='PERCENTAGE').exists():
                    errors['allowances'] = 'Percentage-based allowances are not allowed.'
            
            if max_pct is not None:
                total_pct = sum([a.amount for a in self.allowances.all().filter(type='PERCENTAGE')])
                if total_pct > max_pct:
                    errors['allowances'] = f'Total allowance percentage exceeds maximum allowed ({max_pct}%).'

            if not allow_duplicate_allowances:
                seen = set()
                for allowance in self.allowances.all():
                    key = (allowance.name or '').strip().lower()
                    if not key:
                        continue
                    if key in seen:
                        duplicate_names.add(allowance.name)
                    seen.add(key)
                if duplicate_names:
                    existing = errors.get('allowances')
                    dup_message = f"Duplicate allowances are not allowed: {', '.join(sorted(duplicate_names))}."
                    if existing:
                        if isinstance(existing, list):
                            existing.append(dup_message)
                        else:
                            errors['allowances'] = [existing, dup_message]
                    else:
                        errors['allowances'] = dup_message

        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to run validation and auto-generate ID"""
        # Ensure permanent contracts don't have an end date
        if self.contract_type == 'PERMANENT' and self.end_date:
            self.end_date = None

        if not self.contract_id:
            db_alias = self._state.db or 'default'
            global_config, type_config = Contract.get_config_for(
                employer_id=self.employer_id,
                contract_type=self.contract_type,
                db_alias=db_alias
            )
            config = type_config or global_config
            if config:
                self.contract_id = self.generate_contract_id(config)
            else:
                # Fallback to a random ID if no config exists
                import uuid
                self.contract_id = f"CNT-{uuid.uuid4().hex[:8].upper()}"
        
        # In a multi-tenant environment, full_clean() can fail on ForeignKeys 
        # because it tries to validate them using the default manager.
        # We exclude them here because they are validated by the serializer.
        self._apply_auto_expiry_if_needed()
        self.full_clean(exclude=['employee', 'branch', 'department', 'previous_contract', 'salary_scale'])
        super().save(*args, **kwargs)
        if getattr(self, '_auto_expired', False):
            try:
                self._sync_employee_after_status_change('expired', user=None)
            except Exception:
                pass
            self._auto_expired = False

    @property
    def gross_salary(self):
        """
        Calculate gross salary: Base Salary + Allowances
        Handle Fixed and Percentage allowances.
        """
        
        total = self.base_salary
        
        # We need to access related allowances
        # Note: This might cause N+1 problem if not pre-fetched
        for allowance in self.allowances.all():
            if allowance.type == 'FIXED':
                total += allowance.amount
            elif allowance.type == 'PERCENTAGE':
                # amount is percentage (e.g., 5.0 for 5%)
                allowance_value = self.base_salary * (allowance.amount / Decimal('100.0'))
                total += allowance_value
                
        return total.quantize(Decimal('0.01'))

    def log_action(self, user, action, metadata=None):
        """Helper to log status changes and other actions"""
        # Ensure we write to the same DB as the contract
        db_alias = self._state.db or 'default'
        user_id = user.id if user else None
        
        details = ""
        if metadata:
            if 'reason' in metadata and len(metadata) == 1:
                details = metadata['reason']
            else:
                details = ", ".join([f"{k}: {v}" for k, v in metadata.items()])
            
        ContractAudit.objects.using(db_alias).create(
            contract=self,
            action=action,
            performed_by_id=user_id,
            metadata=metadata or {},
            details=details
        )

    def send_for_signature(self, user):
        if self.status not in ['DRAFT', 'APPROVED']:
            raise ValidationError("Only draft or approved contracts can be sent for signature.")
        
        approval_required, reasons = self.get_approval_requirements()
        if self.status in ['DRAFT', 'APPROVED'] and approval_required:
             self.status = 'PENDING_APPROVAL'
             self.save()
             self.log_action(user, 'SENT_FOR_APPROVAL', metadata={'reasons': reasons})
             return

        self.status = 'PENDING_SIGNATURE'
        self.save()

        if not self.signature_required():
            self.log_action(user, 'SIGNATURE_SKIPPED', metadata={'reasons': ['signature_not_required']})
            self.mark_signed(user)
            return

        self.log_action(user, 'SENT_FOR_SIGNATURE')
        notify_sent_for_signature(self)

    def send_for_approval(self, user):
        """
        New flow: explicitly move to PENDING_APPROVAL (replaces send_for_signature entrypoint).
        """
        if self.status not in ['DRAFT', 'APPROVED', 'PENDING_APPROVAL']:
            raise ValidationError("Only draft or approved contracts can be sent for approval.")
        self.status = 'PENDING_APPROVAL'
        self.save()
        self.log_action(user, 'SENT_FOR_APPROVAL')

    def approve(self, user, role=None):
        """
        Capture approval by role (EMPLOYEE/EMPLOYER). When both approvals exist,
        mark the contract as signed.
        """
        if self.status not in ['PENDING_APPROVAL', 'APPROVED', 'PENDING_SIGNATURE']:
            raise ValidationError("Contract is not pending approval.")

        # Determine which DB to write to (tenant-aware)
        db_alias = self._state.db or 'default'

        # Record/Update signature approval entry
        signer_name = user.get_full_name() or user.email or 'User'
        ContractSignature.objects.using(db_alias).update_or_create(
            contract=self,
            role=role or 'EMPLOYER',
            defaults={
                'signer_user_id': user.id,
                'signer_name': signer_name,
                'signature_text': 'Signature on file',
                'document_hash': '',
            }
        )

        # Check if both parties have approved
        has_employee = ContractSignature.objects.using(db_alias).filter(contract=self, role='EMPLOYEE').exists()
        has_employer = ContractSignature.objects.using(db_alias).filter(contract=self, role='EMPLOYER').exists()

        if has_employee and has_employer:
            # Both approvals captured; mark signed
            self.mark_signed(user)
        else:
            self.status = 'PENDING_APPROVAL'
            self.save()
            self.log_action(user, 'APPROVED')

    def mark_signed(self, user):
        if self.status not in ['PENDING_SIGNATURE', 'PENDING_APPROVAL', 'APPROVED']:
            raise ValidationError("Contract must be awaiting approval/signature to be marked as signed.")
            
        self.status = 'SIGNED'
        self.save()
        self.log_action(user, 'MARKED_SIGNED')
        notify_signed(self)

        # Check auto-activation
        auto_activate = self.get_effective_config('auto_activate_on_start', False)
        if auto_activate:
             today = timezone.now().date()
             if self._should_auto_expire():
                  self.status = 'EXPIRED'
                  self.save()
                  self.log_action(user, 'EXPIRED')
             elif self.start_date <= today:
                  self.activate(user)

    def activate(self, user):
        if self.status != 'SIGNED':
            allow_no_sig = self.get_effective_config('allow_activation_without_signature', False)
            if allow_no_sig and self.status in ['DRAFT', 'APPROVED', 'PENDING_APPROVAL']:
                pass
            else:
                raise ValidationError("Contract must be signed to be activated.")

        if self._should_auto_expire():
            raise ValidationError("Contract has passed its end date and cannot be activated without renewal.")
            
        self.status = 'ACTIVE'
        self.save()
        if self.status == 'EXPIRED':
            self.log_action(user, 'EXPIRED')
        else:
            self.log_action(user, 'ACTIVATED')
            notify_activated(self)
        try:
            self._sync_employee_after_status_change('activated', user=user)
        except Exception:
            pass

    def expire(self, user):
        if self.status != 'ACTIVE':
             from django.core.exceptions import ValidationError
             raise ValidationError("Only active contracts can be expired.")
        if self.end_date:
            grace_days = self.get_effective_config('expiry_grace_period_days', 0) or 0
            cutoff_date = self.end_date + timedelta(days=grace_days)
            if timezone.now().date() <= cutoff_date:
                raise ValidationError("Contract is still within its expiry grace period.")
        self.status = 'EXPIRED'
        self.save()
        self.log_action(user, 'EXPIRED')
        try:
            self._sync_employee_after_status_change('expired', user=user)
        except Exception:
            pass

    def terminate(self, user, reason=None):
        if self.status != 'ACTIVE':
             from django.core.exceptions import ValidationError
             raise ValidationError("Only active contracts can be terminated.")
             
        self.status = 'TERMINATED'
        self.save()
        self.log_action(user, 'TERMINATED', metadata={'reason': reason})
        try:
            self._sync_employee_after_status_change('terminated', user=user)
        except Exception:
            pass

    def _sync_employee_after_status_change(self, action, *, user=None):
        """Sync employee status when contracts change state."""
        employee = self.employee
        if not employee:
            return

        db_alias = self._state.db or 'default'
        try:
            from employees.utils import get_or_create_employee_config, revoke_employee_access
        except Exception:
            return

        config = get_or_create_employee_config(self.employer_id, db_alias)
        today = timezone.now().date()
        active_statuses = ['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE', 'APPROVED', 'PENDING_APPROVAL']
        other_active = Contract.objects.using(db_alias).filter(
            employee=employee,
            status__in=active_statuses
        ).exclude(id=self.id).exists()

        if action == 'activated':
            # Reactivate only if allowed by configuration
            if employee.employment_status in ['TERMINATED', 'RESIGNED', 'RETIRED'] and not config.allow_employee_reactivation:
                return

            if not employee.probation_end_date and self.start_date:
                probation_days = None
                try:
                    compensation_cfg = self.get_effective_config('payroll_configuration', {}) or {}
                    probation_days = compensation_cfg.get('probation_period_days')
                except Exception:
                    probation_days = None

                try:
                    probation_days = int(probation_days) if probation_days is not None else None
                except Exception:
                    probation_days = None

                if probation_days and probation_days > 0:
                    employee.probation_end_date = self.start_date + timedelta(days=probation_days)
                else:
                    months = self.get_effective_config('default_probation_period_months')
                    try:
                        months = int(months) if months is not None else None
                    except Exception:
                        months = None
                    if months and months > 0:
                        import calendar
                        year = self.start_date.year + (self.start_date.month - 1 + months) // 12
                        month = (self.start_date.month - 1 + months) % 12 + 1
                        day = min(self.start_date.day, calendar.monthrange(year, month)[1])
                        employee.probation_end_date = self.start_date.replace(
                            year=year,
                            month=month,
                            day=day
                        )

            if employee.probation_end_date and employee.probation_end_date >= today:
                employee.employment_status = 'PROBATION'
            else:
                employee.employment_status = 'ACTIVE'

            employee.termination_date = None
            employee.termination_reason = None
            employee.save(using=db_alias)
            return

        if action in ['terminated', 'expired']:
            if other_active:
                return
            employee.employment_status = 'TERMINATED'
            if action == 'expired':
                employee.termination_date = self.end_date or today
                if not employee.termination_reason:
                    employee.termination_reason = 'Contract expired'
            else:
                employee.termination_date = self.termination_date or today
                if not employee.termination_reason:
                    employee.termination_reason = self.termination_reason or 'Contract terminated'
            employee.save(using=db_alias)

            if config.termination_revoke_access_timing == 'IMMEDIATE':
                try:
                    revoke_employee_access(employee, config, db_alias)
                except Exception:
                    pass


class SalaryScale(models.Model):
    """Salary scale entry for contract compensation"""

    STATUS_CHOICES = [
        ('ENABLED', 'Enabled'),
        ('DISABLED', 'Disabled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    salary_category = models.CharField(max_length=255, help_text='Salary category')
    echelon = models.CharField(max_length=50, help_text='Echelon')
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text='Salary amount')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ENABLED')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'salary_scales'
        verbose_name = 'Salary Scale'
        verbose_name_plural = 'Salary Scales'
        ordering = ['salary_category', 'echelon']
        indexes = [
            models.Index(fields=['employer_id', 'status'], name='salary_scale_emp_status_idx'),
            models.Index(fields=['employer_id', 'salary_category'], name='salary_scale_emp_cat_idx'),
        ]

    def __str__(self):
        return f"{self.salary_category} - {self.echelon} ({self.amount})"


class CalculationScale(models.Model):
    """Scale table header used by payroll deductions and progressive calculations."""

    code = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    employer_id = models.IntegerField(
        db_index=True,
        help_text='ID of the employer (from main database)'
    )
    branch = models.ForeignKey(
        'employees.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calculation_scales',
    )
    user_id = models.IntegerField(null=True, blank=True)
    year = models.CharField(max_length=10, null=True, blank=True)
    is_enable = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'calculation_scales'
        verbose_name = 'Calculation Scale'
        verbose_name_plural = 'Calculation Scales'
        ordering = ['name', 'code', 'id']
        indexes = [
            models.Index(fields=['employer_id', 'is_enable'], name='calc_scale_emp_enabled_idx'),
        ]

    def __str__(self):
        label = (self.name or '').strip() or (self.code or '').strip() or f"Scale #{self.pk}"
        if self.code and self.name and self.code.strip() != self.name.strip():
            return f"{self.name} ({self.code})"
        return label


class ScaleRange(models.Model):
    """A band/range row attached to a calculation scale."""

    range1 = models.FloatField(null=True, blank=True)
    range2 = models.FloatField(null=True, blank=True)
    calculation_scale = models.ForeignKey(
        'CalculationScale',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ranges',
    )
    coefficient = models.FloatField(null=True, blank=True)
    indice = models.FloatField(null=True, blank=True)
    base = models.FloatField(null=True, blank=True)
    employer_id = models.IntegerField(
        db_index=True,
        help_text='ID of the employer (from main database)'
    )
    branch = models.ForeignKey(
        'employees.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scale_ranges',
    )
    user_id = models.IntegerField(null=True, blank=True)
    year = models.CharField(max_length=10, null=True, blank=True)
    is_enable = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'scale_ranges'
        verbose_name = 'Scale Range'
        verbose_name_plural = 'Scale Ranges'
        ordering = ['calculation_scale_id', 'range1', 'range2', 'id']
        indexes = [
            models.Index(fields=['employer_id', 'is_enable'], name='scale_range_emp_enabled_idx'),
            models.Index(fields=['calculation_scale'], name='scale_range_scale_idx'),
        ]

    def __str__(self):
        start = self.range1 if self.range1 is not None else '-inf'
        end = self.range2 if self.range2 is not None else '+inf'
        return f"{self.calculation_scale_id or 'NoScale'}: {start} - {end}"


class ContractConfiguration(models.Model):
    """Merged contract configurations for an employer.
    If contract_type is null, these are global settings.
    If contract_type is set, these are overrides for that specific type.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    contract_type = models.CharField(
        max_length=20, 
        choices=Contract.CONTRACT_TYPE_CHOICES, 
        null=True, 
        blank=True,
        help_text='Null for global settings, or specific type for overrides'
    )
    
    # 1. Contract ID Format Configuration (Global primary)
    id_prefix = models.CharField(max_length=10, default='CNT')
    id_year_format = models.CharField(max_length=4, choices=[('YYYY', 'YYYY'), ('YY', 'YY')], default='YYYY')
    id_include_institution_code = models.BooleanField(default=False)
    id_sequence_padding = models.IntegerField(default=5)
    id_reset_sequence_yearly = models.BooleanField(default=True)
    last_sequence_number = models.IntegerField(default=0)
    
    # 2. Date & Time Rules 
    max_backdate_days = models.IntegerField(default=30)
    allow_future_contracts = models.BooleanField(default=True)
    min_fixed_term_duration_days = models.IntegerField(default=30)
    probation_must_end_before_contract = models.BooleanField(default=True)
    
    # 3. Contract Type Specific Fields (now in merged model)
    default_duration_months = models.IntegerField(null=True, blank=True)
    end_date_required = models.BooleanField(default=True)
    default_probation_period_months = models.IntegerField(default=3)
    overtime_eligible = models.BooleanField(default=True)
    default_notice_period_days = models.IntegerField(default=30)
    default_leave_policy = models.CharField(max_length=100, blank=True, null=True)
    
    default_template = models.ForeignKey(
        'ContractTemplate', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='configurations'
    )
    
    # 4. Compensation Rules Configuration
    min_wage = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_salary_without_approval = models.DecimalField(max_digits=12, decimal_places=2, default=1000000)
    salary_scale_enforcement = models.CharField(
        max_length=20, 
        choices=[('STRICT', 'Strict'), ('WARNING', 'Warning'), ('DISABLED', 'Disabled')],
        default='WARNING'
    )
    allow_salary_override = models.BooleanField(default=True)
    require_gross_salary_gt_zero = models.BooleanField(default=True)
    
    # 5. Allowance & Deduction Behavior Configuration
    allow_duplicate_allowances = models.BooleanField(default=False)
    auto_apply_default_allowances = models.BooleanField(default=True)
    allow_manual_allowances = models.BooleanField(default=True)
    allow_percentage_allowances = models.BooleanField(default=True)
    max_allowance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=50.00)
    
    # 6. Approval Workflow Configuration
    approval_enabled = models.BooleanField(default=False)
    requires_approval = models.BooleanField(default=False) # Type-specific override
    approval_levels = models.JSONField(default=list, blank=True, help_text='List of roles: ["HR", "FINANCE", "CEO"]')
    salary_thresholds = models.JSONField(default=dict, blank=True, help_text='Thresholds per level: {"FINANCE": 500000, "CEO": 1000000}')
    
    # 7. Signature & Document Rules Configuration
    signature_required = models.BooleanField(default=True)
    requires_signature = models.BooleanField(default=True) # Type-specific override
    signing_order = models.CharField(
        max_length=20,
        choices=[('EMPLOYEE_FIRST', 'Employee -> Employer'), ('EMPLOYER_FIRST', 'Employer -> Employee'), ('PARALLEL', 'Parallel')],
        default='EMPLOYEE_FIRST'
    )
    allow_activation_without_signature = models.BooleanField(default=False)
    signature_reminder_interval_days = models.IntegerField(default=3)
    signature_expiry_days = models.IntegerField(default=14)
    
    # 8. Contract Lifecycle Rules Configuration
    allow_concurrent_contracts_same_inst = models.BooleanField(default=False)
    allow_multi_institution_employment = models.BooleanField(default=False)
    auto_activate_on_start = models.BooleanField(default=True)
    auto_expire_fixed_term = models.BooleanField(default=True)
    auto_renew_option_available = models.BooleanField(default=False)
    expiry_grace_period_days = models.IntegerField(default=0)
    
    # 9. Notification Rules Configuration
    enable_notifications = models.BooleanField(default=True)
    days_before_expiry_notify = models.IntegerField(default=30)
    
    # Module-specific settings stored as JSON for flexibility
    recruitment_configuration = models.JSONField(default=dict, blank=True, help_text='Recruitment metadata defaults (application IDs, offer refs, etc.)')
    attendance_configuration = models.JSONField(default=dict, blank=True, help_text='Work rules (schedule type, shift template, attendance requirements)')
    time_off_configuration = models.JSONField(default=dict, blank=True, help_text='Leave policy defaults & overrides per leave type')
    payroll_configuration = models.JSONField(default=dict, blank=True, help_text='Compensation inputs (tax profile, CNPS, probation, proration)')
    expense_configuration = models.JSONField(default=dict, blank=True, help_text='Expense routing (policy, cost center, reimbursement)')
    fleet_configuration = models.JSONField(default=dict, blank=True, help_text='Fleet entitlements (vehicle, transport allowance)')
    signature_configuration = models.JSONField(default=dict, blank=True, help_text='Document & signature defaults (template, method, document hash)')
    governance_configuration = models.JSONField(default=dict, blank=True, help_text='Governance/audit defaults (approval/activation ownership)')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contract_configurations'
        verbose_name = 'Contract Configuration'
        verbose_name_plural = 'Contract Configurations'
        unique_together = [['employer_id', 'contract_type']]
        constraints = [
            models.UniqueConstraint(
                fields=['employer_id'],
                condition=Q(contract_type__isnull=True),
                name='uniq_contract_config_global_per_employer',
            ),
        ]

    def __str__(self):
        level = "Global" if self.contract_type is None else f"Type: {self.contract_type}"
        return f"Contract Config ({level}) - Employer: {self.employer_id}"


class ContractComponentBase(models.Model):
    """Base class for Allowances and Deductions"""
    
    TYPE_CHOICES = [
        ('FIXED', 'Fixed Amount'),
        ('PERCENTAGE', 'Percentage of Base Salary'),
    ]
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='%(class)ss', # allowances or deductions
        help_text='Contract this component belongs to'
    )
    
    name = models.CharField(
        max_length=255,
        help_text='Name of the allowance/deduction'
    )
    
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='FIXED',
        help_text='Type of calculation'
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Amount value (currency or percentage)'
    )

    code = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional business code for this component'
    )

    calculation_basis = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional calculation basis reference'
    )
    
    taxable = models.BooleanField(
        default=True,
        help_text='Is this component taxable?'
    )
    
    cnps_base = models.BooleanField(
        default=True,
        help_text='Is this component part of CNPS base?'
    )

    is_enable = models.BooleanField(
        default=True,
        help_text='Whether this component is enabled'
    )

    institution_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='Optional institution reference for imported payroll metadata'
    )

    component_branch_id = models.UUIDField(
        null=True,
        blank=True,
        help_text='Optional branch reference for imported payroll metadata'
    )

    component_user_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='Optional user reference for imported payroll metadata'
    )

    component_year = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text='Optional fiscal year reference (e.g., 2026)'
    )

    position = models.IntegerField(
        null=True,
        blank=True,
        help_text='Display/calculation order'
    )

    sys = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional system/integration marker'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()}) - {self.contract.contract_id}"


class Allowance(ContractComponentBase):
    """Allowance associated with a contract"""

    allowance_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='Optional reference to an allowance template or master list'
    )

    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text='Date when this allowance takes effect'
    )

    advantage = models.UUIDField(
        null=True,
        blank=True,
        help_text='Optional link to a payroll advantage catalog item'
    )

    advantage_type = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional advantage type label/code'
    )

    is_contribution = models.BooleanField(
        null=True,
        blank=True,
        help_text='Is this allowance included in contribution calculations?'
    )

    is_permanent = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this allowance is permanent'
    )

    is_variable = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this allowance varies over time'
    )

    is_manual = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this allowance is manually managed'
    )

    is_nature = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this is a benefit in kind'
    )

    is_nature_cnps = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether benefit-in-kind CNPS rules apply'
    )

    majoration = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Optional allowance uplift/majoration rule'
    )

    cnps_majoration = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Optional CNPS-specific majoration rule'
    )

    taux = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Optional rate used for calculations'
    )

    class Meta(ContractComponentBase.Meta):
        db_table = 'contract_allowances'
        verbose_name = 'Allowance'
        verbose_name_plural = 'Allowances'


class Deduction(ContractComponentBase):
    """Deduction associated with a contract"""

    deduction_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='Optional reference to a deduction template or master list'
    )

    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text='Date when this deduction takes effect'
    )

    affectation = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional payroll affectation/impact area'
    )

    deduction_type = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional deduction type label/code'
    )

    deduction_basis = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional deduction basis reference'
    )

    deduction_base = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional upstream/base deduction reference'
    )

    is_employee = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this deduction applies to the employee share'
    )

    is_employer = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this deduction applies to the employer share'
    )

    is_scale = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether scale table calculation is used'
    )

    is_rate = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether rate-based calculation is used'
    )

    is_base = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this deduction acts as a base for others'
    )

    is_count = models.BooleanField(
        null=True,
        blank=True,
        help_text='Whether this deduction is included in totals'
    )

    calculation_scale = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional calculation scale reference'
    )

    employee_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Optional employee-side deduction rate'
    )

    employer_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Optional employer-side deduction rate'
    )

    partner = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional beneficiary/partner institution'
    )

    class Meta(ContractComponentBase.Meta):
        db_table = 'contract_deductions'
        verbose_name = 'Deduction'
        verbose_name_plural = 'Deductions'


class ContractElement(models.Model):
    """
    Payroll element generated from contract components.
    Exactly one of advantage or deduction must be set.
    """

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='elements',
        help_text='Contract this payroll element belongs to'
    )

    deduction = models.ForeignKey(
        Deduction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='elements',
        help_text='Deduction definition applied for this element'
    )

    advantage = models.ForeignKey(
        Allowance,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='elements',
        help_text='Advantage/allowance definition applied for this element'
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Calculated or manual amount for this element and period'
    )

    year = models.CharField(
        max_length=10,
        help_text='Year this element applies to (e.g., 2026)'
    )

    month = models.CharField(
        max_length=10,
        help_text='Month this element applies to (e.g., 01)'
    )

    employee_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Optional employee-side rate snapshot for this period'
    )

    employer_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Optional employer-side rate snapshot for this period'
    )

    institution_id = models.IntegerField(
        db_index=True,
        help_text='Employer/institution identifier owning this element'
    )

    branch = models.ForeignKey(
        'employees.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contract_elements',
        help_text='Optional branch scope for this element'
    )

    user_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='User that created/generated this element'
    )

    is_enable = models.BooleanField(
        default=True,
        help_text='Whether this element is active for payroll calculations'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contract_elements'
        verbose_name = 'Contract Element'
        verbose_name_plural = 'Contract Elements'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contract', 'year', 'month']),
            models.Index(fields=['institution_id', 'is_enable']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(advantage__isnull=False) & models.Q(deduction__isnull=True))
                    | (models.Q(advantage__isnull=True) & models.Q(deduction__isnull=False))
                ),
                name='contract_element_exactly_one_component',
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.advantage_id) == bool(self.deduction_id):
            raise ValidationError('Exactly one of advantage or deduction must be set.')

        if self.advantage_id and self.contract_id and self.advantage and self.advantage.contract_id != self.contract_id:
            raise ValidationError('Advantage must belong to the same contract as the element.')

        if self.deduction_id and self.contract_id and self.deduction and self.deduction.contract_id != self.contract_id:
            raise ValidationError('Deduction must belong to the same contract as the element.')

    def __str__(self):
        target = self.advantage or self.deduction
        label = getattr(target, 'name', 'Unknown')
        return f"{self.contract.contract_id} - {label} ({self.year}-{self.month})"


class ContractAudit(models.Model):
    """Audit log for contract status changes"""
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=50)
    performed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        db_constraint=False, # Allow cross-DB relation (User is in default DB)
        help_text='User who performed the action'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True, null=True, help_text='JSON metadata for the action')

    # Deprecated: use metadata instead
    details = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        db_table = 'contract_audits'


class ContractTemplate(models.Model):
    """Template for generating contract documents"""
    
    # Multitenancy support
    employer_id = models.IntegerField(db_index=True, help_text='ID of the employer (from main database)')
    
    name = models.CharField(max_length=255, help_text='Name of the template')

    category = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Optional category label for organizing templates'
    )

    version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='Optional version label (e.g., v1, 2026-02)'
    )
    
    contract_type = models.CharField(
        max_length=20,
        choices=Contract.CONTRACT_TYPE_CHOICES,
        help_text='Type of contract this template applies to'
    )
    
    file = models.FileField(
        upload_to='contract_templates/',
        help_text='Template file (DOCX, PDF, etc.)',
        blank=True,
        null=True
    )

    # Optional editable body override (used when regenerating default PDF templates)
    body_override = models.TextField(blank=True, null=True)
    
    is_default = models.BooleanField(
        default=False,
        help_text='Use as default template for this contract type'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contract_templates'
        verbose_name = 'Contract Template'
        verbose_name_plural = 'Contract Templates'
        ordering = ['-created_at']
        
    def __str__(self):
        label = f"{self.name} ({self.get_contract_type_display()})"
        if self.version:
            label = f"{label} v{self.version}" if not str(self.version).lower().startswith('v') else f"{label} {self.version}"
        return label
    
    def save(self, *args, **kwargs):
        # Ensure only one default per contract type per employer
        if self.is_default:
            # We need to assume this runs in tenant context or we need to pass using alias
            # But normally save() is called on an instance that is already tied to a DB or default
            # For robustness in tenant context:
            db_alias = self._state.db or 'default'
            
            ContractTemplate.objects.using(db_alias).filter(
                employer_id=self.employer_id,
                contract_type=self.contract_type,
                is_default=True
            ).exclude(id=self.id).update(is_default=False)
            
        super().save(*args, **kwargs)


class ContractDocument(models.Model):
    """Generated contract document (PDF/DOCX)"""
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='documents',
        help_text='Contract this document belongs to'
    )
    
    generated_from = models.ForeignKey(
        ContractTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Template used to generate this document'
    )
    
    name = models.CharField(max_length=255, help_text='Display name of the document')
    
    file = models.FileField(
        upload_to='contract_documents/',
        help_text='The generated document file'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'contract_documents'
        verbose_name = 'Contract Document'
        verbose_name_plural = 'Contract Documents'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.name} - {self.contract.contract_id}"


class ContractTemplateVersion(models.Model):
    """Snapshot of a contract template version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        ContractTemplate,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True, null=True)
    version = models.CharField(max_length=50, blank=True, null=True)
    contract_type = models.CharField(max_length=20, choices=Contract.CONTRACT_TYPE_CHOICES)
    body_override = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='contract_templates/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contract_template_versions'
        verbose_name = 'Contract Template Version'
        verbose_name_plural = 'Contract Template Versions'
        ordering = ['-created_at']

    def __str__(self):
        label = f"{self.name} ({self.contract_type})"
        if self.version:
            label = f"{label} v{self.version}" if not str(self.version).lower().startswith('v') else f"{label} {self.version}"
        return label


class ContractSignature(models.Model):
    """Audit trail for contract signatures"""
    
    ROLE_CHOICES = [
        ('EMPLOYEE', 'Employee'),
        ('EMPLOYER', 'Employer'),
    ]
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='signatures',
        help_text='Contract being signed'
    )
    
    signer_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False, # Cross-DB if needed, though usually same context for now? 
                             # Actually user is in default, contract in tenant.
        help_text='User who signed (optional for magic links)'
    )
    
    signer_name = models.CharField(max_length=255, help_text='Typed name of the signer')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    signature_text = models.CharField(max_length=255, help_text='Text or representation of signature')

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    signature_method = models.CharField(
        max_length=20,
        choices=SIGNATURE_METHOD_CHOICES,
        null=True,
        blank=True,
        help_text='Method used to obtain this signature'
    )

    signature_audit_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional audit trail reference'
    )

    signed_document = models.ForeignKey(
        'ContractDocument',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='signatures',
        help_text='Document that was signed'
    )

    document_hash = models.CharField(max_length=64, help_text='SHA256 hash of the document signed')

    signed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'contract_signatures'
        verbose_name = 'Contract Signature'
        verbose_name_plural = 'Contract Signatures'
        ordering = ['signed_at']
        
    def __str__(self):
        return f"{self.signer_name} ({self.get_role_display()}) - {self.contract.contract_id}"


class ContractAmendment(models.Model):
    """
    Tracks amendments to a contract (version history).
    Stores changed fields and effective date.
    """
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='amendments',
        help_text='Contract being amended'
    )
    
    amendment_number = models.IntegerField(
        help_text='Sequential number of the amendment (1, 2, 3...)'
    )
    
    changed_fields = models.JSONField(
        default=dict,
        help_text='JSON Structure of changed fields (e.g., {"base_salary": {"old": 500000, "new": 550000}})'
    )
    
    effective_date = models.DateField(help_text='Date when this amendment takes effect')
    
    document = models.FileField(
        upload_to='contract_amendments/',
        null=True,
        blank=True,
        help_text='Amendment document (PDF/DOCX)'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        help_text='User who created the amendment'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'contract_amendments'
        verbose_name = 'Contract Amendment'
        verbose_name_plural = 'Contract Amendments'
        ordering = ['amendment_number']
        unique_together = [['contract', 'amendment_number']]
        
    def __str__(self):
        return f"Amendment #{self.amendment_number} - {self.contract.contract_id}"
