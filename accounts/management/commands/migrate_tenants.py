import sys
from django.core.management import BaseCommand, call_command

from accounts.database_utils import ensure_tenant_database_loaded, load_all_tenant_databases
from accounts.models import EmployerProfile


class Command(BaseCommand):
    help = "Run migrations for all tenant databases (optionally the default DB first)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            dest="app_label",
            help="Limit migrations to a specific app label (e.g., timeoff). Defaults to all apps.",
        )
        parser.add_argument(
            "--migration",
            dest="migration_name",
            help="Target a specific migration name/number for the app.",
        )
        parser.add_argument(
            "--include-default",
            action="store_true",
            help="Run migrate on the default database before tenants.",
        )

    def handle(self, *args, **options):
        app_label = options.get("app_label")
        migration_name = options.get("migration_name")
        include_default = options.get("include_default", False)
        verbosity = options.get("verbosity", 1)

        cmd_args = []
        if app_label:
            cmd_args.append(app_label)
        if migration_name:
            cmd_args.append(migration_name)

        if include_default:
            self.stdout.write(self.style.WARNING("Migrating default database..."))
            call_command("migrate", *cmd_args, database="default", verbosity=verbosity)

        self.stdout.write("Loading tenant database aliases...")
        load_all_tenant_databases()

        tenants = EmployerProfile.objects.filter(database_created=True, database_name__isnull=False)
        total = tenants.count()
        if not total:
            self.stdout.write(self.style.WARNING("No tenant databases found."))
            return

        failures = 0
        for idx, employer in enumerate(tenants, start=1):
            alias = ensure_tenant_database_loaded(employer)
            self.stdout.write(f"[{idx}/{total}] Migrating {alias} ...")
            try:
                call_command("migrate", *cmd_args, database=alias, verbosity=verbosity)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                self.stderr.write(self.style.ERROR(f"Failed migrating {alias}: {exc}"))

        if failures:
            self.stderr.write(self.style.ERROR(f"Completed with {failures} failure(s)."))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS(f"Successfully migrated {total} tenant database(s)."))
