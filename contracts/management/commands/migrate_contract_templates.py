from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias


class Command(BaseCommand):
    help = "Apply contract migrations (including body_override) to all tenant databases."

    def handle(self, *args, **options):
        employers = EmployerProfile.objects.all()
        if not employers.exists():
            self.stdout.write("No employers found.")
            return

        for employer in employers:
            alias = get_tenant_database_alias(employer)
            # Ensure alias is registered in settings.DATABASES
            if alias not in settings.DATABASES:
                base = settings.DATABASES["default"].copy()
                base["NAME"] = employer.database_name
                settings.DATABASES[alias] = base
                self.stdout.write(f"Registered DB alias {alias} -> {base['NAME']}")

            self.stdout.write(f"Applying migrations to {alias}...")
            call_command("migrate", "contracts", database=alias, verbosity=0)

        self.stdout.write(self.style.SUCCESS("Contract template migrations applied to all tenants."))
