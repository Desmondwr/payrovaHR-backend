from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for in-app notifications (read-only for feeds)"""
    employer_id = serializers.IntegerField(source='employer_profile.id', read_only=True)

    class Meta:
        model = Notification
        fields = (
            'id',
            'title',
            'body',
            'type',
            'status',
            'data',
            'employer_id',
            'created_at',
            'read_at',
        )
        read_only_fields = fields


class NotificationCreateSerializer(serializers.ModelSerializer):
    """Serializer to emit a notification (service or admin usage)"""
    class Meta:
        model = Notification
        fields = (
            'user',
            'employer_profile',
            'title',
            'body',
            'type',
            'data',
        )


class NotificationMarkReadSerializer(serializers.Serializer):
    """Serializer to mark notifications as read"""
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
