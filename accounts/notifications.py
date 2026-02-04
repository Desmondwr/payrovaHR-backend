from django.utils import timezone

from notifications.models import Notification  # noqa: F401
from accounts.models import EmployerProfile, User  # noqa: F401

def create_notification(user, title, body='', *, type='INFO', data=None, employer_profile=None):
    """
    Helper to emit a notification to a user.
    Intended for use by other apps/services without altering existing flows.
    """
    if user is None:
        return None
    return Notification.objects.create(
        user=user,
        employer_profile=employer_profile,
        title=title,
        body=body or '',
        type=type,
        status=Notification.STATUS_UNREAD,
        data=data or {},
        created_at=timezone.now(),
    )
