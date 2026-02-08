from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from contracts.models import Contract

from .models import Advantage, Deduction, PayrollElement

CONTRACT_DEDUCTION_SYS_CODES = {"CONTRACT_DEDUCTION_FIXED", "CONTRACT_DEDUCTION_PERCENT"}


@receiver(post_save, sender=Contract)
def create_payroll_elements_for_contract(sender, instance: Contract, created, **kwargs):
    """
    When a contract is created, seed payroll elements for all default advantages and deductions.
    """
    if not created:
        return

    db_alias = instance._state.db or "default"
    employer_id = instance.employer_id

    advantages = Advantage.objects.using(db_alias).filter(
        employer_id=employer_id,
        is_active=True,
        is_manual=False,
    )
    deductions = (
        Deduction.objects.using(db_alias)
        .filter(
            employer_id=employer_id,
            is_active=True,
        )
        .exclude(sys_code__in=CONTRACT_DEDUCTION_SYS_CODES)
    )

    elements = []
    for advantage in advantages:
        amount = Decimal("0.00")
        if (advantage.sys_code or "").upper() == "BASIC_SALARY":
            amount = Decimal(str(instance.base_salary or 0))
        elements.append(
            PayrollElement(
                employer_id=employer_id,
                contract=instance,
                advantage=advantage,
                amount=amount,
                month="__",
                year="__",
            )
        )

    for deduction in deductions:
        elements.append(
            PayrollElement(
                employer_id=employer_id,
                contract=instance,
                deduction=deduction,
                amount=Decimal("0.00"),
                month="__",
                year="__",
            )
        )

    if elements:
        with transaction.atomic(using=db_alias):
            PayrollElement.objects.using(db_alias).bulk_create(elements)
