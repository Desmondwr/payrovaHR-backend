"""
Management command to send automated reminders for:
- Profile completion
- Document expiry
- Probation ending
- Scheduled access revocation for terminated employees
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias


class Command(BaseCommand):
    help = 'Send automated reminders and handle scheduled tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reminder-type',
            type=str,
            choices=['profile', 'documents', 'probation', 'access_revocation', 'all'],
            default='all',
            help='Type of reminder to send'
        )

    def handle(self, *args, **options):
        reminder_type = options['reminder_type']
        
        if reminder_type in ['profile', 'all']:
            self.send_profile_completion_reminders()
        
        if reminder_type in ['documents', 'all']:
            self.send_document_expiry_reminders()
        
        if reminder_type in ['probation', 'all']:
            self.send_probation_ending_reminders()
        
        if reminder_type in ['access_revocation', 'all']:
            self.process_scheduled_access_revocations()
        
        self.stdout.write(self.style.SUCCESS('Automated reminders processing completed'))

    def send_profile_completion_reminders(self):
        """Send reminders to employees with incomplete profiles"""
        from employees.models import Employee, EmployeeConfiguration
        from employees.utils import send_profile_completion_notification, get_or_create_employee_config
        
        self.stdout.write('Processing profile completion reminders...')
        count = 0
        
        # Process each employer's tenant database
        for employer in EmployerProfile.objects.filter(user__is_active=True):
            try:
                tenant_db = get_tenant_database_alias(employer)
                config = get_or_create_employee_config(employer.id, tenant_db)
                
                # Skip if reminders are disabled
                if not config.send_profile_completion_reminder:
                    continue
                
                # Find employees with incomplete profiles who accepted invitation X days ago
                reminder_threshold = timezone.now() - timedelta(days=config.profile_completion_reminder_days)
                
                employees = Employee.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    profile_completion_required=True,
                    profile_completed=False,
                    invitation_accepted=True,
                    invitation_accepted_at__lte=reminder_threshold
                )
                
                for employee in employees:
                    # Check if reminder was already sent recently (within last 7 days)
                    if employee.last_reminder_sent_at:
                        days_since_last_reminder = (timezone.now() - employee.last_reminder_sent_at).days
                        if days_since_last_reminder < 7:
                            continue
                    
                    # Send reminder
                    from employees.utils import check_missing_fields_against_config
                    validation_result = check_missing_fields_against_config(employee, config)
                    
                    send_profile_completion_notification(
                        employee,
                        validation_result,
                        employer,
                        tenant_db
                    )
                    
                    # Update last reminder sent timestamp
                    employee.last_reminder_sent_at = timezone.now()
                    employee.save(using=tenant_db, update_fields=['last_reminder_sent_at'])
                    
                    count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing employer {employer.id}: {str(e)}'))
                continue
        
        self.stdout.write(self.style.SUCCESS(f'Sent {count} profile completion reminders'))

    def send_document_expiry_reminders(self):
        """Send reminders for expiring documents"""
        from employees.models import Employee, EmployeeDocument
        from employees.utils import send_document_expiry_reminder, get_or_create_employee_config
        
        self.stdout.write('Processing document expiry reminders...')
        count = 0
        
        # Process each employer's tenant database
        for employer in EmployerProfile.objects.filter(user__is_active=True):
            try:
                tenant_db = get_tenant_database_alias(employer)
                config = get_or_create_employee_config(employer.id, tenant_db)
                
                # Skip if document expiry tracking is disabled
                if not config.document_expiry_tracking_enabled:
                    continue
                
                # Find documents expiring within reminder period
                reminder_date = timezone.now().date() + timedelta(days=config.document_expiry_reminder_days)
                
                documents = EmployeeDocument.objects.using(tenant_db).filter(
                    employee__employer_id=employer.id,
                    expiry_date__lte=reminder_date,
                    expiry_date__gte=timezone.now().date()
                ).select_related('employee')
                
                for document in documents:
                    days_until_expiry = (document.expiry_date - timezone.now().date()).days
                    
                    send_document_expiry_reminder(
                        document.employee,
                        document,
                        employer,
                        days_until_expiry
                    )
                    count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing employer {employer.id}: {str(e)}'))
                continue
        
        self.stdout.write(self.style.SUCCESS(f'Sent {count} document expiry reminders'))

    def send_probation_ending_reminders(self):
        """Send reminders for probation periods ending"""
        from employees.models import Employee
        from employees.utils import send_probation_ending_reminder, get_or_create_employee_config
        
        self.stdout.write('Processing probation ending reminders...')
        count = 0
        
        # Process each employer's tenant database
        for employer in EmployerProfile.objects.filter(user__is_active=True):
            try:
                tenant_db = get_tenant_database_alias(employer)
                config = get_or_create_employee_config(employer.id, tenant_db)
                
                # Skip if probation review is not required
                if not config.probation_review_required:
                    continue
                
                # Find employees whose probation is ending within reminder period
                reminder_date = timezone.now().date() + timedelta(days=config.probation_reminder_before_end_days)
                
                employees = Employee.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    employment_status='ACTIVE',
                    probation_end_date__lte=reminder_date,
                    probation_end_date__gte=timezone.now().date()
                )
                
                for employee in employees:
                    days_until_end = (employee.probation_end_date - timezone.now().date()).days
                    
                    send_probation_ending_reminder(
                        employee,
                        employer,
                        days_until_end
                    )
                    count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing employer {employer.id}: {str(e)}'))
                continue
        
        self.stdout.write(self.style.SUCCESS(f'Sent {count} probation ending reminders'))

    def process_scheduled_access_revocations(self):
        """Process scheduled access revocations for terminated employees"""
        from employees.models import Employee
        from employees.utils import get_or_create_employee_config
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        self.stdout.write('Processing scheduled access revocations...')
        count = 0
        
        # Process each employer's tenant database
        for employer in EmployerProfile.objects.filter(user__is_active=True):
            try:
                tenant_db = get_tenant_database_alias(employer)
                config = get_or_create_employee_config(employer.id, tenant_db)
                
                # Find terminated employees whose access should be revoked today
                employees = Employee.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    employment_status='TERMINATED',
                    user_id__isnull=False
                )
                
                for employee in employees:
                    should_revoke = False
                    
                    if config.termination_revoke_access_timing == 'ON_DATE':
                        # Revoke on termination date
                        if employee.termination_date and employee.termination_date <= timezone.now().date():
                            should_revoke = True
                    
                    elif config.termination_revoke_access_timing == 'CUSTOM':
                        # Revoke after custom delay
                        if employee.termination_date:
                            delay_days = config.termination_access_delay_days or 0
                            revoke_date = employee.termination_date + timedelta(days=delay_days)
                            if revoke_date <= timezone.now().date():
                                should_revoke = True
                    
                    if should_revoke:
                        try:
                            user = User.objects.get(id=employee.user_id)
                            if user.is_active:
                                user.is_active = False
                                user.save(update_fields=['is_active'])
                                count += 1
                                self.stdout.write(f'Revoked access for user {user.email} (Employee: {employee.employee_id})')
                        except User.DoesNotExist:
                            pass
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing employer {employer.id}: {str(e)}'))
                continue
        
        self.stdout.write(self.style.SUCCESS(f'Revoked access for {count} terminated employees'))
