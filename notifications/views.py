from rest_framework import permissions, status
from rest_framework.views import APIView

from accounts.utils import api_response
from django.utils import timezone

from .models import Notification
from .serializers import NotificationSerializer, NotificationMarkReadSerializer


class NotificationListView(APIView):
    """List in-app notifications for the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get('status')
        qs = Notification.objects.filter(user=request.user)
        if status_filter in [Notification.STATUS_READ, Notification.STATUS_UNREAD]:
            qs = qs.filter(status=status_filter)
        serializer = NotificationSerializer(qs.order_by('-created_at'), many=True)
        return api_response(
            success=True,
            message='Notifications retrieved.',
            data=serializer.data,
            status=status.HTTP_200_OK,
        )


class NotificationMarkReadView(APIView):
    """Mark one or more notifications as read for the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = NotificationMarkReadSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message='Invalid payload.',
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        ids = serializer.validated_data['notification_ids']
        qs = Notification.objects.filter(user=request.user, id__in=ids, status=Notification.STATUS_UNREAD)
        now = timezone.now()
        qs.update(status=Notification.STATUS_READ, read_at=now)

        return api_response(
            success=True,
            message='Notifications marked as read.',
            data={'updated': qs.count()},
            status=status.HTTP_200_OK,
        )
