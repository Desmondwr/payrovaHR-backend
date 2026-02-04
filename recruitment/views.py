from collections import defaultdict

from django.db.models import Count, Q
from django.utils import timezone
import logging
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from accounts.database_utils import get_tenant_database_alias
from accounts.permissions import EmployerAccessPermission
from accounts.rbac import apply_scope_filter, get_active_employer, get_delegate_scope, is_delegate_user

from .models import (
    JobPosition,
    RecruitmentApplicant,
    RecruitmentApplicantStageHistory,
    RecruitmentRefuseReason,
    RecruitmentStage,
)
from .serializers import (
    JobPositionSerializer,
    RecruitmentApplicantCreateSerializer,
    RecruitmentApplicantPipelineSerializer,
    RecruitmentApplicantSerializer,
    RecruitmentApplicantUpdateSerializer,
    RecruitmentRefuseReasonSerializer,
    RecruitmentRefuseSerializer,
    RecruitmentSettingsSerializer,
    RecruitmentStageMoveSerializer,
    RecruitmentStageSerializer,
)
from .services import (
    ensure_recruitment_settings,
    get_default_stage,
    get_effective_stages,
    get_required_application_fields,
    get_required_custom_question_ids,
    get_recruitment_settings_cached,
    invalidate_recruitment_settings_cache,
    publish_scope_allowed,
    send_application_ack_email,
    send_stage_email_if_enabled,
)


class RecruitmentSettingsView(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]

    def get_permissions(self):
        if self.request.method in ["PUT", "PATCH"]:
            self.required_permissions = [
                "recruitment.settings.update",
                "recruitment.manage",
            ]
        else:
            self.required_permissions = [
                "recruitment.settings.view",
                "recruitment.manage",
            ]
        return super().get_permissions()

    def _get_context(self, request):
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        return employer, tenant_db

    def list(self, request):
        employer, tenant_db = self._get_context(request)
        data = get_recruitment_settings_cached(employer.id, tenant_db)
        return Response(data)

    def update(self, request):
        return self._update(request, partial=False)

    def partial_update(self, request):
        return self._update(request, partial=True)

    def _update(self, request, partial=False):
        employer, tenant_db = self._get_context(request)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        serializer = RecruitmentSettingsSerializer(
            settings_obj,
            data=request.data,
            partial=partial,
            context={"request": request, "tenant_db": tenant_db},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_recruitment_settings_cache(employer.id, tenant_db)
        return Response(serializer.data, status=status.HTTP_200_OK)


logger = logging.getLogger(__name__)


class JobPositionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    serializer_class = JobPositionSerializer
    permission_map = {
        "list": ["recruitment.job.view", "recruitment.manage"],
        "retrieve": ["recruitment.job.view", "recruitment.manage"],
        "create": ["recruitment.job.create", "recruitment.manage"],
        "update": ["recruitment.job.update", "recruitment.manage"],
        "partial_update": ["recruitment.job.update", "recruitment.manage"],
        "destroy": ["recruitment.job.delete", "recruitment.manage"],
        "publish": ["recruitment.job.publish", "recruitment.manage"],
        "pipeline": ["recruitment.applicant.view", "recruitment.manage"],
        "*": ["recruitment.manage"],
    }

    def create(self, request, *args, **kwargs):
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        department_id = request.data.get("department")
        branch_id = request.data.get("branch")
        employer_header = request.headers.get("X-Employer-Id") or request.META.get("HTTP_X_EMPLOYER_ID")

        dept_exists = None
        branch_exists = None
        dept_employer_id = None
        branch_employer_id = None
        try:
            from employees.models import Branch, Department

            if department_id:
                dept_qs = Department.objects.using(tenant_db).filter(id=department_id)
                dept_exists = dept_qs.exists()
                dept_employer_id = dept_qs.values_list("employer_id", flat=True).first()

            if branch_id:
                branch_qs = Branch.objects.using(tenant_db).filter(id=branch_id)
                branch_exists = branch_qs.exists()
                branch_employer_id = branch_qs.values_list("employer_id", flat=True).first()
        except Exception as exc:
            logger.warning(
                "Recruitment job create FK check failed",
                extra={
                    "employer_id": employer.id,
                    "tenant_db": tenant_db,
                    "department_id": department_id,
                    "branch_id": branch_id,
                    "exception": str(exc),
                },
            )

        logger.info(
            "Recruitment job create debug",
            extra={
                "employer_id": employer.id,
                "tenant_db": tenant_db,
                "x_employer_id": employer_header,
                "department_id": department_id,
                "branch_id": branch_id,
                "department_exists": dept_exists,
                "branch_exists": branch_exists,
                "department_employer_id": dept_employer_id,
                "branch_employer_id": branch_employer_id,
            },
        )

        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        qs = JobPosition.objects.using(tenant_db).filter(employer_id=employer.id)
        if is_delegate_user(self.request.user, employer.id):
            scope = get_delegate_scope(self.request.user, employer.id)
            qs = apply_scope_filter(
                qs,
                scope,
                branch_field="branch_id",
                department_field="department_id",
            )
        return qs

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        publish_scope = serializer.validated_data.get("publish_scope")
        department_id = serializer.validated_data.get("department")
        branch_id = serializer.validated_data.get("branch")

        logger.info(
            "Recruitment job create requested",
            extra={
                "employer_id": employer.id,
                "tenant_db": tenant_db,
                "department_id": department_id,
                "branch_id": branch_id,
            },
        )

        if publish_scope and not publish_scope_allowed(settings_obj, publish_scope):
            raise ValidationError("Publish scope conflicts with recruitment settings.")

        # Validate and fetch department/branch from tenant database
        department_instance = None
        branch_instance = None

        if department_id:
            try:
                from employees.models import Department
                department_instance = Department.objects.using(tenant_db).get(
                    id=department_id,
                    employer_id=employer.id
                )
            except Department.DoesNotExist:
                raise ValidationError({"department": "Department not found in your organization."})

        if branch_id:
            try:
                from employees.models import Branch
                branch_instance = Branch.objects.using(tenant_db).get(
                    id=branch_id,
                    employer_id=employer.id
                )
            except Branch.DoesNotExist:
                raise ValidationError({"branch": "Branch not found in your organization."})

        # Create instance without department/branch first
        validated_data = serializer.validated_data.copy()
        validated_data.pop('department', None)
        validated_data.pop('branch', None)

        instance = JobPosition(
            employer_id=employer.id,
            tenant_id=employer.id,
            created_by=self.request.user.id,
            updated_by=self.request.user.id,
            **validated_data
        )

        # Assign FK instances
        instance.department = department_instance
        instance.branch = branch_instance

        # Save to tenant database
        instance.save(using=tenant_db)

        if instance.is_published and not instance.published_at:
            instance.published_at = timezone.now()
            if instance.status == JobPosition.STATUS_DRAFT:
                instance.status = JobPosition.STATUS_OPEN
            instance.save(using=tenant_db, update_fields=["published_at", "status"])

        serializer.instance = instance

    def perform_update(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        publish_scope = serializer.validated_data.get("publish_scope")

        if publish_scope and not publish_scope_allowed(settings_obj, publish_scope):
            raise ValidationError("Publish scope conflicts with recruitment settings.")

        # Validate and fetch department/branch from tenant database if provided
        department_id = serializer.validated_data.get("department")
        branch_id = serializer.validated_data.get("branch")

        department_instance = None
        branch_instance = None

        if department_id:
            try:
                from employees.models import Department
                department_instance = Department.objects.using(tenant_db).get(
                    id=department_id,
                    employer_id=employer.id
                )
            except Department.DoesNotExist:
                raise ValidationError({"department": "Department not found in your organization."})

        if branch_id:
            try:
                from employees.models import Branch
                branch_instance = Branch.objects.using(tenant_db).get(
                    id=branch_id,
                    employer_id=employer.id
                )
            except Branch.DoesNotExist:
                raise ValidationError({"branch": "Branch not found in your organization."})

        # Remove FK fields from validated_data to handle them manually
        validated_data = serializer.validated_data.copy()
        validated_data.pop('department', None)
        validated_data.pop('branch', None)

        # Update instance fields
        instance = serializer.instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Assign FK instances if provided
        if 'department' in serializer.validated_data:
            instance.department = department_instance
        if 'branch' in serializer.validated_data:
            instance.branch = branch_instance

        instance.updated_by = self.request.user.id
        instance.save(using=tenant_db)

        if instance.is_published and not instance.published_at:
            instance.published_at = timezone.now()
            if instance.status == JobPosition.STATUS_DRAFT:
                instance.status = JobPosition.STATUS_OPEN
            instance.save(using=tenant_db, update_fields=["published_at", "status"])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        tenant_db = instance._state.db or "default"
        instance.status = JobPosition.STATUS_ARCHIVED
        instance.is_published = False
        instance.archived_at = timezone.now()
        instance.save(using=tenant_db)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"], url_path="publish")
    def publish(self, request, pk=None):
        job = self.get_object()
        tenant_db = job._state.db or "default"
        employer = get_active_employer(request, require_context=True)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)

        publish = request.data.get("publish")
        is_published = request.data.get("is_published")
        flag = publish if publish is not None else is_published
        if flag is None:
            raise ValidationError("publish or is_published is required.")
        flag = bool(flag)

        if flag:
            if job.publish_scope and not publish_scope_allowed(settings_obj, job.publish_scope):
                raise ValidationError("Job publish scope is not allowed by recruitment settings.")
            job.is_published = True
            job.published_at = timezone.now()
            if job.status == JobPosition.STATUS_DRAFT:
                job.status = JobPosition.STATUS_OPEN
        else:
            job.is_published = False
        job.updated_by = request.user.id
        job.save(using=tenant_db)
        serializer = self.get_serializer(job)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="pipeline")
    def pipeline(self, request, pk=None):
        job = self.get_object()
        tenant_db = job._state.db or "default"
        employer = get_active_employer(request, require_context=True)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        stages = get_effective_stages(job, tenant_db, settings_obj)

        applicants = RecruitmentApplicant.objects.using(tenant_db).filter(job=job)
        applicants_by_stage = defaultdict(list)
        counts = defaultdict(lambda: {"total": 0, "ready": 0, "blocked": 0, "in_progress": 0})

        for applicant in applicants:
            stage_id = str(applicant.stage_id) if applicant.stage_id else "unassigned"
            applicants_by_stage[stage_id].append(applicant)
            counts[stage_id]["total"] += 1
            if applicant.status == RecruitmentApplicant.STATUS_NEW:
                counts[stage_id]["ready"] += 1
            elif applicant.status in {RecruitmentApplicant.STATUS_BLOCKED, RecruitmentApplicant.STATUS_REFUSED}:
                counts[stage_id]["blocked"] += 1
            else:
                counts[stage_id]["in_progress"] += 1

        stage_payload = []
        applicant_payload = {}
        for stage in stages:
            stage_id = str(stage.id)
            stage_payload.append(
                {
                    "id": stage_id,
                    "name": stage.name,
                    "order": stage.sequence,
                    "folded": stage.is_folded,
                    "is_hired_stage": stage.is_hired_stage,
                    "counts": counts.get(stage_id, {"total": 0, "ready": 0, "blocked": 0, "in_progress": 0}),
                }
            )
            applicant_payload[stage_id] = RecruitmentApplicantPipelineSerializer(
                applicants_by_stage.get(stage_id, []),
                many=True,
            ).data

        response = {
            "job": {
                "id": str(job.id),
                "title": job.title,
                "status": job.status,
                "is_published": job.is_published,
            },
            "stages": stage_payload,
            "applicants": applicant_payload,
        }
        return Response(response)


class RecruitmentApplicantViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["recruitment.applicant.view", "recruitment.manage"],
        "retrieve": ["recruitment.applicant.view", "recruitment.manage"],
        "create": ["recruitment.applicant.create", "recruitment.manage"],
        "update": ["recruitment.applicant.update", "recruitment.manage"],
        "partial_update": ["recruitment.applicant.update", "recruitment.manage"],
        "move_stage": ["recruitment.applicant.move_stage", "recruitment.manage"],
        "refuse": ["recruitment.applicant.refuse", "recruitment.manage"],
        "*": ["recruitment.manage"],
    }

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        qs = RecruitmentApplicant.objects.using(tenant_db).filter(employer_id=employer.id)
        job_id = self.request.query_params.get("job_id")
        if job_id:
            qs = qs.filter(job_id=job_id)
        if is_delegate_user(self.request.user, employer.id):
            scope = get_delegate_scope(self.request.user, employer.id)
            qs = apply_scope_filter(
                qs,
                scope,
                branch_field="job__branch_id",
                department_field="job__department_id",
            )
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return RecruitmentApplicantCreateSerializer
        if self.action in ["update", "partial_update"]:
            return RecruitmentApplicantUpdateSerializer
        return RecruitmentApplicantSerializer

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        required_fields = get_required_application_fields(settings_obj)
        field_aliases = {
            "linkedin": "linkedin_url",
        }
        answers = serializer.validated_data.get("answers") or {}
        if not isinstance(answers, dict):
            answers = {}
        answers = {str(k): v for k, v in answers.items()}
        custom_required = get_required_custom_question_ids(settings_obj)
        missing_custom = [qid for qid in custom_required if not answers.get(qid)]
        if missing_custom:
            raise ValidationError({"answers": "Missing required custom question answers."})

        missing_fields = [
            field
            for field in required_fields
            if not serializer.validated_data.get(field_aliases.get(field, field))
        ]
        if missing_fields:
            raise ValidationError({"detail": f"Missing required fields: {', '.join(missing_fields)}"})

        applicant = serializer.save(
            employer_id=employer.id,
            tenant_id=employer.id,
            last_activity_at=timezone.now(),
        )
        if answers and applicant.answers != answers:
            applicant.answers = answers
            applicant.save(using=tenant_db, update_fields=["answers"])
        if applicant._state.db != tenant_db:
            applicant.save(using=tenant_db)

        stage = applicant.stage
        if stage:
            allowed = get_effective_stages(applicant.job, tenant_db, settings_obj)
            if stage not in allowed:
                raise ValidationError("Stage is not allowed for this job.")
        if not stage:
            stage = get_default_stage(applicant.job, tenant_db, settings_obj)
            if not stage:
                raise ValidationError("No stages configured for this job.")
            applicant.stage = stage
            applicant.save(using=tenant_db, update_fields=["stage"])

        RecruitmentApplicantStageHistory.objects.using(tenant_db).create(
            applicant=applicant,
            from_stage=None,
            to_stage=stage,
            action=RecruitmentApplicantStageHistory.ACTION_APPLY,
            changed_by_user_id=self.request.user.id,
        )

        send_application_ack_email(
            tenant_db=tenant_db,
            employer=employer,
            settings_obj=settings_obj,
            applicant=applicant,
            stage=stage,
        )

    @action(detail=True, methods=["post"], url_path="move-stage")
    def move_stage(self, request, pk=None):
        applicant = self.get_object()
        tenant_db = applicant._state.db or "default"
        employer = get_active_employer(request, require_context=True)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)

        serializer = RecruitmentStageMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        to_stage_id = serializer.validated_data["to_stage_id"]
        note = serializer.validated_data.get("note")

        stage = RecruitmentStage.objects.using(tenant_db).filter(id=to_stage_id).first()
        if not stage:
            raise NotFound("Stage not found.")

        allowed_stages = get_effective_stages(applicant.job, tenant_db, settings_obj)
        if stage not in allowed_stages:
            raise ValidationError("Stage is not allowed for this job.")

        from_stage = applicant.stage
        applicant.stage = stage
        applicant.last_activity_at = timezone.now()
        if stage.is_hired_stage:
            applicant.status = RecruitmentApplicant.STATUS_HIRED
            applicant.hired_at = timezone.now()
        elif stage.is_refused_stage:
            applicant.status = RecruitmentApplicant.STATUS_REFUSED
            applicant.refused_at = timezone.now()
        elif applicant.status == RecruitmentApplicant.STATUS_NEW:
            applicant.status = RecruitmentApplicant.STATUS_IN_PROGRESS
        applicant.save(using=tenant_db)

        # --- Onboarding: create employee + contract on contract/hired stages ---
        if stage.is_contract_stage or stage.is_hired_stage:
            from .onboarding import (
                create_employee_from_applicant,
                create_draft_contract,
                sign_contract_for_employee,
            )
            from contracts.models import Contract

            if not applicant.employee_id:
                employee = create_employee_from_applicant(applicant, tenant_db, employer.id)
                if employee:
                    applicant.employee = employee
                    applicant.save(using=tenant_db, update_fields=["employee"])

            if applicant.employee:
                if stage.is_contract_stage:
                    create_draft_contract(
                        applicant, applicant.employee, tenant_db, employer.id, request.user.id
                    )
                if stage.is_hired_stage:
                    has_contract = Contract.objects.using(tenant_db).filter(
                        employee=applicant.employee
                    ).exists()
                    if not has_contract:
                        create_draft_contract(
                            applicant, applicant.employee, tenant_db, employer.id, request.user.id
                        )
                    sign_contract_for_employee(applicant.employee, tenant_db)
        # --- End onboarding ---

        action = RecruitmentApplicantStageHistory.ACTION_MOVE
        if stage.is_hired_stage:
            action = RecruitmentApplicantStageHistory.ACTION_HIRED
        elif stage.is_refused_stage:
            action = RecruitmentApplicantStageHistory.ACTION_REFUSE
        RecruitmentApplicantStageHistory.objects.using(tenant_db).create(
            applicant=applicant,
            from_stage=from_stage,
            to_stage=stage,
            action=action,
            changed_by_user_id=request.user.id,
            note=note,
        )

        send_stage_email_if_enabled(
            tenant_db=tenant_db,
            employer=employer,
            settings_obj=settings_obj,
            applicant=applicant,
            stage=stage,
            default_subject=settings_obj.default_ack_email_subject,
            default_body=settings_obj.default_ack_email_body,
        )

        output = RecruitmentApplicantSerializer(applicant)
        return Response(output.data)

    @action(detail=True, methods=["post"], url_path="refuse")
    def refuse(self, request, pk=None):
        applicant = self.get_object()
        tenant_db = applicant._state.db or "default"
        employer = get_active_employer(request, require_context=True)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)

        serializer = RecruitmentRefuseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refuse_reason_id = serializer.validated_data.get("refuse_reason_id")
        note = serializer.validated_data.get("note")
        send_email = serializer.validated_data.get("send_email", True)

        refuse_reason = None
        if refuse_reason_id:
            refuse_reason = RecruitmentRefuseReason.objects.using(tenant_db).filter(id=refuse_reason_id).first()
            if not refuse_reason:
                raise NotFound("Refuse reason not found.")

        previous_stage = applicant.stage
        refused_stage = None
        for stage in get_effective_stages(applicant.job, tenant_db, settings_obj):
            if stage.is_refused_stage:
                refused_stage = stage
                break

        applicant.status = RecruitmentApplicant.STATUS_REFUSED
        applicant.refused_at = timezone.now()
        applicant.refuse_reason = refuse_reason
        applicant.refuse_note = note
        applicant.last_activity_at = timezone.now()
        if refused_stage:
            applicant.stage = refused_stage
        applicant.save(using=tenant_db)

        RecruitmentApplicantStageHistory.objects.using(tenant_db).create(
            applicant=applicant,
            from_stage=previous_stage,
            to_stage=refused_stage or previous_stage,
            action=RecruitmentApplicantStageHistory.ACTION_REFUSE,
            changed_by_user_id=request.user.id,
            note=note,
            meta={"refuse_reason_id": str(refuse_reason.id) if refuse_reason else None},
        )

        if send_email:
            from .services import send_refusal_email

            send_refusal_email(
                tenant_db=tenant_db,
                employer=employer,
                applicant=applicant,
                reason_name=refuse_reason.name if refuse_reason else "",
            )

        output = RecruitmentApplicantSerializer(applicant)
        return Response(output.data)


class RecruitmentStageViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    serializer_class = RecruitmentStageSerializer
    permission_map = {
        "list": ["recruitment.stage.view", "recruitment.manage"],
        "retrieve": ["recruitment.stage.view", "recruitment.manage"],
        "create": ["recruitment.stage.manage", "recruitment.manage"],
        "update": ["recruitment.stage.manage", "recruitment.manage"],
        "partial_update": ["recruitment.stage.manage", "recruitment.manage"],
        "destroy": ["recruitment.stage.manage", "recruitment.manage"],
        "*": ["recruitment.manage"],
    }

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        qs = RecruitmentStage.objects.using(tenant_db).filter(employer_id=employer.id)
        job_id = self.request.query_params.get("job_id")
        if job_id:
            qs = qs.filter(job_id=job_id)
        return qs

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        instance = serializer.save(
            settings=settings_obj,
            employer_id=employer.id,
            tenant_id=employer.id,
        )
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)
        invalidate_recruitment_settings_cache(employer.id, tenant_db)

    def perform_update(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)
        invalidate_recruitment_settings_cache(employer.id, tenant_db)

    def destroy(self, request, *args, **kwargs):
        stage = self.get_object()
        tenant_db = stage._state.db or "default"
        has_applicants = RecruitmentApplicant.objects.using(tenant_db).filter(stage=stage).exists()
        if has_applicants:
            raise ValidationError("Cannot delete stage with applicants assigned.")
        stage.delete(using=tenant_db)
        invalidate_recruitment_settings_cache(stage.employer_id, tenant_db)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecruitmentRefuseReasonViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    serializer_class = RecruitmentRefuseReasonSerializer
    permission_map = {
        "list": ["recruitment.refuse_reason.view", "recruitment.manage"],
        "retrieve": ["recruitment.refuse_reason.view", "recruitment.manage"],
        "create": ["recruitment.refuse_reason.manage", "recruitment.manage"],
        "update": ["recruitment.refuse_reason.manage", "recruitment.manage"],
        "partial_update": ["recruitment.refuse_reason.manage", "recruitment.manage"],
        "destroy": ["recruitment.refuse_reason.manage", "recruitment.manage"],
        "*": ["recruitment.manage"],
    }

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        return RecruitmentRefuseReason.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        instance = serializer.save(
            employer_id=employer.id,
            tenant_id=employer.id,
        )
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)


class RecruitmentReportsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["recruitment.report.view", "recruitment.manage"]

    def _get_context(self, request):
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        return employer, tenant_db

    @action(detail=False, methods=["get"], url_path="applicants")
    def applicants(self, request):
        employer, tenant_db = self._get_context(request)
        qs = RecruitmentApplicant.objects.using(tenant_db).filter(employer_id=employer.id)
        data = (
            qs.values("job_id")
            .annotate(
                total=Count("id"),
                hired=Count("id", filter=Q(status=RecruitmentApplicant.STATUS_HIRED)),
                refused=Count("id", filter=Q(status=RecruitmentApplicant.STATUS_REFUSED)),
                in_progress=Count("id", filter=~Q(status__in=[RecruitmentApplicant.STATUS_HIRED, RecruitmentApplicant.STATUS_REFUSED])),
            )
            .order_by("job_id")
        )
        return Response(list(data))

    @action(detail=False, methods=["get"], url_path="sources")
    def sources(self, request):
        employer, tenant_db = self._get_context(request)
        qs = RecruitmentApplicant.objects.using(tenant_db).filter(employer_id=employer.id)
        data = qs.values("source", "medium").annotate(total=Count("id")).order_by("-total")
        return Response(list(data))

    @action(detail=False, methods=["get"], url_path="velocity")
    def velocity(self, request):
        employer, tenant_db = self._get_context(request)
        histories = (
            RecruitmentApplicantStageHistory.objects.using(tenant_db)
            .filter(applicant__employer_id=employer.id)
            .select_related("applicant", "to_stage")
            .order_by("applicant_id", "changed_at")
        )
        durations = defaultdict(list)
        last_entry = {}
        for entry in histories:
            key = entry.applicant_id
            if key in last_entry:
                prev = last_entry[key]
                if prev.to_stage_id:
                    delta = (entry.changed_at - prev.changed_at).total_seconds()
                    durations[str(prev.to_stage_id)].append(delta)
            last_entry[key] = entry

        output = []
        for stage_id, values in durations.items():
            if not values:
                continue
            output.append(
                {
                    "stage_id": stage_id,
                    "avg_seconds": sum(values) / len(values),
                    "count": len(values),
                }
            )
        return Response(output)
