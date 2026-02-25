"""
Management command: delete_employment_certificates
Wipes all generated employment-certificate PDFs (EmployeeDocument records with
type='EMPLOYMENT_CERTIFICATE') and all EmploymentCertificateShare tokens across
every tenant database, plus the default database.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.database_utils import load_all_tenant_databases
from accounts.models import EmployerProfile


class Command(BaseCommand):
    help = (
        "Delete all generated employment-certificate documents and share tokens "
        "from every tenant database."
    )

    def handle(self, *args, **options):
        load_all_tenant_databases()

        from employees.models import EmployeeDocument, EmploymentCertificateShare

        total_docs = 0
        total_files = 0
        total_shares = 0

        dbs_to_check = ["default"] + [
            f"tenant_{emp.id}"
            for emp in EmployerProfile.objects.filter(
                database_created=True, database_name__isnull=False
            )
            if f"tenant_{emp.id}" in settings.DATABASES
        ]

        for db_alias in dbs_to_check:
            label = db_alias

            # ── Share tokens ──────────────────────────────────────────────
            try:
                qs_shares = EmploymentCertificateShare.objects.using(db_alias).all()
                n = qs_shares.count()
                if n:
                    qs_shares.delete()
                    total_shares += n
                    self.stdout.write(f"  [{label}] {n} share token(s) deleted.")
            except Exception as exc:
                self.stderr.write(f"  [{label}] Could not delete shares: {exc}")

            # ── Certificate documents + files ─────────────────────────────
            try:
                qs_docs = EmployeeDocument.objects.using(db_alias).filter(
                    document_type="EMPLOYMENT_CERTIFICATE"
                )
                n = qs_docs.count()
                if n:
                    file_count = 0
                    for doc in qs_docs:
                        if doc.file:
                            try:
                                doc.file.delete(save=False)
                                file_count += 1
                            except Exception:
                                pass
                    qs_docs.delete()
                    total_docs += n
                    total_files += file_count
                    self.stdout.write(
                        f"  [{label}] {n} certificate document(s) deleted "
                        f"({file_count} file(s) removed from storage)."
                    )
            except Exception as exc:
                self.stderr.write(f"  [{label}] Could not delete documents: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFinished. Removed {total_docs} certificate document(s), "
                f"{total_files} file(s) from storage, "
                f"and {total_shares} share token(s)."
            )
        )
