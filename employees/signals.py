from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import EmployeeMembership, EmployerProfile
from employees.models import Employee

User = get_user_model()


@receiver(post_save, sender=Employee)
def sync_employee_membership(sender, instance: Employee, **kwargs):
    """
    Ensure a global EmployeeMembership exists/updates whenever an Employee
    row (tenant DB) is saved with a linked user_id.
    """
    if not instance.user_id:
        return

    try:
        employer = EmployerProfile.objects.get(id=instance.employer_id)
    except EmployerProfile.DoesNotExist:
        return

    status_val = (
        EmployeeMembership.STATUS_ACTIVE
        if instance.employment_status == 'ACTIVE'
        else EmployeeMembership.STATUS_INVITED
    )

    EmployeeMembership.objects.update_or_create(
        user_id=instance.user_id,
        employer_profile=employer,
        defaults={
            'status': status_val,
            'tenant_employee_id': instance.id,
        },
    )

    # Seed last_active_employer_id when not already set
    User.objects.filter(
        id=instance.user_id,
        last_active_employer_id__isnull=True,
    ).update(last_active_employer_id=employer.id)
