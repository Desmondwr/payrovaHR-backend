from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        """
        Called when Django starts up.
        Load all tenant databases into settings on startup.
        """
        # Only run this in the main process, not in management commands like migrate
        import sys
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0]:
            try:
                from accounts.database_utils import load_all_tenant_databases
                load_all_tenant_databases()
                logger.info("Tenant databases loaded successfully on startup")
            except Exception as e:
                logger.warning(f"Could not load tenant databases on startup: {e}")
                # Don't fail startup if tenant databases can't be loaded
                # They will be loaded on-demand when needed

