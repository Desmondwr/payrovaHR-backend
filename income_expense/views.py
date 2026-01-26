from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from accounts.database_utils import get_tenant_database_alias
from accounts.notifications import create_notification
from accounts.permissions import IsAuthenticated, IsEmployer
from accounts.utils import api_response
from accounts.models import EmployerProfile, User

from .models import (
    BudgetLine,
    BudgetPlan,
    ExpenseCategory,
    ExpenseClaim,
    IncomeCategory,
    IncomeExpenseConfiguration,
    IncomeRecord,
)
from .serializers import (
    BudgetLineSerializer,
    BudgetOverrideSerializer,
    BudgetPlanSerializer,
    ExpenseCategorySerializer,
    ExpenseClaimSerializer,
    ExpenseMarkPaidSerializer,
    ExpenseRejectSerializer,
    IncomeCategorySerializer,
    IncomeExpenseConfigurationSerializer,
    IncomeMarkReceivedSerializer,
    IncomeRecordSerializer,
    TreasuryPaymentUpdateSerializer,
)
from .services import (
    apply_budget_consumption,
    apply_budget_reservation,
    check_budget,
    ensure_income_expense_configuration,
    enforce_edit_after_approval,
    push_expense_to_treasury,
    release_budget_reservation,
    resolve_expense_approval_required,
    resolve_expense_scope,
    resolve_income_approval_required,
    resolve_income_scope,
    resolve_institution,
    validate_expense_submission,
    validate_income_submission,
)


class IncomeExpenseConfigurationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        institution = resolve_institution(request)
        tenant_db = get_tenant_database_alias(institution)
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        serializer = IncomeExpenseConfigurationSerializer(config)
        return api_response(success=True, message="Income/Expense config retrieved.", data=serializer.data)

    def put(self, request):
        if not hasattr(request.user, "employer_profile"):
            return api_response(
                success=False,
                message="Only employers can update configurations.",
                status=status.HTTP_403_FORBIDDEN,
            )

        institution = resolve_institution(request)
        tenant_db = get_tenant_database_alias(institution)
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        serializer = IncomeExpenseConfigurationSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(success=True, message="Income/Expense config updated.", data=serializer.data)


class IncomeExpenseTenantViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        institution, tenant_db = self._resolve_institution()
        context["tenant_db"] = tenant_db
        context["institution_id"] = institution.id if institution else None
        return context

    def _resolve_institution(self):
        if hasattr(self.request.user, "employer_profile"):
            institution = self.request.user.employer_profile
            return institution, get_tenant_database_alias(institution)
        employee = getattr(self.request.user, "employee_profile", None)
        if employee and getattr(employee, "employer_id", None):
            institution = EmployerProfile.objects.filter(id=employee.employer_id).first()
            if institution:
                return institution, get_tenant_database_alias(institution)
        return None, None

    def _require_institution(self):
        institution, tenant_db = self._resolve_institution()
        if not institution:
            raise PermissionDenied("Institution context required.")
        return institution, tenant_db


class SoftDeleteMixin:
    def perform_destroy(self, instance):
        if hasattr(instance, "is_deleted"):
            instance.is_deleted = True
            instance.deleted_at = timezone.now()
            instance.deleted_by_id = getattr(self.request.user, "id", None)
            instance.save(update_fields=["is_deleted", "deleted_at", "deleted_by_id", "updated_at"])
        else:
            instance.delete()


class ExpenseCategoryViewSet(SoftDeleteMixin, IncomeExpenseTenantViewSet):
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = ExpenseCategorySerializer

    def get_queryset(self):
        institution, tenant_db = self._resolve_institution()
        if not institution:
            return ExpenseCategory.objects.none()
        return ExpenseCategory.objects.using(tenant_db).filter(
            institution_id=institution.id,
            is_deleted=False,
        )

    def perform_create(self, serializer):
        institution, _ = self._require_institution()
        serializer.save(
            institution_id=institution.id,
            created_by_id=self.request.user.id,
        )


class IncomeCategoryViewSet(SoftDeleteMixin, IncomeExpenseTenantViewSet):
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = IncomeCategorySerializer

    def get_queryset(self):
        institution, tenant_db = self._resolve_institution()
        if not institution:
            return IncomeCategory.objects.none()
        return IncomeCategory.objects.using(tenant_db).filter(
            institution_id=institution.id,
            is_deleted=False,
        )

    def perform_create(self, serializer):
        institution, _ = self._require_institution()
        serializer.save(
            institution_id=institution.id,
            created_by_id=self.request.user.id,
        )


class BudgetPlanViewSet(SoftDeleteMixin, IncomeExpenseTenantViewSet):
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = BudgetPlanSerializer

    def get_queryset(self):
        institution, tenant_db = self._resolve_institution()
        if not institution:
            return BudgetPlan.objects.none()
        return BudgetPlan.objects.using(tenant_db).filter(
            institution_id=institution.id,
            is_deleted=False,
        )

    def perform_create(self, serializer):
        institution, tenant_db = self._require_institution()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        if not config.enable_budgets:
            raise ValidationError("Budgets are disabled in configuration.")
        periodicity = serializer.validated_data.get("periodicity") or config.budget_periodicity
        serializer.save(
            institution_id=institution.id,
            created_by_id=self.request.user.id,
            periodicity=periodicity,
        )

    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        plan = self.get_object()
        lines = plan.lines.filter(is_deleted=False)
        totals = lines.values("currency").annotate(
            allocated=Sum("allocated_amount"),
            consumed=Sum("consumed_amount"),
            reserved=Sum("reserved_amount"),
        )
        data = []
        for entry in totals:
            allocated = entry["allocated"] or 0
            consumed = entry["consumed"] or 0
            reserved = entry["reserved"] or 0
            data.append(
                {
                    "currency": entry["currency"],
                    "allocated_total": allocated,
                    "consumed_total": consumed,
                    "reserved_total": reserved,
                    "remaining_total": allocated - consumed - reserved,
                }
            )

        return api_response(
            success=True,
            message="Budget summary retrieved.",
            data={"budget_id": str(plan.id), "by_currency": data},
        )

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        institution, tenant_db = self._require_institution()
        plan = self.get_object()
        if plan.status == BudgetPlan.STATUS_ACTIVE:
            return api_response(success=True, message="Budget plan already active.", data=BudgetPlanSerializer(plan).data)

        lines = plan.lines.filter(is_deleted=False)
        if not lines.exists():
            raise ValidationError("Budget plan must have at least one line before activation.")

        conflict_qs = BudgetPlan.objects.using(tenant_db).filter(
            institution_id=institution.id,
            status=BudgetPlan.STATUS_ACTIVE,
            periodicity=plan.periodicity,
            start_date__lte=plan.end_date,
            end_date__gte=plan.start_date,
        ).exclude(id=plan.id)

        for line in lines:
            line_conflict = BudgetLine.objects.using(tenant_db).filter(
                budget_plan__in=conflict_qs,
                scope_type=line.scope_type,
                scope_id=line.scope_id,
                category_type=line.category_type,
                expense_category_id=line.expense_category_id,
                income_category_id=line.income_category_id,
                currency=line.currency,
                is_deleted=False,
            ).exists()
            if line_conflict:
                raise ValidationError("An active budget already exists for this scope and category.")

        plan.status = BudgetPlan.STATUS_ACTIVE
        plan.approved_by_id = request.user.id
        plan.save(update_fields=["status", "approved_by_id", "updated_at"])
        return api_response(success=True, message="Budget plan activated.", data=BudgetPlanSerializer(plan).data)


class BudgetLineViewSet(SoftDeleteMixin, IncomeExpenseTenantViewSet):
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = BudgetLineSerializer

    def get_queryset(self):
        institution, tenant_db = self._resolve_institution()
        if not institution:
            return BudgetLine.objects.none()
        return BudgetLine.objects.using(tenant_db).filter(
            budget_plan__institution_id=institution.id,
            is_deleted=False,
        )

    def perform_create(self, serializer):
        institution, tenant_db = self._require_institution()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        if not config.enable_budgets:
            raise ValidationError("Budgets are disabled in configuration.")
        scope_type = serializer.validated_data.get("scope_type")
        if config.budget_scope == IncomeExpenseConfiguration.SCOPE_COMPANY and scope_type != IncomeExpenseConfiguration.SCOPE_COMPANY:
            raise ValidationError("Budget scope must be COMPANY.")
        if config.budget_scope == IncomeExpenseConfiguration.SCOPE_BRANCH and scope_type != IncomeExpenseConfiguration.SCOPE_BRANCH:
            raise ValidationError("Budget scope must be BRANCH.")
        if config.budget_scope == IncomeExpenseConfiguration.SCOPE_DEPARTMENT and scope_type != IncomeExpenseConfiguration.SCOPE_DEPARTMENT:
            raise ValidationError("Budget scope must be DEPARTMENT.")
        serializer.save(created_by_id=self.request.user.id)


class ExpenseClaimViewSet(SoftDeleteMixin, IncomeExpenseTenantViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExpenseClaimSerializer

    def get_queryset(self):
        institution, tenant_db = self._resolve_institution()
        if not institution:
            return ExpenseClaim.objects.none()

        qs = ExpenseClaim.objects.using(tenant_db).filter(
            institution_id=institution.id,
            is_deleted=False,
        )

        if hasattr(self.request.user, "employee_profile") and self.request.user.employee_profile:
            qs = qs.filter(employee=self.request.user.employee_profile)

        status_param = self.request.query_params.get("status")
        employee_id = self.request.query_params.get("employee_id")
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")

        if status_param:
            qs = qs.filter(status=status_param)
        if employee_id and hasattr(self.request.user, "employer_profile"):
            qs = qs.filter(employee_id=employee_id)
        if date_from:
            qs = qs.filter(expense_date__gte=date_from)
        if date_to:
            qs = qs.filter(expense_date__lte=date_to)

        return qs

    def perform_create(self, serializer):
        institution, tenant_db = self._require_institution()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        if not config.enable_expenses:
            raise ValidationError("Expenses are disabled in configuration.")

        employee = getattr(self.request.user, "employee_profile", None)
        if employee and not hasattr(self.request.user, "employer_profile"):
            draft = serializer.save(
                institution_id=institution.id,
                employee=employee,
                created_by_id=self.request.user.id,
                currency=serializer.validated_data.get("currency") or config.default_currency,
                status=ExpenseClaim.STATUS_DRAFT,
            )
            validate_expense_submission(draft, config)
            draft.save()
            return

        if hasattr(self.request.user, "employer_profile"):
            if not serializer.validated_data.get("employee"):
                raise ValidationError("Employee is required for employer-created expense claims.")
            draft = serializer.save(
                institution_id=institution.id,
                created_by_id=self.request.user.id,
                currency=serializer.validated_data.get("currency") or config.default_currency,
                status=ExpenseClaim.STATUS_DRAFT,
            )
            validate_expense_submission(draft, config)
            draft.save()
            return

        raise PermissionDenied("Only employees or employers can create expenses.")

    def perform_update(self, serializer):
        institution, tenant_db = self._require_institution()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        enforce_edit_after_approval(config, serializer.instance)
        serializer.save()

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        institution, tenant_db = self._require_institution()
        expense = self.get_object()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)

        if expense.status not in [ExpenseClaim.STATUS_DRAFT, ExpenseClaim.STATUS_REJECTED]:
            raise ValidationError("Expense cannot be submitted from current status.")
        if hasattr(request.user, "employee_profile") and expense.employee_id != request.user.employee_profile.id:
            raise PermissionDenied("You can only submit your own expense.")

        validate_expense_submission(expense, config)
        approval_required = resolve_expense_approval_required(config, expense.amount)

        budget_result = None
        check_budget_now = (
            config.enable_budgets
            and expense.expense_category_id
            and (config.budget_enforce_on_submit or (not approval_required and config.budget_enforce_on_approval))
        )
        if check_budget_now:
            scope_type, scope_id = resolve_expense_scope(expense, config)
            budget_result = check_budget(
                tenant_db=tenant_db,
                institution_id=expense.institution_id,
                category_type=BudgetLine.CATEGORY_EXPENSE,
                category_id=expense.expense_category_id,
                scope_type=scope_type,
                scope_id=scope_id,
                amount=expense.amount,
                effective_date=expense.expense_date,
                config=config,
            )

        override_reason = ""
        override_applied = False
        if budget_result and budget_result["decision"] == "BLOCK":
            if not config.budget_allow_override:
                raise ValidationError("Budget exceeded and overrides are disabled.")
            override_serializer = BudgetOverrideSerializer(data=request.data)
            override_serializer.is_valid(raise_exception=True)
            override_reason = override_serializer.validated_data.get("budget_override_reason", "")
            if config.budget_override_requires_reason and not override_reason:
                raise ValidationError("Budget override reason is required.")
            override_applied = True

        with transaction.atomic(using=tenant_db):
            if budget_result and budget_result.get("line"):
                expense.budget_line = budget_result["line"]

            if override_applied:
                expense.budget_override_used = True
                expense.budget_override_reason = override_reason

            if config.budget_enforce_on_submit and budget_result and budget_result.get("line"):
                apply_budget_reservation(budget_result["line"], expense.amount)

            if approval_required:
                expense.mark_approval_pending()
            else:
                expense.mark_approved()
                if hasattr(request.user, "employer_profile") or config.expense_allow_self_approval:
                    expense.approved_by_id = request.user.id

            expense.submitted_at = expense.submitted_at or timezone.now()
            expense.save()

            if expense.status == ExpenseClaim.STATUS_APPROVED:
                if config.budget_enforce_on_approval and expense.budget_line:
                    apply_budget_consumption(
                        expense.budget_line,
                        expense.amount,
                        reduce_reserved=config.budget_enforce_on_submit,
                    )
                payment_line_id = push_expense_to_treasury(
                    expense,
                    tenant_db=tenant_db,
                    config=config,
                    created_by_id=request.user.id,
                )
                if payment_line_id:
                    expense.treasury_payment_line_id = payment_line_id
                    expense.save(update_fields=["treasury_payment_line_id", "updated_at"])

        self._notify_expense_submitted(expense, institution)
        payload = ExpenseClaimSerializer(expense).data
        if budget_result and budget_result["decision"] in ["WARN", "BLOCK"]:
            payload["budget_warning"] = "Budget exceeded for this expense."
            payload["budget_remaining"] = budget_result.get("remaining")
        return api_response(success=True, message="Expense submitted.", data=payload)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        if not (hasattr(request.user, "employer_profile") or request.user.is_admin):
            raise PermissionDenied("Only employer/admin users can approve expenses.")

        institution, tenant_db = self._require_institution()
        expense = self.get_object()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)

        if expense.status == ExpenseClaim.STATUS_APPROVED:
            return api_response(success=True, message="Expense already approved.", data=ExpenseClaimSerializer(expense).data)
        if expense.status not in [ExpenseClaim.STATUS_APPROVAL_PENDING]:
            raise ValidationError("Expense cannot be approved from current status.")
        if not config.expense_allow_self_approval and expense.created_by_id == request.user.id:
            raise ValidationError("Self-approval is disabled for expenses.")

        budget_result = None
        if config.enable_budgets and config.budget_enforce_on_approval and expense.expense_category_id:
            scope_type, scope_id = resolve_expense_scope(expense, config)
            budget_result = check_budget(
                tenant_db=tenant_db,
                institution_id=expense.institution_id,
                category_type=BudgetLine.CATEGORY_EXPENSE,
                category_id=expense.expense_category_id,
                scope_type=scope_type,
                scope_id=scope_id,
                amount=expense.amount,
                effective_date=expense.expense_date,
                config=config,
            )

        override_reason = ""
        override_applied = False
        if budget_result and budget_result["decision"] == "BLOCK":
            if not config.budget_allow_override:
                raise ValidationError("Budget exceeded and overrides are disabled.")
            override_serializer = BudgetOverrideSerializer(data=request.data)
            override_serializer.is_valid(raise_exception=True)
            override_reason = override_serializer.validated_data.get("budget_override_reason", "")
            if config.budget_override_requires_reason and not override_reason:
                raise ValidationError("Budget override reason is required.")
            override_applied = True

        with transaction.atomic(using=tenant_db):
            if budget_result and budget_result.get("line"):
                expense.budget_line = budget_result["line"]

            if override_applied:
                expense.budget_override_used = True
                expense.budget_override_reason = override_reason

            if config.budget_enforce_on_approval and expense.budget_line:
                apply_budget_consumption(
                    expense.budget_line,
                    expense.amount,
                    reduce_reserved=config.budget_enforce_on_submit,
                )

            expense.mark_approved()
            expense.approved_by_id = request.user.id
            expense.save()

            payment_line_id = push_expense_to_treasury(
                expense,
                tenant_db=tenant_db,
                config=config,
                created_by_id=request.user.id,
            )
            if payment_line_id:
                expense.treasury_payment_line_id = payment_line_id
                expense.save(update_fields=["treasury_payment_line_id", "updated_at"])

        self._notify_expense_approved(expense, institution)
        payload = ExpenseClaimSerializer(expense).data
        if budget_result and budget_result["decision"] in ["WARN", "BLOCK"]:
            payload["budget_warning"] = "Budget exceeded for this expense."
            payload["budget_remaining"] = budget_result.get("remaining")
        return api_response(success=True, message="Expense approved.", data=payload)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        if not (hasattr(request.user, "employer_profile") or request.user.is_admin):
            raise PermissionDenied("Only employer/admin users can reject expenses.")

        institution, tenant_db = self._require_institution()
        expense = self.get_object()
        if expense.status not in [ExpenseClaim.STATUS_APPROVAL_PENDING]:
            raise ValidationError("Expense cannot be rejected from current status.")
        serializer = ExpenseRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("rejected_reason", "")
        if not reason:
            raise ValidationError("rejected_reason is required.")

        with transaction.atomic(using=tenant_db):
            if expense.budget_line and expense.status == ExpenseClaim.STATUS_APPROVAL_PENDING:
                release_budget_reservation(expense.budget_line, expense.amount)
            expense.mark_rejected(reason)
            expense.save()

        self._notify_expense_rejected(expense, institution)
        return api_response(success=True, message="Expense rejected.", data=ExpenseClaimSerializer(expense).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        institution, tenant_db = self._require_institution()
        expense = self.get_object()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)

        if expense.status not in [ExpenseClaim.STATUS_DRAFT, ExpenseClaim.STATUS_APPROVAL_PENDING, ExpenseClaim.STATUS_APPROVED]:
            raise ValidationError("Expense cannot be cancelled from current status.")
        if (
            config.expense_cancel_requires_approval
            and expense.status in [ExpenseClaim.STATUS_APPROVAL_PENDING, ExpenseClaim.STATUS_APPROVED]
            and not hasattr(request.user, "employer_profile")
        ):
            raise ValidationError("Cancellation requires approval for this expense.")
        if expense.status == ExpenseClaim.STATUS_APPROVED:
            if not config.expense_allow_edit_after_approval:
                raise ValidationError("Approved expenses cannot be cancelled.")
            if expense.treasury_payment_line_id:
                raise ValidationError("Approved expenses pushed to treasury cannot be cancelled.")

        with transaction.atomic(using=tenant_db):
            if expense.budget_line and config.budget_enforce_on_submit and expense.status == ExpenseClaim.STATUS_APPROVAL_PENDING:
                release_budget_reservation(expense.budget_line, expense.amount)
            expense.mark_cancelled()
            expense.save()

        self._notify_expense_cancelled(expense, institution)
        return api_response(success=True, message="Expense cancelled.", data=ExpenseClaimSerializer(expense).data)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        if not (hasattr(request.user, "employer_profile") or request.user.is_admin):
            raise PermissionDenied("Only employer/admin users can mark paid.")

        institution, tenant_db = self._require_institution()
        expense = self.get_object()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        if not config.auto_mark_paid_from_treasury:
            raise ValidationError("Auto-mark paid is disabled in configuration.")
        if expense.status not in [ExpenseClaim.STATUS_APPROVED, ExpenseClaim.STATUS_PAID]:
            raise ValidationError("Expense cannot be marked paid from current status.")

        serializer = ExpenseMarkPaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        paid_at = serializer.validated_data.get("paid_at")
        treasury_payment_line_id = serializer.validated_data.get("treasury_payment_line_id")

        expense.mark_paid(paid_at=paid_at)
        if treasury_payment_line_id:
            expense.treasury_payment_line_id = treasury_payment_line_id
        expense.save()

        self._notify_expense_paid(expense, institution)
        return api_response(success=True, message="Expense marked paid.", data=ExpenseClaimSerializer(expense).data)

    def _notify_expense_submitted(self, expense, institution):
        employee_user = None
        if expense.employee and expense.employee.user_id:
            employee_user = User.objects.filter(id=expense.employee.user_id).first()

        if employee_user:
            create_notification(
                user=employee_user,
                title="Expense submitted",
                body=f"Expense {expense.title} submitted.",
                type="INFO",
                employer_profile=institution,
                data={"expense_id": str(expense.id), "status": expense.status},
            )

        if institution and institution.user:
            create_notification(
                user=institution.user,
                title="New expense submitted",
                body=f"Expense {expense.title} submitted for approval.",
                type="ACTION",
                employer_profile=institution,
                data={"expense_id": str(expense.id), "status": expense.status},
            )

    def _notify_expense_approved(self, expense, institution):
        if expense.employee and expense.employee.user_id:
            employee_user = User.objects.filter(id=expense.employee.user_id).first()
            if employee_user:
                create_notification(
                    user=employee_user,
                    title="Expense approved",
                    body=f"Expense {expense.title} approved.",
                    type="INFO",
                    employer_profile=institution,
                    data={"expense_id": str(expense.id), "status": expense.status},
                )

    def _notify_expense_rejected(self, expense, institution):
        if expense.employee and expense.employee.user_id:
            employee_user = User.objects.filter(id=expense.employee.user_id).first()
            if employee_user:
                create_notification(
                    user=employee_user,
                    title="Expense rejected",
                    body=f"Expense {expense.title} rejected.",
                    type="ALERT",
                    employer_profile=institution,
                    data={"expense_id": str(expense.id), "status": expense.status},
                )

    def _notify_expense_cancelled(self, expense, institution):
        if expense.employee and expense.employee.user_id:
            employee_user = User.objects.filter(id=expense.employee.user_id).first()
            if employee_user:
                create_notification(
                    user=employee_user,
                    title="Expense cancelled",
                    body=f"Expense {expense.title} cancelled.",
                    type="ALERT",
                    employer_profile=institution,
                    data={"expense_id": str(expense.id), "status": expense.status},
                )

    def _notify_expense_paid(self, expense, institution):
        if expense.employee and expense.employee.user_id:
            employee_user = User.objects.filter(id=expense.employee.user_id).first()
            if employee_user:
                create_notification(
                    user=employee_user,
                    title="Expense paid",
                    body=f"Expense {expense.title} marked as paid.",
                    type="INFO",
                    employer_profile=institution,
                    data={"expense_id": str(expense.id), "status": expense.status},
                )


class IncomeRecordViewSet(SoftDeleteMixin, IncomeExpenseTenantViewSet):
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = IncomeRecordSerializer

    def get_queryset(self):
        institution, tenant_db = self._resolve_institution()
        if not institution:
            return IncomeRecord.objects.none()

        qs = IncomeRecord.objects.using(tenant_db).filter(
            institution_id=institution.id,
            is_deleted=False,
        )

        status_param = self.request.query_params.get("status")
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")

        if status_param:
            qs = qs.filter(status=status_param)
        if date_from:
            qs = qs.filter(income_date__gte=date_from)
        if date_to:
            qs = qs.filter(income_date__lte=date_to)

        return qs

    def perform_create(self, serializer):
        institution, tenant_db = self._require_institution()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        if not config.enable_income:
            raise ValidationError("Income records are disabled in configuration.")
        if not config.income_allow_manual_entry:
            raise ValidationError("Manual income entry is disabled in configuration.")

        draft = serializer.save(
            institution_id=institution.id,
            created_by_id=self.request.user.id,
            currency=serializer.validated_data.get("currency") or config.default_currency,
            status=IncomeRecord.STATUS_DRAFT,
        )
        validate_income_submission(draft, config)
        draft.save()

    def perform_update(self, serializer):
        institution, tenant_db = self._require_institution()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        enforce_edit_after_approval(config, serializer.instance)
        serializer.save()

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        institution, tenant_db = self._require_institution()
        income = self.get_object()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)

        if income.status not in [IncomeRecord.STATUS_DRAFT, IncomeRecord.STATUS_REJECTED]:
            raise ValidationError("Income cannot be submitted from current status.")

        validate_income_submission(income, config)
        approval_required = resolve_income_approval_required(config, income.amount)

        budget_result = None
        check_budget_now = (
            config.enable_budgets
            and income.income_category_id
            and (config.budget_enforce_on_submit or (not approval_required and config.budget_enforce_on_approval))
        )
        if check_budget_now:
            scope_type, scope_id = resolve_income_scope(income, config)
            budget_result = check_budget(
                tenant_db=tenant_db,
                institution_id=income.institution_id,
                category_type=BudgetLine.CATEGORY_INCOME,
                category_id=income.income_category_id,
                scope_type=scope_type,
                scope_id=scope_id,
                amount=income.amount,
                effective_date=income.income_date,
                config=config,
            )

        override_reason = ""
        override_applied = False
        if budget_result and budget_result["decision"] == "BLOCK":
            if not config.budget_allow_override:
                raise ValidationError("Budget exceeded and overrides are disabled.")
            override_serializer = BudgetOverrideSerializer(data=request.data)
            override_serializer.is_valid(raise_exception=True)
            override_reason = override_serializer.validated_data.get("budget_override_reason", "")
            if config.budget_override_requires_reason and not override_reason:
                raise ValidationError("Budget override reason is required.")
            override_applied = True

        with transaction.atomic(using=tenant_db):
            if budget_result and budget_result.get("line"):
                income.budget_line = budget_result["line"]

            if override_applied:
                income.budget_override_used = True
                income.budget_override_reason = override_reason

            if config.budget_enforce_on_submit and budget_result and budget_result.get("line"):
                apply_budget_reservation(budget_result["line"], income.amount)

            if approval_required:
                income.mark_submitted()
            else:
                income.mark_approved()
                income.approved_by_id = request.user.id

            income.submitted_at = income.submitted_at or timezone.now()
            income.save()

            if income.status == IncomeRecord.STATUS_APPROVED:
                if config.budget_enforce_on_approval and income.budget_line:
                    apply_budget_consumption(
                        income.budget_line,
                        income.amount,
                        reduce_reserved=config.budget_enforce_on_submit,
                    )

        create_notification(
            user=request.user,
            title="Income submitted",
            body=f"Income {income.title} submitted.",
            type="INFO",
            employer_profile=institution,
            data={"income_id": str(income.id), "status": income.status},
        )

        payload = IncomeRecordSerializer(income).data
        if budget_result and budget_result["decision"] in ["WARN", "BLOCK"]:
            payload["budget_warning"] = "Budget exceeded for this income."
            payload["budget_remaining"] = budget_result.get("remaining")
        return api_response(success=True, message="Income submitted.", data=payload)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        institution, tenant_db = self._require_institution()
        income = self.get_object()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)

        if income.status == IncomeRecord.STATUS_APPROVED:
            return api_response(success=True, message="Income already approved.", data=IncomeRecordSerializer(income).data)
        if income.status not in [IncomeRecord.STATUS_APPROVAL_PENDING]:
            raise ValidationError("Income cannot be approved from current status.")

        budget_result = None
        if config.enable_budgets and config.budget_enforce_on_approval and income.income_category_id:
            scope_type, scope_id = resolve_income_scope(income, config)
            budget_result = check_budget(
                tenant_db=tenant_db,
                institution_id=income.institution_id,
                category_type=BudgetLine.CATEGORY_INCOME,
                category_id=income.income_category_id,
                scope_type=scope_type,
                scope_id=scope_id,
                amount=income.amount,
                effective_date=income.income_date,
                config=config,
            )

        override_reason = ""
        override_applied = False
        if budget_result and budget_result["decision"] == "BLOCK":
            if not config.budget_allow_override:
                raise ValidationError("Budget exceeded and overrides are disabled.")
            override_serializer = BudgetOverrideSerializer(data=request.data)
            override_serializer.is_valid(raise_exception=True)
            override_reason = override_serializer.validated_data.get("budget_override_reason", "")
            if config.budget_override_requires_reason and not override_reason:
                raise ValidationError("Budget override reason is required.")
            override_applied = True

        with transaction.atomic(using=tenant_db):
            if budget_result and budget_result.get("line"):
                income.budget_line = budget_result["line"]

            if override_applied:
                income.budget_override_used = True
                income.budget_override_reason = override_reason

            if config.budget_enforce_on_approval and income.budget_line:
                apply_budget_consumption(
                    income.budget_line,
                    income.amount,
                    reduce_reserved=config.budget_enforce_on_submit,
                )

            income.mark_approved()
            income.approved_by_id = request.user.id
            income.save()

        create_notification(
            user=request.user,
            title="Income approved",
            body=f"Income {income.title} approved.",
            type="INFO",
            employer_profile=institution,
            data={"income_id": str(income.id), "status": income.status},
        )

        payload = IncomeRecordSerializer(income).data
        if budget_result and budget_result["decision"] in ["WARN", "BLOCK"]:
            payload["budget_warning"] = "Budget exceeded for this income."
            payload["budget_remaining"] = budget_result.get("remaining")
        return api_response(success=True, message="Income approved.", data=payload)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        institution, tenant_db = self._require_institution()
        income = self.get_object()
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        if income.status not in [IncomeRecord.STATUS_APPROVAL_PENDING]:
            raise ValidationError("Income cannot be rejected from current status.")
        serializer = ExpenseRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("rejected_reason", "")
        if not reason:
            raise ValidationError("rejected_reason is required.")

        with transaction.atomic(using=tenant_db):
            if income.budget_line and config.budget_enforce_on_submit:
                release_budget_reservation(income.budget_line, income.amount)
            income.mark_rejected(reason)
            income.save()

        create_notification(
            user=request.user,
            title="Income rejected",
            body=f"Income {income.title} rejected.",
            type="ALERT",
            employer_profile=institution,
            data={"income_id": str(income.id), "status": income.status},
        )

        return api_response(success=True, message="Income rejected.", data=IncomeRecordSerializer(income).data)

    @action(detail=True, methods=["post"], url_path="mark-received")
    def mark_received(self, request, pk=None):
        institution, tenant_db = self._require_institution()
        income = self.get_object()
        if income.status not in [IncomeRecord.STATUS_APPROVED, IncomeRecord.STATUS_RECEIVED]:
            raise ValidationError("Income cannot be marked received from current status.")
        serializer = IncomeMarkReceivedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        received_at = serializer.validated_data.get("received_at")
        income.mark_received(received_at=received_at)
        if serializer.validated_data.get("bank_statement_line_id"):
            income.bank_statement_line_id = serializer.validated_data.get("bank_statement_line_id")
        income.save()

        create_notification(
            user=request.user,
            title="Income received",
            body=f"Income {income.title} marked as received.",
            type="INFO",
            employer_profile=institution,
            data={"income_id": str(income.id), "status": income.status},
        )

        return api_response(success=True, message="Income marked received.", data=IncomeRecordSerializer(income).data)


class TreasuryPaymentUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        institution = resolve_institution(request)
        tenant_db = get_tenant_database_alias(institution)
        config = ensure_income_expense_configuration(institution, tenant_db=tenant_db)
        if not config.auto_mark_paid_from_treasury:
            return api_response(
                success=False,
                message="Auto-mark paid is disabled in configuration.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TreasuryPaymentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expense = get_object_or_404(
            ExpenseClaim.objects.using(tenant_db),
            id=serializer.validated_data["expense_id"],
            institution_id=institution.id,
        )

        status_value = serializer.validated_data["status"]
        paid_at = serializer.validated_data.get("paid_at")
        payment_line_id = serializer.validated_data.get("treasury_payment_line_id")
        external_reference = serializer.validated_data.get("external_reference")

        if status_value == "PAID":
            expense.mark_paid(paid_at=paid_at)
            expense.payment_failed = False
            expense.payment_failed_reason = ""
        else:
            expense.status = ExpenseClaim.STATUS_APPROVED
            expense.payment_failed = True
            expense.payment_failed_reason = "Treasury payment failed"

        if payment_line_id:
            expense.treasury_payment_line_id = payment_line_id
        if external_reference:
            expense.treasury_external_reference = external_reference
        expense.save()

        return api_response(success=True, message="Treasury update applied.", data=ExpenseClaimSerializer(expense).data)
