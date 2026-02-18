from django.db.models import Count, Q, Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsAuthenticated, EmployerAccessPermission, IsEmployee
from accounts.rbac import get_active_employer, is_delegate_user, get_delegate_scope, apply_scope_filter
from accounts.database_utils import get_tenant_database_alias
from accounts.models import EmployeeMembership

from employees.models import Employee

from .models import (
    Communication,
    CommunicationRecipient,
    CommunicationResponse,
    CommunicationComment,
    CommunicationTemplate,
    CommunicationAttachment,
    CommunicationTarget,
    CommunicationVersion,
    CommunicationTemplateVersion,
)
from .serializers import (
    CommunicationListSerializer,
    CommunicationDetailSerializer,
    CommunicationCreateUpdateSerializer,
    CommunicationTargetSerializer,
    CommunicationRecipientSerializer,
    CommunicationAuditLogSerializer,
    CommunicationAttachmentSerializer,
    CommunicationAttachmentUploadSerializer,
    CommunicationCorrectionSerializer,
    CommunicationCommentSerializer,
    CommunicationResponseSerializer,
    CommunicationTemplateSerializer,
    EmployeeCommunicationListSerializer,
)
from .services import create_audit_log, resolve_target_employees, send_communication


class CommunicationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["communications.view", "communications.manage"],
        "retrieve": ["communications.view", "communications.manage"],
        "create": ["communications.create", "communications.manage"],
        "update": ["communications.update", "communications.manage"],
        "partial_update": ["communications.update", "communications.manage"],
        "destroy": ["communications.delete", "communications.manage"],
        "delete_action": ["communications.delete", "communications.manage"],
        "comments": ["communications.view", "communications.manage"],
        "preview_recipients": ["communications.send", "communications.manage"],
        "send": ["communications.send", "communications.manage"],
        "schedule": ["communications.schedule", "communications.manage"],
        "cancel": ["communications.schedule", "communications.manage"],
        "close": ["communications.close", "communications.manage"],
        "recipients": ["communications.view", "communications.manage"],
        "audit": ["communications.audit.view", "communications.manage"],
        "attachments": ["communications.attachments", "communications.manage"],
        "create_version": ["communications.update", "communications.manage"],
        "*": ["communications.manage"],
    }

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        qs = (
            Communication.objects.using(tenant_db)
            .filter(employer_id=employer.id)
            .annotate(recipient_count=Count("recipients"))
        )

        if is_delegate_user(self.request.user, employer.id):
            scope = get_delegate_scope(self.request.user, employer.id)
            scoped_employees = apply_scope_filter(
                Employee.objects.using(tenant_db).filter(employer_id=employer.id),
                scope,
                branch_field="branch_id",
                department_field="department_id",
                self_field="id",
            )
            qs = qs.filter(
                Q(created_by_id=self.request.user.id) | Q(recipients__employee__in=scoped_employees)
            ).distinct()

        comm_type = self.request.query_params.get("type")
        if comm_type:
            qs = qs.filter(type=comm_type)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        priority = self.request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)

        requires_ack = self.request.query_params.get("requires_ack")
        if requires_ack in ["true", "false"]:
            qs = qs.filter(requires_ack=(requires_ack == "true"))

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(body__icontains=search))

        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return CommunicationListSerializer
        if self.action in ["create", "update", "partial_update"]:
            return CommunicationCreateUpdateSerializer
        if self.action == "recipients":
            return CommunicationRecipientSerializer
        if self.action == "audit":
            return CommunicationAuditLogSerializer
        if self.action == "attachments":
            return CommunicationAttachmentSerializer
        return CommunicationDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        context.update(
            {
                "employer": employer,
                "tenant_db": tenant_db,
                "actor_id": getattr(self.request.user, "id", None),
            }
        )
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        communication = serializer.save()

        create_audit_log(
            communication=communication,
            action="CREATED",
            actor_user_id=request.user.id,
            request=request,
            tenant_db=self.get_serializer_context()["tenant_db"],
        )
        return Response(
            CommunicationDetailSerializer(communication, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in [Communication.STATUS_DRAFT, Communication.STATUS_SCHEDULED]:
            return Response(
                {"error": "Only draft or scheduled communications can be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        communication = serializer.save()
        create_audit_log(
            communication=communication,
            action="UPDATED",
            actor_user_id=self.request.user.id,
            request=self.request,
            tenant_db=self.get_serializer_context()["tenant_db"],
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.type == Communication.TYPE_HR_LETTER and instance.status in [
            Communication.STATUS_SENT,
            Communication.STATUS_CLOSED,
        ]:
            return Response(
                {"error": "Sent HR letters cannot be deleted. Use corrections instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="delete")
    def delete_action(self, request, pk=None):
        # Convenience endpoint for clients that can't send DELETE.
        return self.destroy(request, pk=pk)

    @action(detail=True, methods=["get"], url_path="comments")
    def comments(self, request, pk=None):
        communication = self.get_object()
        tenant_db = self.get_serializer_context()["tenant_db"]

        if not communication.allow_comments or communication.type != Communication.TYPE_ANNOUNCEMENT:
            return Response([], status=status.HTTP_200_OK)

        qs = CommunicationComment.objects.using(tenant_db).filter(
            communication=communication, is_deleted=False
        ).select_related("employee")
        serializer = CommunicationCommentSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="preview-recipients")
    def preview_recipients(self, request):
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        targets = request.data.get("targets") or []

        serializer = CommunicationTargetSerializer(data=targets, many=True)
        serializer.is_valid(raise_exception=True)

        employees = resolve_target_employees(
            employer_id=employer.id,
            tenant_db=tenant_db,
            targets=serializer.validated_data,
        ).select_related("department", "branch")

        sample = list(
            employees.values("id", "first_name", "last_name", "employee_id", "department_id", "branch_id")[:10]
        )
        return Response(
            {
                "estimated_count": employees.count(),
                "sample": sample,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        communication = self.get_object()
        if communication.status == Communication.STATUS_SENT:
            return Response({"error": "Communication already sent."}, status=status.HTTP_400_BAD_REQUEST)
        if communication.status in [Communication.STATUS_CANCELLED, Communication.STATUS_CLOSED]:
            return Response({"error": "Cancelled or closed communications cannot be sent."}, status=status.HTTP_400_BAD_REQUEST)

        if communication.type == Communication.TYPE_HR_LETTER:
            has_employee_target = communication.targets.filter(
                rule_type=CommunicationTarget.RULE_EMPLOYEE_ID
            ).exists()
            if not has_employee_target:
                return Response(
                    {"error": "HR letters must target specific employees."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        preview_qs = resolve_target_employees(
            employer_id=employer.id,
            tenant_db=tenant_db,
            targets=list(communication.targets.all()),
        )
        if not preview_qs.exists():
            return Response({"error": "No recipients matched the targeting rules."}, status=status.HTTP_400_BAD_REQUEST)
        send_communication(
            communication=communication,
            employer=employer,
            tenant_db=tenant_db,
            actor_user_id=request.user.id,
            request=request,
        )
        return Response(
            CommunicationDetailSerializer(communication, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        communication = self.get_object()
        if communication.status == Communication.STATUS_SENT:
            return Response({"error": "Communication already sent."}, status=status.HTTP_400_BAD_REQUEST)

        scheduled_at = request.data.get("scheduled_at")
        if not scheduled_at:
            return Response({"error": "scheduled_at is required."}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(scheduled_at, str):
            parsed = parse_datetime(scheduled_at)
            if not parsed:
                return Response({"error": "Invalid scheduled_at datetime."}, status=status.HTTP_400_BAD_REQUEST)
            scheduled_at = parsed

        communication.status = Communication.STATUS_SCHEDULED
        communication.scheduled_at = scheduled_at
        communication.updated_by_id = request.user.id
        tenant_db = self.get_serializer_context()["tenant_db"]
        communication.save(using=tenant_db, update_fields=["status", "scheduled_at", "updated_by_id", "updated_at"])

        create_audit_log(
            communication=communication,
            action="SCHEDULED",
            actor_user_id=request.user.id,
            request=request,
            metadata={"scheduled_at": str(scheduled_at)},
            tenant_db=tenant_db,
        )
        return Response(
            CommunicationDetailSerializer(communication, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        communication = self.get_object()
        if communication.status != Communication.STATUS_SCHEDULED:
            return Response({"error": "Only scheduled communications can be cancelled."}, status=status.HTTP_400_BAD_REQUEST)

        tenant_db = self.get_serializer_context()["tenant_db"]
        communication.status = Communication.STATUS_CANCELLED
        communication.updated_by_id = request.user.id
        communication.save(using=tenant_db, update_fields=["status", "updated_by_id", "updated_at"])

        create_audit_log(
            communication=communication,
            action="CANCELLED",
            actor_user_id=request.user.id,
            request=request,
            tenant_db=tenant_db,
        )
        return Response(
            CommunicationDetailSerializer(communication, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        communication = self.get_object()
        if communication.status != Communication.STATUS_SENT:
            return Response({"error": "Only sent communications can be closed."}, status=status.HTTP_400_BAD_REQUEST)

        tenant_db = self.get_serializer_context()["tenant_db"]
        communication.status = Communication.STATUS_CLOSED
        communication.closed_at = timezone.now()
        communication.updated_by_id = request.user.id
        communication.save(using=tenant_db, update_fields=["status", "closed_at", "updated_by_id", "updated_at"])
        CommunicationRecipient.objects.using(tenant_db).filter(communication=communication).update(
            state=CommunicationRecipient.STATE_CLOSED
        )

        create_audit_log(
            communication=communication,
            action="CLOSED",
            actor_user_id=request.user.id,
            request=request,
            tenant_db=tenant_db,
        )
        return Response(
            CommunicationDetailSerializer(communication, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def recipients(self, request, pk=None):
        communication = self.get_object()
        tenant_db = self.get_serializer_context()["tenant_db"]
        qs = CommunicationRecipient.objects.using(tenant_db).filter(communication=communication).select_related(
            "employee", "employee__department", "employee__branch"
        )
        serializer = CommunicationRecipientSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def audit(self, request, pk=None):
        communication = self.get_object()
        tenant_db = self.get_serializer_context()["tenant_db"]
        qs = communication.audit_logs.using(tenant_db).all()
        serializer = CommunicationAuditLogSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"])
    def attachments(self, request, pk=None):
        communication = self.get_object()
        tenant_db = self.get_serializer_context()["tenant_db"]

        if request.method == "GET":
            qs = communication.attachments.using(tenant_db).all()
            serializer = CommunicationAttachmentSerializer(qs, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = CommunicationAttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data.get("file")
        if not upload:
            return Response({"error": "file is required."}, status=status.HTTP_400_BAD_REQUEST)

        attachment = CommunicationAttachment.objects.using(tenant_db).create(
            communication=communication,
            version=serializer.validated_data.get("version"),
            file=upload,
            file_size=getattr(upload, "size", 0),
            content_type=getattr(upload, "content_type", None),
            original_name=getattr(upload, "name", None),
            uploaded_by_id=request.user.id,
        )

        create_audit_log(
            communication=communication,
            action="ATTACHMENT_ADDED",
            actor_user_id=request.user.id,
            request=request,
            metadata={"attachment_id": str(attachment.id)},
            tenant_db=tenant_db,
        )

        return Response(CommunicationAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="correct")
    def create_version(self, request, pk=None):
        communication = self.get_object()
        serializer = CommunicationCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_db = self.get_serializer_context()["tenant_db"]
        title = serializer.validated_data.get("title", communication.title)
        body = serializer.validated_data.get("body", communication.body)
        change_reason = serializer.validated_data.get("change_reason")

        communication.title = title
        communication.body = body
        communication.updated_by_id = request.user.id
        communication.save(using=tenant_db, update_fields=["title", "body", "updated_by_id", "updated_at"])

        max_version = (
            CommunicationVersion.objects.using(tenant_db)
            .filter(communication=communication)
            .aggregate(max_num=Max("version_number"))
            .get("max_num")
            or 0
        )
        version = CommunicationVersion.objects.using(tenant_db).create(
            communication=communication,
            version_number=max_version + 1,
            title=title,
            body=body,
            change_reason=change_reason or None,
            is_correction=True,
            supersedes_version=communication.current_version,
            created_by_id=request.user.id,
        )
        communication.current_version = version
        communication.save(using=tenant_db, update_fields=["current_version", "updated_at"])

        create_audit_log(
            communication=communication,
            action="CORRECTED",
            actor_user_id=request.user.id,
            request=request,
            metadata={"change_reason": change_reason},
            tenant_db=tenant_db,
        )

        return Response(CommunicationDetailSerializer(communication).data, status=status.HTTP_200_OK)


class CommunicationTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["communications.template.view", "communications.manage"],
        "retrieve": ["communications.template.view", "communications.manage"],
        "create": ["communications.template.manage", "communications.manage"],
        "update": ["communications.template.manage", "communications.manage"],
        "partial_update": ["communications.template.manage", "communications.manage"],
        "destroy": ["communications.template.manage", "communications.manage"],
        "*": ["communications.manage"],
    }
    serializer_class = CommunicationTemplateSerializer

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        return CommunicationTemplate.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        data = serializer.validated_data
        instance = CommunicationTemplate.objects.using(tenant_db).create(
            employer_id=employer.id,
            created_by_id=self.request.user.id,
            **data,
        )
        CommunicationTemplateVersion.objects.using(tenant_db).create(
            template=instance,
            version_label="v1",
            subject_template=instance.subject_template,
            body_template=instance.body_template,
            created_by_id=self.request.user.id,
        )
        serializer.instance = instance

    def perform_update(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        instance = serializer.instance
        for field, value in serializer.validated_data.items():
            setattr(instance, field, value)
        instance.save(using=tenant_db)
        CommunicationTemplateVersion.objects.using(tenant_db).create(
            template=instance,
            version_label=None,
            subject_template=instance.subject_template,
            body_template=instance.body_template,
            created_by_id=self.request.user.id,
        )


class EmployeeCommunicationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsEmployee]
    serializer_class = EmployeeCommunicationListSerializer

    def _resolve_employee(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        membership = EmployeeMembership.objects.filter(
            user_id=self.request.user.id,
            employer_profile_id=employer.id,
            status=EmployeeMembership.STATUS_ACTIVE,
        ).first()

        employee = None
        if membership and membership.tenant_employee_id:
            employee = Employee.objects.using(tenant_db).filter(id=membership.tenant_employee_id).first()

        if not employee:
            employee = Employee.objects.using(tenant_db).filter(user_id=self.request.user.id).first()

        return employer, tenant_db, employee

    def get_queryset(self):
        employer, tenant_db, employee = self._resolve_employee()
        if not employee:
            return CommunicationRecipient.objects.none()

        qs = (
            CommunicationRecipient.objects.using(tenant_db)
            .filter(employee=employee)
            .select_related("communication")
            .prefetch_related("communication__attachments")
        )

        filter_value = self.request.query_params.get("filter")
        if filter_value == "unread":
            qs = qs.filter(read_at__isnull=True)
        elif filter_value == "requires_action":
            qs = qs.filter(
                Q(ack_required=True, acknowledged_at__isnull=True)
                | Q(response_required=True, responded_at__isnull=True)
            )

        return qs

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        tenant_db = instance._state.db or "default"
        if not instance.read_at:
            instance.read_at = timezone.now()
            instance.save(using=tenant_db, update_fields=["read_at"])
            create_audit_log(
                communication=instance.communication,
                action="READ",
                actor_user_id=request.user.id,
                actor_employee_id=instance.employee_id,
                request=request,
                tenant_db=tenant_db,
            )
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        recipient = self.get_object()
        tenant_db = recipient._state.db or "default"
        if not recipient.ack_required:
            return Response({"error": "Acknowledgment not required."}, status=status.HTTP_400_BAD_REQUEST)
        if not recipient.acknowledged_at:
            recipient.acknowledged_at = timezone.now()
            recipient.state = CommunicationRecipient.STATE_ACKNOWLEDGED
            recipient.save(using=tenant_db, update_fields=["acknowledged_at", "state", "updated_at"])
            create_audit_log(
                communication=recipient.communication,
                action="ACKNOWLEDGED",
                actor_user_id=request.user.id,
                actor_employee_id=recipient.employee_id,
                request=request,
                tenant_db=tenant_db,
            )
        return Response(self.get_serializer(recipient).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        recipient = self.get_object()
        tenant_db = recipient._state.db or "default"
        if not recipient.response_required:
            return Response({"error": "Response not allowed."}, status=status.HTTP_400_BAD_REQUEST)
        if hasattr(recipient, "response") and recipient.response:
            return Response({"error": "Response already submitted."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CommunicationResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = CommunicationResponse.objects.using(tenant_db).create(
            communication=recipient.communication,
            recipient=recipient,
            body=serializer.validated_data["body"],
        )

        recipient.responded_at = timezone.now()
        recipient.state = CommunicationRecipient.STATE_RESPONDED
        recipient.save(using=tenant_db, update_fields=["responded_at", "state", "updated_at"])

        create_audit_log(
            communication=recipient.communication,
            action="RESPONDED",
            actor_user_id=request.user.id,
            actor_employee_id=recipient.employee_id,
            request=request,
            metadata={"response_id": str(response.id)},
            tenant_db=tenant_db,
        )
        return Response(self.get_serializer(recipient).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None):
        recipient = self.get_object()
        communication = recipient.communication
        tenant_db = recipient._state.db or "default"

        if not communication.allow_comments or communication.type != Communication.TYPE_ANNOUNCEMENT:
            return Response({"error": "Comments are not enabled for this communication."}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == "GET":
            qs = CommunicationComment.objects.using(tenant_db).filter(
                communication=communication, is_deleted=False
            ).select_related("employee")
            serializer = CommunicationCommentSerializer(qs, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = CommunicationCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = CommunicationComment.objects.using(tenant_db).create(
            communication=communication,
            employee=recipient.employee,
            user_id=request.user.id,
            body=serializer.validated_data["body"],
        )
        create_audit_log(
            communication=communication,
            action="COMMENTED",
            actor_user_id=request.user.id,
            actor_employee_id=recipient.employee_id,
            request=request,
            metadata={"comment_id": str(comment.id)},
            tenant_db=tenant_db,
        )
        return Response(CommunicationCommentSerializer(comment).data, status=status.HTTP_201_CREATED)
