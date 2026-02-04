from django.urls import path

from .internal_views import InternalJobApplyView, InternalJobListView

urlpatterns = [
    path("jobs/", InternalJobListView.as_view(), name="internal-jobs"),
    path("jobs/<uuid:job_id>/apply/", InternalJobApplyView.as_view(), name="internal-job-apply"),
]
