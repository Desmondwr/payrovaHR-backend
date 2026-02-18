from django.db import models
from django.utils import timezone
import uuid


class Communication(models.Model):
    TYPE_ANNOUNCEMENT = "ANNOUNCEMENT"
    TYPE_POLICY_UPDATE = "POLICY_UPDATE"
    TYPE_HR_LETTER = "HR_LETTER"

    TYPE_CHOICES = [
        (TYPE_ANNOUNCEMENT, "Announcement"),
        (TYPE_POLICY_UPDATE, "Policy Update"),
        (TYPE_HR_LETTER, "HR Letter"),
    ]

    LETTER_NONE = "NONE"
    LETTER_QUERY = "QUERY"
    LETTER_WARNING = "WARNING"

    LETTER_CHOICES = [
        (LETTER_NONE, "None"),
        (LETTER_QUERY, "Query Letter"),
        (LETTER_WARNING, "Warning Letter"),
    ]

    PRIORITY_NORMAL = "NORMAL"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_EMERGENCY = "EMERGENCY"

    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_EMERGENCY, "Emergency"),
    ]

    VISIBILITY_TARGETED = "TARGETED"
    VISIBILITY_PRIVATE = "PRIVATE"

    VISIBILITY_CHOICES = [
        (VISIBILITY_TARGETED, "Targeted"),
        (VISIBILITY_PRIVATE, "Private"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_SENT = "SENT"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_SENT, "Sent"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_CLOSED, "Closed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    letter_type = models.CharField(max_length=20, choices=LETTER_CHOICES, default=LETTER_NONE)
    title = models.CharField(max_length=255)
    body = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default=VISIBILITY_TARGETED)
    allow_comments = models.BooleanField(default=False)
    requires_ack = models.BooleanField(default=False)
    allow_response = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    current_version = models.ForeignKey(
        "CommunicationVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_by_id = models.IntegerField(db_index=True)
    updated_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer_id", "status"]),
            models.Index(fields=["employer_id", "type"]),
            models.Index(fields=["scheduled_at"]),
            models.Index(fields=["sent_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.type})"

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        super().save(*args, **kwargs)


class CommunicationVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        Communication, on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.IntegerField()
    title = models.CharField(max_length=255)
    body = models.TextField()
    change_reason = models.TextField(blank=True, null=True)
    is_correction = models.BooleanField(default=False)
    supersedes_version = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="superseded_by"
    )
    checksum = models.CharField(max_length=64, blank=True, null=True)
    created_by_id = models.IntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communication_versions"
        ordering = ["-version_number"]
        unique_together = [("communication", "version_number")]

    def __str__(self):
        return f"{self.communication_id} v{self.version_number}"


class CommunicationTarget(models.Model):
    RULE_ALL = "ALL"
    RULE_DEPARTMENT = "DEPARTMENT"
    RULE_BRANCH = "BRANCH"
    RULE_LOCATION = "LOCATION"
    RULE_JOB_TITLE = "JOB_TITLE"
    RULE_EMPLOYMENT_STATUS = "EMPLOYMENT_STATUS"
    RULE_EMPLOYEE_ID = "EMPLOYEE_ID"
    RULE_RBAC_ROLE = "RBAC_ROLE"

    RULE_CHOICES = [
        (RULE_ALL, "All Employees"),
        (RULE_DEPARTMENT, "Department"),
        (RULE_BRANCH, "Branch"),
        (RULE_LOCATION, "Location"),
        (RULE_JOB_TITLE, "Job Title"),
        (RULE_EMPLOYMENT_STATUS, "Employment Status"),
        (RULE_EMPLOYEE_ID, "Employee"),
        (RULE_RBAC_ROLE, "RBAC Role"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        Communication, on_delete=models.CASCADE, related_name="targets"
    )
    rule_type = models.CharField(max_length=30, choices=RULE_CHOICES)
    rule_value = models.JSONField(default=dict, blank=True)
    include = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communication_targets"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["rule_type"]),
        ]

    def __str__(self):
        return f"{self.rule_type} ({'include' if self.include else 'exclude'})"


class CommunicationRecipient(models.Model):
    ROLE_EMPLOYEE = "EMPLOYEE"
    ROLE_MANAGER = "MANAGER"
    ROLE_HR = "HR"

    ROLE_CHOICES = [
        (ROLE_EMPLOYEE, "Employee"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_HR, "HR"),
    ]

    DELIVERY_PENDING = "PENDING"
    DELIVERY_SENT = "SENT"
    DELIVERY_FAILED = "FAILED"

    DELIVERY_CHOICES = [
        (DELIVERY_PENDING, "Pending"),
        (DELIVERY_SENT, "Sent"),
        (DELIVERY_FAILED, "Failed"),
    ]

    STATE_SENT = "SENT"
    STATE_ACKNOWLEDGED = "ACKNOWLEDGED"
    STATE_RESPONDED = "RESPONDED"
    STATE_CLOSED = "CLOSED"

    STATE_CHOICES = [
        (STATE_SENT, "Sent"),
        (STATE_ACKNOWLEDGED, "Acknowledged"),
        (STATE_RESPONDED, "Responded"),
        (STATE_CLOSED, "Closed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        Communication, on_delete=models.CASCADE, related_name="recipients"
    )
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="communications"
    )
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    recipient_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_EMPLOYEE)
    delivery_status = models.CharField(
        max_length=20, choices=DELIVERY_CHOICES, default=DELIVERY_PENDING
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    ack_required = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    response_required = models.BooleanField(default=False)
    responded_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_SENT)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communication_recipients"
        ordering = ["-created_at"]
        unique_together = [("communication", "employee", "recipient_role")]
        indexes = [
            models.Index(fields=["communication", "employee"]),
            models.Index(fields=["user_id"]),
            models.Index(fields=["state"]),
        ]

    def __str__(self):
        return f"{self.communication_id}:{self.employee_id}:{self.recipient_role}"

    def mark_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])


class CommunicationComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        Communication, on_delete=models.CASCADE, related_name="comments"
    )
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="communication_comments"
    )
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    body = models.TextField()
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communication_comments"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["communication", "created_at"]),
        ]

    def __str__(self):
        return f"Comment {self.id} on {self.communication_id}"


class CommunicationResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        Communication, on_delete=models.CASCADE, related_name="responses"
    )
    recipient = models.OneToOneField(
        CommunicationRecipient, on_delete=models.CASCADE, related_name="response"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communication_responses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Response {self.id} on {self.communication_id}"


class CommunicationAttachment(models.Model):
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
    communication = models.ForeignKey(
        Communication, on_delete=models.CASCADE, related_name="attachments"
    )
    version = models.ForeignKey(
        CommunicationVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attachments",
    )
    file = models.FileField(upload_to="communication_attachments/")
    file_size = models.IntegerField(help_text="File size in bytes")
    content_type = models.CharField(max_length=100, blank=True, null=True)
    original_name = models.CharField(max_length=255, blank=True, null=True)
    checksum = models.CharField(max_length=64, blank=True, null=True)
    virus_scan_status = models.CharField(
        max_length=20, choices=SCAN_CHOICES, default=SCAN_PENDING
    )
    uploaded_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communication_attachments"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["communication", "uploaded_at"]),
        ]

    def __str__(self):
        return f"{self.communication_id}:{self.id}"


class CommunicationTemplate(models.Model):
    TEMPLATE_QUERY = "QUERY"
    TEMPLATE_WARNING = "WARNING"

    TEMPLATE_CHOICES = [
        (TEMPLATE_QUERY, "Query Letter"),
        (TEMPLATE_WARNING, "Warning Letter"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_id = models.IntegerField(db_index=True)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_CHOICES)
    subject_template = models.TextField()
    body_template = models.TextField()
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communication_templates"
        ordering = ["-created_at"]
        unique_together = [("employer_id", "name")]
        indexes = [
            models.Index(fields=["employer_id", "template_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.template_type})"

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant_id = self.employer_id
        if self.is_default:
            db_alias = self._state.db or "default"
            CommunicationTemplate.objects.using(db_alias).filter(
                employer_id=self.employer_id,
                template_type=self.template_type,
                is_default=True,
            ).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)


class CommunicationTemplateVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        CommunicationTemplate, on_delete=models.CASCADE, related_name="versions"
    )
    version_label = models.CharField(max_length=50, blank=True, null=True)
    subject_template = models.TextField()
    body_template = models.TextField()
    created_by_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communication_template_versions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.template_id}:{self.version_label or self.id}"


class CommunicationAuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        Communication, on_delete=models.CASCADE, related_name="audit_logs"
    )
    action = models.CharField(max_length=50)
    actor_user_id = models.IntegerField(null=True, blank=True, db_index=True)
    actor_employee_id = models.UUIDField(null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communication_audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["communication", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.communication_id}"
