from rest_framework import permissions, status
from rest_framework.views import APIView

from accounts.utils import api_response
from django.utils import timezone
from django.core.cache import cache

from accounts.notifications import create_notification
from accounts.rbac import get_active_employer
from accounts.database_utils import get_tenant_database_alias, ensure_tenant_database_loaded
from employees.models import Employee
from employees.utils import get_employer_notification_recipients, notify_employee_user

from .models import Notification
from .serializers import NotificationSerializer, NotificationMarkReadSerializer


def _birthday_notification_exists(*, user_id, employer_id, employee_id, event_key, birthday_date, today):
    return Notification.objects.filter(
        user_id=user_id,
        employer_profile_id=employer_id,
        created_at__date=today,
        data__event=event_key,
        data__employee_id=str(employee_id),
        data__birthday_date=birthday_date,
    ).exists()


def _emit_today_birthday_notifications(request):
    """
    Lazy birthday generator:
    runs when notifications endpoint is hit, so no cron/celery is required.
    """
    try:
        employer = get_active_employer(request, require_context=False)
    except Exception:
        employer = None

    if not employer:
        return

    today = timezone.localdate()
    today_str = today.isoformat()
    throttle_key = f"notifications:birthday-sync:{employer.id}:{today_str}"

    # Throttle sync work to avoid repeated scans due to frequent polling.
    if cache.get(throttle_key):
        return

    tenant_db = get_tenant_database_alias(employer)
    ensure_tenant_database_loaded(employer)

    birthday_employees = Employee.objects.using(tenant_db).filter(
        employer_id=employer.id,
        employment_status='ACTIVE',
        date_of_birth__isnull=False,
        date_of_birth__month=today.month,
        date_of_birth__day=today.day,
    )

    recipients = get_employer_notification_recipients(employer)
    for employee in birthday_employees:
        employee_name = employee.full_name
        age = today.year - employee.date_of_birth.year
        if (today.month, today.day) < (employee.date_of_birth.month, employee.date_of_birth.day):
            age -= 1

        admin_payload = {
            'event': 'employees.birthday_admin',
            'employee_id': str(employee.id),
            'employee_number': employee.employee_id,
            'name': employee_name,
            'birthday_date': today_str,
            'age': age,
            'path': f'/employer/employees/{employee.id}',
        }
        admin_body = f"Today is {employee_name}'s birthday ({age} years old)."

        for recipient in recipients:
            if _birthday_notification_exists(
                user_id=recipient.id,
                employer_id=employer.id,
                employee_id=employee.id,
                event_key='employees.birthday_admin',
                birthday_date=today_str,
                today=today,
            ):
                continue
            create_notification(
                user=recipient,
                title='Employee birthday today',
                body=admin_body,
                type='INFO',
                data=admin_payload,
                employer_profile=employer,
            )

        if employee.user_id and not _birthday_notification_exists(
            user_id=employee.user_id,
            employer_id=employer.id,
            employee_id=employee.id,
            event_key='employees.birthday',
            birthday_date=today_str,
            today=today,
        ):
            notify_employee_user(
                employee,
                title='Happy Birthday!',
                body=f'Happy Birthday, {employee_name}! Wishing you a great day.',
                type='INFO',
                data={
                    'event': 'employees.birthday',
                    'employee_id': str(employee.id),
                    'name': employee_name,
                    'birthday_date': today_str,
                    'celebration': True,
                    'path': '/employee',
                },
                employer_profile=employer,
            )

    cache.set(throttle_key, True, timeout=300)


class NotificationListView(APIView):
    """List in-app notifications for the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            _emit_today_birthday_notifications(request)
        except Exception:
            # Birthday sync must not break notification feed.
            pass

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
