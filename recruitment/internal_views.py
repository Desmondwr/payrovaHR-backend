from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsEmployee
from accounts.models import EmployerProfile

from .models import JobPosition, RecruitmentApplicant, RecruitmentApplicantStageHistory, RecruitmentAttachment
from .serializers import JobPositionPublicSerializer, RecruitmentApplySerializer
from .services import (
    ensure_recruitment_settings,
    duplicate_application_detected,
    get_default_stage,
    get_required_application_fields,
    internal_apply_allowed,
    job_scope_allows_internal,
    job_visible_to_internal,
    notify_applicant_application_received,
    notify_employer_application_received,
    notify_integration_resume_ocr_queued,
    send_application_ack_email,
)


class InternalJobListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployee]

    def get(self, request):
        employee = request.user.employee_profile
        if not employee:
            return Response({"detail": "Employee context required."}, status=status.HTTP_403_FORBIDDEN)
        tenant_db = employee._state.db or "default"
        settings_obj = ensure_recruitment_settings(employee.employer_id, tenant_db)
        if not job_visible_to_internal(settings_obj):
            return Response([])

        qs = JobPosition.objects.using(tenant_db).filter(
            employer_id=employee.employer_id,
            status=JobPosition.STATUS_OPEN,
            is_published=True,
        )
        qs = qs.filter(Q(publish_scope__in=["INTERNAL_ONLY", "BOTH"]) | Q(publish_scope__isnull=True))
        keyword = request.query_params.get("keyword")
        location = request.query_params.get("location")
        department = request.query_params.get("department")
        employment_type = request.query_params.get("employment_type")
        remote_flag = request.query_params.get("remote")

        if keyword:
            qs = qs.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))
        if location:
            qs = qs.filter(location__icontains=location)
        if department:
            qs = qs.filter(department_id=department)
        if employment_type:
            qs = qs.filter(employment_type=employment_type)
        if remote_flag is not None:
            qs = qs.filter(is_remote=str(remote_flag).lower() in ["true", "1", "yes"])

        qs = qs.order_by("-created_at")

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = JobPositionPublicSerializer(page, many=True)
        serialized = serializer.data

        if request.user and page:
            job_ids = [job.id for job in page]
            applications = (
                RecruitmentApplicant.objects.using(tenant_db)
                .filter(job_id__in=job_ids, user_id=request.user.id)
                .order_by("-applied_at")
            )
            app_map = {}
            for application in applications:
                job_id = str(application.job_id)
                if job_id in app_map:
                    continue
                app_map[job_id] = application

            for item in serialized:
                application = app_map.get(item.get("id"))
                if application:
                    item["has_applied"] = True
                    item["application_id"] = str(application.id)
                    item["application_status"] = application.status
                    item["application_stage"] = application.stage.name if application.stage else None
                    item["applied_at"] = (
                        application.applied_at.isoformat()
                        if application.applied_at
                        else None
                    )
                else:
                    item["has_applied"] = False

        return paginator.get_paginated_response(serialized)


class InternalJobApplyView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployee]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, job_id):
        employee = request.user.employee_profile
        if not employee:
            return Response({"detail": "Employee context required."}, status=status.HTTP_403_FORBIDDEN)
        tenant_db = employee._state.db or "default"
        settings_obj = ensure_recruitment_settings(employee.employer_id, tenant_db)
        if not internal_apply_allowed(settings_obj):
            return Response({"detail": "Internal applications are disabled."}, status=status.HTTP_403_FORBIDDEN)
        if not job_visible_to_internal(settings_obj):
            return Response({"detail": "Internal applications are disabled."}, status=status.HTTP_403_FORBIDDEN)

        job = JobPosition.objects.using(tenant_db).filter(
            id=job_id,
            employer_id=employee.employer_id,
            status=JobPosition.STATUS_OPEN,
            is_published=True,
        ).first()
        if not job or not job_scope_allows_internal(job, settings_obj):
            return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

        serializer = RecruitmentApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        if not payload.get("full_name"):
            payload["full_name"] = employee.full_name
        if not payload.get("email"):
            payload["email"] = employee.email
        if not payload.get("phone"):
            payload["phone"] = employee.phone_number

        answers = payload.get("answers") or {}
        if not isinstance(answers, dict):
            answers = {}
        answers = {str(k): v for k, v in answers.items()}

        custom_questions = [q for q in (settings_obj.custom_questions or []) if q.get("is_active", True)]
        file_question_ids = {
            str(q.get("id"))
            for q in custom_questions
            if q.get("type") == "file"
        }
        required_questions = [q for q in custom_questions if q.get("required", False)]
        file_uploads = {}
        for key, file in request.FILES.items():
            if key.startswith("custom_file_"):
                qid = key.replace("custom_file_", "")
                file_uploads[qid] = file

        required_fields = get_required_application_fields(settings_obj)
        field_aliases = {}
        known_fields = {"full_name", "email", "phone", "linkedin", "intro", "source", "medium", "referral"}
        missing = []
        for field in required_fields:
            if field == "cv":
                if not payload.get("cv"):
                    missing.append("cv")
                continue
            if field in known_fields:
                if not payload.get(field_aliases.get(field, field)):
                    missing.append(field)
                continue
            if not answers.get(field):
                missing.append(field)
        if missing:
            return Response({"detail": f"Missing required fields: {', '.join(sorted(set(missing)))}"}, status=status.HTTP_400_BAD_REQUEST)

        missing_q = []
        for question in required_questions:
            qid = str(question.get("id"))
            if question.get("type") == "file":
                if qid not in file_uploads:
                    missing_q.append(qid)
            elif not answers.get(qid):
                missing_q.append(qid)
        if missing_q:
            return Response({"detail": "Missing required custom question answers."}, status=status.HTTP_400_BAD_REQUEST)

        last_application = RecruitmentApplicant.objects.using(tenant_db).filter(
            job=job,
            email__iexact=payload.get("email"),
        ).order_by("-applied_at").first()
        is_duplicate = False
        duplicate_warning = False
        if last_application and duplicate_application_detected(settings_obj, last_application.applied_at):
            is_duplicate = True
            if settings_obj.duplicate_application_action == settings_obj.DUPLICATE_ACTION_BLOCK:
                return Response({"detail": "Duplicate application detected."}, status=status.HTTP_409_CONFLICT)
            if settings_obj.duplicate_application_action == settings_obj.DUPLICATE_ACTION_WARN:
                duplicate_warning = True

        cv_file = payload.get("cv")
        def validate_upload(file_obj):
            ext = file_obj.name.split(".")[-1].lower()
            allowed = [e.lower() for e in settings_obj.cv_allowed_extensions or []]
            if allowed and ext not in allowed:
                return False, "Unsupported file format."
            max_bytes = int(settings_obj.cv_max_file_size_mb or 10) * 1024 * 1024
            if file_obj.size > max_bytes:
                return False, "File exceeds maximum size."
            return True, ""

        if cv_file:
            ok, msg = validate_upload(cv_file)
            if not ok:
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        for qid, file_obj in file_uploads.items():
            if qid not in file_question_ids:
                continue
            ok, msg = validate_upload(file_obj)
            if not ok:
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        stage = get_default_stage(job, tenant_db, settings_obj)
        if not stage:
            return Response({"detail": "No stages configured."}, status=status.HTTP_400_BAD_REQUEST)
        applicant = RecruitmentApplicant.objects.using(tenant_db).create(
            employer_id=employee.employer_id,
            tenant_id=employee.employer_id,
            job=job,
            stage=stage,
            full_name=payload.get("full_name"),
            email=payload.get("email"),
            phone=payload.get("phone"),
            linkedin_url=payload.get("linkedin"),
            intro=payload.get("intro"),
            source=payload.get("source"),
            medium=payload.get("medium"),
            referral=payload.get("referral"),
            answers=answers,
            status=RecruitmentApplicant.STATUS_NEW,
            last_activity_at=timezone.now(),
            is_internal_applicant=True,
            user_id=request.user.id,
            employee=employee,
        )

        if cv_file:
            RecruitmentAttachment.objects.using(tenant_db).create(
                employer_id=employee.employer_id,
                tenant_id=employee.employer_id,
                applicant=applicant,
                file=cv_file,
                file_size=cv_file.size,
                content_type=getattr(cv_file, "content_type", None),
                original_name=cv_file.name,
                purpose=RecruitmentAttachment.PURPOSE_CV,
                uploaded_by_user_id=request.user.id,
            )
        for qid, file_obj in file_uploads.items():
            if qid not in file_question_ids:
                continue
            attachment = RecruitmentAttachment.objects.using(tenant_db).create(
                employer_id=employee.employer_id,
                tenant_id=employee.employer_id,
                applicant=applicant,
                file=file_obj,
                file_size=file_obj.size,
                content_type=getattr(file_obj, "content_type", None),
                original_name=file_obj.name,
                purpose=RecruitmentAttachment.PURPOSE_OTHER,
                uploaded_by_user_id=request.user.id,
            )
            answers[qid] = {
                "attachment_id": str(attachment.id),
                "file_name": file_obj.name,
            }

        if answers and applicant.answers != answers:
            applicant.answers = answers
            applicant.save(using=tenant_db, update_fields=["answers"])

        employer = EmployerProfile.objects.filter(id=employee.employer_id).first()
        if employer:
            notify_integration_resume_ocr_queued(
                applicant=applicant,
                employer=employer,
                settings_obj=settings_obj,
                actor_user_id=request.user.id,
            )

        RecruitmentApplicantStageHistory.objects.using(tenant_db).create(
            applicant=applicant,
            from_stage=None,
            to_stage=stage,
            action=RecruitmentApplicantStageHistory.ACTION_APPLY,
            changed_by_user_id=request.user.id,
        )

        if employer:
            send_application_ack_email(
                tenant_db=tenant_db,
                employer=employer,
                settings_obj=settings_obj,
                applicant=applicant,
                stage=stage,
            )
            notify_employer_application_received(
                applicant=applicant,
                employer=employer,
                actor_user_id=request.user.id,
                source="internal",
                is_duplicate=is_duplicate,
            )
            notify_applicant_application_received(
                applicant=applicant,
                user=request.user,
                employer=employer,
            )

        response_payload = {"id": str(applicant.id), "status": applicant.status}
        if duplicate_warning:
            response_payload["warning"] = "Duplicate application detected. We will still review your submission."
            response_payload["warning_code"] = "DUPLICATE_APPLICATION"
        return Response(response_payload, status=status.HTTP_201_CREATED)


class InternalJobDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployee]

    def get(self, request, job_id):
        employee = request.user.employee_profile
        if not employee:
            return Response({"detail": "Employee context required."}, status=status.HTTP_403_FORBIDDEN)
        tenant_db = employee._state.db or "default"
        settings_obj = ensure_recruitment_settings(employee.employer_id, tenant_db)
        if not job_visible_to_internal(settings_obj):
            return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

        job = JobPosition.objects.using(tenant_db).filter(
            id=job_id,
            employer_id=employee.employer_id,
            status=JobPosition.STATUS_OPEN,
            is_published=True,
        ).first()
        if not job or not job_scope_allows_internal(job, settings_obj):
            return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

        serializer = JobPositionPublicSerializer(job)
        payload = serializer.data
        payload.update(
            {
                "application_fields": settings_obj.application_fields or [],
                "custom_questions": settings_obj.custom_questions or [],
                "cv_allowed_extensions": settings_obj.cv_allowed_extensions or [],
                "cv_max_file_size_mb": settings_obj.cv_max_file_size_mb,
                "internal_apply_requires_login": settings_obj.internal_apply_requires_login,
                "duplicate_application_action": settings_obj.duplicate_application_action,
                "duplicate_application_window_days": settings_obj.duplicate_application_window_days,
                "integration_interview_scheduling_enabled": settings_obj.integration_interview_scheduling_enabled,
                "integration_offers_esign_enabled": settings_obj.integration_offers_esign_enabled,
                "integration_resume_ocr_enabled": settings_obj.integration_resume_ocr_enabled,
                "integration_job_board_ingest_enabled": settings_obj.integration_job_board_ingest_enabled,
            }
        )

        application = (
            RecruitmentApplicant.objects.using(tenant_db)
            .filter(job_id=job.id, user_id=request.user.id)
            .order_by("-applied_at")
            .first()
        )
        if application:
            payload["has_applied"] = True
            payload["application_id"] = str(application.id)
            payload["application_status"] = application.status
            payload["application_stage"] = application.stage.name if application.stage else None
            payload["applied_at"] = (
                application.applied_at.isoformat()
                if application.applied_at
                else None
            )
        else:
            payload["has_applied"] = False

        return Response(payload)
