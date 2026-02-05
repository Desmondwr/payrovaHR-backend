from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

from accounts.database_utils import ensure_tenant_database_loaded
from accounts.models import EmployeeMembership, EmployerProfile
from accounts.notifications import create_notification

from .models import (
    JobPosition,
    RecruitmentApplicant,
    RecruitmentAttachment,
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


def duplicate_application_detected(settings: RecruitmentSettings, last_applied_at) -> bool:
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


def notify_internal_job_posted(
    *,
    job: JobPosition,
    employer: EmployerProfile,
    settings_obj: RecruitmentSettings = None,
    actor_user_id: int = None,
) -> int:
    """
    Notify active employees when a job is posted for internal visibility.
    Returns number of notifications created.
    """
    if not job or not job.is_published:
        return 0

    tenant_db = job._state.db or "default"
    settings_obj = settings_obj or ensure_recruitment_settings(job.employer_id, tenant_db)
    if not job_scope_allows_internal(job, settings_obj):
        return 0

    memberships = (
        EmployeeMembership.objects.filter(
            employer_profile_id=employer.id,
            status=EmployeeMembership.STATUS_ACTIVE,
        )
        .select_related("user")
    )

    recipients = []
    for membership in memberships:
        user = membership.user
        if not user or not user.is_active:
            continue
        if actor_user_id and user.id == actor_user_id:
            continue
        recipients.append(user)

    if not recipients:
        return 0

    title = f"New internal role: {job.title}"
    body = f"{employer.company_name} posted a new internal opportunity."
    payload = {
        "job_id": str(job.id),
        "job_title": job.title,
        "path": f"/employee/jobs/{job.id}",
        "event": "recruitment.job_posted",
        "publish_scope": job.publish_scope or settings_obj.job_publish_scope,
    }

    for user in recipients:
        create_notification(
            user=user,
            title=title,
            body=body,
            type="INFO",
            data=payload,
            employer_profile=employer,
        )

    return len(recipients)


def _get_employer_notification_recipients(
    employer: EmployerProfile,
    *,
    exclude_user_id: int = None,
) -> list:
    recipients = {}
    if employer and getattr(employer, "user", None) and employer.user.is_active:
        recipients[employer.user.id] = employer.user

    memberships = (
        EmployeeMembership.objects.filter(
            employer_profile_id=employer.id,
            status=EmployeeMembership.STATUS_ACTIVE,
            role__in=[
                EmployeeMembership.ROLE_HR,
                EmployeeMembership.ROLE_ADMIN,
                EmployeeMembership.ROLE_MANAGER,
            ],
        )
        .select_related("user")
    )
    for membership in memberships:
        user = membership.user
        if not user or not user.is_active:
            continue
        recipients[user.id] = user

    if exclude_user_id:
        recipients.pop(exclude_user_id, None)

    return list(recipients.values())


def notify_employer_application_received(
    *,
    applicant: RecruitmentApplicant,
    employer: EmployerProfile,
    actor_user_id: int = None,
    source: str = "public",
    is_duplicate: bool = False,
) -> int:
    if not applicant or not employer:
        return 0

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if not recipients:
        return 0

    job_title = applicant.job.title if applicant.job else "a role"
    title = "New job application"
    if applicant.is_internal_applicant or source == "internal":
        title = "Internal application submitted"
    if is_duplicate:
        title = "Duplicate application received"
    body = f"{applicant.full_name} applied for {job_title}."
    if is_duplicate:
        body = f"{applicant.full_name} submitted a duplicate application for {job_title}."
    data = {
        "applicant_id": str(applicant.id),
        "job_id": str(applicant.job_id) if applicant.job_id else None,
        "path": "/employer/recruitment",
        "event": "recruitment.application_submitted",
        "source": source,
        "is_internal": bool(applicant.is_internal_applicant),
        "is_duplicate": bool(is_duplicate),
    }

    for user in recipients:
        create_notification(
            user=user,
            title=title,
            body=body,
            type="ACTION",
            data=data,
            employer_profile=employer,
        )

    return len(recipients)


def notify_applicant_application_received(
    *,
    applicant: RecruitmentApplicant,
    user,
    employer: EmployerProfile,
) -> bool:
    if not applicant or not user:
        return False

    job_title = applicant.job.title if applicant.job else "the role"
    title = "Application submitted"
    body = f"We received your application for {job_title}."
    data = {
        "applicant_id": str(applicant.id),
        "job_id": str(applicant.job_id) if applicant.job_id else None,
        "path": f"/employee/jobs/{applicant.job_id}" if applicant.job_id else "/employee/jobs",
        "event": "recruitment.application_submitted",
    }

    create_notification(
        user=user,
        title=title,
        body=body,
        type="INFO",
        data=data,
        employer_profile=employer,
    )
    return True


def _get_applicant_user(applicant: RecruitmentApplicant):
    if not applicant or not applicant.user_id:
        return None
    User = get_user_model()
    return User.objects.filter(id=applicant.user_id, is_active=True).first()


def notify_recruitment_stage_moved(
    *,
    applicant: RecruitmentApplicant,
    employer: EmployerProfile,
    from_stage: RecruitmentStage = None,
    to_stage: RecruitmentStage = None,
    actor_user_id: int = None,
) -> None:
    if not applicant or not employer or not to_stage:
        return

    job_title = applicant.job.title if applicant.job else "a role"
    stage_name = to_stage.name

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if recipients:
        for user in recipients:
            create_notification(
                user=user,
                title="Applicant moved stage",
                body=f"{applicant.full_name} moved to {stage_name} for {job_title}.",
                type="ACTION",
                data={
                    "applicant_id": str(applicant.id),
                    "job_id": str(applicant.job_id) if applicant.job_id else None,
                    "path": "/employer/recruitment",
                    "event": "recruitment.stage_moved",
                    "to_stage": stage_name,
                    "from_stage": from_stage.name if from_stage else None,
                },
                employer_profile=employer,
            )

    user = _get_applicant_user(applicant)
    if user:
        create_notification(
            user=user,
            title="Application update",
            body=f"Your application for {job_title} moved to {stage_name}.",
            type="INFO",
            data={
                "applicant_id": str(applicant.id),
                "job_id": str(applicant.job_id) if applicant.job_id else None,
                "path": f"/employee/jobs/{applicant.job_id}" if applicant.job_id else "/employee/jobs",
                "event": "recruitment.stage_moved",
                "to_stage": stage_name,
                "from_stage": from_stage.name if from_stage else None,
            },
            employer_profile=employer,
        )


def notify_recruitment_refused(
    *,
    applicant: RecruitmentApplicant,
    employer: EmployerProfile,
    actor_user_id: int = None,
    reason_name: str = "",
) -> None:
    if not applicant or not employer:
        return

    job_title = applicant.job.title if applicant.job else "the role"

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if recipients:
        for user in recipients:
            create_notification(
                user=user,
                title="Application refused",
                body=f"{applicant.full_name} was marked refused for {job_title}.",
                type="ALERT",
                data={
                    "applicant_id": str(applicant.id),
                    "job_id": str(applicant.job_id) if applicant.job_id else None,
                    "path": "/employer/recruitment",
                    "event": "recruitment.refused",
                    "reason": reason_name or None,
                },
                employer_profile=employer,
            )

    user = _get_applicant_user(applicant)
    if user:
        create_notification(
            user=user,
            title="Application update",
            body=f"Your application for {job_title} was not selected.",
            type="INFO",
            data={
                "applicant_id": str(applicant.id),
                "job_id": str(applicant.job_id) if applicant.job_id else None,
                "path": f"/employee/jobs/{applicant.job_id}" if applicant.job_id else "/employee/jobs",
                "event": "recruitment.refused",
            },
            employer_profile=employer,
        )


def notify_recruitment_hired(
    *,
    applicant: RecruitmentApplicant,
    employer: EmployerProfile,
    actor_user_id: int = None,
) -> None:
    if not applicant or not employer:
        return

    job_title = applicant.job.title if applicant.job else "the role"

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if recipients:
        for user in recipients:
            create_notification(
                user=user,
                title="Applicant hired",
                body=f"{applicant.full_name} was marked hired for {job_title}.",
                type="ACTION",
                data={
                    "applicant_id": str(applicant.id),
                    "job_id": str(applicant.job_id) if applicant.job_id else None,
                    "path": "/employer/recruitment",
                    "event": "recruitment.hired",
                },
                employer_profile=employer,
            )

    user = _get_applicant_user(applicant)
    if user:
        create_notification(
            user=user,
            title="Congratulations!",
            body=f"You have been marked hired for {job_title}.",
            type="INFO",
            data={
                "applicant_id": str(applicant.id),
                "job_id": str(applicant.job_id) if applicant.job_id else None,
                "path": f"/employee/jobs/{applicant.job_id}" if applicant.job_id else "/employee/jobs",
                "event": "recruitment.hired",
            },
            employer_profile=employer,
        )


def notify_recruitment_offer_sent(
    *,
    offer,
    employer: EmployerProfile,
    actor_user_id: int = None,
    settings_obj: RecruitmentSettings = None,
) -> None:
    if not offer or not employer:
        return

    applicant = getattr(offer, "applicant", None)
    if not applicant:
        return

    tenant_db = offer._state.db
    if not tenant_db and getattr(applicant, "_state", None):
        tenant_db = applicant._state.db
    tenant_db = tenant_db or "default"
    if settings_obj is None and employer:
        try:
            settings_obj = ensure_recruitment_settings(employer.id, tenant_db)
        except Exception:
            settings_obj = None

    job_title = applicant.job.title if applicant.job else "the role"
    esign_enabled = bool(getattr(settings_obj, "integration_offers_esign_enabled", False))

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if recipients:
        title = "Offer sent"
        body = f"Offer sent to {applicant.full_name} for {job_title}."
        if esign_enabled:
            title = "Offer sent for e-signature"
            body = f"Offer sent to {applicant.full_name} for e-signature on {job_title}."
        for user in recipients:
            create_notification(
                user=user,
                title=title,
                body=body,
                type="ACTION",
                data={
                    "applicant_id": str(applicant.id),
                    "job_id": str(applicant.job_id) if applicant.job_id else None,
                    "offer_id": str(getattr(offer, "id", "")) or None,
                    "path": "/employer/recruitment",
                    "event": "recruitment.offer_sent",
                    "integration_esign_enabled": esign_enabled,
                },
                employer_profile=employer,
            )

    user = _get_applicant_user(applicant)
    if user:
        title = "Offer sent"
        body = f"An offer has been sent to you for {job_title}."
        if esign_enabled:
            title = "Offer ready for signature"
            body = f"Your offer for {job_title} is ready for e-signature."
        create_notification(
            user=user,
            title=title,
            body=body,
            type="INFO",
            data={
                "applicant_id": str(applicant.id),
                "job_id": str(applicant.job_id) if applicant.job_id else None,
                "offer_id": str(getattr(offer, "id", "")) or None,
                "path": f"/employee/jobs/{applicant.job_id}" if applicant.job_id else "/employee/jobs",
                "event": "recruitment.offer_sent",
                "integration_esign_enabled": esign_enabled,
            },
            employer_profile=employer,
        )


def _is_interview_stage(stage: RecruitmentStage) -> bool:
    if not stage:
        return False
    name = (stage.name or "").lower()
    return "interview" in name


def notify_integration_job_board_ingest(
    *,
    job: JobPosition,
    employer: EmployerProfile,
    settings_obj: RecruitmentSettings = None,
    actor_user_id: int = None,
) -> int:
    if not job or not employer:
        return 0

    tenant_db = job._state.db or "default"
    settings_obj = settings_obj or ensure_recruitment_settings(employer.id, tenant_db)
    if not settings_obj.integration_job_board_ingest_enabled:
        return 0
    if not job.is_published:
        return 0
    if not job_scope_allows_public(job, settings_obj):
        return 0

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if not recipients:
        return 0

    title = "Job board sync queued"
    body = f"{job.title} is queued for job board distribution."
    payload = {
        "job_id": str(job.id),
        "job_title": job.title,
        "path": "/employer/recruitment",
        "event": "recruitment.integration.job_board_ingest",
    }

    for user in recipients:
        create_notification(
            user=user,
            title=title,
            body=body,
            type="INFO",
            data=payload,
            employer_profile=employer,
        )

    return len(recipients)


def notify_integration_resume_ocr_queued(
    *,
    applicant: RecruitmentApplicant,
    employer: EmployerProfile,
    settings_obj: RecruitmentSettings = None,
    actor_user_id: int = None,
) -> int:
    if not applicant or not employer:
        return 0

    tenant_db = applicant._state.db or "default"
    settings_obj = settings_obj or ensure_recruitment_settings(employer.id, tenant_db)
    if not settings_obj.integration_resume_ocr_enabled:
        return 0

    has_cv = RecruitmentAttachment.objects.using(tenant_db).filter(
        applicant=applicant,
        purpose=RecruitmentAttachment.PURPOSE_CV,
    ).exists()
    if not has_cv:
        return 0

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if not recipients:
        return 0

    job_title = applicant.job.title if applicant.job else "the role"
    title = "Resume parsing queued"
    body = f"Resume OCR queued for {applicant.full_name} ({job_title})."
    payload = {
        "applicant_id": str(applicant.id),
        "job_id": str(applicant.job_id) if applicant.job_id else None,
        "path": "/employer/recruitment",
        "event": "recruitment.integration.resume_ocr",
    }

    for user in recipients:
        create_notification(
            user=user,
            title=title,
            body=body,
            type="INFO",
            data=payload,
            employer_profile=employer,
        )

    return len(recipients)


def notify_integration_interview_scheduling(
    *,
    applicant: RecruitmentApplicant,
    employer: EmployerProfile,
    stage: RecruitmentStage,
    settings_obj: RecruitmentSettings = None,
    actor_user_id: int = None,
) -> None:
    if not applicant or not employer or not stage:
        return

    tenant_db = applicant._state.db or "default"
    settings_obj = settings_obj or ensure_recruitment_settings(employer.id, tenant_db)
    if not settings_obj.integration_interview_scheduling_enabled:
        return
    if not _is_interview_stage(stage):
        return

    job_title = applicant.job.title if applicant.job else "the role"
    stage_name = stage.name

    recipients = _get_employer_notification_recipients(
        employer,
        exclude_user_id=actor_user_id,
    )
    if recipients:
        for user in recipients:
            create_notification(
                user=user,
                title="Interview scheduling needed",
                body=f"Schedule {stage_name} for {applicant.full_name} ({job_title}).",
                type="ACTION",
                data={
                    "applicant_id": str(applicant.id),
                    "job_id": str(applicant.job_id) if applicant.job_id else None,
                    "path": "/employer/recruitment",
                    "event": "recruitment.integration.interview_scheduling",
                    "stage": stage_name,
                },
                employer_profile=employer,
            )

    user = _get_applicant_user(applicant)
    if user:
        create_notification(
            user=user,
            title="Interview scheduling",
            body=f"We will contact you to schedule your {stage_name} for {job_title}.",
            type="INFO",
            data={
                "applicant_id": str(applicant.id),
                "job_id": str(applicant.job_id) if applicant.job_id else None,
                "path": f"/employee/jobs/{applicant.job_id}" if applicant.job_id else "/employee/jobs",
                "event": "recruitment.integration.interview_scheduling",
                "stage": stage_name,
            },
            employer_profile=employer,
        )
