import sys
from typing import List

from django.core.exceptions import FieldDoesNotExist
from django.core.management import BaseCommand, call_command
from django.db import transaction

from accounts.database_utils import ensure_tenant_database_loaded, load_all_tenant_databases
from accounts.models import EmployerProfile
from timeoff.models import TimeOffConfiguration, TimeOffType


class Command(BaseCommand):
    help = (
        "Backfill structured time-off tables (TimeOffType/ApprovalStep) from legacy "
        "JSON in timeoff_configurations.configuration. Intended for tenants created "
        "before the normalization migration. No-op if the legacy column is removed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            dest="database",
            default="default",
            help="Database alias to run against (default: default).",
        )
        parser.add_argument(
            "--all-tenants",
            action="store_true",
            help="Process all tenant databases (auto-load aliases from EmployerProfile).",
        )
        parser.add_argument(
            "--clear-legacy",
            action="store_true",
            help="After backfill, clear the legacy configuration JSON field.",
        )
        parser.add_argument(
            "--app-migrate-first",
            dest="app_label",
            help="Optional app label to migrate on each DB before backfilling (e.g., timeoff).",
        )

    def handle(self, *args, **options):
        if not self._legacy_configuration_available():
            self.stdout.write(
                self.style.WARNING(
                    "Legacy configuration column is not available; nothing to backfill."
                )
            )
            return

        clear_legacy = options.get("clear_legacy", False)
        app_label = options.get("app_label")
        verbosity = options.get("verbosity", 1)

        aliases: List[str] = []
        if options.get("all_tenants"):
            self.stdout.write("Loading tenant database aliases...")
            load_all_tenant_databases()
            tenants = EmployerProfile.objects.filter(database_created=True, database_name__isnull=False)
            aliases = [ensure_tenant_database_loaded(emp) for emp in tenants]
            if not aliases:
                self.stdout.write(self.style.WARNING("No tenant databases found."))
                return
        else:
            aliases = [options.get("database", "default")]

        failures = 0
        for idx, alias in enumerate(aliases, start=1):
            self.stdout.write(f"[{idx}/{len(aliases)}] Processing {alias}...")

            if app_label:
                call_command("migrate", app_label, database=alias, verbosity=verbosity)

            try:
                self._process_alias(alias, clear_legacy)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                self.stderr.write(self.style.ERROR(f"Failed on {alias}: {exc}"))

        if failures:
            self.stderr.write(self.style.ERROR(f"Completed with {failures} failure(s)."))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(f"Backfill completed for {len(aliases)} database(s)."))

    def _legacy_configuration_available(self) -> bool:
        try:
            TimeOffConfiguration._meta.get_field("configuration")
        except FieldDoesNotExist:
            return False
        return True

    def _process_alias(self, alias: str, clear_legacy: bool):
        configs = TimeOffConfiguration.objects.using(alias).all()
        for cfg in configs:
            if cfg.leave_types.exists():
                continue  # Already normalized
            payload = cfg.configuration or {}
            leave_types = payload.get("leave_types") or []
            if not leave_types:
                continue

            with transaction.atomic(using=alias):
                for entry in leave_types:
                    TimeOffType.from_dict(configuration=cfg, data=entry, db_alias=alias)
                if clear_legacy:
                    cfg.configuration = {}
                    cfg.save(using=alias, update_fields=["configuration"])
