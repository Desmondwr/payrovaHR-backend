from django.apps import AppConfig


class EmployeesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'employees'

    def ready(self):
        # Import signals to ensure membership sync hooks are registered
        from . import signals  # noqa: F401
