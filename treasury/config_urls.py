from django.urls import path

from .views import TreasuryConfigurationView, TreasuryReferencePreviewView

urlpatterns = [
    path("", TreasuryConfigurationView.as_view(), name="treasury-config"),
    path("preview-reference/", TreasuryReferencePreviewView.as_view(), name="treasury-preview-reference"),
]
