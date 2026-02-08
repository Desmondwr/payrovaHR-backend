from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias
from contracts.models import Contract
from contracts.notifications import notify_expiring_soon

class Command(BaseCommand):
    help = 'Checks for contracts expiring soon based on employer configuration'

    def handle(self, *args, **options):
        today = timezone.now().date()

        total_notifications = 0

        for employer in EmployerProfile.objects.all():
            tenant_db = get_tenant_database_alias(employer)
            try:
                contracts = Contract.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    status='ACTIVE',
                    end_date__isnull=False,
                )
                for contract in contracts:
                    try:
                        if not contract.get_effective_config('enable_notifications', True):
                            continue
                        days_before = contract.get_effective_config('days_before_expiry_notify', 30) or 30
                        days_left = (contract.end_date - today).days
                        if days_left < 0:
                            continue
                        if days_left == int(days_before):
                            notify_expiring_soon(contract)
                            total_notifications += 1
                            self.stdout.write(
                                f'  - Notification sent for {contract.contract_id} ({employer.company_name})'
                            )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'  - Failed to notify for {contract.contract_id}: {e}')
                        )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error processing {employer.company_name}: {e}')
                )

        self.stdout.write(self.style.SUCCESS(f'Done. Sent {total_notifications} notifications.'))
