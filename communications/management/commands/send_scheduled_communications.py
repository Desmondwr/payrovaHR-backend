from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.database_utils import ensure_tenant_database_loaded
from accounts.models import EmployerProfile

from communications.models import Communication
from communications.services import send_communication


class Command(BaseCommand):
    help = "Send scheduled communications that are due."

    def handle(self, *args, **options):
        now = timezone.now()
        sent_count = 0
        checked = 0

        employers = EmployerProfile.objects.filter(
            database_created=True, database_name__isnull=False
        )

        for employer in employers:
            tenant_db = ensure_tenant_database_loaded(employer)
            due = Communication.objects.using(tenant_db).filter(
                employer_id=employer.id,
                status=Communication.STATUS_SCHEDULED,
                scheduled_at__lte=now,
            )
            for communication in due:
                checked += 1
                try:
                    send_communication(
                        communication=communication,
                        employer=employer,
                        tenant_db=tenant_db,
                        actor_user_id=communication.updated_by_id or communication.created_by_id,
                        request=None,
                    )
                    sent_count += 1
                except Exception:
                    continue

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {checked} scheduled communications. Sent {sent_count}."
            )
        )
