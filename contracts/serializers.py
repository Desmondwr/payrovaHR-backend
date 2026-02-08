from rest_framework import serializers
from decimal import Decimal
from .models import (
    Contract, Allowance, Deduction, ContractAmendment,
    ContractConfiguration, SalaryScale, ContractTemplate, ContractTemplateVersion
)
from timeoff.defaults import merge_time_off_defaults, validate_time_off_config
from accounts.rbac import get_active_employer, is_delegate_user
from .configuration_defaults import CONFIGURATION_MERGE_FUNCTIONS
from .payroll_sync import sync_contract_payroll_elements

class AllowanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allowance
        exclude = ('contract', 'created_at', 'updated_at')
        read_only_fields = ('id',)

class DeductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deduction
        exclude = ('contract', 'created_at', 'updated_at')
        read_only_fields = ('id',)

class SalaryScaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryScale
        fields = '__all__'
        read_only_fields = ('id', 'employer_id', 'created_at', 'updated_at')

    def create(self, validated_data):
        tenant_db = self.context.get('tenant_db')
        if tenant_db:
            return SalaryScale.objects.using(tenant_db).create(**validated_data)
        return super().create(validated_data)


class ContractTemplateSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ContractTemplate
        fields = [
            'id',
            'employer_id',
            'name',
            'category',
            'version',
            'contract_type',
            'file',
            'file_url',
            'body_override',
            'is_default',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ('id', 'employer_id', 'created_at', 'updated_at', 'file_url')

    def get_file_url(self, obj):
        if not obj.file:
            return None
        try:
            url = obj.file.url
        except Exception:
            return None
        request = self.context.get('request')
        if request:
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def create(self, validated_data):
        tenant_db = self.context.get('tenant_db')
        if tenant_db:
            return ContractTemplate.objects.using(tenant_db).create(**validated_data)
        return super().create(validated_data)


class ContractTemplateVersionSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ContractTemplateVersion
        fields = [
            'id',
            'template',
            'name',
            'category',
            'version',
            'contract_type',
            'body_override',
            'file',
            'file_url',
            'created_at',
        ]
        read_only_fields = ('id', 'created_at', 'file_url')

    def get_file_url(self, obj):
        if not obj.file:
            return None
        try:
            url = obj.file.url
        except Exception:
            return None
        request = self.context.get('request')
        if request:
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

class ContractSerializer(serializers.ModelSerializer):
    allowances = AllowanceSerializer(many=True, required=False, allow_null=True)
    deductions = DeductionSerializer(many=True, required=False, allow_null=True)
    gross_salary = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)

    class Meta:
        model = Contract
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'employer_id', 'created_by', 'gross_salary')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        tenant_db = 'default'
        instance = self.instance
        is_list_instance = isinstance(instance, (list, tuple))

        if request and hasattr(request, 'user'):
            from accounts.database_utils import get_tenant_database_alias
            from employees.models import Employee, Branch, Department
            employer = None
            if getattr(request.user, 'employer_profile', None):
                employer = request.user.employer_profile
            else:
                resolved = get_active_employer(request, require_context=False)
                if resolved and is_delegate_user(request.user, resolved.id):
                    employer = resolved

            if employer:
                tenant_db = get_tenant_database_alias(employer)
            
            # Set dynamic querysets for tenant-aware relational fields
            if 'employee' in self.fields:
                self.fields['employee'].queryset = Employee.objects.using(tenant_db).all()
            if 'branch' in self.fields:
                self.fields['branch'].queryset = Branch.objects.using(tenant_db).all()
            if 'department' in self.fields:
                self.fields['department'].queryset = Department.objects.using(tenant_db).all()
        elif instance and not is_list_instance:
            tenant_db = instance._state.db or tenant_db

        if 'previous_contract' in self.fields:
            self.fields['previous_contract'].queryset = Contract.objects.using(tenant_db).all()
        if 'salary_scale' in self.fields:
            self.fields['salary_scale'].queryset = SalaryScale.objects.using(tenant_db).all()

    def _get_config_context(self, data):
        """
        Resolve the effective contract configuration getter and tenant DB alias
        for the current request/employer.
        """
        contract_type = data.get('contract_type') or (self.instance.contract_type if self.instance else None)
        request = self.context.get('request')
        employer_id = None
        tenant_db = 'default'

        if request and hasattr(request, 'user'):
            from accounts.database_utils import get_tenant_database_alias
            employer = None
            if getattr(request.user, 'employer_profile', None):
                employer = request.user.employer_profile
            else:
                resolved = get_active_employer(request, require_context=False)
                if resolved and is_delegate_user(request.user, resolved.id):
                    employer = resolved
            if employer:
                employer_id = employer.id
                tenant_db = get_tenant_database_alias(employer)
        elif self.instance:
            employer_id = getattr(self.instance, 'employer_id', None)
            tenant_db = self.instance._state.db or 'default'

        global_config = None
        type_config = None
        if employer_id:
            global_config, type_config = Contract.get_config_for(
                employer_id=employer_id,
                contract_type=contract_type,
                db_alias=tenant_db
            )

        def get_value(field, default=None):
            if type_config and getattr(type_config, field) is not None:
                return getattr(type_config, field)
            if global_config and getattr(global_config, field) is not None:
                return getattr(global_config, field)
            return default

        return get_value, tenant_db

    def validate(self, data):
        """
        Validate that there are no overlapping active contracts for the same employee
        """
        def add_error(field, message):
            if field in errors:
                if isinstance(errors[field], list):
                    errors[field].append(message)
                else:
                    errors[field] = [errors[field], message]
            else:
                errors[field] = message

        errors = {}
        config_get, tenant_db = self._get_config_context(data)

        # Resolve core fields from incoming data or existing instance during updates
        employee = data.get('employee') or getattr(self.instance, 'employee', None)
        status = data.get('status', getattr(self.instance, 'status', 'DRAFT'))
        start_date = data.get('start_date') if 'start_date' in data else getattr(self.instance, 'start_date', None)
        end_date = data.get('end_date') if 'end_date' in data else getattr(self.instance, 'end_date', None)
        base_salary = data.get('base_salary', getattr(self.instance, 'base_salary', None))
        salary_scale = data.get('salary_scale') or getattr(self.instance, 'salary_scale', None)

        # Only check if status is active/signed/pending and we have start date
        allow_concurrent = config_get('allow_concurrent_contracts_same_inst', False)
        if not allow_concurrent and status in ['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE'] and start_date and employee:
            # Query existing contracts for this employee
            existing_contracts = Contract.objects.using(tenant_db).filter(
                employee=employee,
                status__in=['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE']
            )
            
            # If updating, exclude the current instance
            if self.instance:
                existing_contracts = existing_contracts.exclude(id=self.instance.id)
            
            # Check for overlap
            for existing in existing_contracts:
                exist_start = existing.start_date
                exist_end = existing.end_date
                
                # Logic 1: If both have end dates, check overlap
                if end_date and exist_end:
                     if start_date <= exist_end and end_date >= exist_start:
                         add_error(
                             'start_date',
                             f"Overlapping contract exists: {existing.contract_id} ({exist_start} - {exist_end})"
                         )
                         break
                
                # Logic 2: If existing is permanent (no end date)
                elif not exist_end:
                    if end_date:
                         if end_date >= exist_start:
                              add_error(
                                 'start_date',
                                 f"Overlapping permanent contract exists: {existing.contract_id} (Starts {exist_start})"
                             )
                              break
                    else:
                         add_error(
                             'start_date',
                             f"Employee already has a permanent contract: {existing.contract_id}"
                         )
                         break
                         
                # Logic 3: If new one is permanent (no end date)
                elif not end_date:
                    if exist_end and start_date <= exist_end:
                         add_error(
                             'start_date',
                             f"Cannot start permanent contract during existing contract: {existing.contract_id}"
                         )
                         break

        allowances_data = data.get('allowances', None)
        allow_manual = config_get('allow_manual_allowances', True)
        if allowances_data and not allow_manual:
            add_error('allowances', 'Manual allowances are disabled by configuration.')

        allow_duplicates = config_get('allow_duplicate_allowances', False)
        if allowances_data and not allow_duplicates:
            seen = set()
            duplicates = set()
            for allowance in allowances_data:
                key = (allowance.get('name') or '').strip().lower()
                if not key:
                    continue
                if key in seen:
                    duplicates.add(allowance.get('name') or key)
                seen.add(key)
            if duplicates:
                add_error('allowances', f"Duplicate allowances are not allowed: {', '.join(sorted(duplicates))}.")

        allow_pct = config_get('allow_percentage_allowances', True)
        max_pct = config_get('max_allowance_percentage')
        if allowances_data:
            if allow_pct is not None and not allow_pct:
                if any((a.get('type') or '').upper() == 'PERCENTAGE' for a in allowances_data):
                    add_error('allowances', 'Percentage-based allowances are not allowed by configuration.')
            if max_pct is not None:
                total_pct = sum(
                    Decimal(str(a.get('amount'))) for a in allowances_data
                    if (a.get('type') or '').upper() == 'PERCENTAGE' and a.get('amount') is not None
                )
                if total_pct > max_pct:
                    add_error(
                        'allowances',
                        f"Total percentage allowances exceed the maximum allowed ({max_pct}%)."
                    )

        require_gross_gt_zero = config_get('require_gross_salary_gt_zero')
        if require_gross_gt_zero:
            gross_total = Decimal(str(base_salary or 0))
            if allowances_data is not None:
                for allowance in allowances_data:
                    try:
                        amount = Decimal(str(allowance.get('amount') or 0))
                    except Exception:
                        amount = Decimal('0')
                    if (allowance.get('type') or '').upper() == 'PERCENTAGE':
                        try:
                            gross_total += (Decimal(str(base_salary or 0)) * amount / Decimal('100'))
                        except Exception:
                            pass
                    else:
                        gross_total += amount
            elif self.instance:
                try:
                    gross_total = self.instance.gross_salary
                except Exception:
                    pass
            if gross_total <= 0:
                add_error('base_salary', 'Gross salary must be greater than zero.')

        allow_salary_override = config_get('allow_salary_override', True)
        salary_scale_enforcement = config_get('salary_scale_enforcement', 'WARNING')

        if salary_scale_enforcement == 'STRICT' and not salary_scale:
            add_error('salary_scale', 'Salary scale is required by configuration.')
        if salary_scale and allow_salary_override is not None and not allow_salary_override:
            if base_salary is not None and salary_scale.amount != base_salary:
                add_error(
                    'base_salary',
                    'Base salary must match the selected salary scale when overrides are disabled.'
                )

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        allowances_data = validated_data.pop('allowances', [])
        deductions_data = validated_data.pop('deductions', [])
        if allowances_data is None:
            allowances_data = []
        if deductions_data is None:
            deductions_data = []

        # Apply default duration if end_date is missing and config provides a default.
        try:
            config_get, _tenant_db = self._get_config_context(validated_data)
            start_date = validated_data.get('start_date')
            end_date = validated_data.get('end_date')
            contract_type = (validated_data.get('contract_type') or '').upper()
            default_months = config_get('default_duration_months')
            if start_date and not end_date and default_months and contract_type != 'PERMANENT':
                import calendar

                months = int(default_months)
                if months > 0:
                    year = start_date.year + (start_date.month - 1 + months) // 12
                    month = (start_date.month - 1 + months) % 12 + 1
                    day = min(start_date.day, calendar.monthrange(year, month)[1])
                    validated_data['end_date'] = start_date.replace(year=year, month=month, day=day)
        except Exception:
            # Default duration is best-effort; validation will catch missing/invalid end dates.
            pass
        
        # Set tenant and user context automatically
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            from accounts.database_utils import get_tenant_database_alias
            employer = None
            if getattr(request.user, 'employer_profile', None):
                employer = request.user.employer_profile
            else:
                resolved = get_active_employer(request, require_context=False)
                if resolved and is_delegate_user(request.user, resolved.id):
                    employer = resolved

            if employer:
                validated_data['employer_id'] = employer.id
                validated_data['created_by'] = request.user.id
                
                tenant_db = get_tenant_database_alias(employer)
                contract = Contract.objects.using(tenant_db).create(**validated_data)
            
                # Create nested objects
                for allowance_data in allowances_data:
                    Allowance.objects.using(tenant_db).create(contract=contract, **allowance_data)
                    
                for deduction_data in deductions_data:
                    Deduction.objects.using(tenant_db).create(contract=contract, **deduction_data)

                sync_contract_payroll_elements(contract, tenant_db=tenant_db)
                    
                return contract
            
        return super().create(validated_data)

    def update(self, instance, validated_data):
        allowances_data = validated_data.pop('allowances', None)
        deductions_data = validated_data.pop('deductions', None)
        base_salary_changed = (
            'base_salary' in validated_data
            and validated_data.get('base_salary') != instance.base_salary
        )
        
        # Get tenant DB
        request = self.context.get('request')
        tenant_db = 'default'
        if request and hasattr(request, 'user'):
            from accounts.database_utils import get_tenant_database_alias
            employer = None
            if getattr(request.user, 'employer_profile', None):
                employer = request.user.employer_profile
            else:
                resolved = get_active_employer(request, require_context=False)
                if resolved and is_delegate_user(request.user, resolved.id):
                    employer = resolved
            if employer:
                tenant_db = get_tenant_database_alias(employer)

        # Update contract fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=tenant_db)

        # Update nested allowances if provided
        if allowances_data is not None:
            # Delete existing
            instance.allowances.all().using(tenant_db).delete()
            # Create new
            for allowance_data in allowances_data:
                Allowance.objects.using(tenant_db).create(contract=instance, **allowance_data)

        # Update nested deductions if provided
        if deductions_data is not None:
             # Delete existing
            instance.deductions.all().using(tenant_db).delete()
            # Create new
            for deduction_data in deductions_data:
                Deduction.objects.using(tenant_db).create(contract=instance, **deduction_data)

        sync_contract_payroll_elements(
            instance,
            tenant_db=tenant_db,
            sync_allowances=allowances_data is not None or base_salary_changed,
            sync_deductions=deductions_data is not None,
        )

        return instance

class ContractAmendmentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = ContractAmendment
        exclude = ('contract',)
        read_only_fields = ('amendment_number', 'created_by', 'created_at', 'created_by_name')
        
    def create(self, validated_data):
        # We need to handle this manually in the ViewSet or here
        # But typically we need the contract context which is not in validated_data yet
        return super().create(validated_data)


class ContractConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractConfiguration
        fields = '__all__'
        read_only_fields = ('id', 'employer_id', 'created_at', 'updated_at')

    def validate_time_off_configuration(self, value):
        merged = merge_time_off_defaults(value or {})
        errors = validate_time_off_config(merged)
        if errors:
            raise serializers.ValidationError(errors)
        return merged

    def _normalize_json_sections(self, data, include_missing=False):
        for field, merge_fn in CONFIGURATION_MERGE_FUNCTIONS.items():
            if field in data:
                data[field] = merge_fn(data[field])
            elif include_missing:
                data[field] = merge_fn(None)

    def create(self, validated_data):
        validated_data['time_off_configuration'] = merge_time_off_defaults(
            validated_data.get('time_off_configuration', {})
        )
        self._normalize_json_sections(validated_data, include_missing=True)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'time_off_configuration' in validated_data:
            validated_data['time_off_configuration'] = merge_time_off_defaults(
                validated_data.get('time_off_configuration', {})
            )
        self._normalize_json_sections(validated_data, include_missing=False)
        return super().update(instance, validated_data)
