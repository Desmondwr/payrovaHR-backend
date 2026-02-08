import uuid

from rest_framework import serializers

from .models import (
    JobPosition,
    RecruitmentApplicant,
    RecruitmentAttachment,
    RecruitmentRefuseReason,
    RecruitmentSettings,
    RecruitmentStage,
)
from .utils import sanitize_rich_text, sanitize_text


class RecruitmentStageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)

    class Meta:
        model = RecruitmentStage
        fields = [
            "id",
            "name",
            "slug",
            "sequence",
            "scope",
            "job_id",
            "is_active",
            "is_folded",
            "is_hired_stage",
            "is_refused_stage",
            "is_contract_stage",
            "auto_email_enabled",
            "auto_email_subject",
            "auto_email_body",
        ]
        read_only_fields = ["slug"]

    def validate_scope(self, value):
        if value not in {RecruitmentStage.SCOPE_GLOBAL, RecruitmentStage.SCOPE_JOB}:
            raise serializers.ValidationError("Invalid stage scope.")
        return value

    def validate(self, attrs):
        scope = attrs.get("scope")
        job_id = attrs.get("job_id")
        if scope == RecruitmentStage.SCOPE_JOB and not job_id:
            raise serializers.ValidationError("job_id is required for JOB-scoped stages.")
        return attrs


class RecruitmentSettingsSerializer(serializers.ModelSerializer):
    application_fields = serializers.ListField(child=serializers.DictField(), required=False)
    custom_questions = serializers.ListField(child=serializers.DictField(), required=False)
    cv_allowed_extensions = serializers.ListField(child=serializers.CharField(), required=False)
    stages = RecruitmentStageSerializer(many=True, required=False)

    class Meta:
        model = RecruitmentSettings
        fields = [
            "id",
            "employer_id",
            "schema_version",
            "job_publish_scope",
            "public_applications_enabled",
            "internal_applications_enabled",
            "public_apply_requires_login",
            "internal_apply_requires_login",
            "application_fields",
            "custom_questions",
            "email_automation_enabled",
            "default_ack_email_subject",
            "default_ack_email_body",
            "cv_allowed_extensions",
            "cv_max_file_size_mb",
            "public_apply_rate_limit_requests",
            "public_apply_rate_limit_window_seconds",
            "public_apply_captcha_enabled",
            "public_apply_spam_check_enabled",
            "public_apply_honeypot_enabled",
            "duplicate_application_window_days",
            "duplicate_application_action",
            "integration_interview_scheduling_enabled",
            "integration_offers_esign_enabled",
            "integration_resume_ocr_enabled",
            "integration_job_board_ingest_enabled",
            "stages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "schema_version", "created_at", "updated_at"]

    def validate_application_fields(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("application_fields must be a list.")
        allowed_types = {"text", "email", "phone", "file", "url", "textarea"}
        seen = set()
        normalized = []
        for entry in value:
            if not isinstance(entry, dict):
                raise serializers.ValidationError("Each application field must be an object.")
            key = entry.get("key")
            if not key:
                raise serializers.ValidationError("Each application field must include a key.")
            if key in seen:
                raise serializers.ValidationError(f"Duplicate application field key: {key}.")
            seen.add(key)
            field_type = entry.get("type", "text")
            if field_type not in allowed_types:
                raise serializers.ValidationError(f"Unsupported field type: {field_type}.")
            normalized.append(
                {
                    "key": key,
                    "label": entry.get("label") or key.replace("_", " ").title(),
                    "type": field_type,
                    "required": bool(entry.get("required", False)),
                    "enabled": bool(entry.get("enabled", True)),
                }
            )
        return normalized

    def validate_custom_questions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("custom_questions must be a list.")
        allowed_types = {
            "text",
            "textarea",
            "email",
            "phone",
            "url",
            "select",
            "multi_select",
            "boolean",
            "number",
            "date",
            "file",
        }
        normalized = []
        for entry in value:
            if not isinstance(entry, dict):
                raise serializers.ValidationError("Each custom question must be an object.")
            question = sanitize_text(entry.get("question"))
            if not question:
                raise serializers.ValidationError("Each custom question must include question text.")
            q_type = entry.get("type", "text")
            if q_type not in allowed_types:
                raise serializers.ValidationError(f"Unsupported custom question type: {q_type}.")
            options = entry.get("options") or []
            if q_type in {"select", "multi_select"} and not options:
                raise serializers.ValidationError("Options are required for select questions.")
            if options and not isinstance(options, list):
                raise serializers.ValidationError("Options must be a list.")
            normalized.append(
                {
                    "id": entry.get("id") or str(uuid.uuid4()),
                    "question": question,
                    "type": q_type,
                    "required": bool(entry.get("required", False)),
                    "options": options,
                    "is_active": bool(entry.get("is_active", True)),
                }
            )
        return normalized

    def validate_cv_allowed_extensions(self, value):
        allowed = {"pdf", "doc", "docx"}
        cleaned = []
        for ext in value or []:
            ext = str(ext).lower().strip().lstrip(".")
            if not ext:
                continue
            if ext not in allowed:
                raise serializers.ValidationError("CV uploads only support PDF, DOC, or DOCX.")
            cleaned.append(ext)
        return cleaned

    def validate_cv_max_file_size_mb(self, value):
        if value is None:
            return value
        if int(value) <= 0:
            raise serializers.ValidationError("cv_max_file_size_mb must be positive.")
        return value

    def validate_public_apply_rate_limit_requests(self, value):
        if value is None:
            return value
        if int(value) < 0:
            raise serializers.ValidationError("public_apply_rate_limit_requests must be >= 0.")
        return value

    def validate_public_apply_rate_limit_window_seconds(self, value):
        if value is None:
            return value
        if int(value) < 0:
            raise serializers.ValidationError("public_apply_rate_limit_window_seconds must be >= 0.")
        return value

    def validate_duplicate_application_window_days(self, value):
        if value is None:
            return value
        if int(value) < 0:
            raise serializers.ValidationError("duplicate_application_window_days must be >= 0.")
        return value

    def validate_default_ack_email_subject(self, value):
        return sanitize_text(value)

    def validate_default_ack_email_body(self, value):
        return sanitize_rich_text(value)

    def update(self, instance, validated_data):
        stages_data = validated_data.pop("stages", None)
        tenant_db = self.context.get("tenant_db") or instance._state.db or "default"

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=tenant_db)

        if stages_data is not None:
            self._sync_stages(instance, stages_data, tenant_db)

        return instance

    def validate(self, attrs):
        stages = attrs.get("stages")
        if stages is not None:
            sequences = [stage.get("sequence") for stage in stages]
            if len(sequences) != len(set(sequences)):
                raise serializers.ValidationError("Stage sequence values must be unique.")
        return attrs

    def _sync_stages(self, instance, stages_data, tenant_db):
        existing = {
            str(stage.id): stage
            for stage in RecruitmentStage.objects.using(tenant_db).filter(settings=instance)
        }
        seen = set()
        for entry in stages_data:
            stage_id = entry.get("id")
            stage_key = str(stage_id) if stage_id else None
            payload = {
                "name": entry.get("name"),
                "sequence": entry.get("sequence"),
                "scope": entry.get("scope", RecruitmentStage.SCOPE_GLOBAL),
                "job_id": entry.get("job_id"),
                "is_active": entry.get("is_active", True),
                "is_folded": entry.get("is_folded", False),
                "is_hired_stage": entry.get("is_hired_stage", False),
                "is_refused_stage": entry.get("is_refused_stage", False),
                "is_contract_stage": entry.get("is_contract_stage", False),
                "auto_email_enabled": entry.get("auto_email_enabled", False),
                "auto_email_subject": sanitize_text(entry.get("auto_email_subject")),
                "auto_email_body": sanitize_rich_text(entry.get("auto_email_body")),
            }
            if stage_key and stage_key in existing:
                stage = existing[stage_key]
                for attr, value in payload.items():
                    setattr(stage, attr, value)
                stage.save(using=tenant_db)
                seen.add(stage_key)
                continue
            stage = RecruitmentStage.objects.using(tenant_db).create(
                settings=instance,
                employer_id=instance.employer_id,
                tenant_id=instance.tenant_id,
                **payload,
            )
            seen.add(str(stage.id))

    def create(self, validated_data):
        stages_data = validated_data.pop("stages", None)
        tenant_db = self.context.get("tenant_db") or "default"
        instance = RecruitmentSettings.objects.using(tenant_db).create(**validated_data)
        if stages_data:
            self._sync_stages(instance, stages_data, tenant_db)
        return instance

class JobPositionSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    # Accept UUIDs as strings to avoid FK validation against default DB
    department = serializers.UUIDField(required=False, allow_null=True)
    branch = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = JobPosition
        fields = [
            "id",
            "employer_id",
            "title",
            "slug",
            "reference_code",
            "level",
            "contract_duration",
            "number_of_positions",
            "description",
            "requirements",
            "responsibilities",
            "qualifications",
            "experience_years_min",
            "experience_years_max",
            "skills",
            "languages",
            "department",
            "department_name",
            "branch",
            "branch_name",
            "location",
            "employment_type",
            "is_remote",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_visibility",
            "application_deadline",
            "publish_scope",
            "is_published",
            "published_at",
            "status",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "archived_at",
        ]
        read_only_fields = [
            "id",
            "employer_id",
            "slug",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "archived_at",
        ]

    def validate_description(self, value):
        return sanitize_rich_text(value)

    def validate_requirements(self, value):
        return sanitize_rich_text(value)

    def validate_responsibilities(self, value):
        return sanitize_rich_text(value)

    def validate_qualifications(self, value):
        return sanitize_rich_text(value)

    def validate_reference_code(self, value):
        return sanitize_text(value)

    def validate_contract_duration(self, value):
        return sanitize_text(value)

    def validate_salary_currency(self, value):
        return sanitize_text(value.upper()) if value else value

    def _normalize_list(self, value, field_name):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError(f"{field_name} must be a list.")
        cleaned = []
        for entry in value:
            text = sanitize_text(entry)
            if text:
                cleaned.append(text)
        return cleaned

    def validate_skills(self, value):
        return self._normalize_list(value, "skills")

    def validate_languages(self, value):
        return self._normalize_list(value, "languages")

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        salary_min = attrs.get("salary_min", getattr(instance, "salary_min", None))
        salary_max = attrs.get("salary_max", getattr(instance, "salary_max", None))
        salary_visibility = attrs.get(
            "salary_visibility", getattr(instance, "salary_visibility", None)
        )
        salary_currency = attrs.get("salary_currency", getattr(instance, "salary_currency", None))
        exp_min = attrs.get("experience_years_min", getattr(instance, "experience_years_min", None))
        exp_max = attrs.get("experience_years_max", getattr(instance, "experience_years_max", None))
        positions = attrs.get("number_of_positions", getattr(instance, "number_of_positions", None))

        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            raise serializers.ValidationError({"salary_max": "Must be greater than or equal to salary_min."})
        if exp_min is not None and exp_max is not None and exp_min > exp_max:
            raise serializers.ValidationError({"experience_years_max": "Must be greater than or equal to experience_years_min."})
        if positions is not None and int(positions) < 1:
            raise serializers.ValidationError({"number_of_positions": "Must be at least 1."})
        if salary_visibility == JobPosition.SALARY_PUBLIC:
            if salary_min is None or salary_max is None or not salary_currency:
                raise serializers.ValidationError(
                    {"salary_visibility": "Public salary visibility requires salary_min, salary_max, and salary_currency."}
                )

        return attrs

    def to_representation(self, instance):
        """Override to properly serialize FK UUIDs"""
        data = super().to_representation(instance)
        # Convert FK instances to UUIDs for output
        if instance.department_id:
            data['department'] = str(instance.department_id)
        if instance.branch_id:
            data['branch'] = str(instance.branch_id)
        return data


class JobPositionPublicSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    employer_name = serializers.SerializerMethodField()
    employer_slug = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    company_logo = serializers.SerializerMethodField()
    company_tagline = serializers.SerializerMethodField()
    company_overview = serializers.SerializerMethodField()
    company_website = serializers.SerializerMethodField()
    company_size = serializers.SerializerMethodField()
    careers_email = serializers.SerializerMethodField()
    linkedin_url = serializers.SerializerMethodField()

    class Meta:
        model = JobPosition
        fields = [
            "id",
            "title",
            "slug",
            "reference_code",
            "level",
            "contract_duration",
            "number_of_positions",
            "description",
            "requirements",
            "responsibilities",
            "qualifications",
            "experience_years_min",
            "experience_years_max",
            "skills",
            "languages",
            "department",
            "department_name",
            "employer_name",
            "employer_slug",
            "company_name",
            "company_logo",
            "company_tagline",
            "company_overview",
            "company_website",
            "company_size",
            "careers_email",
            "linkedin_url",
            "location",
            "employment_type",
            "is_remote",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_visibility",
            "application_deadline",
            "published_at",
        ]

    def _get_employer_profile(self, obj):
        cache = getattr(self, "_employer_cache", None)
        if cache is None:
            cache = {}
            self._employer_cache = cache

        employer_id = obj.employer_id
        if employer_id in cache:
            return cache[employer_id]

        from accounts.models import EmployerProfile

        profile = EmployerProfile.objects.filter(id=employer_id).first()
        cache[employer_id] = profile
        return profile

    def get_employer_name(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.company_name if profile else None

    def get_employer_slug(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.slug if profile else None

    def get_company_name(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.company_name if profile else None

    def get_company_logo(self, obj):
        profile = self._get_employer_profile(obj)
        if profile and profile.company_logo:
            try:
                return profile.company_logo.url
            except Exception:
                return None
        return None

    def get_company_tagline(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.company_tagline if profile else None

    def get_company_overview(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.company_overview if profile else None

    def get_company_website(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.company_website if profile else None

    def get_company_size(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.company_size if profile else None

    def get_careers_email(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.careers_email if profile else None

    def get_linkedin_url(self, obj):
        profile = self._get_employer_profile(obj)
        return profile.linkedin_url if profile else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        visibility = instance.salary_visibility or JobPosition.SALARY_PRIVATE
        data["salary_visibility"] = visibility
        if visibility != JobPosition.SALARY_PUBLIC:
            data["salary_min"] = None
            data["salary_max"] = None
            data["salary_currency"] = None
        return data


class RecruitmentAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecruitmentAttachment
        fields = [
            "id",
            "purpose",
            "file",
            "file_size",
            "content_type",
            "original_name",
            "virus_scan_status",
            "uploaded_at",
        ]
        read_only_fields = [
            "id",
            "file_size",
            "content_type",
            "original_name",
            "virus_scan_status",
            "uploaded_at",
        ]


class RecruitmentApplicantSerializer(serializers.ModelSerializer):
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)
    status_color = serializers.SerializerMethodField()
    attachments = RecruitmentAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = RecruitmentApplicant
        fields = [
            "id",
            "employer_id",
            "job",
            "job_title",
            "stage",
            "stage_name",
            "full_name",
            "email",
            "phone",
            "linkedin_url",
            "intro",
            "status",
            "status_color",
            "rating",
            "tags",
            "source",
            "medium",
            "referral",
            "answers",
            "is_internal_applicant",
            "user_id",
            "refuse_reason",
            "refuse_note",
            "employee",
            "applied_at",
            "last_activity_at",
            "hired_at",
            "refused_at",
            "created_at",
            "updated_at",
            "attachments",
        ]
        read_only_fields = [
            "id",
            "employer_id",
            "job_title",
            "stage_name",
            "status_color",
            "applied_at",
            "last_activity_at",
            "hired_at",
            "refused_at",
            "created_at",
            "updated_at",
        ]

    def get_status_color(self, obj):
        return obj.status_color


class RecruitmentApplicantCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecruitmentApplicant
        fields = [
            "job",
            "stage",
            "full_name",
            "email",
            "phone",
            "linkedin_url",
            "intro",
            "status",
            "rating",
            "tags",
            "source",
            "medium",
            "referral",
            "answers",
            "is_internal_applicant",
            "user_id",
            "refuse_reason",
            "refuse_note",
            "employee",
        ]

    def validate_intro(self, value):
        return sanitize_rich_text(value)


class RecruitmentApplicantUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecruitmentApplicant
        fields = [
            "full_name",
            "email",
            "phone",
            "linkedin_url",
            "intro",
            "status",
            "rating",
            "tags",
            "source",
            "medium",
            "referral",
            "answers",
            "refuse_reason",
            "refuse_note",
        ]

    def validate_intro(self, value):
        return sanitize_rich_text(value)


class RecruitmentApplicantPipelineSerializer(serializers.ModelSerializer):
    status_color = serializers.SerializerMethodField()
    job_title = serializers.CharField(source="job.title", read_only=True)

    class Meta:
        model = RecruitmentApplicant
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "rating",
            "tags",
            "status",
            "status_color",
            "created_at",
            "last_activity_at",
            "job_title",
        ]

    def get_status_color(self, obj):
        return obj.status_color


class RecruitmentRefuseReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecruitmentRefuseReason
        fields = ["id", "code", "name", "description", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class RecruitmentApplySerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    linkedin = serializers.CharField(required=False, allow_blank=True)
    intro = serializers.CharField(required=False, allow_blank=True)
    cv = serializers.FileField(required=False)
    answers = serializers.JSONField(required=False)
    source = serializers.CharField(required=False, allow_blank=True)
    medium = serializers.CharField(required=False, allow_blank=True)
    referral = serializers.CharField(required=False, allow_blank=True)
    captcha_token = serializers.CharField(required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_intro(self, value):
        return sanitize_rich_text(value)


class RecruitmentStageMoveSerializer(serializers.Serializer):
    to_stage_id = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=True)


class RecruitmentRefuseSerializer(serializers.Serializer):
    refuse_reason_id = serializers.UUIDField(required=False)
    send_email = serializers.BooleanField(default=True)
    note = serializers.CharField(required=False, allow_blank=True)
