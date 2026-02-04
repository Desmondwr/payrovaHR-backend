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
    duplicate_application_blocked,
    get_default_stage,
    get_required_application_fields,
    get_required_custom_question_ids,
    internal_apply_allowed,
    job_scope_allows_internal,
    job_visible_to_internal,
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
        return paginator.get_paginated_response(serializer.data)


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

        required_fields = get_required_application_fields(settings_obj)
        field_aliases = {}
        missing = [field for field in required_fields if not payload.get(field_aliases.get(field, field))]
        if "cv" in required_fields and not payload.get("cv"):
            missing.append("cv")
        if missing:
            return Response({"detail": f"Missing required fields: {', '.join(sorted(set(missing)))}"}, status=status.HTTP_400_BAD_REQUEST)

        answers = payload.get("answers") or {}
        if not isinstance(answers, dict):
            answers = {}
        answers = {str(k): v for k, v in answers.items()}
        required_questions = get_required_custom_question_ids(settings_obj)
        missing_q = [qid for qid in required_questions if not answers.get(qid)]
        if missing_q:
            return Response({"detail": "Missing required custom question answers."}, status=status.HTTP_400_BAD_REQUEST)

        last_application = RecruitmentApplicant.objects.using(tenant_db).filter(
            job=job,
            email__iexact=payload.get("email"),
        ).order_by("-applied_at").first()
        if last_application and duplicate_application_blocked(settings_obj, last_application.applied_at):
            return Response({"detail": "Duplicate application detected."}, status=status.HTTP_409_CONFLICT)

        cv_file = payload.get("cv")
        if cv_file:
            ext = cv_file.name.split(".")[-1].lower()
            allowed = [e.lower() for e in settings_obj.cv_allowed_extensions or []]
            if ext not in allowed:
                return Response({"detail": "Unsupported CV format."}, status=status.HTTP_400_BAD_REQUEST)
            max_bytes = int(settings_obj.cv_max_file_size_mb or 10) * 1024 * 1024
            if cv_file.size > max_bytes:
                return Response({"detail": "CV exceeds maximum file size."}, status=status.HTTP_400_BAD_REQUEST)

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

        RecruitmentApplicantStageHistory.objects.using(tenant_db).create(
            applicant=applicant,
            from_stage=None,
            to_stage=stage,
            action=RecruitmentApplicantStageHistory.ACTION_APPLY,
            changed_by_user_id=request.user.id,
        )

        employer = EmployerProfile.objects.filter(id=employee.employer_id).first()
        if employer:
            send_application_ack_email(
                tenant_db=tenant_db,
                employer=employer,
                settings_obj=settings_obj,
                applicant=applicant,
                stage=stage,
            )

        return Response({"id": str(applicant.id), "status": applicant.status}, status=status.HTTP_201_CREATED)
