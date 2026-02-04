from django.urls import path

from .public_views import PublicJobApplyView, PublicJobDetailView, PublicJobListView

urlpatterns = [
    path("jobs/", PublicJobListView.as_view(), name="public-jobs"),
    path("jobs/<uuid:job_id>/", PublicJobDetailView.as_view(), name="public-job-detail"),
    path("jobs/<uuid:job_id>/apply/", PublicJobApplyView.as_view(), name="public-job-apply"),
]
