from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from .models import ActivationToken, EmployerProfile, EmployeeRegistry
from .serializers import (
    UserSerializer, CreateEmployerSerializer, ActivateAccountSerializer,
    LoginSerializer, EmployerProfileSerializer, Enable2FASerializer,
    Disable2FASerializer, EmployeeRegistrySerializer,
    EmployerListSerializer
)
from .utils import (
    api_response, send_activation_email, generate_totp_secret,
    generate_qr_code, verify_totp_code
)
from .database_utils import create_tenant_database
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# --- All class definitions below ---

class EmployerStatusView(APIView):
    """Admin-only view to enable or disable an employer account"""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            employer = User.objects.get(pk=pk, is_employer=True)
        except User.DoesNotExist:
            return api_response(
                success=False,
                message='Employer not found.',
                status=status.HTTP_404_NOT_FOUND
            )
        is_active = request.data.get('is_active')
        if is_active is None:
            return api_response(
                success=False,
                message='Missing is_active field.',
                status=status.HTTP_400_BAD_REQUEST
            )
        employer.is_active = bool(is_active)
        employer.save()
        return api_response(
            success=True,
            message=f'Employer account {"enabled" if employer.is_active else "disabled"}.',
            data={'id': employer.id, 'is_active': employer.is_active},
            status=status.HTTP_200_OK
        )
from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from .models import ActivationToken, EmployerProfile, EmployeeRegistry
from .serializers import (
    UserSerializer, CreateEmployerSerializer, ActivateAccountSerializer,
    LoginSerializer, EmployerProfileSerializer, Enable2FASerializer,
    Disable2FASerializer, EmployeeRegistrySerializer,
    EmployerListSerializer
)
from .utils import (
    api_response, send_activation_email, generate_totp_secret,
    generate_qr_code, verify_totp_code
)
from .database_utils import create_tenant_database
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class ListEmployersView(APIView):
    """Admin-only view to list all employer users and their profiles"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        employers = User.objects.filter(is_employer=True)
        serializer = EmployerListSerializer(employers, many=True)
        return api_response(
            success=True,
            message='List of all employers.',
            data=serializer.data,
            status=status.HTTP_200_OK
        )
from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from .models import ActivationToken, EmployerProfile, EmployeeRegistry
from .serializers import (
    UserSerializer, CreateEmployerSerializer, ActivateAccountSerializer,
    LoginSerializer, EmployerProfileSerializer, Enable2FASerializer,
    Disable2FASerializer, EmployeeRegistrySerializer
)
from .utils import (
    api_response, send_activation_email, generate_totp_secret,
    generate_qr_code, verify_totp_code
)
from .database_utils import create_tenant_database
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class IsAdminUser(permissions.BasePermission):
    """Custom permission to only allow admin users"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_admin


class CreateEmployerView(APIView):
    """View for admin to create employer accounts"""
    
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        serializer = CreateEmployerSerializer(data=request.data)
        
        if serializer.is_valid():
            user, activation_token = serializer.save()
            
            # Send activation email
            email_sent = send_activation_email(user, activation_token)
            
            return api_response(
                success=True,
                message='Employer account created successfully. Activation email sent.',
                data={
                    'user': UserSerializer(user).data,
                    'activation_token': activation_token.token if not email_sent else None,
                },
                status=status.HTTP_201_CREATED
            )
        
        return api_response(
            success=False,
            message='Failed to create employer account.',
            errors=serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


@method_decorator(ratelimit(key='ip', rate='5/h', method='POST'), name='dispatch')
class ActivateAccountView(APIView):
    """View for employer to activate their account"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = ActivateAccountSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            
            return api_response(
                success=True,
                message='Account activated successfully. You can now log in.',
                data={'user': UserSerializer(user).data},
                status=status.HTTP_200_OK
            )
        
        return api_response(
            success=False,
            message='Failed to activate account.',
            errors=serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


@method_decorator(ratelimit(key='ip', rate='10/h', method='POST'), name='dispatch')
class LoginView(APIView):
    """View for user login with JWT and 2FA support"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            # Check employee profile completion status
            employee_profile_completed = None
            if user.is_employee:
                employee = user.employee_profile
                if employee:
                    employee_profile_completed = employee.profile_completed
            
            response_data = {
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'profile_incomplete': user.is_employer and not user.profile_completed,
                'employee_profile_completed': employee_profile_completed,
            }
            
            return api_response(
                success=True,
                message='Login successful.',
                data=response_data,
                status=status.HTTP_200_OK
            )
        
        return api_response(
            success=False,
            message='Login failed.',
            errors=serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class Setup2FAView(APIView):
    """View to setup 2FA - generates secret and QR code"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user = request.user
        
        if user.two_factor_enabled:
            return api_response(
                success=False,
                message='2FA is already enabled.',
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate secret
        secret = generate_totp_secret()
        
        # Save secret to user (temporarily, not enabled yet)
        user.two_factor_secret = secret
        user.save()
        
        # Generate QR code
        qr_code = generate_qr_code(secret, user.email)
        
        return api_response(
            success=True,
            message='2FA setup initiated. Scan the QR code with your authenticator app.',
            data={
                'secret': secret,
                'qr_code': qr_code,
            },
            status=status.HTTP_200_OK
        )


class Verify2FAView(APIView):
    """View to verify and enable 2FA"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = Enable2FASerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = request.user
            user.two_factor_enabled = True
            user.save()
            
            return api_response(
                success=True,
                message='2FA enabled successfully.',
                data={'user': UserSerializer(user).data},
                status=status.HTTP_200_OK
            )
        
        return api_response(
            success=False,
            message='Failed to enable 2FA.',
            errors=serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class Disable2FAView(APIView):
    """View to disable 2FA"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = Disable2FASerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = request.user
            user.two_factor_enabled = False
            user.two_factor_secret = None
            user.save()
            
            return api_response(
                success=True,
                message='2FA disabled successfully.',
                data={'user': UserSerializer(user).data},
                status=status.HTTP_200_OK
            )
        
        return api_response(
            success=False,
            message='Failed to disable 2FA.',
            errors=serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class EmployerProfileView(generics.RetrieveUpdateAPIView):
    """View to retrieve and update employer profile"""
    
    serializer_class = EmployerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        # Get or create employer profile for current user
        user = self.request.user
        
        if not user.is_employer:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only employers can access this endpoint.")
        
        profile, created = EmployerProfile.objects.get_or_create(user=user)
        return profile
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return api_response(
            success=True,
            message='Employer profile retrieved successfully.',
            data=serializer.data,
            status=status.HTTP_200_OK
        )
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if serializer.is_valid():
            serializer.save()
            
            return api_response(
                success=True,
                message='Employer profile updated successfully.',
                data=serializer.data,
                status=status.HTTP_200_OK
            )
        
        return api_response(
            success=False,
            message='Failed to update employer profile.',
            errors=serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class CompleteEmployerProfileView(APIView):
    """View for first-time employer profile completion"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user = request.user
        
        if not user.is_employer:
            return api_response(
                success=False,
                message='Only employers can complete this profile.',
                status=status.HTTP_403_FORBIDDEN
            )
        
        if user.profile_completed:
            return api_response(
                success=False,
                message='Profile has already been completed.',
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = EmployerProfileSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            employer_profile = serializer.save()
            
            # Create tenant database for this employer
            logger.info(f"Creating tenant database for employer: {user.email}")
            success, db_name, error_msg = create_tenant_database(employer_profile)
            
            if success:
                logger.info(f"Tenant database created successfully: {db_name}")
                response_message = f'Employer profile completed successfully. Tenant database "{db_name}" created.'
            else:
                logger.error(f"Failed to create tenant database: {error_msg}")
                response_message = f'Employer profile completed, but database creation failed: {error_msg}'
            
            return api_response(
                success=True,
                message=response_message,
                data={
                    'profile': serializer.data,
                    'database_created': success,
                    'database_name': db_name,
                },
                status=status.HTTP_201_CREATED
            )
        
        return api_response(
            success=False,
            message='Failed to complete employer profile.',
            errors=serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class UserProfileView(APIView):
    """View to get current user profile"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        user_data = UserSerializer(user).data
        
        # Add employer profile if exists
        if user.is_employer and hasattr(user, 'employer_profile'):
            user_data['employer_profile'] = EmployerProfileSerializer(user.employer_profile).data
        
        # Add employee registry if exists
        if user.is_employee and hasattr(user, 'employee_registry'):
            user_data['employee_registry'] = EmployeeRegistrySerializer(user.employee_registry).data
        
        return api_response(
            success=True,
            message='User profile retrieved successfully.',
            data=user_data,
            status=status.HTTP_200_OK
        )


