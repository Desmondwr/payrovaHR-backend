from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        """
        Called when Django starts up.
        Load all tenant databases into settings on first request.
        This avoids hitting the database during app initialization.
        """
        # Only wire this in web server processes, not during management commands like migrate
        import sys
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0]:
            from django.core.signals import request_started

            def _preload_tenants(**kwargs):
                if getattr(_preload_tenants, "_done", False):
                    return
                _preload_tenants._done = True
                try:
                    from accounts.database_utils import load_all_tenant_databases
                    load_all_tenant_databases()
                    logger.info("Tenant databases loaded successfully on first request")
                except Exception as e:
                    logger.warning(f"Could not load tenant databases on first request: {e}")

            request_started.connect(
                _preload_tenants,
                dispatch_uid="accounts.preload_tenant_databases",
                weak=False,
            )

