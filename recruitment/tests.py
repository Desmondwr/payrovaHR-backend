from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from accounts.models import EmployerProfile
from recruitment.models import RecruitmentSettings, RecruitmentStage
from recruitment.services import (
    ensure_recruitment_settings,
    job_visible_to_internal,
    job_visible_to_public,
    public_apply_allowed,
    internal_apply_allowed,
    duplicate_application_blocked,
)
from recruitment.views import RecruitmentSettingsView
from recruitment.public_views import PublicJobApplyView, PublicJobListView
from recruitment.models import JobPosition
from django.core.files.uploadedfile import SimpleUploadedFile


class RecruitmentSettingsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.employer_user = User.objects.create_user(
            email="recruiter@example.com",
            password="pass",
            is_employer=True,
        )
        self.employer_profile = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name="Acme Corp",
            employer_name_or_group="Acme",
            organization_type="PRIVATE",
            industry_sector="Tech",
            date_of_incorporation=date.today(),
            company_location="City",
            physical_address="123 Street",
            phone_number="1234567890",
            official_company_email="hr@acme.test",
            rccm="rccm",
            taxpayer_identification_number="tin",
            cnps_employer_number="cnps",
            labour_inspectorate_declaration="decl",
            business_license="license",
            bank_name="Bank",
            bank_account_number="123",
        )

    def test_defaults_seeded(self):
        settings_obj = ensure_recruitment_settings(self.employer_profile.id, "default")
        self.assertTrue(settings_obj.application_fields)
        self.assertTrue(settings_obj.cv_allowed_extensions)
        self.assertEqual(
            RecruitmentStage.objects.filter(employer_id=self.employer_profile.id).count(),
            6,
        )

    def test_visibility_helpers(self):
        settings_obj = ensure_recruitment_settings(self.employer_profile.id, "default")
        settings_obj.job_publish_scope = RecruitmentSettings.PUBLISH_SCOPE_PUBLIC
        self.assertTrue(job_visible_to_public(settings_obj))
        self.assertFalse(job_visible_to_internal(settings_obj))

        settings_obj.job_publish_scope = RecruitmentSettings.PUBLISH_SCOPE_BOTH
        self.assertTrue(job_visible_to_public(settings_obj))
        self.assertTrue(job_visible_to_internal(settings_obj))

    def test_apply_flags(self):
        settings_obj = ensure_recruitment_settings(self.employer_profile.id, "default")
        settings_obj.public_applications_enabled = False
        settings_obj.internal_applications_enabled = True
        self.assertFalse(public_apply_allowed(settings_obj))
        self.assertTrue(internal_apply_allowed(settings_obj))

    def test_duplicate_application_window(self):
        settings_obj = ensure_recruitment_settings(self.employer_profile.id, "default")
        settings_obj.duplicate_application_action = RecruitmentSettings.DUPLICATE_ACTION_BLOCK
        settings_obj.duplicate_application_window_days = 30
        recent = timezone.now() - timedelta(days=10)
        old = timezone.now() - timedelta(days=40)
        self.assertTrue(duplicate_application_blocked(settings_obj, recent))
        self.assertFalse(duplicate_application_blocked(settings_obj, old))

    def test_settings_api_patch(self):
        ensure_recruitment_settings(self.employer_profile.id, "default")
        stage = RecruitmentStage.objects.filter(employer_id=self.employer_profile.id).order_by("sequence").first()
        payload = {
            "job_publish_scope": "PUBLIC_ONLY",
            "stages": [
                {
                    "id": str(stage.id),
                    "name": stage.name,
                    "sequence": stage.sequence,
                    "scope": stage.scope,
                    "job_id": stage.job_id,
                    "is_active": stage.is_active,
                    "auto_email_enabled": False,
                    "auto_email_subject": stage.auto_email_subject,
                    "auto_email_body": stage.auto_email_body,
                }
            ],
        }
        factory = APIRequestFactory()
        view = RecruitmentSettingsView.as_view({"patch": "partial_update"})
        request = factory.patch("/api/v1/recruitment/settings/", payload, format="json")
        request.user = self.employer_user
        response = view(request)
        self.assertEqual(response.status_code, 200)
        stage.refresh_from_db()
        self.assertFalse(stage.auto_email_enabled)


class RecruitmentPublicApplyTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        User = get_user_model()
        self.employer_user = User.objects.create_user(
            email="public@example.com",
            password="pass",
            is_employer=True,
        )
        from accounts.models import EmployerProfile

        self.employer_profile = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name="Public Co",
            employer_name_or_group="Public Co",
            organization_type="PRIVATE",
            industry_sector="Tech",
            date_of_incorporation=date.today(),
            company_location="City",
            physical_address="123 Street",
            phone_number="1234567890",
            official_company_email="hr@public.test",
            rccm="rccm",
            taxpayer_identification_number="tin",
            cnps_employer_number="cnps",
            labour_inspectorate_declaration="decl",
            business_license="license",
            bank_name="Bank",
            bank_account_number="123",
        )

    def _create_job(self):
        settings_obj = ensure_recruitment_settings(self.employer_profile.id, "default")
        settings_obj.job_publish_scope = RecruitmentSettings.PUBLISH_SCOPE_BOTH
        settings_obj.public_applications_enabled = True
        settings_obj.save()
        return JobPosition.objects.create(
            employer_id=self.employer_profile.id,
            tenant_id=self.employer_profile.id,
            title="Engineer",
            status=JobPosition.STATUS_OPEN,
            is_published=True,
            publish_scope=RecruitmentSettings.PUBLISH_SCOPE_PUBLIC,
            created_by=self.employer_user.id,
            updated_by=self.employer_user.id,
        )

    def test_public_job_list_requires_employer_context(self):
        self._create_job()
        view = PublicJobListView.as_view()
        request = self.factory.get("/api/v1/public/jobs/")
        response = view(request)
        self.assertEqual(response.status_code, 400)

    def test_public_apply_blocks_duplicates(self):
        job = self._create_job()
        view = PublicJobApplyView.as_view()
        file = SimpleUploadedFile("cv.pdf", b"test", content_type="application/pdf")
        payload = {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "cv": file,
        }
        request = self.factory.post(
            f"/api/v1/public/jobs/{job.id}/apply/",
            payload,
            **{"HTTP_X_EMPLOYER_ID": str(self.employer_profile.id)},
        )
        response = view(request, job_id=job.id)
        self.assertEqual(response.status_code, 201)

        file2 = SimpleUploadedFile("cv.pdf", b"test", content_type="application/pdf")
        payload2 = {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "cv": file2,
        }
        request2 = self.factory.post(
            f"/api/v1/public/jobs/{job.id}/apply/",
            payload2,
            **{"HTTP_X_EMPLOYER_ID": str(self.employer_profile.id)},
        )
        response2 = view(request2, job_id=job.id)
        self.assertEqual(response2.status_code, 409)
