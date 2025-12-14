from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CreateEmployerView, ActivateAccountView, LoginView,
    Setup2FAView, Verify2FAView, Disable2FAView,
    EmployerProfileView, CompleteEmployerProfileView, UserProfileView,
    EmployeeRegistrationView, EmployeeProfileDetailView, ListEmployersView, EmployerStatusView
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
    path('auth/register/employee/', EmployeeRegistrationView.as_view(), name='register-employee'),
    
    # 2FA endpoints
    path('auth/2fa/setup/', Setup2FAView.as_view(), name='setup-2fa'),
    path('auth/2fa/verify/', Verify2FAView.as_view(), name='verify-2fa'),
    path('auth/2fa/disable/', Disable2FAView.as_view(), name='disable-2fa'),
    
    # Profile endpoints
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('employer/profile/', EmployerProfileView.as_view(), name='employer-profile'),
    path('employer/profile/complete/', CompleteEmployerProfileView.as_view(), name='complete-employer-profile'),
    path('employee/profile/', EmployeeProfileDetailView.as_view(), name='employee-profile'),
]

