from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ContractViewSet, ContractAmendmentViewSet,
    ContractConfigurationViewSet, SalaryScaleViewSet, ContractTemplateViewSet
)

router = DefaultRouter()
router.register(r'config', ContractConfigurationViewSet, basename='contract-config')
router.register(r'salary-scales', SalaryScaleViewSet, basename='salary-scale')
router.register(r'templates', ContractTemplateViewSet, basename='contract-template')
router.register(r'', ContractViewSet, basename='contract')

amendment_list = ContractAmendmentViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

amendment_detail = ContractAmendmentViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy'
})

urlpatterns = [
    path('', include(router.urls)),
    path('<uuid:contract_pk>/amendments/', amendment_list, name='contract-amendments-list'),
    path('<uuid:contract_pk>/amendments/<int:pk>/', amendment_detail, name='contract-amendments-detail'),
]
