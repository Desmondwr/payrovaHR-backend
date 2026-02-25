from django.core.management.base import BaseCommand

from accounts.database_utils import get_tenant_database_alias
from accounts.models import EmployerProfile

from billing.gbpay_ops import poll_pending_transfers


class Command(BaseCommand):
    help = "Poll GbPay transaction statuses for pending transfers."

    def add_arguments(self, parser):
        parser.add_argument("--employer-id", type=int, help="Limit polling to a specific employer id.")
        parser.add_argument("--limit", type=int, default=50, help="Max transfers to poll per employer.")
        parser.add_argument("--max-pending-hours", type=int, default=24, help="Timeout window for pending transfers.")

    def handle(self, *args, **options):
        employer_id = options.get("employer_id")
        limit = options.get("limit") or 50
        max_pending_hours = options.get("max_pending_hours") or 24

        if employer_id:
            employers = EmployerProfile.objects.filter(id=employer_id)
        else:
            employers = EmployerProfile.objects.filter(user__is_active=True)

        total_processed = 0
        for employer in employers:
            tenant_db = get_tenant_database_alias(employer)
            if not tenant_db:
                continue
            processed = poll_pending_transfers(
                tenant_db=tenant_db,
                employer_id=employer.id,
                limit=limit,
                max_pending_hours=max_pending_hours,
            )
            total_processed += processed

        self.stdout.write(self.style.SUCCESS(f"Polled {total_processed} GbPay transfers."))
