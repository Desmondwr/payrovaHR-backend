from django.core.management.base import BaseCommand
from django.utils import timezone
from contracts.models import Contract
from contracts.notifications import notify_expiring_soon
from datetime import timedelta

class Command(BaseCommand):
    help = 'Checks for contracts expiring in 30, 15, or 7 days and sends notifications'

    def handle(self, *args, **options):
        today = timezone.now().date()
        target_offsets = [30, 15, 7]
        
        total_notifications = 0
        
        for days in target_offsets:
            target_date = today + timedelta(days=days)
            expiring_contracts = Contract.objects.filter(
                status='ACTIVE',
                end_date=target_date
            )
            
            count = expiring_contracts.count()
            if count > 0:
                self.stdout.write(self.style.SUCCESS(f'Found {count} contracts expiring in {days} days ({target_date})'))
                
                for contract in expiring_contracts:
                    try:
                        notify_expiring_soon(contract)
                        total_notifications += 1
                        self.stdout.write(f'  - Notification sent for {contract.contract_id}')
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'  - Failed to notify for {contract.contract_id}: {e}'))
            else:
                 self.stdout.write(f'No contracts expiring in {days} days ({target_date})')

        self.stdout.write(self.style.SUCCESS(f'Done. Sent {total_notifications} notifications.'))
