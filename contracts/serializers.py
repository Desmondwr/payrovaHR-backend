from rest_framework import serializers
from .models import (
    Contract, Allowance, Deduction, ContractAmendment, 
    ContractConfiguration
)

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

class ContractSerializer(serializers.ModelSerializer):
    allowances = AllowanceSerializer(many=True, required=False)
    deductions = DeductionSerializer(many=True, required=False)
    gross_salary = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Contract
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'employer_id', 'created_by', 'gross_salary')

    def validate(self, data):
        """
        Validate that there are no overlapping active contracts for the same employee
        """
        from django.db.models import Q
        
        employee = data.get('employee')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        status = data.get('status', 'DRAFT')
        
        # Only check if status is active/signed/pending and we have start date
        if status in ['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE'] and start_date:
            request = self.context.get('request')
            if request and hasattr(request, 'user') and hasattr(request.user, 'employer_profile'):
                from accounts.database_utils import get_tenant_database_alias
                tenant_db = get_tenant_database_alias(request.user.employer_profile)
                
                # Query existing contracts for this employee
                existing_contracts = Contract.objects.using(tenant_db).filter(
                    employee=employee,
                    status__in=['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE']
                )
                
                # If updating, exclude the current instance
                if self.instance:
                    existing_contracts = existing_contracts.exclude(id=self.instance.id)
                
                # Check for overlap
                # Overlap logic: (StartA <= EndB) and (EndA >= StartB)
                # If EndB is null (permanent), use a far future date or handle Logic
                
                for existing in existing_contracts:
                    # Determine existing range
                    exist_start = existing.start_date
                    exist_end = existing.end_date
                    
                    # Logic 1: If both have end dates, check overlap
                    if end_date and exist_end:
                         if start_date <= exist_end and end_date >= exist_start:
                             raise serializers.ValidationError(
                                 f"Overlapping contract exists: {existing.contract_id} ({exist_start} - {exist_end})"
                             )
                    
                    # Logic 2: If existing is permanent (no end date)
                    # New start date must be after existing start date? 
                    # Actually if one is permanent, they overlap if the new one starts after existing starts
                    elif not exist_end:
                        if end_date:
                             # New one ends after permanent one starts -> overlap
                             if end_date >= exist_start:
                                  raise serializers.ValidationError(
                                     f"Overlapping permanent contract exists: {existing.contract_id} (Starts {exist_start})"
                                 )
                        else:
                             # Both permanent -> overlap
                             raise serializers.ValidationError(
                                 f"Employee already has a permanent contract: {existing.contract_id}"
                             )
                             
                    # Logic 3: If new one is permanent (no end date)
                    elif not end_date:
                        if exist_end:
                             # New permanent starts before existing ends -> overlap
                             if start_date <= exist_end:
                                  raise serializers.ValidationError(
                                     f"Cannot start permanent contract during existing contract: {existing.contract_id}"
                                 )

        return data

    def create(self, validated_data):
        allowances_data = validated_data.pop('allowances', [])
        deductions_data = validated_data.pop('deductions', [])
        
        # Set tenant and user context automatically
        request = self.context.get('request')
        if request and hasattr(request, 'user') and hasattr(request.user, 'employer_profile'):
            from accounts.database_utils import get_tenant_database_alias
            
            validated_data['employer_id'] = request.user.employer_profile.id
            validated_data['created_by'] = request.user.id
            
            tenant_db = get_tenant_database_alias(request.user.employer_profile)
            contract = Contract.objects.using(tenant_db).create(**validated_data)
            
            # Create nested objects
            for allowance_data in allowances_data:
                Allowance.objects.using(tenant_db).create(contract=contract, **allowance_data)
                
            for deduction_data in deductions_data:
                Deduction.objects.using(tenant_db).create(contract=contract, **deduction_data)
                
            return contract
            
        return super().create(validated_data)

    def update(self, instance, validated_data):
        allowances_data = validated_data.pop('allowances', None)
        deductions_data = validated_data.pop('deductions', None)
        
        # Get tenant DB
        request = self.context.get('request')
        tenant_db = 'default'
        if request and hasattr(request, 'user') and hasattr(request.user, 'employer_profile'):
             from accounts.database_utils import get_tenant_database_alias
             tenant_db = get_tenant_database_alias(request.user.employer_profile)

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
