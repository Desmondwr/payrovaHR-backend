"""
Management command to migrate all tenant databases
Usage: python manage.py migrate_tenants [app_label] [migration_name]
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connections
from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias, add_tenant_database_to_settings


class Command(BaseCommand):
    help = 'Run migrations on all tenant databases'

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label',
            nargs='?',
            help='App label of the application to migrate.'
        )
        parser.add_argument(
            'migration_name',
            nargs='?',
            help='Migration name to migrate to.'
        )
        parser.add_argument(
            '--fake',
            action='store_true',
            help='Mark migrations as run without actually running them.'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='Show a list of all known migrations and which are applied.'
        )

    def handle(self, *args, **options):
        app_label = options.get('app_label')
        migration_name = options.get('migration_name')
        fake = options.get('fake', False)
        list_migrations = options.get('list', False)
        
        # Get all active employer profiles with databases
        employers = EmployerProfile.objects.filter(
            database_created=True,
            user__is_active=True
        ).select_related('user')
        
        if not employers.exists():
            self.stdout.write(self.style.WARNING('No tenant databases found.'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'Found {employers.count()} tenant database(s)'))
        
        for employer in employers:
            tenant_db = get_tenant_database_alias(employer)
            
            self.stdout.write(f'\n{"-" * 70}')
            self.stdout.write(
                self.style.NOTICE(
                    f'Migrating tenant: {employer.company_name} (DB: {employer.database_name})'
                )
            )
            
            try:
                # Ensure the tenant database is added to Django settings
                add_tenant_database_to_settings(employer.database_name, employer.id)
                
                # Check if database connection is valid
                connection = connections[tenant_db]
                connection.ensure_connection()
                
                # Build migrate command arguments
                migrate_args = []
                migrate_kwargs = {'database': tenant_db, 'verbosity': 2}
                
                if app_label:
                    migrate_args.append(app_label)
                if migration_name:
                    migrate_args.append(migration_name)
                if fake:
                    migrate_kwargs['fake'] = True
                if list_migrations:
                    migrate_kwargs['list'] = True
                
                # Run migrations
                call_command('migrate', *migrate_args, **migrate_kwargs)
                
                self.stdout.write(
                    self.style.SUCCESS(f'バ" Successfully migrated {employer.company_name}')
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'バ- Error migrating {employer.company_name}: {str(e)}')
                )
                continue
        
        self.stdout.write(f'\n{"-" * 70}')
        self.stdout.write(self.style.SUCCESS('\nMigration of all tenant databases completed!'))
