from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a super admin user'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Admin email address', required=True)
        parser.add_argument('--password', type=str, help='Admin password', required=False)

    def handle(self, *args, **options):
        email = options['email']
        password = options.get('password')
        
        # Validate email
        if not email:
            self.stdout.write(self.style.ERROR('Email is required'))
            return
        
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.ERROR(f'User with email {email} already exists'))
            return
        
        # Get password if not provided
        if not password:
            import getpass
            password = getpass.getpass('Enter password: ')
            confirm_password = getpass.getpass('Confirm password: ')
            
            if password != confirm_password:
                self.stdout.write(self.style.ERROR('Passwords do not match'))
                return
        
        try:
            # Create super admin
            user = User.objects.create_superuser(
                email=email,
                password=password,
                is_admin=True
            )
            
            self.stdout.write(self.style.SUCCESS(f'Successfully created super admin: {email}'))
            self.stdout.write(self.style.SUCCESS('User details:'))
            self.stdout.write(f'  - Email: {user.email}')
            self.stdout.write(f'  - Is Admin: {user.is_admin}')
            self.stdout.write(f'  - Is Superuser: {user.is_superuser}')
            self.stdout.write(f'  - Is Active: {user.is_active}')
            
        except IntegrityError as e:
            self.stdout.write(self.style.ERROR(f'Error creating user: {str(e)}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Unexpected error: {str(e)}'))
