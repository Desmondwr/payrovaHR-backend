from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CreateEmployerView, ActivateAccountView, LoginView,
    Setup2FAView, Verify2FAView, Disable2FAView,
    EmployerProfileView, CompleteEmployerProfileView, UserProfileView,
    ListEmployersView, EmployerStatusView, UserSignatureView,
    RequestPasswordResetView, VerifyResetCodeView, ResendResetCodeView,
    ChangePasswordView, MyEmployersView, SetActiveEmployerView
)

app_name = 'accounts'

urlpatterns = [
    # Admin endpoints
    path('admin/create-employer/', CreateEmployerView.as_view(), name='create-employer'),
    path('admin/employers/', ListEmployersView.as_view(), name='list-employers'),
    path('admin/employers/<int:pk>/status/', EmployerStatusView.as_view(), name='employer-status'),
    
    # Authentication endpoints
    path('auth/activate/', ActivateAccountView.as_view(), name='activate-account'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Password reset endpoints
    path('auth/password-reset/request/', RequestPasswordResetView.as_view(), name='request-password-reset'),
    path('auth/password-reset/verify/', VerifyResetCodeView.as_view(), name='verify-reset-code'),
    path('auth/password-reset/resend/', ResendResetCodeView.as_view(), name='resend-reset-code'),
    
    # Password change endpoint (authenticated users)
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
    
    # 2FA endpoints
    path('auth/2fa/setup/', Setup2FAView.as_view(), name='setup-2fa'),
    path('auth/2fa/verify/', Verify2FAView.as_view(), name='verify-2fa'),
    path('auth/2fa/disable/', Disable2FAView.as_view(), name='disable-2fa'),
    
    # Profile endpoints
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('profile/signature/', UserSignatureView.as_view(), name='user-signature'),
    path('employer/profile/', EmployerProfileView.as_view(), name='employer-profile'),
    path('employer/profile/complete/', CompleteEmployerProfileView.as_view(), name='complete-employer-profile'),
    path('accounts/my-employers/', MyEmployersView.as_view(), name='my-employers'),
    path('accounts/set-active-employer/', SetActiveEmployerView.as_view(), name='set-active-employer'),
]

