import uuid

from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .defaults import RECRUITMENT_DEFAULTS


class RecruitmentSettings(models.Model):
    PUBLISH_SCOPE_INTERNAL = "INTERNAL_ONLY"
    PUBLISH_SCOPE_PUBLIC = "PUBLIC_ONLY"
    PUBLISH_SCOPE_BOTH = "BOTH"

    PUBLISH_SCOPE_CHOICES = [
        (PUBLISH_SCOPE_INTERNAL, "Internal only"),
        (PUBLISH_SCOPE_PUBLIC, "Public only"),
        (PUBLISH_SCOPE_BOTH, "Internal + Public"),
    ]

    DUPLICATE_ACTION_BLOCK = "BLOCK"
    DUPLICATE_ACTION_WARN = "WARN"
    DUPLICATE_ACTION_ALLOW = "ALLOW"

    DUPLICATE_ACTION_CHOICES = [
        (DUPLICATE_ACTION_BLOCK, "Block"),
        (DUPLICATE_ACTION_WARN, "Warn"),
        (DUPLICATE_ACTION_ALLOW, "Allow"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True, help_text="Employer ID from main database")
    tenant_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Alias for employer_id to simplify tenant-aware queries",
    )
    schema_version = models.IntegerField(default=1)

    job_publish_scope = models.CharField(
        max_length=20,
        choices=PUBLISH_SCOPE_CHOICES,
        default=PUBLISH_SCOPE_INTERNAL,
    )

    public_applications_enabled = models.BooleanField(default=False)
    internal_applications_enabled = models.BooleanField(default=True)
    public_apply_requires_login = models.BooleanField(default=False)
    internal_apply_requires_login = models.BooleanField(default=True)

    application_fields = models.JSONField(default=list, blank=True)
    custom_questions = models.JSONField(default=list, blank=True)

    email_automation_enabled = models.BooleanField(default=True)
    default_ack_email_subject = models.CharField(max_length=200, blank=True)
    default_ack_email_body = models.TextField(blank=True)

    cv_allowed_extensions = models.JSONField(default=list, blank=True)
    cv_max_file_size_mb = models.IntegerField(default=10)

    public_apply_rate_limit_requests = models.IntegerField(default=20)
    public_apply_rate_limit_window_seconds = models.IntegerField(default=3600)
    public_apply_captcha_enabled = models.BooleanField(default=False)
    public_apply_spam_check_enabled = models.BooleanField(default=True)
    public_apply_honeypot_enabled = models.BooleanField(default=True)

    duplicate_application_window_days = models.IntegerField(default=30)
    duplicate_application_action = models.CharField(
        max_length=10,
        choices=DUPLICATE_ACTION_CHOICES,
        default=DUPLICATE_ACTION_BLOCK,
    )

    integration_interview_scheduling_enabled = models.BooleanField(default=False)
    integration_offers_esign_enabled = models.BooleanField(default=False)
    integration_resume_ocr_enabled = models.BooleanField(default=False)
    integration_job_board_ingest_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "recruitment_settings"
        verbose_name = "Recruitment Settings"
        verbose_name_plural = "Recruitment Settings"
        unique_together = [["employer_id"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Recruitment Settings - Employer {self.employer_id}"

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        super().save(*args, **kwargs)

    @classmethod
    def build_defaults(cls, employer_id: int) -> dict:
        defaults = RECRUITMENT_DEFAULTS.get("settings", {})
        return {
            "employer_id": employer_id,
            "tenant_id": employer_id,
            "schema_version": RECRUITMENT_DEFAULTS.get("schema_version", 1),
            "job_publish_scope": defaults.get("job_publish_scope", cls.PUBLISH_SCOPE_INTERNAL),
            "public_applications_enabled": defaults.get("public_applications_enabled", False),
            "internal_applications_enabled": defaults.get("internal_applications_enabled", True),
            "public_apply_requires_login": defaults.get("public_apply_requires_login", False),
            "internal_apply_requires_login": defaults.get("internal_apply_requires_login", True),
            "application_fields": RECRUITMENT_DEFAULTS.get("application_fields", []),
            "custom_questions": RECRUITMENT_DEFAULTS.get("custom_questions", []),
            "email_automation_enabled": defaults.get("email_automation_enabled", True),
            "default_ack_email_subject": defaults.get("default_ack_email_subject", ""),
            "default_ack_email_body": defaults.get("default_ack_email_body", ""),
            "cv_allowed_extensions": defaults.get("cv_allowed_extensions", ["pdf", "doc", "docx"]),
            "cv_max_file_size_mb": defaults.get("cv_max_file_size_mb", 10),
            "public_apply_rate_limit_requests": defaults.get("public_apply_rate_limit_requests", 20),
            "public_apply_rate_limit_window_seconds": defaults.get("public_apply_rate_limit_window_seconds", 3600),
            "public_apply_captcha_enabled": defaults.get("public_apply_captcha_enabled", False),
            "public_apply_spam_check_enabled": defaults.get("public_apply_spam_check_enabled", True),
            "public_apply_honeypot_enabled": defaults.get("public_apply_honeypot_enabled", True),
            "duplicate_application_window_days": defaults.get("duplicate_application_window_days", 30),
            "duplicate_application_action": defaults.get("duplicate_application_action", cls.DUPLICATE_ACTION_BLOCK),
            "integration_interview_scheduling_enabled": defaults.get("integration_interview_scheduling_enabled", False),
            "integration_offers_esign_enabled": defaults.get("integration_offers_esign_enabled", False),
            "integration_resume_ocr_enabled": defaults.get("integration_resume_ocr_enabled", False),
            "integration_job_board_ingest_enabled": defaults.get("integration_job_board_ingest_enabled", False),
        }

    def to_config_dict(self, db_alias: str = None) -> dict:
        alias = db_alias or self._state.db or "default"
        stages = (
            RecruitmentStage.objects.using(alias)
            .filter(settings=self)
            .order_by("sequence", "created_at")
        )
        return {
            "id": str(self.id),
            "employer_id": self.employer_id,
            "schema_version": self.schema_version,
            "job_publish_scope": self.job_publish_scope,
            "public_applications_enabled": self.public_applications_enabled,
            "internal_applications_enabled": self.internal_applications_enabled,
            "public_apply_requires_login": self.public_apply_requires_login,
            "internal_apply_requires_login": self.internal_apply_requires_login,
            "application_fields": self.application_fields or [],
            "custom_questions": self.custom_questions or [],
            "email_automation_enabled": self.email_automation_enabled,
            "default_ack_email_subject": self.default_ack_email_subject,
            "default_ack_email_body": self.default_ack_email_body,
            "cv_allowed_extensions": self.cv_allowed_extensions or [],
            "cv_max_file_size_mb": self.cv_max_file_size_mb,
            "public_apply_rate_limit_requests": self.public_apply_rate_limit_requests,
            "public_apply_rate_limit_window_seconds": self.public_apply_rate_limit_window_seconds,
            "public_apply_captcha_enabled": self.public_apply_captcha_enabled,
            "public_apply_spam_check_enabled": self.public_apply_spam_check_enabled,
            "public_apply_honeypot_enabled": self.public_apply_honeypot_enabled,
            "duplicate_application_window_days": self.duplicate_application_window_days,
            "duplicate_application_action": self.duplicate_application_action,
            "integration_interview_scheduling_enabled": self.integration_interview_scheduling_enabled,
            "integration_offers_esign_enabled": self.integration_offers_esign_enabled,
            "integration_resume_ocr_enabled": self.integration_resume_ocr_enabled,
            "integration_job_board_ingest_enabled": self.integration_job_board_ingest_enabled,
            "stages": [stage.to_dict() for stage in stages],
        }

    def seed_default_stages(self, db_alias: str = "default") -> None:
        defaults = RECRUITMENT_DEFAULTS.get("stages", [])
        for entry in defaults:
            name = entry.get("name")
            sequence = entry.get("sequence")
            if not name:
                continue
            exists = RecruitmentStage.objects.using(db_alias).filter(
                employer_id=self.employer_id,
                name=name,
            ).exists()
            if exists:
                continue
            RecruitmentStage.objects.using(db_alias).create(
                settings=self,
                employer_id=self.employer_id,
                tenant_id=self.tenant_id,
                name=name,
                sequence=sequence or 0,
                scope=entry.get("scope", RecruitmentStage.SCOPE_GLOBAL),
                is_active=entry.get("is_active", True),
                is_folded=entry.get("is_folded", False),
                is_hired_stage=entry.get("is_hired_stage", False),
                is_refused_stage=entry.get("is_refused_stage", False),
                is_contract_stage=entry.get("is_contract_stage", False),
                auto_email_enabled=entry.get("auto_email_enabled", False),
                auto_email_subject=entry.get("auto_email_subject"),
                auto_email_body=entry.get("auto_email_body"),
            )


class RecruitmentStage(models.Model):
    SCOPE_GLOBAL = "GLOBAL"
    SCOPE_JOB = "JOB"

    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_JOB, "Job-specific"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    settings = models.ForeignKey(
        RecruitmentSettings,
        on_delete=models.CASCADE,
        related_name="stages",
    )
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)

    name = models.CharField(max_length=120)
    slug = models.CharField(max_length=150, db_index=True)
    sequence = models.IntegerField(default=1)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SCOPE_GLOBAL)
    job_id = models.CharField(max_length=64, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_folded = models.BooleanField(default=False)
    is_hired_stage = models.BooleanField(default=False)
    is_refused_stage = models.BooleanField(default=False)
    is_contract_stage = models.BooleanField(default=False)

    auto_email_enabled = models.BooleanField(default=False)
    auto_email_subject = models.CharField(max_length=200, blank=True, null=True)
    auto_email_body = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "recruitment_stages"
        ordering = ["sequence", "created_at"]
        unique_together = [["employer_id", "slug"]]
        indexes = [
            models.Index(fields=["employer_id", "sequence"]),
            models.Index(fields=["employer_id", "scope"]),
            models.Index(fields=["job_id"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.employer_id})"

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or "default"
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        if self.employer_id is None and self.settings_id:
            self.employer_id = self.settings.employer_id
        if not self.slug:
            base = slugify(self.name) or "stage"
            candidate = base
            counter = 1
            while RecruitmentStage.objects.using(using).filter(
                employer_id=self.employer_id,
                slug=candidate,
            ).exclude(id=self.id).exists():
                counter += 1
                candidate = f"{base}-{counter}"
            self.slug = candidate
        super().save(*args, **kwargs)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "sequence": self.sequence,
            "scope": self.scope,
            "job_id": self.job_id,
            "is_active": self.is_active,
            "is_folded": self.is_folded,
            "is_hired_stage": self.is_hired_stage,
            "is_refused_stage": self.is_refused_stage,
            "is_contract_stage": self.is_contract_stage,
            "auto_email_enabled": self.auto_email_enabled,
            "auto_email_subject": self.auto_email_subject,
            "auto_email_body": self.auto_email_body,
        }


class JobPosition(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_OPEN = "OPEN"
    STATUS_CLOSED = "CLOSED"
    STATUS_ARCHIVED = "ARCHIVED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    LEVEL_JUNIOR = "JUNIOR"
    LEVEL_MID = "MID"
    LEVEL_SENIOR = "SENIOR"
    LEVEL_LEAD = "LEAD"
    LEVEL_EXECUTIVE = "EXECUTIVE"

    LEVEL_CHOICES = [
        (LEVEL_JUNIOR, "Junior"),
        (LEVEL_MID, "Mid"),
        (LEVEL_SENIOR, "Senior"),
        (LEVEL_LEAD, "Lead"),
        (LEVEL_EXECUTIVE, "Executive"),
    ]

    SALARY_PUBLIC = "PUBLIC"
    SALARY_PRIVATE = "PRIVATE"
    SALARY_NEGOTIABLE = "NEGOTIABLE"

    SALARY_VISIBILITY_CHOICES = [
        (SALARY_PUBLIC, "Public"),
        (SALARY_PRIVATE, "Private"),
        (SALARY_NEGOTIABLE, "Negotiable"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)

    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, db_index=True)
    reference_code = models.CharField(max_length=60, blank=True, null=True, db_index=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, blank=True, null=True)
    contract_duration = models.CharField(max_length=100, blank=True, null=True)
    number_of_positions = models.PositiveIntegerField(default=1, blank=True)
    description = models.TextField(blank=True, null=True)
    requirements = models.TextField(blank=True, null=True)
    responsibilities = models.TextField(blank=True, null=True)
    qualifications = models.TextField(blank=True, null=True)
    experience_years_min = models.PositiveIntegerField(blank=True, null=True)
    experience_years_max = models.PositiveIntegerField(blank=True, null=True)
    skills = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    department = models.ForeignKey(
        "employees.Department",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="recruitment_jobs",
    )
    branch = models.ForeignKey(
        "employees.Branch",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="recruitment_jobs",
    )
    location = models.CharField(max_length=255, blank=True, null=True)
    employment_type = models.CharField(max_length=50, blank=True, null=True)
    is_remote = models.BooleanField(default=False)
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    salary_currency = models.CharField(max_length=10, blank=True, null=True)
    salary_visibility = models.CharField(
        max_length=20,
        choices=SALARY_VISIBILITY_CHOICES,
        default=SALARY_PRIVATE,
    )
    application_deadline = models.DateField(blank=True, null=True)

    publish_scope = models.CharField(
        max_length=20,
        choices=RecruitmentSettings.PUBLISH_SCOPE_CHOICES,
        blank=True,
        null=True,
        help_text="Override publish scope for this job.",
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    created_by = models.IntegerField(db_index=True, help_text="User ID from main DB")
    updated_by = models.IntegerField(db_index=True, help_text="User ID from main DB")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "recruitment_job_positions"
        ordering = ["-created_at"]
        unique_together = [["employer_id", "slug"]]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["employer_id", "is_published"]),
            models.Index(fields=["employer_id", "created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.employer_id})"

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or "default"
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        if not self.slug:
            base = slugify(self.title) or "job"
            candidate = base
            counter = 1
            while JobPosition.objects.using(using).filter(
                employer_id=self.employer_id,
                slug=candidate,
            ).exclude(id=self.id).exists():
                counter += 1
                candidate = f"{base}-{counter}"
            self.slug = candidate
        super().save(*args, **kwargs)


class RecruitmentApplicant(models.Model):
    STATUS_NEW = "NEW"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_BLOCKED = "BLOCKED"
    STATUS_HIRED = "HIRED"
    STATUS_REFUSED = "REFUSED"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_HIRED, "Hired"),
        (STATUS_REFUSED, "Refused"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)

    job = models.ForeignKey(JobPosition, on_delete=models.CASCADE, related_name="applicants")
    stage = models.ForeignKey(
        RecruitmentStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applicants",
    )

    full_name = models.CharField(max_length=255)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    linkedin_url = models.CharField(max_length=255, blank=True, null=True)
    intro = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True)
    rating = models.IntegerField(default=0)
    tags = models.JSONField(default=list, blank=True)

    source = models.CharField(max_length=100, blank=True, null=True)
    medium = models.CharField(max_length=100, blank=True, null=True)
    referral = models.CharField(max_length=100, blank=True, null=True)

    answers = models.JSONField(default=dict, blank=True)

    is_internal_applicant = models.BooleanField(default=False)
    user_id = models.IntegerField(blank=True, null=True, db_index=True)
    refuse_reason = models.ForeignKey(
        "RecruitmentRefuseReason",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="refused_applicants",
    )
    refuse_note = models.TextField(blank=True, null=True)
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="recruitment_applications",
    )

    applied_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(default=timezone.now)
    hired_at = models.DateTimeField(blank=True, null=True)
    refused_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "recruitment_applicants"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "job"]),
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["employer_id", "email"]),
            models.Index(fields=["job", "stage"]),
        ]

    def __str__(self):
        return f"{self.full_name} -> {self.job_id}"

    @property
    def status_color(self) -> str:
        if self.status in {self.STATUS_BLOCKED, self.STATUS_REFUSED}:
            return "red"
        if self.status == self.STATUS_NEW:
            return "gray"
        return "green"

    @property
    def state(self) -> str:
        if self.status == self.STATUS_HIRED:
            return "HIRED"
        if self.status == self.STATUS_REFUSED:
            return "REFUSED"
        return "IN_PROGRESS"


class RecruitmentApplicantStageHistory(models.Model):
    ACTION_APPLY = "APPLY"
    ACTION_MOVE = "MOVE_STAGE"
    ACTION_REFUSE = "REFUSE"
    ACTION_HIRED = "HIRED"

    ACTION_CHOICES = [
        (ACTION_APPLY, "Apply"),
        (ACTION_MOVE, "Move stage"),
        (ACTION_REFUSE, "Refuse"),
        (ACTION_HIRED, "Hired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(
        RecruitmentApplicant,
        on_delete=models.CASCADE,
        related_name="stage_history",
    )
    from_stage = models.ForeignKey(
        RecruitmentStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stage_history_from",
    )
    to_stage = models.ForeignKey(
        RecruitmentStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stage_history_to",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default=ACTION_MOVE)
    changed_by_user_id = models.IntegerField(blank=True, null=True, db_index=True)
    note = models.TextField(blank=True, null=True)
    meta = models.JSONField(default=dict, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recruitment_applicant_stage_history"
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["applicant", "changed_at"]),
            models.Index(fields=["to_stage", "changed_at"]),
        ]


class RecruitmentRefuseReason(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recruitment_refuse_reasons"
        ordering = ["name"]
        unique_together = [["employer_id", "code"]]
        indexes = [
            models.Index(fields=["employer_id", "is_active"]),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        super().save(*args, **kwargs)


class RecruitmentEmailTemplate(models.Model):
    CODE_APPLICATION_ACK = "APPLICATION_ACK"
    CODE_STAGE_ENTER = "STAGE_ENTER"
    CODE_REFUSAL = "REFUSAL"

    CODE_CHOICES = [
        (CODE_APPLICATION_ACK, "Application acknowledgement"),
        (CODE_STAGE_ENTER, "Stage entry"),
        (CODE_REFUSAL, "Refusal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    code = models.CharField(max_length=50, choices=CODE_CHOICES)
    stage = models.ForeignKey(
        RecruitmentStage,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="email_templates",
    )
    job_id = models.CharField(max_length=64, blank=True, null=True)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "recruitment_email_templates"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "code"]),
            models.Index(fields=["stage", "code"]),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        super().save(*args, **kwargs)


class RecruitmentEmailLog(models.Model):
    STATUS_SENT = "SENT"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    applicant = models.ForeignKey(
        RecruitmentApplicant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    job = models.ForeignKey(
        JobPosition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    template = models.ForeignKey(
        RecruitmentEmailTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SENT)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recruitment_email_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        super().save(*args, **kwargs)


class RecruitmentAttachment(models.Model):
    PURPOSE_CV = "CV"
    PURPOSE_COVER = "COVER_LETTER"
    PURPOSE_OTHER = "OTHER"

    PURPOSE_CHOICES = [
        (PURPOSE_CV, "CV"),
        (PURPOSE_COVER, "Cover letter"),
        (PURPOSE_OTHER, "Other"),
    ]

    SCAN_PENDING = "PENDING"
    SCAN_CLEAN = "CLEAN"
    SCAN_INFECTED = "INFECTED"
    SCAN_SKIPPED = "SKIPPED"

    SCAN_CHOICES = [
        (SCAN_PENDING, "Pending"),
        (SCAN_CLEAN, "Clean"),
        (SCAN_INFECTED, "Infected"),
        (SCAN_SKIPPED, "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    applicant = models.ForeignKey(
        RecruitmentApplicant,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="recruitment_attachments/")
    file_size = models.IntegerField(help_text="File size in bytes")
    content_type = models.CharField(max_length=100, blank=True, null=True)
    original_name = models.CharField(max_length=255, blank=True, null=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default=PURPOSE_CV)
    virus_scan_status = models.CharField(max_length=20, choices=SCAN_CHOICES, default=SCAN_PENDING)
    uploaded_by_user_id = models.IntegerField(blank=True, null=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recruitment_attachments"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["employer_id", "purpose"]),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        super().save(*args, **kwargs)


class RecruitmentInterviewEvent(models.Model):
    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    applicant = models.ForeignKey(
        RecruitmentApplicant,
        on_delete=models.CASCADE,
        related_name="interviews",
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=30)
    location = models.CharField(max_length=255, blank=True, null=True)
    meeting_link = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recruitment_interview_events"
        ordering = ["-scheduled_at"]
        indexes = [
            models.Index(fields=["employer_id", "scheduled_at"]),
        ]


class RecruitmentOffer(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_SENT = "SENT"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_DECLINED = "DECLINED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    applicant = models.ForeignKey(
        RecruitmentApplicant,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recruitment_offers"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        using = kwargs.get("using") or self._state.db or "default"
        previous_status = None
        if self.pk:
            previous = RecruitmentOffer.objects.using(using).filter(id=self.id).only("status").first()
            if previous:
                previous_status = previous.status
        super().save(*args, **kwargs)

        if self.status == self.STATUS_SENT and previous_status != self.STATUS_SENT:
            try:
                from accounts.models import EmployerProfile
                from .services import notify_recruitment_offer_sent

                employer = EmployerProfile.objects.filter(id=self.employer_id).first()
                if employer:
                    notify_recruitment_offer_sent(offer=self, employer=employer)
            except Exception:
                # Avoid blocking offer persistence on notification failures
                pass
