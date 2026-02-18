from django.db.models import Max
from rest_framework import serializers

from .models import (
    Communication,
    CommunicationAttachment,
    CommunicationAuditLog,
    CommunicationComment,
    CommunicationRecipient,
    CommunicationResponse,
    CommunicationTarget,
    CommunicationTemplate,
    CommunicationTemplateVersion,
    CommunicationVersion,
)


class CommunicationTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationTarget
        fields = ["id", "rule_type", "rule_value", "include", "created_at"]
        read_only_fields = ["id", "created_at"]


class CommunicationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationVersion
        fields = [
            "id",
            "version_number",
            "title",
            "body",
            "change_reason",
            "is_correction",
            "supersedes_version",
            "checksum",
            "created_by_id",
            "created_at",
        ]
        read_only_fields = ["id", "version_number", "created_by_id", "created_at"]


class CommunicationAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationAttachment
        fields = [
            "id",
            "file",
            "file_size",
            "content_type",
            "original_name",
            "checksum",
            "virus_scan_status",
            "uploaded_by_id",
            "uploaded_at",
            "version",
        ]
        read_only_fields = [
            "id",
            "file_size",
            "content_type",
            "original_name",
            "checksum",
            "virus_scan_status",
            "uploaded_by_id",
            "uploaded_at",
        ]


class CommunicationAttachmentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationAttachment
        fields = ["id", "file", "version"]


class CommunicationListSerializer(serializers.ModelSerializer):
    recipient_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Communication
        fields = [
            "id",
            "type",
            "letter_type",
            "title",
            "priority",
            "visibility",
            "status",
            "requires_ack",
            "allow_response",
            "allow_comments",
            "scheduled_at",
            "sent_at",
            "closed_at",
            "recipient_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CommunicationDetailSerializer(serializers.ModelSerializer):
    targets = CommunicationTargetSerializer(many=True, read_only=True)
    attachments = CommunicationAttachmentSerializer(many=True, read_only=True)
    current_version = CommunicationVersionSerializer(read_only=True)
    recipient_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Communication
        fields = [
            "id",
            "employer_id",
            "type",
            "letter_type",
            "title",
            "body",
            "priority",
            "visibility",
            "allow_comments",
            "requires_ack",
            "allow_response",
            "status",
            "scheduled_at",
            "sent_at",
            "closed_at",
            "current_version",
            "targets",
            "attachments",
            "recipient_count",
            "created_by_id",
            "updated_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CommunicationCreateUpdateSerializer(serializers.ModelSerializer):
    targets = CommunicationTargetSerializer(many=True, required=False)
    change_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Communication
        fields = [
            "id",
            "type",
            "letter_type",
            "title",
            "body",
            "priority",
            "visibility",
            "allow_comments",
            "requires_ack",
            "allow_response",
            "status",
            "scheduled_at",
            "targets",
            "change_reason",
        ]
        read_only_fields = ["id", "status"]

    def validate(self, attrs):
        instance = self.instance
        comm_type = attrs.get("type") or getattr(instance, "type", None)
        letter_type = attrs.get("letter_type") or getattr(instance, "letter_type", Communication.LETTER_NONE)

        if comm_type == Communication.TYPE_HR_LETTER:
            attrs["visibility"] = Communication.VISIBILITY_PRIVATE
            attrs["allow_comments"] = False
            attrs["requires_ack"] = True
            attrs["allow_response"] = attrs.get("allow_response", True)
            if letter_type == Communication.LETTER_NONE:
                raise serializers.ValidationError(
                    {"letter_type": "HR letters must specify a letter type."}
                )

        if comm_type == Communication.TYPE_POLICY_UPDATE:
            attrs["requires_ack"] = True

        if comm_type == Communication.TYPE_ANNOUNCEMENT:
            attrs.setdefault("allow_response", False)

        return attrs

    def _create_version(self, communication, *, title, body, change_reason=None, is_correction=False, created_by_id=None):
        tenant_db = self.context.get("tenant_db") or "default"
        max_version = (
            CommunicationVersion.objects.using(tenant_db)
            .filter(communication=communication)
            .aggregate(max_num=Max("version_number"))
            .get("max_num")
            or 0
        )
        supersedes = communication.current_version
        version = CommunicationVersion.objects.using(tenant_db).create(
            communication=communication,
            version_number=max_version + 1,
            title=title,
            body=body,
            change_reason=change_reason or None,
            is_correction=is_correction,
            supersedes_version=supersedes,
            created_by_id=created_by_id or communication.created_by_id,
        )
        communication.current_version = version
        communication.save(using=tenant_db, update_fields=["current_version", "updated_at"])
        return version

    def create(self, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        employer = self.context.get("employer")
        actor_id = self.context.get("actor_id")
        targets = validated_data.pop("targets", [])
        change_reason = validated_data.pop("change_reason", None)

        communication = Communication.objects.using(tenant_db).create(
            employer_id=getattr(employer, "id", None),
            created_by_id=actor_id,
            updated_by_id=actor_id,
            **validated_data,
        )

        for target in targets:
            CommunicationTarget.objects.using(tenant_db).create(
                communication=communication,
                rule_type=target["rule_type"],
                rule_value=target.get("rule_value", {}),
                include=target.get("include", True),
            )

        self._create_version(
            communication,
            title=communication.title,
            body=communication.body,
            change_reason=change_reason,
            is_correction=False,
            created_by_id=actor_id,
        )
        return communication

    def update(self, instance, validated_data):
        tenant_db = self.context.get("tenant_db") or "default"
        actor_id = self.context.get("actor_id")
        targets = validated_data.pop("targets", None)
        change_reason = validated_data.pop("change_reason", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.updated_by_id = actor_id
        instance.save(using=tenant_db)

        if targets is not None:
            CommunicationTarget.objects.using(tenant_db).filter(communication=instance).delete()
            for target in targets:
                CommunicationTarget.objects.using(tenant_db).create(
                    communication=instance,
                    rule_type=target["rule_type"],
                    rule_value=target.get("rule_value", {}),
                    include=target.get("include", True),
                )

        self._create_version(
            instance,
            title=instance.title,
            body=instance.body,
            change_reason=change_reason,
            is_correction=False,
            created_by_id=actor_id,
        )
        return instance


class CommunicationCorrectionSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=False)
    body = serializers.CharField(required=False, allow_blank=False)
    change_reason = serializers.CharField(required=False, allow_blank=True)


class CommunicationRecipientSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_number = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()

    class Meta:
        model = CommunicationRecipient
        fields = [
            "id",
            "employee",
            "employee_name",
            "employee_number",
            "department_name",
            "branch_name",
            "recipient_role",
            "delivery_status",
            "delivered_at",
            "read_at",
            "ack_required",
            "acknowledged_at",
            "response_required",
            "responded_at",
            "state",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_employee_name(self, obj):
        if obj.employee:
            return getattr(obj.employee, "full_name", None) or f"{obj.employee.first_name} {obj.employee.last_name}"
        return None

    def get_employee_number(self, obj):
        return getattr(obj.employee, "employee_id", None) if obj.employee else None

    def get_department_name(self, obj):
        if obj.employee and getattr(obj.employee, "department", None):
            return obj.employee.department.name
        return None

    def get_branch_name(self, obj):
        if obj.employee and getattr(obj.employee, "branch", None):
            return obj.employee.branch.name
        return None


class CommunicationAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationAuditLog
        fields = [
            "id",
            "action",
            "actor_user_id",
            "actor_employee_id",
            "ip_address",
            "user_agent",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class CommunicationCommentSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = CommunicationComment
        fields = [
            "id",
            "employee",
            "employee_name",
            "body",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employee", "employee_name", "created_at", "updated_at"]

    def get_employee_name(self, obj):
        if obj.employee:
            return getattr(obj.employee, "full_name", None) or f"{obj.employee.first_name} {obj.employee.last_name}"
        return None


class CommunicationResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationResponse
        fields = ["id", "body", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class CommunicationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationTemplate
        fields = [
            "id",
            "employer_id",
            "name",
            "template_type",
            "subject_template",
            "body_template",
            "is_default",
            "is_active",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "created_by_id", "created_at", "updated_at"]


class CommunicationTemplateVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationTemplateVersion
        fields = [
            "id",
            "template",
            "version_label",
            "subject_template",
            "body_template",
            "created_by_id",
            "created_at",
        ]
        read_only_fields = ["id", "template", "created_by_id", "created_at"]


class EmployeeCommunicationListSerializer(serializers.ModelSerializer):
    communication_id = serializers.UUIDField(source="communication.id", read_only=True)
    title = serializers.CharField(source="communication.title", read_only=True)
    body = serializers.CharField(source="communication.body", read_only=True)
    type = serializers.CharField(source="communication.type", read_only=True)
    letter_type = serializers.CharField(source="communication.letter_type", read_only=True)
    priority = serializers.CharField(source="communication.priority", read_only=True)
    allow_comments = serializers.BooleanField(source="communication.allow_comments", read_only=True)
    requires_ack = serializers.BooleanField(source="communication.requires_ack", read_only=True)
    allow_response = serializers.BooleanField(source="communication.allow_response", read_only=True)
    status = serializers.CharField(source="communication.status", read_only=True)
    sent_at = serializers.DateTimeField(source="communication.sent_at", read_only=True)
    attachments = CommunicationAttachmentSerializer(source="communication.attachments", many=True, read_only=True)
    response = CommunicationResponseSerializer(read_only=True)

    class Meta:
        model = CommunicationRecipient
        fields = [
            "id",
            "communication_id",
            "title",
            "body",
            "type",
            "letter_type",
            "priority",
            "status",
            "allow_comments",
            "requires_ack",
            "allow_response",
            "sent_at",
            "read_at",
            "ack_required",
            "acknowledged_at",
            "response_required",
            "responded_at",
            "state",
            "attachments",
            "response",
        ]
        read_only_fields = fields
