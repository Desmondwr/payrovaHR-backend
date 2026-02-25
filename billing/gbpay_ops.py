import hashlib
import logging
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from employees.models import Employee

from .crypto import decrypt_json, encrypt_json
from .gbpay_service import EmployerGbPayContext, GbPayApiError, GbPayService
from .models import (
    BillingPaymentAttempt,
    BillingPayout,
    BillingPayoutBatch,
    GbPayEmployerConnection,
    GbPayTransfer,
    PayoutMethod,
)
from .services import (
    get_default_payout_method,
    get_payout_provider,
    log_billing_action,
    notify_employer_owner,
    update_payout_status,
)
from .services import create_payout_with_transactions

logger = logging.getLogger(__name__)

PROVIDER_NAME = "GBPAY"
PROVIDER_MANUAL = "MANUAL"
CATEGORY_TYPE_BANK = "ACCOUNT_TRANSFER"
CATEGORY_TYPE_MOBILE = "ACCOUNT_TO_WALLET"
FAILURE_ALERT_THRESHOLD = 0.3
FAILURE_ALERT_MIN_COUNT = 5
INSUFFICIENT_FUNDS_KEYWORDS = ("insufficient", "not enough", "balance")
TERMINAL_SUCCESS = {"SUCCESS", "COMPLETED", "PAID"}
TERMINAL_FAILURE = {"FAILED", "REJECTED", "CANCELLED", "CANCELED", "REVERSED"}


def emit_metric(name: str, count: int = 1, **tags):
    logger.info("metric=%s count=%s tags=%s", name, count, tags)


def mask_value(value: Optional[str], visible: int = 4) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"


def sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted = {}
        for key, value in payload.items():
            if key.lower() in {"token", "accesstoken", "access_token", "clientsecret", "secret", "password"}:
                redacted[key] = "***"
            else:
                redacted[key] = sanitize_payload(value)
        return redacted
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload


def is_insufficient_funds(payload: Any, message: str = "") -> bool:
    text = message or ""
    if isinstance(payload, dict):
        text = f"{text} {payload.get('message', '')} {payload.get('error', '')} {payload.get('detail', '')}"
    text = text.lower()
    return any(keyword in text for keyword in INSUFFICIENT_FUNDS_KEYWORDS)


def build_idempotency_key(payout: BillingPayout) -> str:
    raw = f"{payout.employer_id}:{payout.id}:{payout.category}:{payout.amount}:{payout.currency}:{payout.linked_object_type}:{payout.linked_object_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_value(payload: Dict[str, Any], *keys):
    for key in keys:
        if key in payload and payload[key]:
            return payload[key]
    data = payload.get("data") if isinstance(payload, dict) else {}
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key]:
                return data[key]
    return ""


def _extract_status(payload: Dict[str, Any]) -> str:
    return (
        _extract_value(payload, "status", "transactionStatus", "state", "transaction_state") or ""
    ).upper()


def _map_provider_status(status: str) -> Tuple[str, bool]:
    if status in TERMINAL_SUCCESS:
        return "SUCCESS", True
    if status in TERMINAL_FAILURE:
        return "FAILED", True
    return "PENDING", False


def _next_poll_at(current_count: int) -> timezone.datetime:
    intervals = [2, 5, 10, 20, 30, 60]  # minutes
    idx = min(current_count, len(intervals) - 1)
    return timezone.now() + timedelta(minutes=intervals[idx])


def build_gbpay_context(connection: GbPayEmployerConnection) -> EmployerGbPayContext:
    creds = decrypt_json(connection.credentials_encrypted)
    if not creds.get("api_key") or not creds.get("secret_key") or not creds.get("scope"):
        raise ValidationError("GbPay credentials missing or could not be decrypted. Please re-save the connection.")
    base_url = getattr(settings, "GBPAY_API_BASE_URL", "")
    if not base_url:
        raise ValidationError("GBPAY_API_BASE_URL is not configured.")
    return EmployerGbPayContext(
        employer_id=connection.employer_id,
        connection_id=str(connection.id),
        credentials=creds,
        environment=connection.environment,
        base_url=base_url,
    )


def get_active_connection(employer_id: int, tenant_db: str) -> Optional[GbPayEmployerConnection]:
    return (
        GbPayEmployerConnection.objects.using(tenant_db)
        .filter(employer_id=employer_id, is_active=True, status=GbPayEmployerConnection.STATUS_ACTIVE)
        .order_by("-updated_at")
        .first()
    )


def save_gbpay_connection(
    *,
    tenant_db: str,
    employer_id: int,
    credentials: Dict[str, Any],
    environment: str,
    actor_id: Optional[int] = None,
    label: str = "",
    connection: Optional[GbPayEmployerConnection] = None,
) -> GbPayEmployerConnection:
    credentials_payload = {
        "api_key": credentials.get("api_key"),
        "secret_key": credentials.get("secret_key"),
        "scope": credentials.get("scope"),
    }
    encrypted = encrypt_json(credentials_payload)
    hint_source = credentials_payload.get("api_key")
    hint = mask_value(hint_source)

    with transaction.atomic(using=tenant_db):
        if connection is None:
            connection = GbPayEmployerConnection.objects.using(tenant_db).create(
                employer_id=employer_id,
                label=label or "",
                environment=environment,
                credentials_encrypted=encrypted,
                credentials_hint=hint,
                status=GbPayEmployerConnection.STATUS_PENDING,
                is_active=False,
            )
        else:
            if label:
                connection.label = label
            connection.environment = environment
            connection.credentials_encrypted = encrypted
            connection.credentials_hint = hint
            connection.status = GbPayEmployerConnection.STATUS_PENDING
            connection.save(using=tenant_db, update_fields=["label", "environment", "credentials_encrypted", "credentials_hint", "status", "updated_at"])

    # Validate credentials
    try:
        ctx = build_gbpay_context(connection)
        GbPayService(ctx).authenticate()
        with transaction.atomic(using=tenant_db):
            GbPayEmployerConnection.objects.using(tenant_db).filter(
                employer_id=employer_id,
                is_active=True,
            ).exclude(id=connection.id).update(is_active=False, status=GbPayEmployerConnection.STATUS_INACTIVE)
            connection.is_active = True
            connection.status = GbPayEmployerConnection.STATUS_ACTIVE
            connection.last_validated_at = timezone.now()
            connection.last_validation_error = ""
            connection.last_validated_by_id = actor_id
            connection.save(using=tenant_db, update_fields=[
                "is_active",
                "status",
                "last_validated_at",
                "last_validation_error",
                "last_validated_by_id",
                "updated_at",
            ])
    except Exception as exc:
        message = str(exc)
        connection.is_active = False
        connection.status = GbPayEmployerConnection.STATUS_INVALID
        connection.last_validation_error = message
        connection.last_validated_at = timezone.now()
        connection.last_validated_by_id = actor_id
        connection.save(using=tenant_db, update_fields=[
            "is_active",
            "status",
            "last_validation_error",
            "last_validated_at",
            "last_validated_by_id",
            "updated_at",
        ])
        log_billing_action(
            tenant_db=tenant_db,
            action="gbpay.connection.validation_failed",
            entity_type="GbPayEmployerConnection",
            entity_id=connection.id,
            actor_id=actor_id,
            employer_id=employer_id,
            meta_new={"error": message},
        )
        raise ValidationError(f"GbPay connection validation failed: {message}")

    log_billing_action(
        tenant_db=tenant_db,
        action="gbpay.connection.saved",
        entity_type="GbPayEmployerConnection",
        entity_id=connection.id,
        actor_id=actor_id,
        employer_id=employer_id,
        meta_new={"status": connection.status},
    )
    return connection


def set_connection_active(
    *,
    connection: GbPayEmployerConnection,
    tenant_db: str,
    actor_id: Optional[int] = None,
    enable: bool,
) -> GbPayEmployerConnection:
    if not enable:
        connection.is_active = False
        connection.status = GbPayEmployerConnection.STATUS_INACTIVE
        connection.save(using=tenant_db, update_fields=["is_active", "status", "updated_at"])
        log_billing_action(
            tenant_db=tenant_db,
            action="gbpay.connection.disabled",
            entity_type="GbPayEmployerConnection",
            entity_id=connection.id,
            actor_id=actor_id,
            employer_id=connection.employer_id,
        )
        return connection

    ctx = build_gbpay_context(connection)
    try:
        GbPayService(ctx).authenticate()
    except Exception as exc:
        connection.is_active = False
        connection.status = GbPayEmployerConnection.STATUS_INVALID
        message = str(exc)
        connection.last_validation_error = message
        connection.last_validated_at = timezone.now()
        connection.last_validated_by_id = actor_id
        connection.save(using=tenant_db, update_fields=[
            "is_active",
            "status",
            "last_validation_error",
            "last_validated_at",
            "last_validated_by_id",
            "updated_at",
        ])
        raise ValidationError(f"GbPay connection validation failed: {message}")
    with transaction.atomic(using=tenant_db):
        GbPayEmployerConnection.objects.using(tenant_db).filter(
            employer_id=connection.employer_id,
            is_active=True,
        ).exclude(id=connection.id).update(is_active=False, status=GbPayEmployerConnection.STATUS_INACTIVE)
        connection.is_active = True
        connection.status = GbPayEmployerConnection.STATUS_ACTIVE
        connection.last_validated_at = timezone.now()
        connection.last_validation_error = ""
        connection.last_validated_by_id = actor_id
        connection.save(using=tenant_db, update_fields=[
            "is_active",
            "status",
            "last_validated_at",
            "last_validation_error",
            "last_validated_by_id",
            "updated_at",
        ])
    log_billing_action(
        tenant_db=tenant_db,
        action="gbpay.connection.enabled",
        entity_type="GbPayEmployerConnection",
        entity_id=connection.id,
        actor_id=actor_id,
        employer_id=connection.employer_id,
    )
    return connection


def verify_payout_destination(
    *,
    tenant_db: str,
    employer_id: int,
    method_type: str,
    bank_code: Optional[str],
    operator_code: Optional[str],
    account_number: Optional[str],
    wallet_destination: Optional[str],
    country_code: str,
    entity_product_uuid: str,
) -> Dict[str, Any]:
    connection = get_active_connection(employer_id, tenant_db)
    if not connection:
        raise ValidationError("Active GbPay connection not found for employer.")

    ctx = build_gbpay_context(connection)
    service = GbPayService(ctx)

    # Currency validation removed (GbPay doc does not require it).

    payload = {
        "country": country_code,
        "entityProduct": entity_product_uuid,
    }
    if method_type == PayoutMethod.METHOD_BANK_ACCOUNT:
        payload.update(
            {
                "bankCode": bank_code,
                "bankAccountDestination": account_number,
            }
        )
    elif method_type == PayoutMethod.METHOD_MOBILE_MONEY:
        payload.update(
            {
                "operatorCode": operator_code,
                "walletDestination": wallet_destination,
            }
        )
    else:
        raise ValidationError("Unsupported payout method type for GbPay verification.")

    response = service.lookupAccount(payload)
    status = _extract_status(response)
    if status and status not in TERMINAL_SUCCESS:
        raise ValidationError("Payout destination verification failed.")
    if not status and response.get("success") is False:
        raise ValidationError("Payout destination verification failed.")

    reference = _extract_value(response, "reference", "lookupReference", "verificationReference")
    account_name = _extract_value(response, "accountName", "beneficiaryName", "name", "fullName")
    return {
        "reference": reference,
        "account_name": account_name,
        "payload": sanitize_payload(response),
    }


def _ensure_provider_metadata(payout: BillingPayout, tenant_db: str):
    if payout.provider != PROVIDER_NAME:
        payout.provider = PROVIDER_NAME
        payout.save(using=tenant_db, update_fields=["provider", "updated_at"])
    for txn in [payout.employer_transaction, payout.employee_transaction]:
        if txn and txn.provider != PROVIDER_NAME:
            txn.provider = PROVIDER_NAME
            txn.save(using=tenant_db, update_fields=["provider", "updated_at"])


def _ensure_manual_metadata(payout: BillingPayout, tenant_db: str):
    if payout.provider != PROVIDER_MANUAL:
        payout.provider = PROVIDER_MANUAL
    payout.metadata = payout.metadata or {}
    payout.metadata["payout_mode"] = PROVIDER_MANUAL
    payout.failure_reason = ""
    payout.save(using=tenant_db, update_fields=["provider", "metadata", "failure_reason", "updated_at"])
    for txn in [payout.employer_transaction, payout.employee_transaction]:
        if txn and txn.provider != PROVIDER_MANUAL:
            txn.provider = PROVIDER_MANUAL
            txn.save(using=tenant_db, update_fields=["provider", "updated_at"])


def _store_transfer_event(transfer: GbPayTransfer, event_type: str, payload: Any, tenant_db: str):
    event_log = list(transfer.event_log or [])
    event_log.append({"type": event_type, "at": timezone.now().isoformat(), "payload": sanitize_payload(payload)})
    transfer.event_log = event_log
    transfer.save(using=tenant_db, update_fields=["event_log", "updated_at"])


def build_transfer_request(
    *,
    payout: BillingPayout,
    payout_method: PayoutMethod,
    employee_name: str,
    idempotency_key: str,
) -> Dict[str, Any]:
    request = {
        "amount": str(payout.amount),
        "currency": payout.currency,
        "transactionReference": idempotency_key,
        "description": f"{payout.category} payout",
        "entityProduct": payout_method.entity_product_uuid,
    }
    if payout_method.method_type == PayoutMethod.METHOD_BANK_ACCOUNT:
        request.update(
            {
                "bankAccountDestination": payout_method.get_account_number(),
            }
        )
    else:
        request.update(
            {
                "walletDestination": payout_method.get_wallet_destination(),
            }
        )
    return {k: v for k, v in request.items() if v not in (None, "")}


def _resolve_category_type(method_type: str) -> str:
    if method_type == PayoutMethod.METHOD_BANK_ACCOUNT:
        return CATEGORY_TYPE_BANK
    if method_type == PayoutMethod.METHOD_MOBILE_MONEY:
        return CATEGORY_TYPE_MOBILE
    return ""


def _extract_supported_currencies(response: Dict[str, Any]) -> list:
    if not isinstance(response, dict):
        return []
    data = response.get("data") or response.get("currencies") or response.get("supportedCurrencies")
    if isinstance(data, list):
        normalized = []
        for item in data:
            if isinstance(item, dict):
                code = item.get("code") or item.get("currency")
                if code:
                    normalized.append(code.upper())
            elif isinstance(item, str):
                normalized.append(item.upper())
        return normalized
    return []


def create_payout_batch(
    *,
    tenant_db: str,
    employer_id: int,
    batch_type: str,
    currency: str,
    planned_date=None,
    items=None,
    actor_id: Optional[int] = None,
) -> BillingPayoutBatch:
    if batch_type not in [BillingPayoutBatch.TYPE_PAYROLL, BillingPayoutBatch.TYPE_EXPENSE]:
        raise ValidationError("Batch type must be PAYROLL or EXPENSE.")

    items = items or []
    provider = (get_payout_provider(employer_id=employer_id, tenant_db=tenant_db, category=batch_type) or "").upper()
    requires_approval = provider == PROVIDER_NAME
    initial_status = (
        BillingPayoutBatch.STATUS_APPROVAL_PENDING if requires_approval else BillingPayoutBatch.STATUS_DRAFT
    )

    with transaction.atomic(using=tenant_db):
        batch = BillingPayoutBatch.objects.using(tenant_db).create(
            employer_id=employer_id,
            batch_type=batch_type,
            status=initial_status,
            requires_approval=requires_approval,
            currency=currency or "XAF",
            planned_date=planned_date or timezone.now().date(),
            created_by_id=actor_id,
            metadata={"source": PROVIDER_NAME, "provider": provider or PROVIDER_MANUAL},
        )

        for item in items:
            employee_id = item.get("employee_id")
            employee = Employee.objects.using(tenant_db).filter(id=employee_id, employer_id=employer_id).first()
            if not employee:
                raise ValidationError(f"Employee {employee_id} not found.")

            linked_object_type = (item.get("linked_object_type") or "OTHER").upper()
            linked_object_id = item.get("linked_object_id")
            if linked_object_id:
                existing = BillingPayout.objects.using(tenant_db).filter(
                    employer_id=employer_id,
                    employee=employee,
                    linked_object_type=linked_object_type,
                    linked_object_id=linked_object_id,
                ).first()
                if existing:
                    continue

            payout_method = None
            payout_method_id = item.get("payout_method_id")
            if payout_method_id:
                payout_method = PayoutMethod.objects.using(tenant_db).filter(
                    id=payout_method_id,
                    employee=employee,
                ).first()

            create_payout_with_transactions(
                tenant_db=tenant_db,
                employer_id=employer_id,
                employee=employee,
                amount=item.get("amount"),
                currency=item.get("currency") or batch.currency,
                category=BillingPayout.CATEGORY_PAYROLL if batch_type == BillingPayoutBatch.TYPE_PAYROLL else BillingPayout.CATEGORY_EXPENSE,
                payout_method=payout_method,
                batch=batch,
                linked_object_type=linked_object_type,
                linked_object_id=linked_object_id,
                treasury_payment_line_id=item.get("treasury_payment_line_id"),
                treasury_batch_id=item.get("treasury_batch_id"),
                actor_id=actor_id,
            )

    log_billing_action(
        tenant_db=tenant_db,
        action="gbpay.batch.created",
        entity_type="BillingPayoutBatch",
        entity_id=batch.id,
        actor_id=actor_id,
        employer_id=employer_id,
        meta_new={"batch_type": batch_type, "item_count": len(items)},
    )
    return batch


def process_payout(
    *,
    payout: BillingPayout,
    tenant_db: str,
    actor_id: Optional[int] = None,
    allow_retry: bool = False,
) -> Dict[str, Any]:
    if payout.status == BillingPayout.STATUS_PAID:
        return {"status": "skipped", "reason": "already_paid"}

    provider = (get_payout_provider(employer_id=payout.employer_id, tenant_db=tenant_db, category=payout.category) or "").upper()
    if provider == PROVIDER_MANUAL:
        _ensure_manual_metadata(payout, tenant_db)
        if payout.status != BillingPayout.STATUS_PENDING:
            payout.status = BillingPayout.STATUS_PENDING
            payout.save(using=tenant_db, update_fields=["status", "updated_at"])
        return {"status": "manual", "reason": "manual_mode"}

    payout_method = payout.payout_method or get_default_payout_method(payout.employee, tenant_db=tenant_db)
    if not payout_method:
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason="No payout destination",
            actor_id=actor_id,
        )
        return {"status": "failed", "reason": "no_payout_method"}

    if not payout_method.is_active:
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason="Payout destination inactive",
            actor_id=actor_id,
        )
        return {"status": "failed", "reason": "destination_inactive"}

    if payout_method.verification_status != PayoutMethod.VERIFICATION_VERIFIED:
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason="Payout destination not verified",
            actor_id=actor_id,
        )
        return {"status": "failed", "reason": "destination_not_verified"}

    _ensure_provider_metadata(payout, tenant_db)

    idempotency_key = build_idempotency_key(payout)
    attempt = BillingPaymentAttempt.objects.using(tenant_db).filter(idempotency_key=idempotency_key).first()
    if attempt and attempt.status == BillingPaymentAttempt.STATUS_SUCCESS:
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_PAID,
            provider_reference=attempt.provider_reference,
            actor_id=actor_id,
        )
        return {"status": "skipped", "reason": "already_success"}

    if attempt and attempt.status == BillingPaymentAttempt.STATUS_PENDING:
        return {"status": "skipped", "reason": "already_processing"}

    if attempt and attempt.status == BillingPaymentAttempt.STATUS_FAILED and not allow_retry:
        return {"status": "failed", "reason": "previous_failure"}

    with transaction.atomic(using=tenant_db):
        if not attempt:
            attempt = BillingPaymentAttempt.objects.using(tenant_db).create(
                employer_id=payout.employer_id,
                attempt_type=BillingPaymentAttempt.TYPE_PAYOUT,
                status=BillingPaymentAttempt.STATUS_PENDING,
                payout_method=payout_method,
                payout=payout,
                amount=payout.amount,
                currency=payout.currency,
                provider=PROVIDER_NAME,
                idempotency_key=idempotency_key,
            )
        else:
            attempt.status = BillingPaymentAttempt.STATUS_RETRYING if allow_retry else BillingPaymentAttempt.STATUS_PENDING
            attempt.retry_count = attempt.retry_count + (1 if allow_retry else 0)
            attempt.failure_message = ""
            attempt.failure_code = ""
            attempt.next_retry_at = None
            attempt.save(using=tenant_db, update_fields=[
                "status",
                "retry_count",
                "failure_message",
                "failure_code",
                "next_retry_at",
            ])

    connection = get_active_connection(payout.employer_id, tenant_db)
    if not connection:
        attempt.status = BillingPaymentAttempt.STATUS_FAILED
        attempt.failure_message = "Active GbPay connection not found"
        attempt.save(using=tenant_db, update_fields=["status", "failure_message"])
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason="Active GbPay connection not found",
            actor_id=actor_id,
        )
        return {"status": "failed", "reason": "no_connection"}

    ctx = build_gbpay_context(connection)
    service = GbPayService(ctx)

    transfer = GbPayTransfer.objects.using(tenant_db).create(
        employer_id=payout.employer_id,
        payout=payout,
        attempt=attempt,
        status=GbPayTransfer.STATUS_PENDING,
        provider_status="",
        poll_count=0,
        next_poll_at=_next_poll_at(0),
    )

    transfer_request = build_transfer_request(
        payout=payout,
        payout_method=payout_method,
        employee_name=getattr(payout.employee, "full_name", "") if payout.employee else "",
        idempotency_key=idempotency_key,
    )
    transfer.request_payload = sanitize_payload(transfer_request)
    transfer.save(using=tenant_db, update_fields=["request_payload", "updated_at"])
    _store_transfer_event(transfer, "initiate_request", transfer_request, tenant_db)

    category_type = _resolve_category_type(payout_method.method_type)
    try:
        initiate_resp = service.initiateTransfer(transfer_request, category_type)
    except GbPayApiError as exc:
        transfer.status = GbPayTransfer.STATUS_FAILED
        transfer.failure_message = str(exc)
        transfer.response_payload = sanitize_payload(exc.payload)
        transfer.save(using=tenant_db, update_fields=["status", "failure_message", "response_payload", "updated_at"])
        attempt.status = BillingPaymentAttempt.STATUS_FAILED
        attempt.failure_message = str(exc)
        attempt.save(using=tenant_db, update_fields=["status", "failure_message"])
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason=str(exc),
            actor_id=actor_id,
        )
        emit_metric("gbpay.payout.failed", employer_id=payout.employer_id)
        return {"status": "failed", "reason": "initiate_failed", "stop_batch": is_insufficient_funds(exc.payload, str(exc))}

    transfer.response_payload = sanitize_payload(initiate_resp)
    _store_transfer_event(transfer, "initiate_response", initiate_resp, tenant_db)
    quote_id = _extract_value(initiate_resp, "quoteId", "quote_id", "id")
    transfer.quote_id = quote_id
    transfer.save(using=tenant_db, update_fields=["response_payload", "quote_id", "updated_at"])

    if quote_id:
        payout.metadata = payout.metadata or {}
        payout.metadata["gbpay_quote_id"] = quote_id
        payout.save(using=tenant_db, update_fields=["metadata", "updated_at"])
        for txn in [payout.employer_transaction, payout.employee_transaction]:
            if txn:
                txn.metadata = txn.metadata or {}
                txn.metadata["gbpay_quote_id"] = quote_id
                txn.save(using=tenant_db, update_fields=["metadata", "updated_at"])

    if not quote_id:
        attempt.status = BillingPaymentAttempt.STATUS_FAILED
        attempt.failure_message = "GbPay did not return quoteId"
        attempt.save(using=tenant_db, update_fields=["status", "failure_message"])
        transfer.status = GbPayTransfer.STATUS_FAILED
        transfer.failure_message = "Missing quoteId"
        transfer.save(using=tenant_db, update_fields=["status", "failure_message", "updated_at"])
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason="Missing quoteId",
            actor_id=actor_id,
        )
        emit_metric("gbpay.payout.failed", employer_id=payout.employer_id)
        return {"status": "failed", "reason": "missing_quote"}

    try:
        exec_resp = service.executeTransfer(quote_id)
    except GbPayApiError as exc:
        transfer.status = GbPayTransfer.STATUS_FAILED
        transfer.failure_message = str(exc)
        transfer.response_payload = sanitize_payload(exc.payload)
        transfer.save(using=tenant_db, update_fields=["status", "failure_message", "response_payload", "updated_at"])
        attempt.status = BillingPaymentAttempt.STATUS_FAILED
        attempt.failure_message = str(exc)
        attempt.save(using=tenant_db, update_fields=["status", "failure_message"])
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason=str(exc),
            actor_id=actor_id,
        )
        emit_metric("gbpay.payout.failed", employer_id=payout.employer_id)
        return {"status": "failed", "reason": "execute_failed", "stop_batch": is_insufficient_funds(exc.payload, str(exc))}

    _store_transfer_event(transfer, "execute_response", exec_resp, tenant_db)
    transfer.response_payload = sanitize_payload(exec_resp)
    transaction_reference = _extract_value(exec_resp, "transactionReference", "transaction_reference", "reference")
    transfer.transaction_reference = transaction_reference
    provider_status = _extract_status(exec_resp)
    transfer.provider_status = provider_status
    internal_status, is_terminal = _map_provider_status(provider_status)
    transfer.status = GbPayTransfer.STATUS_SUCCESS if internal_status == "SUCCESS" else (
        GbPayTransfer.STATUS_FAILED if internal_status == "FAILED" else GbPayTransfer.STATUS_PROCESSING
    )
    transfer.save(using=tenant_db, update_fields=[
        "response_payload",
        "transaction_reference",
        "provider_status",
        "status",
        "updated_at",
    ])

    if transaction_reference:
        payout.metadata = payout.metadata or {}
        payout.metadata["gbpay_transaction_reference"] = transaction_reference
        payout.save(using=tenant_db, update_fields=["metadata", "updated_at"])
        for txn in [payout.employer_transaction, payout.employee_transaction]:
            if txn:
                txn.metadata = txn.metadata or {}
                txn.metadata["gbpay_transaction_reference"] = transaction_reference
                txn.save(using=tenant_db, update_fields=["metadata", "updated_at"])

    attempt.provider_reference = transaction_reference or attempt.provider_reference

    if is_terminal and internal_status == "SUCCESS":
        attempt.status = BillingPaymentAttempt.STATUS_SUCCESS
        attempt.save(using=tenant_db, update_fields=["status", "provider_reference"])
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_PAID,
            provider_reference=transaction_reference,
            actor_id=actor_id,
        )
        emit_metric("gbpay.payout.success", employer_id=payout.employer_id)
        return {"status": "success"}

    if is_terminal and internal_status == "FAILED":
        attempt.status = BillingPaymentAttempt.STATUS_FAILED
        attempt.failure_message = "GbPay transfer failed"
        attempt.save(using=tenant_db, update_fields=["status", "provider_reference", "failure_message"])
        update_payout_status(
            payout=payout,
            tenant_db=tenant_db,
            status=BillingPayout.STATUS_FAILED,
            failure_reason="GbPay transfer failed",
            actor_id=actor_id,
        )
        emit_metric("gbpay.payout.failed", employer_id=payout.employer_id)
        return {"status": "failed", "reason": "terminal_failure", "stop_batch": is_insufficient_funds(exec_resp)}

    # Pending -> mark processing and wait for polling
    payout.status = BillingPayout.STATUS_PROCESSING
    payout.save(using=tenant_db, update_fields=["status", "updated_at"])
    attempt.status = BillingPaymentAttempt.STATUS_PENDING
    attempt.save(using=tenant_db, update_fields=["status", "provider_reference"])
    transfer.next_poll_at = _next_poll_at(transfer.poll_count + 1)
    transfer.save(using=tenant_db, update_fields=["next_poll_at", "updated_at"])
    emit_metric("gbpay.payout.pending", employer_id=payout.employer_id)
    return {"status": "pending"}


def update_batch_status_from_payouts(batch: BillingPayoutBatch, tenant_db: str):
    payouts = batch.payouts.all()
    status_counts = {status: payouts.filter(status=status).count() for status in [
        BillingPayout.STATUS_PENDING,
        BillingPayout.STATUS_PROCESSING,
        BillingPayout.STATUS_PAID,
        BillingPayout.STATUS_FAILED,
    ]}

    if status_counts[BillingPayout.STATUS_PENDING] or status_counts[BillingPayout.STATUS_PROCESSING]:
        batch.status = BillingPayoutBatch.STATUS_PROCESSING
    elif status_counts[BillingPayout.STATUS_PAID] and status_counts[BillingPayout.STATUS_FAILED]:
        batch.status = BillingPayoutBatch.STATUS_PARTIAL
        batch.processed_at = timezone.now()
    elif status_counts[BillingPayout.STATUS_PAID]:
        batch.status = BillingPayoutBatch.STATUS_COMPLETED
        batch.processed_at = timezone.now()
    else:
        batch.status = BillingPayoutBatch.STATUS_FAILED
        batch.processed_at = timezone.now()

    batch.save(using=tenant_db, update_fields=["status", "processed_at", "updated_at"])


def process_batch(
    *,
    batch: BillingPayoutBatch,
    tenant_db: str,
    actor_id: Optional[int] = None,
    allow_retry: bool = False,
) -> Dict[str, Any]:
    if batch.status == BillingPayoutBatch.STATUS_COMPLETED:
        return {"status": "skipped", "reason": "already_completed"}

    if batch.requires_approval and not batch.approved_at:
        raise ValidationError("Batch requires approval before processing.")

    provider = (get_payout_provider(employer_id=batch.employer_id, tenant_db=tenant_db, category=batch.batch_type) or "").upper()
    if provider == PROVIDER_NAME and not get_active_connection(batch.employer_id, tenant_db):
        raise ValidationError("Active GbPay connection is required for this payout batch.")

    if provider == PROVIDER_MANUAL:
        if batch.status != BillingPayoutBatch.STATUS_PROCESSING:
            batch.status = BillingPayoutBatch.STATUS_PROCESSING
            batch.save(using=tenant_db, update_fields=["status", "updated_at"])
        return {"status": "manual", "reason": "manual_mode"}

    batch.status = BillingPayoutBatch.STATUS_PROCESSING
    batch.save(using=tenant_db, update_fields=["status", "updated_at"])

    stop_batch = False
    for payout in batch.payouts.select_related("employee", "payout_method").all():
        if payout.status == BillingPayout.STATUS_PAID:
            continue
        result = process_payout(
            payout=payout,
            tenant_db=tenant_db,
            actor_id=actor_id,
            allow_retry=allow_retry,
        )
        if result.get("stop_batch"):
            stop_batch = True
            batch.metadata = batch.metadata or {}
            batch.metadata["stop_reason"] = "INSUFFICIENT_FUNDS"
            batch.save(using=tenant_db, update_fields=["metadata", "updated_at"])
            break

    if stop_batch:
        paid_count = batch.payouts.filter(status=BillingPayout.STATUS_PAID).count()
        batch.status = BillingPayoutBatch.STATUS_PARTIAL if paid_count else BillingPayoutBatch.STATUS_FAILED
        batch.processed_at = timezone.now()
        batch.save(using=tenant_db, update_fields=["status", "processed_at", "updated_at"])
    else:
        update_batch_status_from_payouts(batch, tenant_db)
    _maybe_notify_failure_rate(batch, tenant_db)
    return {"status": batch.status, "stop_batch": stop_batch}


def _maybe_notify_failure_rate(batch: BillingPayoutBatch, tenant_db: str):
    try:
        total = batch.payouts.count()
        if total < FAILURE_ALERT_MIN_COUNT:
            return
        failed = batch.payouts.filter(status=BillingPayout.STATUS_FAILED).count()
        if total == 0:
            return
        failure_rate = failed / float(total)
        metadata = batch.metadata or {}
        if metadata.get("failure_alert_sent"):
            return
        if failure_rate < FAILURE_ALERT_THRESHOLD:
            return
        notify_employer_owner(
            employer_id=batch.employer_id,
            title="High payout failure rate detected",
            body=f"{failed} of {total} payouts failed in batch {batch.id}.",
            notification_type="ALERT",
            data={
                "batch_id": str(batch.id),
                "failed": failed,
                "total": total,
                "failure_rate": round(failure_rate, 2),
            },
        )
        metadata["failure_alert_sent"] = True
        metadata["failure_rate"] = round(failure_rate, 4)
        batch.metadata = metadata
        batch.save(using=tenant_db, update_fields=["metadata", "updated_at"])
    except Exception:
        return


def poll_pending_transfers(
    *,
    tenant_db: str,
    employer_id: Optional[int] = None,
    limit: int = 50,
    max_pending_hours: int = 24,
) -> int:
    now = timezone.now()
    qs = GbPayTransfer.objects.using(tenant_db).filter(
        status__in=[GbPayTransfer.STATUS_PENDING, GbPayTransfer.STATUS_PROCESSING],
        next_poll_at__lte=now,
    )
    if employer_id:
        qs = qs.filter(employer_id=employer_id)
    transfers = qs.order_by("next_poll_at")[:limit]
    processed = 0

    for transfer in transfers:
        processed += 1
        if transfer.created_at and transfer.created_at < now - timedelta(hours=max_pending_hours):
            transfer.status = GbPayTransfer.STATUS_TIMEOUT
            transfer.failure_message = "Polling timeout"
            transfer.save(using=tenant_db, update_fields=["status", "failure_message", "updated_at"])
            if transfer.payout:
                update_payout_status(
                    payout=transfer.payout,
                    tenant_db=tenant_db,
                    status=BillingPayout.STATUS_FAILED,
                    failure_reason="Polling timeout",
                )
                if transfer.payout.batch:
                    update_batch_status_from_payouts(transfer.payout.batch, tenant_db)
            emit_metric("gbpay.payout.timeout", employer_id=transfer.employer_id)
            _maybe_notify_timeout(transfer, tenant_db)
            continue

        connection = get_active_connection(transfer.employer_id, tenant_db)
        if not connection or not transfer.transaction_reference:
            continue

        ctx = build_gbpay_context(connection)
        service = GbPayService(ctx)
        try:
            status_resp = service.getTransactionStatus(transfer.transaction_reference)
        except GbPayApiError as exc:
            transfer.poll_count += 1
            transfer.last_polled_at = now
            transfer.next_poll_at = _next_poll_at(transfer.poll_count)
            transfer.status_payload = sanitize_payload(exc.payload)
            transfer.save(using=tenant_db, update_fields=[
                "poll_count",
                "last_polled_at",
                "next_poll_at",
                "status_payload",
                "updated_at",
            ])
            continue

        transfer.status_payload = sanitize_payload(status_resp)
        transfer.provider_status = _extract_status(status_resp)
        internal_status, is_terminal = _map_provider_status(transfer.provider_status)
        transfer.poll_count += 1
        transfer.last_polled_at = now
        transfer.next_poll_at = _next_poll_at(transfer.poll_count)
        transfer.save(using=tenant_db, update_fields=[
            "status_payload",
            "provider_status",
            "poll_count",
            "last_polled_at",
            "next_poll_at",
            "updated_at",
        ])

        if not is_terminal:
            emit_metric("gbpay.payout.pending", employer_id=transfer.employer_id)
            continue

        if internal_status == "SUCCESS":
            transfer.status = GbPayTransfer.STATUS_SUCCESS
            transfer.save(using=tenant_db, update_fields=["status", "updated_at"])
            if transfer.attempt:
                transfer.attempt.status = BillingPaymentAttempt.STATUS_SUCCESS
                transfer.attempt.provider_reference = transfer.transaction_reference
                transfer.attempt.save(using=tenant_db, update_fields=["status", "provider_reference"])
            if transfer.payout:
                update_payout_status(
                    payout=transfer.payout,
                    tenant_db=tenant_db,
                    status=BillingPayout.STATUS_PAID,
                    provider_reference=transfer.transaction_reference,
                )
                if transfer.payout.batch:
                    update_batch_status_from_payouts(transfer.payout.batch, tenant_db)
            emit_metric("gbpay.payout.success", employer_id=transfer.employer_id)
        else:
            transfer.status = GbPayTransfer.STATUS_FAILED
            transfer.failure_message = "GbPay transfer failed"
            transfer.save(using=tenant_db, update_fields=["status", "failure_message", "updated_at"])
            if transfer.attempt:
                transfer.attempt.status = BillingPaymentAttempt.STATUS_FAILED
                transfer.attempt.failure_message = "GbPay transfer failed"
                transfer.attempt.save(using=tenant_db, update_fields=["status", "failure_message"])
            if transfer.payout:
                update_payout_status(
                    payout=transfer.payout,
                    tenant_db=tenant_db,
                    status=BillingPayout.STATUS_FAILED,
                    failure_reason="GbPay transfer failed",
                )
                if transfer.payout.batch:
                    update_batch_status_from_payouts(transfer.payout.batch, tenant_db)
            emit_metric("gbpay.payout.failed", employer_id=transfer.employer_id)

    return processed


def _maybe_notify_timeout(transfer: GbPayTransfer, tenant_db: str):
    event_log = list(transfer.event_log or [])
    if any(event.get("type") == "timeout_notified" for event in event_log):
        return
    notify_employer_owner(
        employer_id=transfer.employer_id,
        title="GbPay payout polling timeout",
        body=f"Payout transfer {transfer.id} timed out while awaiting confirmation.",
        notification_type="ALERT",
        data={
            "transfer_id": str(transfer.id),
            "payout_id": str(transfer.payout_id) if transfer.payout_id else None,
            "transaction_reference": transfer.transaction_reference,
        },
    )
    event_log.append({"type": "timeout_notified", "at": timezone.now().isoformat()})
    transfer.event_log = event_log
    transfer.save(using=tenant_db, update_fields=["event_log", "updated_at"])
