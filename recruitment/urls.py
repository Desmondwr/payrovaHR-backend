from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    JobPositionViewSet,
    RecruitmentApplicantViewSet,
    RecruitmentRefuseReasonViewSet,
    RecruitmentReportsViewSet,
    RecruitmentSettingsView,
    RecruitmentStageViewSet,
)

router = DefaultRouter()
router.register(r"jobs", JobPositionViewSet, basename="recruitment-job")
router.register(r"applicants", RecruitmentApplicantViewSet, basename="recruitment-applicant")
router.register(r"stages", RecruitmentStageViewSet, basename="recruitment-stage")
router.register(r"refuse-reasons", RecruitmentRefuseReasonViewSet, basename="recruitment-refuse-reason")
router.register(r"reports", RecruitmentReportsViewSet, basename="recruitment-reports")

settings_view = RecruitmentSettingsView.as_view({
    "get": "list",
    "put": "update",
    "patch": "partial_update",
})

urlpatterns = [
    path("settings/", settings_view, name="recruitment-settings"),
    path("", include(router.urls)),
]
