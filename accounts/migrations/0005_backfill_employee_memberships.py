from django.db import migrations


def migrate_employee_profiles_to_memberships(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    EmployerProfile = apps.get_model('accounts', 'EmployerProfile')
    EmployeeMembership = apps.get_model('accounts', 'EmployeeMembership')
    status_active = getattr(EmployeeMembership, 'STATUS_ACTIVE', 'ACTIVE')
    status_invited = getattr(EmployeeMembership, 'STATUS_INVITED', 'INVITED')

    for user in User.objects.using(schema_editor.connection.alias).filter(is_employee=True):
        # Skip if membership already exists
        if EmployeeMembership.objects.filter(user_id=user.id).exists():
            continue

        try:
            employee = user.employee_profile
        except Exception:
            # Legacy lookup failed; leave for manual backfill
            continue

        if not employee:
            continue

        employer_profile = EmployerProfile.objects.filter(id=getattr(employee, 'employer_id', None)).first()
        if not employer_profile:
            continue

        status = status_active if getattr(employee, 'employment_status', '') == 'ACTIVE' else status_invited

        membership, created = EmployeeMembership.objects.get_or_create(
            user_id=user.id,
            employer_profile=employer_profile,
            defaults={
                'status': status,
                'tenant_employee_id': getattr(employee, 'id', None),
            },
        )

        if created and not user.last_active_employer_id:
            user.last_active_employer_id = employer_profile.id
            user.save(update_fields=['last_active_employer_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_employeemembership_last_active_employer'),
    ]

    operations = [
        migrations.RunPython(
            migrate_employee_profiles_to_memberships,
            migrations.RunPython.noop,
        ),
    ]
