from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias
from contracts.models import Contract, ContractAudit
from contracts.notifications import notify_signature_reminder, notify_signature_expired


class Command(BaseCommand):
    help = "Send signature reminders and expire stale signature requests."

    def handle(self, *args, **options):
        today = timezone.now().date()
        reminder_count = 0
        expired_count = 0

        for employer in EmployerProfile.objects.all():
            tenant_db = get_tenant_database_alias(employer)
            try:
                contracts = Contract.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    status='PENDING_SIGNATURE',
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Error fetching contracts for {employer.company_name}: {e}"
                ))
                continue

            for contract in contracts:
                try:
                    if not contract.signature_required():
                        continue
                    if not contract.get_effective_config('enable_notifications', True):
                        continue

                    expiry_days = contract.get_effective_config('signature_expiry_days', 0) or 0
                    reminder_days = contract.get_effective_config('signature_reminder_interval_days', 0) or 0

                    sent_ts = ContractAudit.objects.using(tenant_db).filter(
                        contract=contract,
                        action='SENT_FOR_SIGNATURE'
                    ).order_by('-timestamp').values_list('timestamp', flat=True).first()
                    if not sent_ts:
                        sent_ts = contract.updated_at

                    sent_date = sent_ts.date() if sent_ts else today
                    expiry_date = sent_date + timedelta(days=int(expiry_days or 0))

                    if expiry_days and today > expiry_date:
                        contract.status = 'CANCELLED'
                        contract.save(using=tenant_db)
                        try:
                            contract.log_action(
                                user=None,
                                action='SIGNATURE_EXPIRED',
                                metadata={
                                    'expired_on': str(expiry_date),
                                    'expiry_days': int(expiry_days),
                                },
                            )
                        except Exception:
                            pass
                        try:
                            notify_signature_expired(contract, expired_on=expiry_date)
                        except Exception:
                            pass
                        expired_count += 1
                        continue

                    if reminder_days:
                        last_reminder = ContractAudit.objects.using(tenant_db).filter(
                            contract=contract,
                            action='SIGNATURE_REMINDER_SENT'
                        ).order_by('-timestamp').values_list('timestamp', flat=True).first()
                        base_date = (last_reminder.date() if last_reminder else sent_date)
                        next_due = base_date + timedelta(days=int(reminder_days))
                        if today >= next_due:
                            days_left = None
                            if expiry_days:
                                days_left = max((expiry_date - today).days, 0)
                            try:
                                notify_signature_reminder(
                                    contract,
                                    days_left=days_left,
                                    expires_on=expiry_date if expiry_days else None,
                                )
                            except Exception:
                                pass
                            try:
                                contract.log_action(
                                    user=None,
                                    action='SIGNATURE_REMINDER_SENT',
                                    metadata={
                                        'interval_days': int(reminder_days),
                                        'expires_on': str(expiry_date) if expiry_days else None,
                                        'days_left': days_left,
                                    },
                                )
                            except Exception:
                                pass
                            reminder_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"Failed to process contract {contract.contract_id}: {e}"
                    ))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Reminders sent: {reminder_count}. Signature requests expired: {expired_count}."
            )
        )
