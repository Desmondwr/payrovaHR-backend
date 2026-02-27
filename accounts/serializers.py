from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .models import (
    User,
    ActivationToken,
    EmployerProfile,
    EmployeeRegistry,
    EmployeeMembership,
    Permission,
    Role,
    RolePermission,
    EmployeeRole,
    UserPermissionOverride,
)



# ...existing code...

class EmployerProfileSerializer(serializers.ModelSerializer):
    """Serializer for EmployerProfile model"""
    class Meta:
        model = EmployerProfile
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')
    def validate(self, data):
        if self.instance is None and not self.partial:
            missing = {}
            if not data.get("company_logo"):
                missing["company_logo"] = "Company logo is required."
            if not data.get("company_size"):
                missing["company_size"] = "Company size is required."
            if missing:
                raise serializers.ValidationError(missing)
        return data
    def create(self, validated_data):
        user = self.context['request'].user
        # Check if profile already exists
        if hasattr(user, 'employer_profile'):
            raise serializers.ValidationError("Employer profile already exists.")
        # Create profile
        profile = EmployerProfile.objects.create(user=user, **validated_data)
        # Mark profile as completed
        user.profile_completed = True
        if not user.is_employer_owner:
            user.is_employer_owner = True
        user.save()
        return profile
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        # Ensure profile is marked as completed
        if not instance.user.profile_completed:
            instance.user.profile_completed = True
        if not instance.user.is_employer_owner:
            instance.user.is_employer_owner = True
        instance.user.save()
        return instance

class EmployerListSerializer(serializers.ModelSerializer):
    """Serializer for listing employers with their profile"""
    employer_profile = EmployerProfileSerializer(read_only=True)
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'is_employer', 'is_active', 'created_at', 'employer_profile')
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    
    class Meta:
        model = User
        fields = (
            'id', 'email', 'first_name', 'last_name', 'is_admin', 'is_employer',
            'is_employee', 'profile_completed', 'two_factor_enabled',
            'last_active_employer_id', 'created_at'
        )
        read_only_fields = ('id', 'created_at')


class CreateEmployerSerializer(serializers.Serializer):
    """Serializer for creating employer account by admin"""
    
    email = serializers.EmailField()
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def create(self, validated_data):
        # Create inactive user
        user = User.objects.create_user(
            email=validated_data['email'],
            is_employer=True,
            is_active=False
        )
        
        # Create activation token
        activation_token = ActivationToken.objects.create(user=user)
        
        return user, activation_token


class ActivateAccountSerializer(serializers.Serializer):
    """Serializer for account activation"""
    
    token = serializers.CharField(max_length=100)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        # Check if passwords match
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        # Validate activation token
        try:
            activation_token = ActivationToken.objects.get(token=data['token'])
        except ActivationToken.DoesNotExist:
            raise serializers.ValidationError({"token": "Invalid activation token."})
        
        # Check if token is valid
        if not activation_token.is_valid():
            if activation_token.is_used:
                raise serializers.ValidationError({"token": "This activation token has already been used."})
            else:
                raise serializers.ValidationError({"token": "This activation token has expired."})
        
        # Check if user is already active
        if activation_token.user.is_active:
            raise serializers.ValidationError({"token": "This account is already activated."})
        
        data['activation_token'] = activation_token
        return data
    
    def save(self):
        activation_token = self.validated_data['activation_token']
        user = activation_token.user
        
        # Set password and activate user
        user.set_password(self.validated_data['password'])
        user.is_active = True
        user.save()
        
        # Mark token as used
        activation_token.is_used = True
        activation_token.save()
        
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    two_factor_code = serializers.CharField(max_length=6, required=False, allow_blank=True)
    
    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        two_factor_code = data.get('two_factor_code', '')
        
        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email or password."})
        
        # Authenticate user first
        user = authenticate(username=email, password=password)
        if user is None:
            raise serializers.ValidationError({"email": "Invalid email or password."})
        
        # Check if account is active (not disabled by admin)
        if not user.is_active:
            raise serializers.ValidationError({"email": "Your account has been disabled. Please contact the administrator."})
        
        # Check 2FA if enabled
        if user.two_factor_enabled:
            if not two_factor_code:
                raise serializers.ValidationError({
                    "two_factor_code": "2FA is enabled. Please provide authentication code.",
                    "requires_2fa": True
                })
            
            from .utils import verify_totp_code
            if not verify_totp_code(user.two_factor_secret, two_factor_code):
                raise serializers.ValidationError({"two_factor_code": "Invalid authentication code."})
        
        data['user'] = user
        return data


class EmployerProfileSerializer(serializers.ModelSerializer):
    """Serializer for EmployerProfile model"""
    
    class Meta:
        model = EmployerProfile
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')
    
    def validate(self, data):
        if self.instance is None and not self.partial:
            missing = {}
            if not data.get("company_logo"):
                missing["company_logo"] = "Company logo is required."
            if not data.get("company_size"):
                missing["company_size"] = "Company size is required."
            if missing:
                raise serializers.ValidationError(missing)
        return data
    
    def create(self, validated_data):
        user = self.context['request'].user
        
        # Check if profile already exists
        if hasattr(user, 'employer_profile'):
            raise serializers.ValidationError("Employer profile already exists.")
        
        # Create profile
        profile = EmployerProfile.objects.create(user=user, **validated_data)
        
        # Mark profile as completed
        user.profile_completed = True
        if not user.is_employer_owner:
            user.is_employer_owner = True
        user.save()
        
        return profile
    
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Ensure profile is marked as completed
        if not instance.user.profile_completed:
            instance.user.profile_completed = True
        if not instance.user.is_employer_owner:
            instance.user.is_employer_owner = True
        instance.user.save()
        
        return instance


class EmployerPublicProfileSerializer(serializers.ModelSerializer):
    """Public-safe serializer for EmployerProfile"""

    class Meta:
        model = EmployerProfile
        fields = (
            'id',
            'company_name',
            'employer_name_or_group',
            'slug',
            'company_logo',
            'company_tagline',
            'company_overview',
            'company_mission',
            'company_values',
            'company_benefits',
            'company_website',
            'company_size',
            'careers_email',
            'linkedin_url',
            'company_location',
            'physical_address',
            'industry_sector',
            'organization_type',
            'date_of_incorporation',
            'phone_number',
        )


class Enable2FASerializer(serializers.Serializer):
    """Serializer for enabling 2FA"""
    
    verification_code = serializers.CharField(max_length=6)
    
    def validate(self, data):
        user = self.context['request'].user
        
        if user.two_factor_enabled:
            raise serializers.ValidationError("2FA is already enabled.")
        
        if not hasattr(user, 'two_factor_secret') or not user.two_factor_secret:
            raise serializers.ValidationError("2FA secret not generated. Please setup 2FA first.")
        
        # Verify the code
        from .utils import verify_totp_code
        if not verify_totp_code(user.two_factor_secret, data['verification_code']):
            raise serializers.ValidationError({"verification_code": "Invalid verification code."})
        
        return data


class Disable2FASerializer(serializers.Serializer):
    """Serializer for disabling 2FA"""
    
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        user = self.context['request'].user
        
        if not user.two_factor_enabled:
            raise serializers.ValidationError("2FA is not enabled.")
        
        # Verify password
        if not user.check_password(data['password']):
            raise serializers.ValidationError({"password": "Invalid password."})
        
        return data


class EmployeeRegistrySerializer(serializers.ModelSerializer):
    """Serializer for EmployeeRegistry model (central cross-institutional registry)"""
    
    class Meta:
        model = EmployeeRegistry
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')
    
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class RequestPasswordResetSerializer(serializers.Serializer):
    """Serializer for requesting password reset code"""
    
    email = serializers.EmailField()
    
    def validate_email(self, value):
        # Check if user exists
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No account found with this email address.")
        return value


class VerifyResetCodeSerializer(serializers.Serializer):
    """Serializer for verifying reset code and setting new password"""
    
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        # Check if passwords match
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        # Check if user exists
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "No account found with this email address."})
        
        return data


class ResendResetCodeSerializer(serializers.Serializer):
    """Serializer for resending password reset code"""
    
    email = serializers.EmailField()
    
    def validate_email(self, value):
        # Check if user exists
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No account found with this email address.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password (authenticated users)"""
    
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    confirm_new_password = serializers.CharField(write_only=True, required=True)
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
    
    def validate(self, data):
        # Check if new passwords match
        if data['new_password'] != data['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "New passwords do not match."})
        
        # Check if new password is different from old password
        if data['old_password'] == data['new_password']:
            raise serializers.ValidationError({"new_password": "New password must be different from current password."})
        
        return data
    
    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class SignatureUploadSerializer(serializers.Serializer):
    """Serializer to accept uploaded or base64 signatures"""
    signature = serializers.ImageField(required=False, allow_null=True)
    signature_data_url = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get('signature') and not attrs.get('signature_data_url'):
            raise serializers.ValidationError("Provide a signature file or signature_data_url.")
        return attrs




class EmployeeMembershipSerializer(serializers.ModelSerializer):
    """Lightweight serializer for user->employer memberships"""

    employer_id = serializers.IntegerField(source='employer_profile.id', read_only=True)
    employer_name = serializers.CharField(source='employer_profile.company_name', read_only=True)

    class Meta:
        model = EmployeeMembership
        fields = ('employer_id', 'employer_name', 'role', 'status')
        read_only_fields = fields


class SetActiveEmployerSerializer(serializers.Serializer):
    """Serializer to validate and store the user's active employer context"""

    employer_id = serializers.IntegerField()

    def validate_employer_id(self, value):
        user = self.context['request'].user
        membership = EmployeeMembership.objects.filter(
            user=user,
            employer_profile_id=value,
            status=EmployeeMembership.STATUS_ACTIVE,
        ).exists()
        if membership:
            return value

        # Fallback for legacy/single-employer employee accounts without a
        # membership row: allow selecting their own employee employer context.
        employee = getattr(user, "employee_profile", None)
        if employee and getattr(employee, "employer_id", None) == value:
            return value

        raise serializers.ValidationError("Active membership not found for this employer.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        employer_id = self.validated_data['employer_id']
        user.last_active_employer_id = employer_id
        user.save(update_fields=['last_active_employer_id'])
        return user


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = (
            "id",
            "code",
            "module",
            "resource",
            "action",
            "scope",
            "description",
            "is_active",
        )
        read_only_fields = ("id",)


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )
    permission_codes = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "name",
            "description",
            "is_system_role",
            "is_active",
            "allow_high_risk_combination",
            "permission_codes",
            "permissions",
        )
        read_only_fields = ("id", "is_system_role")

    def get_permission_codes(self, obj):
        return list(
            obj.role_permissions.values_list("permission__code", flat=True)
        )

    def _sync_permissions(self, role, codes):
        if codes is None:
            return
        perms = Permission.objects.filter(code__in=codes, is_active=True)
        RolePermission.objects.filter(role=role).exclude(permission__in=perms).delete()
        existing = set(
            RolePermission.objects.filter(role=role, permission__in=perms).values_list(
                "permission_id", flat=True
            )
        )
        for perm in perms:
            if perm.id not in existing:
                RolePermission.objects.create(role=role, permission=perm)

    def create(self, validated_data):
        codes = validated_data.pop("permissions", None)
        role = Role.objects.create(**validated_data)
        self._sync_permissions(role, codes)
        return role

    def update(self, instance, validated_data):
        codes = validated_data.pop("permissions", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        self._sync_permissions(instance, codes)
        return instance


class EmployeeRoleSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = EmployeeRole
        fields = (
            "id",
            "role",
            "role_name",
            "user",
            "employee_id",
            "scope_type",
            "scope_id",
            "assigned_at",
            "assigned_by",
        )
        read_only_fields = ("id", "assigned_at", "assigned_by")


class UserPermissionOverrideSerializer(serializers.ModelSerializer):
    permission_code = serializers.CharField(source="permission.code", read_only=True)

    class Meta:
        model = UserPermissionOverride
        fields = (
            "id",
            "user",
            "permission",
            "permission_code",
            "effect",
            "reason",
            "created_at",
        )
        read_only_fields = ("id", "created_at")
