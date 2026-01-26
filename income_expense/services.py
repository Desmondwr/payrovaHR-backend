from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import EmployerProfile

from .models import (
    BudgetLine,
    BudgetPlan,
    ExpenseClaim,
    IncomeExpenseConfiguration,
    IncomeRecord,
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


def ensure_income_expense_configuration(institution, *, tenant_db=None):
    queryset = IncomeExpenseConfiguration.objects
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


def _decimal_amount(value):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        raise ValidationError("Amount must be a valid number.")


def resolve_expense_scope(expense, config):
    if not config:
        return IncomeExpenseConfiguration.SCOPE_COMPANY, None

    scope = config.budget_scope
    if scope == IncomeExpenseConfiguration.SCOPE_COMPANY:
        return scope, None

    employee = getattr(expense, "employee", None)
    if not employee:
        return IncomeExpenseConfiguration.SCOPE_COMPANY, None

    if scope == IncomeExpenseConfiguration.SCOPE_BRANCH:
        branch = getattr(employee, "branch", None)
        return scope, getattr(branch, "id", None)

    if scope == IncomeExpenseConfiguration.SCOPE_DEPARTMENT:
        department = getattr(employee, "department", None)
        return scope, getattr(department, "id", None)

    return IncomeExpenseConfiguration.SCOPE_COMPANY, None


def resolve_income_scope(income, config):
    if not config:
        return IncomeExpenseConfiguration.SCOPE_COMPANY, None
    if config.budget_scope == IncomeExpenseConfiguration.SCOPE_COMPANY:
        return IncomeExpenseConfiguration.SCOPE_COMPANY, None
    return IncomeExpenseConfiguration.SCOPE_COMPANY, None


def check_budget(
    *,
    tenant_db,
    institution_id,
    category_type,
    category_id,
    scope_type,
    scope_id,
    amount,
    effective_date,
    config,
):
    if not config or not config.enable_budgets:
        return {
            "decision": "OK",
            "remaining": None,
            "line": None,
            "control_mode": IncomeExpenseConfiguration.BUDGET_CONTROL_OFF,
        }

    amount_value = _decimal_amount(amount)
    if config.budget_control_mode == IncomeExpenseConfiguration.BUDGET_CONTROL_OFF:
        return {
            "decision": "OK",
            "remaining": None,
            "line": None,
            "control_mode": config.budget_control_mode,
        }

    plan_qs = BudgetPlan.objects.using(tenant_db).filter(
        institution_id=institution_id,
        status=BudgetPlan.STATUS_ACTIVE,
        is_deleted=False,
    )
    if config.budget_periodicity:
        plan_qs = plan_qs.filter(periodicity=config.budget_periodicity)
    if effective_date:
        plan_qs = plan_qs.filter(start_date__lte=effective_date, end_date__gte=effective_date)

    plan = plan_qs.order_by("-start_date", "-created_at").first()
    if not plan:
        return {
            "decision": "OK",
            "remaining": None,
            "line": None,
            "control_mode": config.budget_control_mode,
        }

    line_qs = BudgetLine.objects.using(tenant_db).filter(
        budget_plan=plan,
        scope_type=scope_type,
        is_active=True,
        is_deleted=False,
    )
    if scope_type == IncomeExpenseConfiguration.SCOPE_COMPANY:
        line_qs = line_qs.filter(scope_id__isnull=True)
    else:
        line_qs = line_qs.filter(scope_id=scope_id)

    if category_type == BudgetLine.CATEGORY_EXPENSE:
        line_qs = line_qs.filter(expense_category_id=category_id)
    else:
        line_qs = line_qs.filter(income_category_id=category_id)

    line = line_qs.first()
    if not line:
        return {
            "decision": "OK",
            "remaining": None,
            "line": None,
            "control_mode": config.budget_control_mode,
        }

    remaining = line.allocated_amount - line.consumed_amount - line.reserved_amount
    if amount_value <= remaining:
        return {
            "decision": "OK",
            "remaining": remaining,
            "line": line,
            "control_mode": config.budget_control_mode,
        }

    if config.budget_control_mode == IncomeExpenseConfiguration.BUDGET_CONTROL_BLOCK:
        decision = "BLOCK"
    else:
        decision = "WARN"

    return {
        "decision": decision,
        "remaining": remaining,
        "line": line,
        "control_mode": config.budget_control_mode,
    }


def apply_budget_reservation(line, amount):
    if not isinstance(line, BudgetLine):
        raise ValueError("line must be a BudgetLine instance.")
    amount_value = _decimal_amount(amount)
    line.reserved_amount = line.reserved_amount + amount_value
    line.save(update_fields=["reserved_amount", "updated_at"])


def release_budget_reservation(line, amount):
    if not isinstance(line, BudgetLine):
        raise ValueError("line must be a BudgetLine instance.")
    amount_value = _decimal_amount(amount)
    line.reserved_amount = max(Decimal("0.00"), line.reserved_amount - amount_value)
    line.save(update_fields=["reserved_amount", "updated_at"])


def apply_budget_consumption(line, amount, *, reduce_reserved=False):
    if not isinstance(line, BudgetLine):
        raise ValueError("line must be a BudgetLine instance.")
    amount_value = _decimal_amount(amount)
    if reduce_reserved:
        line.reserved_amount = max(Decimal("0.00"), line.reserved_amount - amount_value)
    line.consumed_amount = line.consumed_amount + amount_value
    line.save(update_fields=["consumed_amount", "reserved_amount", "updated_at"])


def push_expense_to_treasury(expense, *, tenant_db, config, created_by_id=None):
    """
    Lightweight integration hook for treasury payments.

    If treasury lives in a separate service, emit an event or call its API here.
    When a payment line id is returned, set it on the expense.
    """
    if not config.push_approved_expenses_to_treasury:
        return None
    if expense.treasury_payment_line_id:
        return expense.treasury_payment_line_id

    # TODO: implement external Treasury integration.
    return None


def enforce_edit_after_approval(config, instance):
    if not config:
        return
    if not config.expense_allow_edit_after_approval and isinstance(instance, ExpenseClaim):
        if instance.status in (
            ExpenseClaim.STATUS_APPROVAL_PENDING,
            ExpenseClaim.STATUS_APPROVED,
            ExpenseClaim.STATUS_PAID,
            ExpenseClaim.STATUS_CANCELLED,
        ):
            raise ValidationError("Edits are disabled after approval.")
    if isinstance(instance, IncomeRecord) and instance.status in (
        IncomeRecord.STATUS_APPROVED,
        IncomeRecord.STATUS_RECEIVED,
        IncomeRecord.STATUS_CANCELLED,
    ):
        raise ValidationError("Edits are disabled after approval.")


def resolve_expense_approval_required(config, amount):
    if not config.expense_approval_required:
        return False
    return _decimal_amount(amount) >= config.expense_approval_threshold_amount


def resolve_income_approval_required(config, amount):
    if not config.income_approval_required:
        return False
    return _decimal_amount(amount) >= config.income_approval_threshold_amount


def validate_expense_submission(expense, config):
    if not config.enable_expenses:
        raise ValidationError("Expenses are disabled in configuration.")
    if config.expense_require_attachment and not expense.attachment:
        raise ValidationError("Attachment is required to submit an expense.")
    if config.expense_require_notes and not (expense.notes or "").strip():
        raise ValidationError("Notes are required to submit an expense.")
    if expense.expense_date:
        days_back = (timezone.now().date() - expense.expense_date).days
        if days_back > 0 and not config.expense_allow_backdate:
            raise ValidationError("Backdated expenses are not allowed.")
        if days_back > 0 and config.expense_max_backdate_days is not None:
            if days_back > config.expense_max_backdate_days:
                raise ValidationError("Backdated expenses exceed allowed days.")


def validate_income_submission(income, config):
    if not config.enable_income:
        raise ValidationError("Income records are disabled in configuration.")
    if config.income_require_attachment and not income.attachment:
        raise ValidationError("Attachment is required to submit income.")
    if config.income_require_notes and not (income.notes or "").strip():
        raise ValidationError("Notes are required to submit income.")
