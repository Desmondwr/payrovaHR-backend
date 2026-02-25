"""URL Configuration for employees app"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DepartmentViewSet, BranchViewSet, EmployeeViewSet,
    EmployeeDocumentViewSet, EmployeeConfigurationViewSet,
    EmployeeInvitationViewSet, EmployeeProfileViewSet,
    CrossInstitutionConsentViewSet, EmploymentCertificateShareViewSet
)

app_name = 'employees'

router = DefaultRouter()
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'branches', BranchViewSet, basename='branch')
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'documents', EmployeeDocumentViewSet, basename='employee-document')
router.register(r'configuration', EmployeeConfigurationViewSet, basename='employee-config')
router.register(r'invitations', EmployeeInvitationViewSet, basename='employee-invitation')
router.register(r'consents', CrossInstitutionConsentViewSet, basename='employee-consent')
router.register(r'certificate-shares', EmploymentCertificateShareViewSet, basename='certificate-share')

urlpatterns = [
    path(
        'profile/',
        EmployeeProfileViewSet.as_view({'get': 'get_profile', 'patch': 'update_profile', 'put': 'update_profile'}),
        name='employee-profile',
    ),
    path(
        'profile/me/',
        EmployeeProfileViewSet.as_view({'get': 'get_own_profile'}),
        name='employee-profile-me',
    ),
    path(
        'profile/complete-profile/',
        EmployeeProfileViewSet.as_view({'patch': 'complete_profile', 'put': 'complete_profile'}),
        name='employee-profile-complete',
    ),
    path(
        'profile/photo/',
        EmployeeProfileViewSet.as_view({'post': 'upload_profile_photo'}),
        name='employee-profile-photo',
    ),
    path(
        'profile/consent-preferences/',
        EmployeeProfileViewSet.as_view({
            'get': 'get_consent_preferences',
            'patch': 'update_consent_preferences',
            'put': 'update_consent_preferences',
        }),
        name='employee-consent-preferences',
    ),
    path('', include(router.urls)),
]
