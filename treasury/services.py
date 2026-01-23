import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import EmployerProfile

from .models import (
    BankAccount,
    CashDesk,
    CashDeskSession,
    PaymentBatch,
    PaymentLine,
    TreasuryConfiguration,
    TreasuryTransaction,
)


def resolve_institution(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if hasattr(user, "employer_profile"):
        return user.employer_profile

    employee = getattr(user, "employee_profile", None)
    if employee and getattr(employee, "employer_id", None):
        institution = EmployerProfile.objects.filter(id=employee.employer_id).first()
        if institution:
            return institution

    raise PermissionDenied("Unable to resolve institution.")


def ensure_treasury_configuration(institution, *, tenant_db=None):
    queryset = TreasuryConfiguration.objects
    if tenant_db:
        queryset = queryset.using(tenant_db)

    with transaction.atomic(using=tenant_db):
        base_qs = queryset.filter(institution=institution)
        active_qs = base_qs.filter(is_active=True).order_by("-updated_at", "-created_at", "-id")

        active_config = active_qs.first()
        if active_config:
            active_ids = list(active_qs.values_list("id", flat=True))
            if len(active_ids) > 1:
                base_qs.filter(is_active=True).exclude(id=active_config.id).update(is_active=False)
            return active_config

        latest = base_qs.order_by("-updated_at", "-created_at", "-id").first()
        if latest:
            latest.is_active = True
            latest.save(using=tenant_db, update_fields=["is_active", "updated_at"])
            return latest

        return queryset.create(institution=institution, is_active=True)


def build_reference_preview(config, reference_type, branch_code=None):
    reference_type = (reference_type or "").strip().lower()
    if reference_type == "batch":
        fmt = config.batch_reference_format
    elif reference_type == "trx":
        fmt = config.transaction_reference_format
    elif reference_type == "cash":
        fmt = config.cash_voucher_format
    else:
        raise ValueError("Invalid reference type.")

    now = timezone.now()
    replacements = {
        "{YYYY}": now.strftime("%Y"),
        "{MM}": now.strftime("%m"),
        "{SEQ}": "0001",
        "{BRANCH}": branch_code or "MAIN",
    }
    preview = fmt
    for key, value in replacements.items():
        preview = preview.replace(key, value)
    return preview


def _decimal_amount(value):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        raise ValidationError("Amount must be a valid number.")


def ensure_payment_method_allowed(config, method):
    method = (method or "").upper()
    if method == TreasuryConfiguration.PAYMENT_METHOD_BANK_TRANSFER and not config.enable_bank_accounts:
        raise ValidationError("Bank transfer payments are disabled in treasury configuration.")
    if method == TreasuryConfiguration.PAYMENT_METHOD_CASH and not config.enable_cash_desks:
        raise ValidationError("Cash desk payments are disabled in treasury configuration.")
    if method == TreasuryConfiguration.PAYMENT_METHOD_MOBILE_MONEY and not config.enable_mobile_money:
        raise ValidationError("Mobile money payments are disabled in treasury configuration.")
    if method == TreasuryConfiguration.PAYMENT_METHOD_CHEQUE and not config.enable_cheques:
        raise ValidationError("Cheque payments are disabled in treasury configuration.")


def resolve_default_payment_method(config, payee_type):
    if payee_type == PaymentLine.PAYEE_EMPLOYEE:
        return config.default_salary_payment_method
    if payee_type == PaymentLine.PAYEE_VENDOR:
        return config.default_vendor_payment_method
    return config.default_expense_payment_method


def apply_batch_approval_rules(batch, config):
    if not isinstance(batch, PaymentBatch):
        raise ValueError("batch must be a PaymentBatch instance.")
    if config.batch_approval_required and batch.total_amount >= config.batch_approval_threshold_amount:
        batch.status = PaymentBatch.STATUS_APPROVAL_PENDING
    else:
        batch.status = PaymentBatch.STATUS_APPROVED
    return batch.status


def apply_line_approval_rules(line, config):
    if not isinstance(line, PaymentLine):
        raise ValueError("line must be a PaymentLine instance.")
    requires_approval = False
    if config.line_approval_required and line.amount >= config.line_approval_threshold_amount:
        requires_approval = True
    line.requires_approval = requires_approval
    if requires_approval:
        line.approved = False
    return requires_approval


def ensure_open_cashdesk_session(config, cashdesk):
    if not isinstance(cashdesk, CashDesk):
        raise ValueError("cashdesk must be a CashDesk instance.")
    session = cashdesk.sessions.filter(status=CashDeskSession.STATUS_OPEN).first()
    if config.require_open_session and not session:
        raise ValidationError("An open cash desk session is required for this operation.")
    return session


def validate_cashdesk_balance_change(config, cashdesk, delta, notes=""):
    if not isinstance(cashdesk, CashDesk):
        raise ValueError("cashdesk must be a CashDesk instance.")
    delta_value = _decimal_amount(delta)
    new_balance = cashdesk.current_balance + delta_value
    if not config.allow_negative_cash_balance and new_balance < 0:
        raise ValidationError("Insufficient cash desk balance.")
    if config.max_cash_desk_balance and new_balance > config.max_cash_desk_balance:
        raise ValidationError("Cash desk balance exceeds configured maximum.")
    if delta_value < 0 and config.cash_out_requires_reason and not notes:
        raise ValidationError("Cash-out operations require a reason.")
    return new_balance


def resolve_cash_out_approval_required(config, amount):
    amount_value = _decimal_amount(amount)
    return amount_value >= config.cash_out_approval_threshold


def resolve_batch_approval_required(config, total_amount):
    if not config.batch_approval_required:
        return False
    amount_value = _decimal_amount(total_amount)
    return amount_value >= config.batch_approval_threshold_amount


def resolve_line_approval_required(config, amount):
    if not config.line_approval_required:
        return False
    amount_value = _decimal_amount(amount)
    return amount_value >= config.line_approval_threshold_amount


def ensure_beneficiary_details(config, payment_method, has_details):
    if (
        config.require_beneficiary_details_for_non_cash
        and payment_method != TreasuryConfiguration.PAYMENT_METHOD_CASH
        and not has_details
    ):
        raise ValidationError("Beneficiary details are required for non-cash payments.")


def ensure_execution_proof(config, proof_reference):
    if config.execution_proof_required and not proof_reference:
        raise ValidationError("Execution proof is required by treasury configuration.")


def enforce_edit_after_approval(config, batch):
    if batch.status in (
        PaymentBatch.STATUS_APPROVED,
        PaymentBatch.STATUS_EXECUTED,
        PaymentBatch.STATUS_RECONCILED,
    ) and not config.allow_edit_after_approval:
        raise ValidationError("Edits are disabled after batch approval.")


def enforce_batch_cancellation(config, batch):
    if config.cancellation_requires_approval and batch.status == PaymentBatch.STATUS_APPROVAL_PENDING:
        raise ValidationError("Cancellation requires approval for this batch.")


def enforce_reconciliation_enabled(config):
    if not config.enable_reconciliation:
        raise ValidationError("Reconciliation is disabled in treasury configuration.")


def create_treasury_transaction(
    *,
    tenant_db=None,
    employer_id,
    source_type,
    source_id,
    direction,
    category,
    amount,
    currency,
    created_by_id=None,
    reference=None,
    counterparty_name="",
    status=TreasuryTransaction.STATUS_POSTED,
    linked_object_type=TreasuryTransaction.LINKED_OBJECT_CHOICES[-1][0],
    linked_object_id=None,
    cashdesk_session=None,
    notes="",
):
    amount_value = _decimal_amount(amount)
    if reference is None:
        reference = uuid.uuid4().hex
    queryset = TreasuryTransaction.objects
    if tenant_db:
        queryset = queryset.using(tenant_db)
    return queryset.create(
        employer_id=employer_id,
        source_type=source_type,
        source_id=source_id,
        direction=direction,
        category=category,
        amount=amount_value,
        currency=currency,
        transaction_date=timezone.now(),
        reference=reference,
        counterparty_name=counterparty_name,
        status=status,
        created_by_id=created_by_id,
        linked_object_type=linked_object_type,
        linked_object_id=linked_object_id,
        cashdesk_session=cashdesk_session,
        notes=notes,
    )


def adjust_bank_balance(bank_account, delta):
    if not isinstance(bank_account, BankAccount):
        raise ValueError("bank_account must be a BankAccount instance.")
    delta_value = _decimal_amount(delta)
    bank_account.current_balance = bank_account.current_balance + delta_value
    bank_account.save(update_fields=["current_balance"])


def adjust_cashdesk_balance(cashdesk, delta, config, notes=""):
    new_balance = validate_cashdesk_balance_change(config, cashdesk, delta, notes=notes)
    cashdesk.current_balance = new_balance
    cashdesk.save(update_fields=["current_balance"])
