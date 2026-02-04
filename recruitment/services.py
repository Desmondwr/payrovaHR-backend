from datetime import timedelta

from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

from accounts.database_utils import ensure_tenant_database_loaded
from accounts.models import EmployerProfile

from .models import (
    JobPosition,
    RecruitmentApplicant,
    RecruitmentEmailLog,
    RecruitmentEmailTemplate,
    RecruitmentSettings,
    RecruitmentStage,
)

SETTINGS_CACHE_TTL_SECONDS = 300


def _cache_key(employer_id: int, tenant_db: str) -> str:
    return f"recruitment_settings:{tenant_db}:{employer_id}"


def ensure_recruitment_settings(employer_id: int, tenant_db: str = "default") -> RecruitmentSettings:
    defaults = RecruitmentSettings.build_defaults(employer_id)
    settings_obj, _ = RecruitmentSettings.objects.using(tenant_db).get_or_create(
        employer_id=employer_id,
        defaults=defaults,
    )

    updates = []
    if settings_obj.tenant_id is None:
        settings_obj.tenant_id = employer_id
        updates.append("tenant_id")
    if not settings_obj.schema_version:
        settings_obj.schema_version = defaults.get("schema_version", 1)
        updates.append("schema_version")
    if not settings_obj.application_fields:
        settings_obj.application_fields = defaults.get("application_fields", [])
        updates.append("application_fields")
    if not settings_obj.custom_questions:
        settings_obj.custom_questions = defaults.get("custom_questions", [])
        updates.append("custom_questions")
    if not settings_obj.cv_allowed_extensions:
        settings_obj.cv_allowed_extensions = defaults.get("cv_allowed_extensions", ["pdf", "doc", "docx"])
        updates.append("cv_allowed_extensions")

    if updates:
        settings_obj.save(using=tenant_db, update_fields=updates)

    if not RecruitmentStage.objects.using(tenant_db).filter(employer_id=employer_id).exists():
        settings_obj.seed_default_stages(db_alias=tenant_db)

    return settings_obj


def get_recruitment_settings_cached(employer_id: int, tenant_db: str = "default") -> dict:
    key = _cache_key(employer_id, tenant_db)
    cached = cache.get(key)
    if cached:
        return cached
    settings_obj = ensure_recruitment_settings(employer_id, tenant_db)
    payload = settings_obj.to_config_dict(db_alias=tenant_db)
    cache.set(key, payload, timeout=SETTINGS_CACHE_TTL_SECONDS)
    return payload


def invalidate_recruitment_settings_cache(employer_id: int, tenant_db: str = "default") -> None:
    cache.delete(_cache_key(employer_id, tenant_db))


def resolve_public_employer(request):
    employer = None
    employer_id = None
    employer_slug = None

    # Priority 1: Check for X-Employer-Slug header
    if hasattr(request, "headers"):
        slug_raw = request.headers.get("X-Employer-Slug") or request.headers.get("x-employer-slug")
        if slug_raw:
            employer_slug = slug_raw.strip()
            employer = EmployerProfile.objects.filter(slug=employer_slug).first()
            if employer:
                tenant_db = ensure_tenant_database_loaded(employer)
                return employer, tenant_db

    # Priority 2: Check for X-Employer-Id header
    if not employer and hasattr(request, "headers"):
        raw = request.headers.get("X-Employer-Id") or request.headers.get("x-employer-id")
        if raw:
            try:
                employer_id = int(raw)
            except (TypeError, ValueError):
                employer_id = None

    # Priority 3: Check for employer_id query parameter
    if employer_id is None:
        raw = request.query_params.get("employer_id") if hasattr(request, "query_params") else None
        if raw:
            try:
                employer_id = int(raw)
            except (TypeError, ValueError):
                employer_id = None

    # Try to get employer by ID
    if employer_id:
        employer = EmployerProfile.objects.filter(id=employer_id).first()

    # Priority 4: Fallback to CURRENT_TENANT_DB setting
    if not employer:
        tenant_db = getattr(django_settings, "CURRENT_TENANT_DB", None)
        if tenant_db and tenant_db.startswith("tenant_"):
            try:
                employer_id = int(tenant_db.split("_")[1])
            except (IndexError, ValueError):
                employer_id = None
            if employer_id:
                employer = EmployerProfile.objects.filter(id=employer_id).first()

    if not employer:
        return None, None

    tenant_db = ensure_tenant_database_loaded(employer)
    return employer, tenant_db


def job_visible_to_public(settings: RecruitmentSettings) -> bool:
    return settings.job_publish_scope in {
        RecruitmentSettings.PUBLISH_SCOPE_PUBLIC,
        RecruitmentSettings.PUBLISH_SCOPE_BOTH,
    }


def job_visible_to_internal(settings: RecruitmentSettings) -> bool:
    return settings.job_publish_scope in {
        RecruitmentSettings.PUBLISH_SCOPE_INTERNAL,
        RecruitmentSettings.PUBLISH_SCOPE_BOTH,
    }


def job_scope_allows_public(job: JobPosition, settings: RecruitmentSettings) -> bool:
    scope = job.publish_scope or settings.job_publish_scope
    return scope in {RecruitmentSettings.PUBLISH_SCOPE_PUBLIC, RecruitmentSettings.PUBLISH_SCOPE_BOTH}


def job_scope_allows_internal(job: JobPosition, settings: RecruitmentSettings) -> bool:
    scope = job.publish_scope or settings.job_publish_scope
    return scope in {RecruitmentSettings.PUBLISH_SCOPE_INTERNAL, RecruitmentSettings.PUBLISH_SCOPE_BOTH}


def publish_scope_allowed(settings_obj: RecruitmentSettings, scope: str) -> bool:
    if not scope:
        return True
    if settings_obj.job_publish_scope == RecruitmentSettings.PUBLISH_SCOPE_INTERNAL:
        return scope == RecruitmentSettings.PUBLISH_SCOPE_INTERNAL
    if settings_obj.job_publish_scope == RecruitmentSettings.PUBLISH_SCOPE_PUBLIC:
        return scope == RecruitmentSettings.PUBLISH_SCOPE_PUBLIC
    return True


def public_apply_allowed(settings: RecruitmentSettings) -> bool:
    return bool(settings.public_applications_enabled)


def internal_apply_allowed(settings: RecruitmentSettings) -> bool:
    return bool(settings.internal_applications_enabled)


def duplicate_application_blocked(settings: RecruitmentSettings, last_applied_at) -> bool:
    if settings.duplicate_application_action != RecruitmentSettings.DUPLICATE_ACTION_BLOCK:
        return False
    window_days = int(settings.duplicate_application_window_days or 0)
    if window_days <= 0:
        return False
    if not last_applied_at:
        return False
    cutoff = timezone.now() - timedelta(days=window_days)
    return last_applied_at >= cutoff


def public_apply_rate_limit(settings: RecruitmentSettings) -> str:
    requests = int(settings.public_apply_rate_limit_requests or 0)
    window = int(settings.public_apply_rate_limit_window_seconds or 0)
    if requests <= 0 or window <= 0:
        return ""
    return f"{requests}/{window}s"


def get_required_application_fields(settings_obj: RecruitmentSettings) -> set:
    required = set()
    for field in settings_obj.application_fields or []:
        if field.get("enabled", True) and field.get("required", False):
            key = field.get("key")
            if key:
                required.add(key)
    return required


def get_required_custom_question_ids(settings_obj: RecruitmentSettings) -> set:
    required = set()
    for question in settings_obj.custom_questions or []:
        if question.get("is_active", True) and question.get("required", False):
            qid = question.get("id")
            if qid:
                required.add(str(qid))
    return required


def get_effective_stages(job: JobPosition, tenant_db: str, settings_obj: RecruitmentSettings):
    stages = RecruitmentStage.objects.using(tenant_db).filter(
        settings=settings_obj,
        is_active=True,
    )
    global_stages = stages.filter(scope=RecruitmentStage.SCOPE_GLOBAL)
    job_stages = stages.filter(scope=RecruitmentStage.SCOPE_JOB, job_id=str(job.id))
    combined = list(global_stages) + list(job_stages)
    combined.sort(key=lambda s: (s.sequence, s.created_at))
    return combined


def get_default_stage(job: JobPosition, tenant_db: str, settings_obj: RecruitmentSettings) -> RecruitmentStage:
    stages = get_effective_stages(job, tenant_db, settings_obj)
    if not stages:
        return None
    for stage in stages:
        if stage.name.strip().lower() == "new":
            return stage
    return stages[0]


def render_template(template: str, context: dict) -> str:
    if not template:
        return ""
    rendered = template
    for key, value in (context or {}).items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def _select_email_template(tenant_db: str, employer_id: int, code: str, stage=None, job=None):
    qs = RecruitmentEmailTemplate.objects.using(tenant_db).filter(
        employer_id=employer_id,
        code=code,
        is_active=True,
    )
    if stage:
        stage_specific = qs.filter(stage=stage)
        if stage_specific.exists():
            return stage_specific.first()
    if job:
        job_specific = qs.filter(job_id=str(job.id))
        if job_specific.exists():
            return job_specific.first()
    return qs.first()


def send_recruitment_email(
    *,
    tenant_db: str,
    employer: EmployerProfile,
    applicant: RecruitmentApplicant,
    subject: str,
    body: str,
    template=None,
):
    to_email = applicant.email
    status = RecruitmentEmailLog.STATUS_SENT
    error_message = None
    sent_at = timezone.now()

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
    except Exception as exc:
        status = RecruitmentEmailLog.STATUS_FAILED
        error_message = str(exc)

    RecruitmentEmailLog.objects.using(tenant_db).create(
        employer_id=employer.id,
        tenant_id=employer.id,
        applicant=applicant,
        job=applicant.job,
        template=template,
        to_email=to_email,
        subject=subject,
        body=body,
        status=status,
        error_message=error_message,
        sent_at=sent_at if status == RecruitmentEmailLog.STATUS_SENT else None,
    )


def send_stage_email_if_enabled(
    *,
    tenant_db: str,
    employer: EmployerProfile,
    settings_obj: RecruitmentSettings,
    applicant: RecruitmentApplicant,
    stage: RecruitmentStage,
    default_subject: str = "",
    default_body: str = "",
):
    if not settings_obj.email_automation_enabled:
        return
    if not stage.auto_email_enabled:
        return

    template = _select_email_template(
        tenant_db=tenant_db,
        employer_id=employer.id,
        code=RecruitmentEmailTemplate.CODE_STAGE_ENTER,
        stage=stage,
        job=applicant.job,
    )

    context = {
        "applicant_name": applicant.full_name,
        "candidate_name": applicant.full_name,
        "job_title": applicant.job.title,
        "company_name": employer.company_name,
        "stage_name": stage.name,
        "next_steps": "",
    }

    subject = stage.auto_email_subject or default_subject
    body = stage.auto_email_body or default_body

    if template:
        subject = template.subject
        body = template.body

    subject = render_template(subject, context)
    body = render_template(body, context)

    if subject and body:
        send_recruitment_email(
            tenant_db=tenant_db,
            employer=employer,
            applicant=applicant,
            subject=subject,
            body=body,
            template=template,
        )


def send_application_ack_email(
    *,
    tenant_db: str,
    employer: EmployerProfile,
    settings_obj: RecruitmentSettings,
    applicant: RecruitmentApplicant,
    stage: RecruitmentStage,
):
    if not settings_obj.email_automation_enabled:
        return
    if not stage or not stage.auto_email_enabled:
        return

    template = _select_email_template(
        tenant_db=tenant_db,
        employer_id=employer.id,
        code=RecruitmentEmailTemplate.CODE_APPLICATION_ACK,
        stage=stage,
        job=applicant.job,
    )

    context = {
        "applicant_name": applicant.full_name,
        "candidate_name": applicant.full_name,
        "job_title": applicant.job.title,
        "company_name": employer.company_name,
        "stage_name": stage.name if stage else "New",
        "next_steps": "",
    }

    subject = settings_obj.default_ack_email_subject
    body = settings_obj.default_ack_email_body

    if template:
        subject = template.subject
        body = template.body

    subject = render_template(subject, context)
    body = render_template(body, context)

    if subject and body:
        send_recruitment_email(
            tenant_db=tenant_db,
            employer=employer,
            applicant=applicant,
            subject=subject,
            body=body,
            template=template,
        )


def send_refusal_email(
    *,
    tenant_db: str,
    employer: EmployerProfile,
    applicant: RecruitmentApplicant,
    reason_name: str = "",
):
    template = _select_email_template(
        tenant_db=tenant_db,
        employer_id=employer.id,
        code=RecruitmentEmailTemplate.CODE_REFUSAL,
        stage=applicant.stage,
        job=applicant.job,
    )

    context = {
        "applicant_name": applicant.full_name,
        "candidate_name": applicant.full_name,
        "job_title": applicant.job.title,
        "company_name": employer.company_name,
        "stage_name": applicant.stage.name if applicant.stage else "",
        "next_steps": "",
        "refuse_reason": reason_name or "",
    }

    subject = "Application update"
    body = "Thank you for your interest. We have decided to move forward with other candidates."

    if template:
        subject = template.subject
        body = template.body

    subject = render_template(subject, context)
    body = render_template(body, context)

    send_recruitment_email(
        tenant_db=tenant_db,
        employer=employer,
        applicant=applicant,
        subject=subject,
        body=body,
        template=template,
    )
