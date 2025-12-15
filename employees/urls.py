"""URL Configuration for employees app"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DepartmentViewSet, BranchViewSet, EmployeeViewSet,
    EmployeeDocumentViewSet, EmployeeConfigurationViewSet,
    EmployeeInvitationViewSet
)

app_name = 'employees'

router = DefaultRouter()
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'branches', BranchViewSet, basename='branch')
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'documents', EmployeeDocumentViewSet, basename='employee-document')
router.register(r'configuration', EmployeeConfigurationViewSet, basename='employee-config')
router.register(r'invitations', EmployeeInvitationViewSet, basename='employee-invitation')

urlpatterns = [
    path('', include(router.urls)),
]
