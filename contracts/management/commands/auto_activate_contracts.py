from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias
from contracts.models import Contract
from contracts.notifications import notify_expired

class Command(BaseCommand):
    help = 'Automatically activates signed contracts that have reached their start date.'

    def handle(self, *args, **options):
        self.stdout.write("Starting auto-activation process...")
        
        # Iterate over all employers to access their tenant databases
        employers = EmployerProfile.objects.all()
        
        total_activated = 0
        
        for employer in employers:
            tenant_db = get_tenant_database_alias(employer)
            # self.stdout.write(f"Checking tenant DB: {tenant_db} for {employer.company_name}")
            
            try:
                # Find contracts that are:
                # 1. SIGNED
                # 2. start_date <= today
                today = timezone.now().date()
                
                contracts_to_activate = Contract.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    status='SIGNED',
                    start_date__lte=today
                )
                
                count = 0
                for contract in contracts_to_activate:
                    try:
                        if not contract.get_effective_config('auto_activate_on_start', False):
                            continue
                        # Activate with user=None (System action)
                        contract.activate(user=None)
                        count += 1
                        self.stdout.write(self.style.SUCCESS(f"Activated contract {contract.contract_id} for {employer.company_name}"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Failed to activate contract {contract.contract_id}: {str(e)}"))
                
                total_activated += count

                # Auto-expire fixed-term contracts when configured
                expirable = Contract.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    status__in=['ACTIVE', 'SIGNED', 'PENDING_SIGNATURE', 'APPROVED', 'PENDING_APPROVAL'],
                    end_date__isnull=False,
                )
                for contract in expirable:
                    try:
                        if contract._should_auto_expire():
                            contract.status = 'EXPIRED'
                            contract.save(using=tenant_db)
                            contract.log_action(user=None, action='EXPIRED')
                            try:
                                contract._sync_employee_after_status_change('expired', user=None)
                            except Exception:
                                pass
                            try:
                                notify_expired(contract)
                            except Exception:
                                pass
                            self.stdout.write(self.style.SUCCESS(
                                f"Auto-expired contract {contract.contract_id} for {employer.company_name}"
                            ))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f"Failed to auto-expire contract {contract.contract_id}: {str(e)}"
                        ))
                
            except Exception as e:
                 self.stdout.write(self.style.ERROR(f"Error processing tenant {employer.company_name}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"Auto-activation complete. Total activated: {total_activated}"))
