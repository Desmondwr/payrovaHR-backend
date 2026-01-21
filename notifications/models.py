from django.db import models
from django.utils import timezone
from django.conf import settings


class Notification(models.Model):
    """In-app notification feed for users (default DB)."""

    TYPE_INFO = 'INFO'
    TYPE_ACTION = 'ACTION'
    TYPE_ALERT = 'ALERT'

    TYPE_CHOICES = [
        (TYPE_INFO, 'Info'),
        (TYPE_ACTION, 'Action'),
        (TYPE_ALERT, 'Alert'),
    ]

    STATUS_UNREAD = 'UNREAD'
    STATUS_READ = 'READ'

    STATUS_CHOICES = [
        (STATUS_UNREAD, 'Unread'),
        (STATUS_READ, 'Read'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    employer_profile = models.ForeignKey(
        'accounts.EmployerProfile',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
        help_text='Optional employer context for multi-employer users'
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_INFO)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNREAD, db_index=True)
    data = models.JSONField(null=True, blank=True, help_text='Additional payload for the frontend')
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['employer_profile', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def mark_read(self):
        if self.status != self.STATUS_READ:
            self.status = self.STATUS_READ
            self.read_at = timezone.now()
            self.save(update_fields=['status', 'read_at'])
