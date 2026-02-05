from django.db.models import Q
from django.utils import timezone
from django_ratelimit.core import is_ratelimited
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import JobPosition, RecruitmentApplicant, RecruitmentApplicantStageHistory, RecruitmentAttachment
from .serializers import JobPositionPublicSerializer, RecruitmentApplySerializer
from .services import (
    ensure_recruitment_settings,
    duplicate_application_detected,
    get_default_stage,
    get_required_application_fields,
    job_scope_allows_public,
    job_visible_to_public,
    notify_applicant_application_received,
    notify_employer_application_received,
    notify_integration_resume_ocr_queued,
    public_apply_allowed,
    public_apply_rate_limit,
    resolve_public_employer,
    send_application_ack_email,
)


class PublicJobListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from accounts.models import EmployerProfile
        from accounts.database_utils import get_tenant_database_alias, ensure_tenant_database_loaded

        employer, tenant_db = resolve_public_employer(request)

        # If employer context is provided, filter by that employer
        if employer:
            settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
            if not job_visible_to_public(settings_obj):
                return Response([])

            qs = JobPosition.objects.using(tenant_db).filter(
                employer_id=employer.id,
                status=JobPosition.STATUS_OPEN,
                is_published=True,
            )
            qs = qs.filter(Q(publish_scope__in=["PUBLIC_ONLY", "BOTH"]) | Q(publish_scope__isnull=True))
        else:
            # No employer context - show jobs from ALL employers
            all_jobs = []
            employers = EmployerProfile.objects.filter(database_created=True)

            for emp in employers:
                emp_tenant_db = get_tenant_database_alias(emp)
                ensure_tenant_database_loaded(emp)

                settings_obj = ensure_recruitment_settings(emp.id, emp_tenant_db)
                if not job_visible_to_public(settings_obj):
                    continue

                jobs = JobPosition.objects.using(emp_tenant_db).filter(
                    employer_id=emp.id,
                    status=JobPosition.STATUS_OPEN,
                    is_published=True,
                )
                jobs = jobs.filter(Q(publish_scope__in=["PUBLIC_ONLY", "BOTH"]) | Q(publish_scope__isnull=True))
                all_jobs.extend(list(jobs))

            # Create a queryset-like list for filtering
            qs = all_jobs

        # Apply filters
        keyword = request.query_params.get("keyword")
        location = request.query_params.get("location")
        department = request.query_params.get("department")
        employment_type = request.query_params.get("employment_type")
        remote_flag = request.query_params.get("remote")

        if isinstance(qs, list):
            # Filter list of jobs
            if keyword:
                qs = [job for job in qs if keyword.lower() in job.title.lower() or (job.description and keyword.lower() in job.description.lower())]
            if location:
                qs = [job for job in qs if job.location and location.lower() in job.location.lower()]
            if department:
                qs = [job for job in qs if str(job.department_id) == department]
            if employment_type:
                qs = [job for job in qs if job.employment_type == employment_type]
            if remote_flag:
                is_remote = str(remote_flag).lower() in ["true", "1", "yes"]
                qs = [job for job in qs if job.is_remote == is_remote]

            # Sort by created_at
            qs = sorted(qs, key=lambda x: x.created_at, reverse=True)

            # Manual pagination
            paginator = PageNumberPagination()
            page_size = paginator.page_size or 10
            page_num = int(request.query_params.get('page', 1))
            start = (page_num - 1) * page_size
            end = start + page_size
            page = qs[start:end]

            serializer = JobPositionPublicSerializer(page, many=True)
            return Response({
                "count": len(qs),
                "next": None,
                "previous": None,
                "results": serializer.data
            })
        else:
            # QuerySet filtering
            if keyword:
                qs = qs.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))
            if location:
                qs = qs.filter(location__icontains=location)
            if department:
                qs = qs.filter(department_id=department)
            if employment_type:
                qs = qs.filter(employment_type=employment_type)
            if remote_flag:
                qs = qs.filter(is_remote=str(remote_flag).lower() in ["true", "1", "yes"])

            qs = qs.order_by("-created_at")

            paginator = PageNumberPagination()
            page = paginator.paginate_queryset(qs, request)
            serializer = JobPositionPublicSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)


class PublicJobDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, job_id):
        from accounts.models import EmployerProfile
        from accounts.database_utils import get_tenant_database_alias, ensure_tenant_database_loaded

        employer, tenant_db = resolve_public_employer(request)

        # If employer context is provided, use it
        if employer:
            settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
            if not job_visible_to_public(settings_obj):
                return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

            job = JobPosition.objects.using(tenant_db).filter(
                id=job_id,
                employer_id=employer.id,
                status=JobPosition.STATUS_OPEN,
                is_published=True,
            ).first()
            if not job or not job_scope_allows_public(job, settings_obj):
                return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

            serializer = JobPositionPublicSerializer(job)
            payload = serializer.data
            payload.update(
                {
                    "application_fields": settings_obj.application_fields or [],
                    "custom_questions": settings_obj.custom_questions or [],
                    "cv_allowed_extensions": settings_obj.cv_allowed_extensions or [],
                    "cv_max_file_size_mb": settings_obj.cv_max_file_size_mb,
                    "public_apply_requires_login": settings_obj.public_apply_requires_login,
                    "public_apply_captcha_enabled": settings_obj.public_apply_captcha_enabled,
                    "public_apply_spam_check_enabled": settings_obj.public_apply_spam_check_enabled,
                    "public_apply_honeypot_enabled": settings_obj.public_apply_honeypot_enabled,
                    "duplicate_application_action": settings_obj.duplicate_application_action,
                    "duplicate_application_window_days": settings_obj.duplicate_application_window_days,
                    "integration_interview_scheduling_enabled": settings_obj.integration_interview_scheduling_enabled,
                    "integration_offers_esign_enabled": settings_obj.integration_offers_esign_enabled,
                    "integration_resume_ocr_enabled": settings_obj.integration_resume_ocr_enabled,
                    "integration_job_board_ingest_enabled": settings_obj.integration_job_board_ingest_enabled,
                }
            )
            return Response(payload)

        # No employer context - search across all employers
        employers = EmployerProfile.objects.filter(database_created=True)
        for emp in employers:
            emp_tenant_db = get_tenant_database_alias(emp)
            ensure_tenant_database_loaded(emp)

            settings_obj = ensure_recruitment_settings(emp.id, emp_tenant_db)
            if not job_visible_to_public(settings_obj):
                continue

            job = JobPosition.objects.using(emp_tenant_db).filter(
                id=job_id,
                employer_id=emp.id,
                status=JobPosition.STATUS_OPEN,
                is_published=True,
            ).first()
            if job and job_scope_allows_public(job, settings_obj):
                serializer = JobPositionPublicSerializer(job)
                payload = serializer.data
                payload.update(
                    {
                        "application_fields": settings_obj.application_fields or [],
                        "custom_questions": settings_obj.custom_questions or [],
                        "cv_allowed_extensions": settings_obj.cv_allowed_extensions or [],
                        "cv_max_file_size_mb": settings_obj.cv_max_file_size_mb,
                        "public_apply_requires_login": settings_obj.public_apply_requires_login,
                        "public_apply_captcha_enabled": settings_obj.public_apply_captcha_enabled,
                        "public_apply_spam_check_enabled": settings_obj.public_apply_spam_check_enabled,
                        "public_apply_honeypot_enabled": settings_obj.public_apply_honeypot_enabled,
                        "duplicate_application_action": settings_obj.duplicate_application_action,
                        "duplicate_application_window_days": settings_obj.duplicate_application_window_days,
                        "integration_interview_scheduling_enabled": settings_obj.integration_interview_scheduling_enabled,
                        "integration_offers_esign_enabled": settings_obj.integration_offers_esign_enabled,
                        "integration_resume_ocr_enabled": settings_obj.integration_resume_ocr_enabled,
                        "integration_job_board_ingest_enabled": settings_obj.integration_job_board_ingest_enabled,
                    }
                )
                return Response(payload)

        return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)


class PublicJobApplyView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, job_id):
        from accounts.models import EmployerProfile
        from accounts.database_utils import get_tenant_database_alias, ensure_tenant_database_loaded

        employer, tenant_db = resolve_public_employer(request)

        # If no employer context, search across all employers to find the job
        if not employer:
            employers = EmployerProfile.objects.filter(database_created=True)
            for emp in employers:
                emp_tenant_db = get_tenant_database_alias(emp)
                ensure_tenant_database_loaded(emp)

                job = JobPosition.objects.using(emp_tenant_db).filter(
                    id=job_id,
                    employer_id=emp.id,
                    status=JobPosition.STATUS_OPEN,
                    is_published=True,
                ).first()

                if job:
                    employer = emp
                    tenant_db = emp_tenant_db
                    break

            if not employer:
                return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        if not public_apply_allowed(settings_obj):
            return Response({"detail": "Public applications are disabled."}, status=status.HTTP_403_FORBIDDEN)
        if not job_visible_to_public(settings_obj):
            return Response({"detail": "Public applications are disabled."}, status=status.HTTP_403_FORBIDDEN)
        if settings_obj.public_apply_requires_login and not (request.user and request.user.is_authenticated):
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        job = JobPosition.objects.using(tenant_db).filter(
            id=job_id,
            employer_id=employer.id,
            status=JobPosition.STATUS_OPEN,
            is_published=True,
        ).first()
        if not job or not job_scope_allows_public(job, settings_obj):
            return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

        if settings_obj.public_apply_spam_check_enabled:
            if settings_obj.public_apply_honeypot_enabled and request.data.get("website"):
                return Response({"detail": "Invalid submission."}, status=status.HTTP_400_BAD_REQUEST)
            if settings_obj.public_apply_captcha_enabled and not request.data.get("captcha_token"):
                return Response({"detail": "Captcha verification required."}, status=status.HTTP_400_BAD_REQUEST)

        rate = public_apply_rate_limit(settings_obj)
        if rate:
            limited = is_ratelimited(request, group="recruitment_public_apply", key="ip", rate=rate, increment=True)
            if limited:
                return Response({"detail": "Too many requests."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        serializer = RecruitmentApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

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
            employer_id=employer.id,
            tenant_id=employer.id,
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
            is_internal_applicant=False,
        )

        if cv_file:
            RecruitmentAttachment.objects.using(tenant_db).create(
                employer_id=employer.id,
                tenant_id=employer.id,
                applicant=applicant,
                file=cv_file,
                file_size=cv_file.size,
                content_type=getattr(cv_file, "content_type", None),
                original_name=cv_file.name,
                purpose=RecruitmentAttachment.PURPOSE_CV,
            )
        for qid, file_obj in file_uploads.items():
            if qid not in file_question_ids:
                continue
            attachment = RecruitmentAttachment.objects.using(tenant_db).create(
                employer_id=employer.id,
                tenant_id=employer.id,
                applicant=applicant,
                file=file_obj,
                file_size=file_obj.size,
                content_type=getattr(file_obj, "content_type", None),
                original_name=file_obj.name,
                purpose=RecruitmentAttachment.PURPOSE_OTHER,
            )
            answers[qid] = {
                "attachment_id": str(attachment.id),
                "file_name": file_obj.name,
            }

        if answers and applicant.answers != answers:
            applicant.answers = answers
            applicant.save(using=tenant_db, update_fields=["answers"])

        notify_integration_resume_ocr_queued(
            applicant=applicant,
            employer=employer,
            settings_obj=settings_obj,
            actor_user_id=request.user.id if request.user and request.user.is_authenticated else None,
        )

        RecruitmentApplicantStageHistory.objects.using(tenant_db).create(
            applicant=applicant,
            from_stage=None,
            to_stage=stage,
            action=RecruitmentApplicantStageHistory.ACTION_APPLY,
        )

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
            actor_user_id=request.user.id if request.user and request.user.is_authenticated else None,
            source="public",
            is_duplicate=is_duplicate,
        )
        if request.user and request.user.is_authenticated and request.user.is_employee:
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
