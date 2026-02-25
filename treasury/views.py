
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from accounts.database_utils import get_tenant_database_alias
from accounts.notifications import create_notification
from accounts.permissions import IsAuthenticated, EmployerAccessPermission
from accounts.rbac import get_active_employer, is_delegate_user
from accounts.utils import api_response

from .models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    CashDesk,
    CashDeskSession,
    PaymentBatch,
    PaymentLine,
    ReconciliationMatch,
    TreasuryTransaction,
)
from .serializers import (
    BankAccountSerializer,
    BankAccountWithdrawSerializer,
    BankStatementImportSerializer,
    BankStatementLineSerializer,
    BankStatementSerializer,
    CashDeskOperationSerializer,
    CashDeskSessionCloseSerializer,
    CashDeskSessionOpenSerializer,
    CashDeskSerializer,
    CashDeskSessionSerializer,
    CashDeskTransferSerializer,
    PaymentBatchSerializer,
    PaymentLineSerializer,
    PaymentLineStatusUpdateSerializer,
    ReconciliationActionSerializer,
    ReconciliationMatchSerializer,
    TreasuryConfigurationSerializer,
)
from .services import (
    adjust_bank_balance,
    adjust_cashdesk_balance,
    apply_batch_approval_rules,
    apply_line_approval_rules,
    build_reference_preview,
    create_treasury_transaction,
    enforce_batch_cancellation,
    enforce_edit_after_approval,
    enforce_reconciliation_enabled,
    ensure_beneficiary_details,
    ensure_execution_proof,
    ensure_open_cashdesk_session,
    ensure_payment_method_allowed,
    ensure_treasury_configuration,
    resolve_cash_out_approval_required,
    resolve_institution,
)


def _ensure_positive_amount(amount):
    if amount is None or amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    return amount


def _update_batch_reconciliation_status(batch, tenant_db):
    line_ids = list(batch.lines.values_list("id", flat=True))
    if not line_ids:
        return
    confirmed_matches = (
        ReconciliationMatch.objects.using(tenant_db)
        .filter(
            match_type=ReconciliationMatch.MATCH_TYPE_CHOICES[0][0],
            match_id__in=line_ids,
            status=ReconciliationMatch.STATUS_CONFIRMED,
        )
        .values_list("match_id", flat=True)
        .distinct()
    )
    confirmed_set = set(confirmed_matches)
    if not confirmed_set:
        if batch.status not in [PaymentBatch.STATUS_EXECUTED, PaymentBatch.STATUS_CANCELLED]:
            return
    if len(confirmed_set) == len(line_ids):
        batch.status = PaymentBatch.STATUS_RECONCILED
    else:
        batch.status = PaymentBatch.STATUS_PARTIALLY_RECONCILED
    batch.save(update_fields=["status", "updated_at"])


class TreasuryConfigurationView(APIView):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["treasury.manage"]

    def get(self, request):
        institution = resolve_institution(request)
        tenant_db = get_tenant_database_alias(institution)
        config = ensure_treasury_configuration(institution, tenant_db=tenant_db)
        serializer = TreasuryConfigurationSerializer(config)
        return api_response(success=True, message="Treasury config retrieved.", data=serializer.data)

    def put(self, request):
        institution = resolve_institution(request)
        tenant_db = get_tenant_database_alias(institution)
        config = ensure_treasury_configuration(institution, tenant_db=tenant_db)
        serializer = TreasuryConfigurationSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(success=True, message="Treasury config updated.", data=serializer.data)


class TreasuryReferencePreviewView(APIView):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["treasury.manage"]

    def get(self, request):
        reference_type = request.query_params.get("type")
        branch_code = request.query_params.get("branch")
        if not reference_type:
            return api_response(
                success=False,
                message="Query param 'type' is required (batch, trx, cash).",
                status=status.HTTP_400_BAD_REQUEST,
            )

        institution = resolve_institution(request)
        tenant_db = get_tenant_database_alias(institution)
        config = ensure_treasury_configuration(institution, tenant_db=tenant_db)
        try:
            preview = build_reference_preview(config, reference_type, branch_code=branch_code)
        except ValueError:
            return api_response(
                success=False,
                message="type must be one of: batch, trx, cash.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        return api_response(success=True, message="Reference preview generated.", data={"reference": preview})


class TreasuryTenantViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {"*": ["treasury.manage"]}

    def get_serializer_context(self):
        context = super().get_serializer_context()
        employer, tenant_db = self._resolve_employer()
        context["tenant_db"] = tenant_db
        context["employer_id"] = employer.id if employer else None
        return context

    def _resolve_employer(self):
        user = self.request.user
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if not employer:
            return None, None
        tenant_db = get_tenant_database_alias(employer)
        return employer, tenant_db

    def _require_employer(self):
        employer, tenant_db = self._resolve_employer()
        if not employer:
            raise PermissionDenied("Employer context required.")
        return employer, tenant_db

    def _get_config(self):
        employer, tenant_db = self._resolve_employer()
        if not employer:
            return None
        return ensure_treasury_configuration(employer, tenant_db=tenant_db)


class BankAccountViewSet(TreasuryTenantViewSet):
    permission_map = {
        "list": ["treasury.account.view", "treasury.manage"],
        "retrieve": ["treasury.account.view", "treasury.manage"],
        "create": ["treasury.account.create", "treasury.manage"],
        "update": ["treasury.account.update", "treasury.manage"],
        "partial_update": ["treasury.account.update", "treasury.manage"],
        "destroy": ["treasury.account.delete", "treasury.manage"],
        "withdraw_to_cashdesk": ["treasury.account.withdraw", "treasury.manage"],
        "*": ["treasury.manage"],
    }
    serializer_class = BankAccountSerializer

    def get_queryset(self):
        employer, tenant_db = self._resolve_employer()
        if not employer:
            return BankAccount.objects.none()
        return BankAccount.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer, _ = self._require_employer()
        config = self._get_config()
        if not config.enable_bank_accounts:
            raise ValidationError("Bank accounts are disabled in treasury configuration.")
        serializer.save(employer_id=employer.id)

    @action(detail=True, methods=["post"], url_path="withdraw-to-cashdesk")
    def withdraw_to_cashdesk(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        if not config.enable_bank_accounts:
            raise ValidationError("Bank accounts are disabled in treasury configuration.")
        if not config.enable_cash_desks:
            raise ValidationError("Cash desks are disabled in treasury configuration.")

        bank_account = self.get_object()
        serializer = BankAccountWithdrawSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = _ensure_positive_amount(serializer.validated_data["amount"])
        cashdesk_id = serializer.validated_data["cashdesk_id"]
        cashdesk = CashDesk.objects.using(tenant_db).filter(id=cashdesk_id, employer_id=employer.id).first()
        if not cashdesk:
            raise ValidationError("Cash desk not found.")

        session = ensure_open_cashdesk_session(config, cashdesk)
        if bank_account.current_balance - amount < Decimal("0"):
            raise ValidationError("Insufficient bank account balance.")

        reference = serializer.validated_data.get("reference") or None
        notes = serializer.validated_data.get("notes") or ""

        with transaction.atomic(using=tenant_db):
            adjust_bank_balance(bank_account, -amount)
            adjust_cashdesk_balance(cashdesk, amount, config, notes=notes)
            create_treasury_transaction(
                tenant_db=tenant_db,
                employer_id=employer.id,
                source_type=TreasuryTransaction.SOURCE_BANK,
                source_id=bank_account.id,
                direction=TreasuryTransaction.DIRECTION_OUT,
                category="WITHDRAWAL",
                amount=amount,
                currency=bank_account.currency,
                created_by_id=request.user.id,
                reference=reference,
                counterparty_name=cashdesk.name,
                linked_object_type="MANUAL",
                notes=notes,
            )
            create_treasury_transaction(
                tenant_db=tenant_db,
                employer_id=employer.id,
                source_type=TreasuryTransaction.SOURCE_CASHDESK,
                source_id=cashdesk.id,
                direction=TreasuryTransaction.DIRECTION_IN,
                category="DEPOSIT",
                amount=amount,
                currency=cashdesk.currency,
                created_by_id=request.user.id,
                counterparty_name=bank_account.name,
                linked_object_type="MANUAL",
                cashdesk_session=session,
                notes=notes,
            )

        create_notification(
            user=request.user,
            title="Bank withdrawal to cash desk",
            body=f"{amount} {bank_account.currency} moved from {bank_account.name} to {cashdesk.name}.",
            type="ACTION",
            employer_profile=employer,
            data={"bank_account_id": str(bank_account.id), "cashdesk_id": str(cashdesk.id)},
        )

        return api_response(
            success=True,
            message="Withdrawal completed.",
            data={"bank_account_id": str(bank_account.id), "cashdesk_id": str(cashdesk.id)},
            status=status.HTTP_200_OK,
        )

class CashDeskViewSet(TreasuryTenantViewSet):
    permission_map = {
        "list": ["treasury.cashdesk.view", "treasury.manage"],
        "retrieve": ["treasury.cashdesk.view", "treasury.manage"],
        "create": ["treasury.cashdesk.create", "treasury.manage"],
        "update": ["treasury.cashdesk.update", "treasury.manage"],
        "partial_update": ["treasury.cashdesk.update", "treasury.manage"],
        "destroy": ["treasury.cashdesk.delete", "treasury.manage"],
        "open_session": ["treasury.cashdesk.open", "treasury.manage"],
        "close_session": ["treasury.cashdesk.close", "treasury.manage"],
        "cash_in": ["treasury.cashdesk.cash_in", "treasury.manage"],
        "cash_out": ["treasury.cashdesk.cash_out", "treasury.manage"],
        "transfer_to_bank": ["treasury.cashdesk.transfer_to_bank", "treasury.manage"],
        "*": ["treasury.manage"],
    }
    serializer_class = CashDeskSerializer

    def get_queryset(self):
        employer, tenant_db = self._resolve_employer()
        if not employer:
            return CashDesk.objects.none()
        return CashDesk.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer, _ = self._require_employer()
        config = self._get_config()
        if not config.enable_cash_desks:
            raise ValidationError("Cash desks are disabled in treasury configuration.")
        serializer.save(employer_id=employer.id)

    @action(detail=True, methods=["post"], url_path="open-session")
    def open_session(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        if not config.enable_cash_desks:
            raise ValidationError("Cash desks are disabled in treasury configuration.")

        cashdesk = self.get_object()
        if cashdesk.sessions.filter(status=CashDeskSession.STATUS_OPEN).exists():
            raise ValidationError("Cash desk already has an open session.")

        serializer = CashDeskSessionOpenSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = CashDeskSession.objects.using(tenant_db).create(
            cashdesk=cashdesk,
            opened_by_id=request.user.id,
            opening_count_amount=serializer.validated_data["opening_count_amount"],
            status=CashDeskSession.STATUS_OPEN,
        )

        create_notification(
            user=request.user,
            title="Cash desk session opened",
            body=f"{cashdesk.name} session opened.",
            type="ACTION",
            employer_profile=employer,
            data={"cashdesk_id": str(cashdesk.id), "session_id": str(session.id)},
        )

        session_data = CashDeskSessionSerializer(session).data
        return api_response(success=True, message="Cash desk session opened.", data=session_data)

    @action(detail=True, methods=["post"], url_path="close-session")
    def close_session(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        if not config.enable_cash_desks:
            raise ValidationError("Cash desks are disabled in treasury configuration.")

        cashdesk = self.get_object()
        session = cashdesk.sessions.filter(status=CashDeskSession.STATUS_OPEN).first()
        if not session:
            raise ValidationError("No open session found for this cash desk.")

        serializer = CashDeskSessionCloseSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        closing_amount = serializer.validated_data["closing_count_amount"]
        discrepancy = closing_amount - cashdesk.current_balance
        session.status = CashDeskSession.STATUS_CLOSED
        session.closed_by_id = request.user.id
        session.closed_at = timezone.now()
        session.closing_count_amount = closing_amount
        session.discrepancy_amount = discrepancy
        session.discrepancy_note = serializer.validated_data.get("discrepancy_note", "")
        session.save()

        if config.auto_lock_cash_desk_on_discrepancy and abs(discrepancy) > config.discrepancy_tolerance_amount:
            cashdesk.is_active = False
            cashdesk.save(update_fields=["is_active"])

        create_notification(
            user=request.user,
            title="Cash desk session closed",
            body=f"{cashdesk.name} session closed.",
            type="ACTION",
            employer_profile=employer,
            data={"cashdesk_id": str(cashdesk.id), "session_id": str(session.id)},
        )

        session_data = CashDeskSessionSerializer(session).data
        return api_response(success=True, message="Cash desk session closed.", data=session_data)

    @action(detail=True, methods=["post"], url_path="cash-in")
    def cash_in(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        if not config.enable_cash_desks:
            raise ValidationError("Cash desks are disabled in treasury configuration.")

        cashdesk = self.get_object()
        session = ensure_open_cashdesk_session(config, cashdesk)

        serializer = CashDeskOperationSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = _ensure_positive_amount(serializer.validated_data["amount"])
        category = serializer.validated_data["category"]
        notes = serializer.validated_data.get("notes", "")
        if category.upper() == "ADJUSTMENT" and config.adjustments_require_approval:
            raise ValidationError("Cash desk adjustments require approval.")

        with transaction.atomic(using=tenant_db):
            adjust_cashdesk_balance(cashdesk, amount, config, notes=notes)
            txn = create_treasury_transaction(
                tenant_db=tenant_db,
                employer_id=employer.id,
                source_type=TreasuryTransaction.SOURCE_CASHDESK,
                source_id=cashdesk.id,
                direction=TreasuryTransaction.DIRECTION_IN,
                category=category,
                amount=amount,
                currency=cashdesk.currency,
                created_by_id=request.user.id,
                cashdesk_session=session,
                notes=notes,
            )

        create_notification(
            user=request.user,
            title="Cash desk cash-in",
            body=f"{amount} {cashdesk.currency} received into {cashdesk.name}.",
            type="ACTION",
            employer_profile=employer,
            data={"cashdesk_id": str(cashdesk.id), "transaction_id": str(txn.id)},
        )

        return api_response(
            success=True,
            message="Cash-in recorded.",
            data={"cashdesk_id": str(cashdesk.id), "transaction_id": str(txn.id)},
        )

    @action(detail=True, methods=["post"], url_path="cash-out")
    def cash_out(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        if not config.enable_cash_desks:
            raise ValidationError("Cash desks are disabled in treasury configuration.")

        cashdesk = self.get_object()
        session = ensure_open_cashdesk_session(config, cashdesk)

        serializer = CashDeskOperationSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = _ensure_positive_amount(serializer.validated_data["amount"])
        if resolve_cash_out_approval_required(config, amount):
            raise ValidationError("Cash-out above the approval threshold requires approval.")

        category = serializer.validated_data["category"]
        notes = serializer.validated_data.get("notes", "")
        if category.upper() == "ADJUSTMENT" and config.adjustments_require_approval:
            raise ValidationError("Cash desk adjustments require approval.")

        with transaction.atomic(using=tenant_db):
            adjust_cashdesk_balance(cashdesk, -amount, config, notes=notes)
            txn = create_treasury_transaction(
                tenant_db=tenant_db,
                employer_id=employer.id,
                source_type=TreasuryTransaction.SOURCE_CASHDESK,
                source_id=cashdesk.id,
                direction=TreasuryTransaction.DIRECTION_OUT,
                category=category,
                amount=amount,
                currency=cashdesk.currency,
                created_by_id=request.user.id,
                cashdesk_session=session,
                notes=notes,
            )

        create_notification(
            user=request.user,
            title="Cash desk cash-out",
            body=f"{amount} {cashdesk.currency} paid out from {cashdesk.name}.",
            type="ACTION",
            employer_profile=employer,
            data={"cashdesk_id": str(cashdesk.id), "transaction_id": str(txn.id)},
        )

        return api_response(
            success=True,
            message="Cash-out recorded.",
            data={"cashdesk_id": str(cashdesk.id), "transaction_id": str(txn.id)},
        )

    @action(detail=True, methods=["post"], url_path="transfer-to-bank")
    def transfer_to_bank(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        if not config.enable_cash_desks:
            raise ValidationError("Cash desks are disabled in treasury configuration.")
        if not config.enable_bank_accounts:
            raise ValidationError("Bank accounts are disabled in treasury configuration.")

        cashdesk = self.get_object()
        session = ensure_open_cashdesk_session(config, cashdesk)

        serializer = CashDeskTransferSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = _ensure_positive_amount(serializer.validated_data["amount"])
        bank_account_id = serializer.validated_data["bank_account_id"]
        bank_account = BankAccount.objects.using(tenant_db).filter(id=bank_account_id, employer_id=employer.id).first()
        if not bank_account:
            raise ValidationError("Bank account not found.")

        reference = serializer.validated_data.get("reference") or None
        notes = serializer.validated_data.get("notes") or ""

        with transaction.atomic(using=tenant_db):
            adjust_cashdesk_balance(cashdesk, -amount, config, notes=notes)
            adjust_bank_balance(bank_account, amount)
            create_treasury_transaction(
                tenant_db=tenant_db,
                employer_id=employer.id,
                source_type=TreasuryTransaction.SOURCE_CASHDESK,
                source_id=cashdesk.id,
                direction=TreasuryTransaction.DIRECTION_OUT,
                category="TRANSFER",
                amount=amount,
                currency=cashdesk.currency,
                created_by_id=request.user.id,
                reference=reference,
                cashdesk_session=session,
                counterparty_name=bank_account.name,
                notes=notes,
            )
            create_treasury_transaction(
                tenant_db=tenant_db,
                employer_id=employer.id,
                source_type=TreasuryTransaction.SOURCE_BANK,
                source_id=bank_account.id,
                direction=TreasuryTransaction.DIRECTION_IN,
                category="TRANSFER",
                amount=amount,
                currency=bank_account.currency,
                created_by_id=request.user.id,
                counterparty_name=cashdesk.name,
                notes=notes,
            )

        create_notification(
            user=request.user,
            title="Cash desk transfer to bank",
            body=f"{amount} {cashdesk.currency} transferred from {cashdesk.name} to {bank_account.name}.",
            type="ACTION",
            employer_profile=employer,
            data={"cashdesk_id": str(cashdesk.id), "bank_account_id": str(bank_account.id)},
        )

        return api_response(
            success=True,
            message="Transfer completed.",
            data={"cashdesk_id": str(cashdesk.id), "bank_account_id": str(bank_account.id)},
        )


class PaymentBatchViewSet(TreasuryTenantViewSet):
    permission_map = {
        "list": ["treasury.payment.view", "treasury.manage"],
        "retrieve": ["treasury.payment.view", "treasury.manage"],
        "create": ["treasury.payment.create", "treasury.manage"],
        "update": ["treasury.payment.update", "treasury.manage"],
        "partial_update": ["treasury.payment.update", "treasury.manage"],
        "destroy": ["treasury.payment.delete", "treasury.manage"],
        "submit_approval": ["treasury.payment.submit", "treasury.manage"],
        "approve": ["treasury.payment.approve", "treasury.manage"],
        "execute": ["treasury.payment.execute", "treasury.manage"],
        "cancel": ["treasury.payment.cancel", "treasury.manage"],
        "*": ["treasury.manage"],
    }
    serializer_class = PaymentBatchSerializer

    def get_queryset(self):
        employer, tenant_db = self._resolve_employer()
        if not employer:
            return PaymentBatch.objects.none()
        return PaymentBatch.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        ensure_payment_method_allowed(config, serializer.validated_data.get("payment_method"))

        source_type = serializer.validated_data.get("source_type")
        source_id = serializer.validated_data.get("source_id")
        if source_type == TreasuryTransaction.SOURCE_BANK:
            if not config.enable_bank_accounts:
                raise ValidationError("Bank accounts are disabled in treasury configuration.")
            if not BankAccount.objects.using(tenant_db).filter(id=source_id, employer_id=employer.id).exists():
                raise ValidationError("Bank account not found for the selected source.")
        elif source_type == TreasuryTransaction.SOURCE_CASHDESK:
            if not config.enable_cash_desks:
                raise ValidationError("Cash desks are disabled in treasury configuration.")
            if not CashDesk.objects.using(tenant_db).filter(id=source_id, employer_id=employer.id).exists():
                raise ValidationError("Cash desk not found for the selected source.")

        serializer.save(employer_id=employer.id, created_by_id=self.request.user.id)

    def perform_update(self, serializer):
        config = self._get_config()
        instance = self.get_object()
        enforce_edit_after_approval(config, instance)
        ensure_payment_method_allowed(config, serializer.validated_data.get("payment_method", instance.payment_method))
        serializer.save()

    @action(detail=True, methods=["post"], url_path="submit-approval")
    def submit_approval(self, request, pk=None):
        employer, _ = self._require_employer()
        config = self._get_config()
        batch = self.get_object()
        enforce_edit_after_approval(config, batch)

        batch.recalculate_total()
        new_status = apply_batch_approval_rules(batch, config)
        batch.status = new_status
        if new_status == PaymentBatch.STATUS_APPROVAL_PENDING:
            batch.approved_by_id = None
        else:
            batch.approved_by_id = request.user.id
        batch.save(update_fields=["status", "approved_by_id", "updated_at"])

        create_notification(
            user=request.user,
            title="Payment batch submitted",
            body=f"Batch {batch.name} submitted for approval.",
            type="ACTION",
            employer_profile=employer,
            data={"batch_id": str(batch.id), "status": batch.status},
        )

        return api_response(
            success=True,
            message="Batch submitted for approval.",
            data=PaymentBatchSerializer(batch).data,
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        employer, _ = self._require_employer()
        config = self._get_config()
        batch = self.get_object()
        if batch.status != PaymentBatch.STATUS_APPROVAL_PENDING:
            raise ValidationError("Batch is not awaiting approval.")
        if not config.allow_self_approval and batch.created_by_id == request.user.id:
            raise ValidationError("Self-approval is not allowed for this batch.")

        batch.status = PaymentBatch.STATUS_APPROVED
        batch.approved_by_id = request.user.id
        batch.save(update_fields=["status", "approved_by_id", "updated_at"])

        create_notification(
            user=request.user,
            title="Payment batch approved",
            body=f"Batch {batch.name} approved.",
            type="ACTION",
            employer_profile=employer,
            data={"batch_id": str(batch.id), "status": batch.status},
        )

        return api_response(
            success=True,
            message="Batch approved.",
            data=PaymentBatchSerializer(batch).data,
        )

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        batch = self.get_object()
        if batch.status != PaymentBatch.STATUS_APPROVED:
            raise ValidationError("Only approved batches can be executed.")

        ensure_payment_method_allowed(config, batch.payment_method)
        if config.execution_proof_required:
            proof_reference = request.data.get("proof_reference")
            ensure_execution_proof(config, proof_reference)
        else:
            proof_reference = request.data.get("proof_reference", "")
        cashdesk_notes = request.data.get("notes", "") or proof_reference or ""

        if batch.payment_method == "CASH" and batch.source_type != TreasuryTransaction.SOURCE_CASHDESK:
            raise ValidationError("Cash payments must use a cash desk source.")

        batch.recalculate_total()
        if batch.total_amount <= 0:
            raise ValidationError("Batch total must be greater than zero before execution.")

        lines_qs = batch.lines.all()
        if not lines_qs.exists():
            raise ValidationError("Batch has no payment lines to execute.")

        if lines_qs.filter(requires_approval=True, approved=False).exists():
            raise ValidationError("All approval-required lines must be approved before execution.")

        for line in lines_qs:
            ensure_beneficiary_details(
                config,
                batch.payment_method,
                bool(line.payee_name or line.payee_id),
            )

        cashdesk_session = None
        source_currency = batch.currency
        if batch.source_type == TreasuryTransaction.SOURCE_BANK:
            if not config.enable_bank_accounts:
                raise ValidationError("Bank accounts are disabled in treasury configuration.")
            bank_account = get_object_or_404(
                BankAccount.objects.using(tenant_db),
                id=batch.source_id,
                employer_id=employer.id,
            )
            source_currency = bank_account.currency
            if bank_account.current_balance - batch.total_amount < Decimal("0"):
                raise ValidationError("Insufficient bank account balance for this batch.")
        else:
            if not config.enable_cash_desks:
                raise ValidationError("Cash desks are disabled in treasury configuration.")
            cashdesk = get_object_or_404(
                CashDesk.objects.using(tenant_db),
                id=batch.source_id,
                employer_id=employer.id,
            )
            source_currency = cashdesk.currency
            cashdesk_session = ensure_open_cashdesk_session(config, cashdesk)

        with transaction.atomic(using=tenant_db):
            if batch.source_type == TreasuryTransaction.SOURCE_BANK:
                adjust_bank_balance(bank_account, -batch.total_amount)
            else:
                adjust_cashdesk_balance(cashdesk, -batch.total_amount, config, notes=cashdesk_notes)

            for line in lines_qs:
                if line.currency != source_currency:
                    raise ValidationError("All payment line currencies must match the source account currency.")
                category = "EXPENSE"
                if line.payee_type == PaymentLine.PAYEE_EMPLOYEE:
                    category = "SALARY"
                elif line.payee_type == PaymentLine.PAYEE_VENDOR:
                    category = "VENDOR"

                create_treasury_transaction(
                    tenant_db=tenant_db,
                    employer_id=employer.id,
                    source_type=batch.source_type,
                    source_id=batch.source_id,
                    direction=TreasuryTransaction.DIRECTION_OUT,
                    category=category,
                    amount=line.amount,
                    currency=line.currency,
                    created_by_id=request.user.id,
                    counterparty_name=line.payee_name,
                    linked_object_type="PAYMENT_LINE",
                    linked_object_id=line.id,
                    cashdesk_session=cashdesk_session,
                    notes=proof_reference,
                )
                line_update_fields = []
                if line.status == PaymentLine.STATUS_PENDING:
                    line.status = PaymentLine.STATUS_PAID
                    line_update_fields.append("status")
                if proof_reference and not line.external_reference:
                    line.external_reference = proof_reference
                    line_update_fields.append("external_reference")
                if line_update_fields:
                    line_update_fields.append("updated_at")
                    line.save(update_fields=line_update_fields)

            batch.status = PaymentBatch.STATUS_EXECUTED
            batch.executed_by_id = request.user.id
            batch.executed_at = timezone.now()
            batch.save(update_fields=["status", "executed_by_id", "executed_at", "updated_at"])

        create_notification(
            user=request.user,
            title="Payment batch executed",
            body=f"Batch {batch.name} executed.",
            type="ACTION",
            employer_profile=employer,
            data={"batch_id": str(batch.id), "status": batch.status},
        )

        return api_response(
            success=True,
            message="Batch executed.",
            data=PaymentBatchSerializer(batch).data,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        employer, _ = self._require_employer()
        config = self._get_config()
        batch = self.get_object()
        if batch.status in [PaymentBatch.STATUS_EXECUTED, PaymentBatch.STATUS_RECONCILED]:
            raise ValidationError("Executed batches cannot be cancelled.")
        enforce_batch_cancellation(config, batch)

        batch.status = PaymentBatch.STATUS_CANCELLED
        batch.save(update_fields=["status", "updated_at"])

        create_notification(
            user=request.user,
            title="Payment batch cancelled",
            body=f"Batch {batch.name} cancelled.",
            type="ACTION",
            employer_profile=employer,
            data={"batch_id": str(batch.id), "status": batch.status},
        )

        return api_response(
            success=True,
            message="Batch cancelled.",
            data=PaymentBatchSerializer(batch).data,
        )

class PaymentLineViewSet(TreasuryTenantViewSet):
    permission_map = {
        "list": ["treasury.payment.view", "treasury.manage"],
        "retrieve": ["treasury.payment.view", "treasury.manage"],
        "create": ["treasury.payment.update", "treasury.manage"],
        "update": ["treasury.payment.update", "treasury.manage"],
        "partial_update": ["treasury.payment.update", "treasury.manage"],
        "destroy": ["treasury.payment.update", "treasury.manage"],
        "mark_paid": ["treasury.payment.mark_paid", "treasury.manage"],
        "mark_failed": ["treasury.payment.fail", "treasury.manage"],
        "*": ["treasury.manage"],
    }
    serializer_class = PaymentLineSerializer

    def get_queryset(self):
        employer, tenant_db = self._resolve_employer()
        if not employer:
            return PaymentLine.objects.none()
        return PaymentLine.objects.using(tenant_db).filter(batch__employer_id=employer.id)

    def perform_create(self, serializer):
        employer, _ = self._require_employer()
        config = self._get_config()
        batch = serializer.validated_data.get("batch")
        if batch.employer_id != employer.id:
            raise ValidationError("Batch does not belong to this employer.")
        enforce_edit_after_approval(config, batch)
        line = serializer.save()
        apply_line_approval_rules(line, config)
        line.save(update_fields=["requires_approval", "approved", "updated_at"])
        batch.recalculate_total()

        create_notification(
            user=self.request.user,
            title="Payment line added",
            body=f"Payment line added to batch {batch.name}.",
            type="INFO",
            employer_profile=employer,
            data={"batch_id": str(batch.id), "line_id": str(line.id)},
        )

    def perform_update(self, serializer):
        config = self._get_config()
        line = self.get_object()
        batch = line.batch
        enforce_edit_after_approval(config, batch)
        instance = serializer.save()
        apply_line_approval_rules(instance, config)
        instance.save(update_fields=["requires_approval", "approved", "updated_at"])
        batch.recalculate_total()

    def perform_destroy(self, instance):
        batch = instance.batch
        instance.delete()
        batch.recalculate_total()

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        line = self.get_object()

        serializer = PaymentLineStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        line.status = PaymentLine.STATUS_PAID
        line.external_reference = serializer.validated_data.get("external_reference")
        line.save(update_fields=["status", "external_reference", "updated_at"])

        try:
            from billing.models import BillingPayout
            from billing.services import update_payout_status
        except Exception:
            BillingPayout = None
            update_payout_status = None

        if BillingPayout and update_payout_status:
            payout = BillingPayout.objects.using(tenant_db).filter(
                treasury_payment_line_id=line.id,
                employer_id=employer.id,
            ).first()
            if payout:
                update_payout_status(
                    payout=payout,
                    tenant_db=tenant_db,
                    status="PAID",
                    provider_reference=line.external_reference,
                    actor_id=getattr(request.user, "id", None),
                )

        create_notification(
            user=request.user,
            title="Payment line marked paid",
            body=f"Payment line {line.payee_name} marked as paid.",
            type="ACTION",
            employer_profile=employer,
            data={"line_id": str(line.id), "batch_id": str(line.batch_id)},
        )

        return api_response(
            success=True,
            message="Payment line marked as paid.",
            data=PaymentLineSerializer(line).data,
        )

    @action(detail=True, methods=["post"], url_path="fail")
    def mark_failed(self, request, pk=None):
        employer, tenant_db = self._require_employer()
        line = self.get_object()

        serializer = PaymentLineStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        line.status = PaymentLine.STATUS_FAILED
        line.external_reference = serializer.validated_data.get("external_reference")
        line.save(update_fields=["status", "external_reference", "updated_at"])

        try:
            from billing.models import BillingPayout
            from billing.services import update_payout_status
        except Exception:
            BillingPayout = None
            update_payout_status = None

        if BillingPayout and update_payout_status:
            payout = BillingPayout.objects.using(tenant_db).filter(
                treasury_payment_line_id=line.id,
                employer_id=employer.id,
            ).first()
            if payout:
                update_payout_status(
                    payout=payout,
                    tenant_db=tenant_db,
                    status="FAILED",
                    failure_reason="Treasury payment failed",
                    actor_id=getattr(request.user, "id", None),
                )

        create_notification(
            user=request.user,
            title="Payment line failed",
            body=f"Payment line {line.payee_name} marked as failed.",
            type="ALERT",
            employer_profile=employer,
            data={"line_id": str(line.id), "batch_id": str(line.batch_id)},
        )

        return api_response(
            success=True,
            message="Payment line marked as failed.",
            data=PaymentLineSerializer(line).data,
        )


class BankStatementViewSet(TreasuryTenantViewSet):
    permission_map = {
        "list": ["treasury.statement.view", "treasury.manage"],
        "retrieve": ["treasury.statement.view", "treasury.manage"],
        "create": ["treasury.statement.create", "treasury.manage"],
        "update": ["treasury.statement.update", "treasury.manage"],
        "partial_update": ["treasury.statement.update", "treasury.manage"],
        "destroy": ["treasury.statement.delete", "treasury.manage"],
        "import_statement": ["treasury.statement.import", "treasury.manage"],
        "lines": ["treasury.statement.view", "treasury.manage"],
        "*": ["treasury.manage"],
    }
    serializer_class = BankStatementSerializer

    def get_queryset(self):
        employer, tenant_db = self._resolve_employer()
        if not employer:
            return BankStatement.objects.none()
        return BankStatement.objects.using(tenant_db).filter(employer_id=employer.id)

    @action(detail=False, methods=["post"], url_path="import")
    def import_statement(self, request):
        employer, tenant_db = self._require_employer()
        config = self._get_config()
        enforce_reconciliation_enabled(config)

        serializer = BankStatementImportSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        bank_account_id = serializer.validated_data["bank_account_id"]
        bank_account = BankAccount.objects.using(tenant_db).filter(id=bank_account_id, employer_id=employer.id).first()
        if not bank_account:
            raise ValidationError("Bank account not found.")

        with transaction.atomic(using=tenant_db):
            statement = BankStatement.objects.using(tenant_db).create(
                employer_id=employer.id,
                bank_account=bank_account,
                period_start=serializer.validated_data["period_start"],
                period_end=serializer.validated_data["period_end"],
                status=BankStatement.STATUS_IMPORTED,
            )
            lines_payload = serializer.validated_data.get("lines", [])
            for line_payload in lines_payload:
                BankStatementLine.objects.using(tenant_db).create(
                    bank_statement=statement,
                    txn_date=line_payload["txn_date"],
                    description=line_payload.get("description", ""),
                    amount_signed=line_payload["amount_signed"],
                    currency=line_payload["currency"],
                    reference_raw=line_payload.get("reference_raw"),
                    external_id=line_payload.get("external_id"),
                )

        create_notification(
            user=request.user,
            title="Bank statement imported",
            body=f"Statement imported for {bank_account.name}.",
            type="INFO",
            employer_profile=employer,
            data={"statement_id": str(statement.id)},
        )

        return api_response(
            success=True,
            message="Bank statement imported.",
            data=BankStatementSerializer(statement).data,
        )

    @action(detail=True, methods=["get"], url_path="lines")
    def lines(self, request, pk=None):
        statement = self.get_object()
        lines = statement.lines.prefetch_related("matches").all()
        serializer = BankStatementLineSerializer(lines, many=True)
        return api_response(success=True, message="Statement lines retrieved.", data=serializer.data)


class ReconciliationAutoMatchView(APIView):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["treasury.manage"]

    def get(self, request, statement_id=None):
        return self.post(request, statement_id=statement_id)

    def post(self, request, statement_id=None):
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        config = ensure_treasury_configuration(employer, tenant_db=tenant_db)
        enforce_reconciliation_enabled(config)
        if not config.auto_match_enabled:
            raise ValidationError("Auto-match is disabled in treasury configuration.")

        statement = get_object_or_404(
            BankStatement.objects.using(tenant_db),
            id=statement_id,
            employer_id=employer.id,
        )

        created_count = 0
        confirmed_count = 0
        window_days = config.match_window_days
        for line in statement.lines.all():
            if line.matched or line.matches.filter(status=ReconciliationMatch.STATUS_CONFIRMED).exists():
                continue
            if line.matches.exists():
                continue

            amount = abs(line.amount_signed)
            start_date = line.txn_date - timedelta(days=window_days)
            end_date = line.txn_date + timedelta(days=window_days)
            match = None
            confidence = 0
            reference_candidates = list(
                {value for value in [line.reference_raw, line.external_id] if value}
            )

            if reference_candidates:
                payment_line = (
                    PaymentLine.objects.using(tenant_db)
                    .filter(batch__employer_id=employer.id, external_reference__in=reference_candidates)
                    .exclude(status=PaymentLine.STATUS_FAILED)
                    .order_by("-created_at")
                    .first()
                )
                if payment_line:
                    match = ReconciliationMatch.objects.using(tenant_db).create(
                        statement_line=line,
                        match_type=ReconciliationMatch.MATCH_TYPE_CHOICES[0][0],
                        match_id=payment_line.id,
                        confidence=98,
                        status=ReconciliationMatch.STATUS_SUGGESTED,
                    )
                    confidence = 98
                else:
                    treasury_txn = (
                        TreasuryTransaction.objects.using(tenant_db)
                        .filter(
                            Q(reference__in=reference_candidates) | Q(notes__in=reference_candidates),
                            employer_id=employer.id,
                        )
                        .order_by("-transaction_date")
                        .first()
                    )
                    if treasury_txn:
                        match = ReconciliationMatch.objects.using(tenant_db).create(
                            statement_line=line,
                            match_type=ReconciliationMatch.MATCH_TYPE_CHOICES[1][0],
                            match_id=treasury_txn.id,
                            confidence=96,
                            status=ReconciliationMatch.STATUS_SUGGESTED,
                        )
                        confidence = 96

            if not match:
                payment_line = (
                    PaymentLine.objects.using(tenant_db)
                    .filter(
                        batch__employer_id=employer.id,
                        amount=amount,
                        currency=line.currency,
                        batch__planned_date__range=(start_date, end_date),
                    )
                    .exclude(status=PaymentLine.STATUS_FAILED)
                    .order_by("-created_at")
                    .first()
                )
                if payment_line:
                    match = ReconciliationMatch.objects.using(tenant_db).create(
                        statement_line=line,
                        match_type=ReconciliationMatch.MATCH_TYPE_CHOICES[0][0],
                        match_id=payment_line.id,
                        confidence=90,
                        status=ReconciliationMatch.STATUS_SUGGESTED,
                    )
                    confidence = 90
                else:
                    direction = (
                        TreasuryTransaction.DIRECTION_OUT
                        if line.amount_signed < 0
                        else TreasuryTransaction.DIRECTION_IN
                    )
                    treasury_txn = (
                        TreasuryTransaction.objects.using(tenant_db)
                        .filter(
                            employer_id=employer.id,
                            amount=amount,
                            currency=line.currency,
                            direction=direction,
                            transaction_date__date__range=(start_date, end_date),
                        )
                        .order_by("-transaction_date")
                        .first()
                    )
                    if treasury_txn:
                        match = ReconciliationMatch.objects.using(tenant_db).create(
                            statement_line=line,
                            match_type=ReconciliationMatch.MATCH_TYPE_CHOICES[1][0],
                            match_id=treasury_txn.id,
                            confidence=85,
                            status=ReconciliationMatch.STATUS_SUGGESTED,
                        )
                        confidence = 85

            if match:
                created_count += 1
                if confidence >= config.auto_confirm_confidence_threshold:
                    match.status = ReconciliationMatch.STATUS_CONFIRMED
                    match.confirmed_by_id = request.user.id
                    match.confirmed_at = timezone.now()
                    match.save(update_fields=["status", "confirmed_by_id", "confirmed_at"])
                    line.matched = True
                    line.save(update_fields=["matched"])
                    confirmed_count += 1
                    if match.match_type == ReconciliationMatch.MATCH_TYPE_CHOICES[0][0]:
                        matched_line = PaymentLine.objects.using(tenant_db).filter(id=match.match_id).first()
                        if matched_line:
                            _update_batch_reconciliation_status(matched_line.batch, tenant_db)

        create_notification(
            user=request.user,
            title="Reconciliation auto-match",
            body=f"Auto-match completed for statement {statement.id}.",
            type="INFO",
            employer_profile=employer,
            data={"statement_id": str(statement.id), "created": created_count, "confirmed": confirmed_count},
        )

        return api_response(
            success=True,
            message="Auto-match completed.",
            data={"created": created_count, "confirmed": confirmed_count},
        )


class ReconciliationConfirmView(APIView):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["treasury.manage"]

    def post(self, request):
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        config = ensure_treasury_configuration(employer, tenant_db=tenant_db)
        enforce_reconciliation_enabled(config)

        serializer = ReconciliationActionSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        match = get_object_or_404(
            ReconciliationMatch.objects.using(tenant_db),
            id=serializer.validated_data["match_id"],
        )
        match.status = ReconciliationMatch.STATUS_CONFIRMED
        match.confirmed_by_id = request.user.id
        match.confirmed_at = timezone.now()
        match.save(update_fields=["status", "confirmed_by_id", "confirmed_at"])

        line = match.statement_line
        line.matched = True
        line.save(update_fields=["matched"])

        if match.match_type == ReconciliationMatch.MATCH_TYPE_CHOICES[0][0]:
            matched_line = PaymentLine.objects.using(tenant_db).filter(id=match.match_id).first()
            if matched_line:
                _update_batch_reconciliation_status(matched_line.batch, tenant_db)

        create_notification(
            user=request.user,
            title="Reconciliation confirmed",
            body="A reconciliation match was confirmed.",
            type="ACTION",
            employer_profile=employer,
            data={"match_id": str(match.id), "statement_line_id": str(line.id)},
        )

        return api_response(
            success=True,
            message="Match confirmed.",
            data=ReconciliationMatchSerializer(match).data,
        )


class ReconciliationRejectView(APIView):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["treasury.manage"]

    def post(self, request):
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        config = ensure_treasury_configuration(employer, tenant_db=tenant_db)
        enforce_reconciliation_enabled(config)

        serializer = ReconciliationActionSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid payload.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        match = get_object_or_404(
            ReconciliationMatch.objects.using(tenant_db),
            id=serializer.validated_data["match_id"],
        )
        match.status = ReconciliationMatch.STATUS_REJECTED
        match.rejected_reason = serializer.validated_data.get("rejected_reason", "")
        match.save(update_fields=["status", "rejected_reason"])

        line = match.statement_line
        if not line.matches.filter(status=ReconciliationMatch.STATUS_CONFIRMED).exists():
            line.matched = False
            line.save(update_fields=["matched"])

        if match.match_type == ReconciliationMatch.MATCH_TYPE_CHOICES[0][0]:
            matched_line = PaymentLine.objects.using(tenant_db).filter(id=match.match_id).first()
            if matched_line:
                _update_batch_reconciliation_status(matched_line.batch, tenant_db)

        create_notification(
            user=request.user,
            title="Reconciliation rejected",
            body="A reconciliation match was rejected.",
            type="ALERT",
            employer_profile=employer,
            data={"match_id": str(match.id), "statement_line_id": str(line.id)},
        )

        return api_response(
            success=True,
            message="Match rejected.",
            data=ReconciliationMatchSerializer(match).data,
        )
