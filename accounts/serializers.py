from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .models import User, ActivationToken, EmployerProfile, EmployeeRegistry



# ...existing code...

class EmployerProfileSerializer(serializers.ModelSerializer):
    """Serializer for EmployerProfile model"""
    class Meta:
        model = EmployerProfile
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')
    def validate(self, data):
        # Custom validation can be added here
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
        user.save()
        return profile
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        # Ensure profile is marked as completed
        if not instance.user.profile_completed:
            instance.user.profile_completed = True
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
        fields = ('id', 'email', 'first_name', 'last_name', 'is_admin', 'is_employer', 
                  'profile_completed', 'two_factor_enabled', 'created_at')
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
        # Custom validation can be added here
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
        user.save()
        
        return profile
    
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Ensure profile is marked as completed
        if not instance.user.profile_completed:
            instance.user.profile_completed = True
            instance.user.save()
        
        return instance


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

