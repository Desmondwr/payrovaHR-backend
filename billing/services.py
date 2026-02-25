import calendar
import json
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import EmployerProfile
from accounts.rbac import get_active_employer, is_delegate_user

from .models import (
    BillingAuditLog,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPaymentAttempt,
    BillingPayout,
    BillingPayoutBatch,
    BillingPayoutConfiguration,
    BillingPlan,
    BillingSequence,
    BillingTransaction,
    EmployerSubscription,
    FundingMethod,
    PayoutMethod,
)


def resolve_institution(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        raise ValidationError("Authentication required.")

    if getattr(user, "employer_profile", None):
        return user.employer_profile

    resolved = get_active_employer(request, require_context=False)
    if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
        return resolved

    employee = getattr(user, "employee_profile", None)
    if employee and getattr(employee, "employer_id", None):
        institution = EmployerProfile.objects.filter(id=employee.employer_id).first()
        if institution:
            return institution

    raise ValidationError("Unable to resolve institution.")


def _decimal_amount(value):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        raise ValidationError("Amount must be a valid number.")


def _add_months(base_date, months):
    year = base_date.year + (base_date.month - 1 + months) // 12
    month = (base_date.month - 1 + months) % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_interval(base_date, interval, count):
    if not base_date:
        return None
    count = max(1, int(count or 1))
    if interval == BillingPlan.INTERVAL_MONTHLY:
        return _add_months(base_date, count)
    if interval == BillingPlan.INTERVAL_QUARTERLY:
        return _add_months(base_date, 3 * count)
    if interval == BillingPlan.INTERVAL_YEARLY:
        return date(base_date.year + count, base_date.month, base_date.day)
    return _add_months(base_date, count)


def _serialize_meta(data):
    try:
        return json.dumps(data or {})
    except Exception:
        return ""


def log_billing_action(
    *,
    tenant_db,
    action,
    entity_type,
    entity_id,
    actor_id=None,
    employer_id=None,
    employee=None,
    meta_old=None,
    meta_new=None,
    request=None,
):
    return BillingAuditLog.objects.using(tenant_db).create(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor_id=actor_id,
        employer_id=employer_id,
        employee=employee,
        meta_old=_serialize_meta(meta_old),
        meta_new=_serialize_meta(meta_new),
        ip_address=getattr(request, "META", {}).get("REMOTE_ADDR") if request else None,
        user_agent=getattr(request, "META", {}).get("HTTP_USER_AGENT") if request else "",
    )


def notify_employer_owner(*, employer_id, title, body="", notification_type="ALERT", data=None):
    try:
        employer = EmployerProfile.objects.filter(id=employer_id).first()
    except Exception:
        employer = None
    if not employer or not getattr(employer, "user", None):
        return None
    try:
        from accounts.notifications import create_notification
    except Exception:
        return None
    return create_notification(
        user=employer.user,
        title=title,
        body=body or "",
        type=notification_type,
        data=data or {},
        employer_profile=employer,
    )


def set_default_funding_method(method, *, tenant_db, scope, actor_id=None, request=None):
    if not isinstance(method, FundingMethod):
        raise ValidationError("Invalid funding method.")
    scope = (scope or "").upper()
    if scope not in {"SUBSCRIPTION", "PAYROLL"}:
        raise ValidationError("Scope must be SUBSCRIPTION or PAYROLL.")

    with transaction.atomic(using=tenant_db):
        qs = FundingMethod.objects.using(tenant_db).filter(employer_id=method.employer_id, is_active=True)
        if scope == "SUBSCRIPTION":
            qs.update(is_default_subscription=False)
            method.is_default_subscription = True
        else:
            qs.update(is_default_payroll=False)
            method.is_default_payroll = True
        method.save(using=tenant_db, update_fields=["is_default_subscription", "is_default_payroll", "updated_at"])

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.funding_method.default_changed",
        entity_type="FundingMethod",
        entity_id=method.id,
        actor_id=actor_id,
        employer_id=method.employer_id,
        meta_new={"scope": scope},
        request=request,
    )
    return method


def set_default_payout_method(method, *, tenant_db, actor_id=None, request=None):
    if not isinstance(method, PayoutMethod):
        raise ValidationError("Invalid payout method.")

    with transaction.atomic(using=tenant_db):
        PayoutMethod.objects.using(tenant_db).filter(employee=method.employee, is_active=True).update(is_default=False)
        method.is_default = True
        method.save(using=tenant_db, update_fields=["is_default", "updated_at"])

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.payout_method.default_changed",
        entity_type="PayoutMethod",
        entity_id=method.id,
        actor_id=actor_id,
        employer_id=getattr(method.employee, "employer_id", None),
        employee=method.employee,
        request=request,
    )
    return method


def get_default_funding_method(employer_id, *, tenant_db, scope):
    scope = (scope or "").upper()
    qs = FundingMethod.objects.using(tenant_db).filter(employer_id=employer_id, is_active=True)
    if scope == "SUBSCRIPTION":
        return qs.filter(is_default_subscription=True).first()
    return qs.filter(is_default_payroll=True).first()


def get_default_payout_method(employee, *, tenant_db):
    if not employee:
        return None
    return (
        PayoutMethod.objects.using(tenant_db)
        .filter(employee=employee, is_active=True, is_default=True)
        .first()
    )


def ensure_billing_payout_configuration(*, employer_id, tenant_db):
    config = (
        BillingPayoutConfiguration.objects.using(tenant_db)
        .filter(employer_id=employer_id, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if config:
        return config
    return BillingPayoutConfiguration.objects.using(tenant_db).create(
        employer_id=employer_id,
        is_active=True,
    )


def get_payout_provider(*, employer_id, tenant_db, category):
    config = ensure_billing_payout_configuration(employer_id=employer_id, tenant_db=tenant_db)
    if category == BillingPayout.CATEGORY_EXPENSE:
        return config.expense_provider
    return config.payroll_provider


def generate_invoice_number(*, employer_id, tenant_db):
    key = timezone.now().strftime("%Y%m")
    with transaction.atomic(using=tenant_db):
        seq, _ = BillingSequence.objects.using(tenant_db).select_for_update().get_or_create(
            employer_id=employer_id,
            key=key,
            defaults={"last_number": 0},
        )
        seq.last_number += 1
        seq.save(using=tenant_db, update_fields=["last_number", "updated_at"])
        return f"INV-{key}-{seq.last_number:04d}"


def render_invoice_pdf(invoice, line_items, employer_name=""):
    title = f"Invoice {invoice.number}"
    body_lines = [
        f"Employer: {employer_name}",
        f"Invoice: {invoice.number}",
        f"Status: {invoice.status}",
        f"Period: {invoice.period_start} - {invoice.period_end}",
        "",
        "Items:",
    ]
    for item in line_items:
        body_lines.append(f"- {item.description}: {item.quantity} x {item.unit_price} = {item.amount}")
    body_lines.append("")
    body_lines.append(f"Subtotal: {invoice.subtotal} {invoice.currency}")
    body_lines.append(f"Tax: {invoice.tax_amount} {invoice.currency}")
    body_lines.append(f"Total: {invoice.total_amount} {invoice.currency}")

    body = "\n".join(body_lines)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from io import BytesIO

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        y = 800
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, title)
        y -= 24
        pdf.setFont("Helvetica", 10)
        for line in body.split("\n"):
            pdf.drawString(40, y, line)
            y -= 14
            if y < 40:
                pdf.showPage()
                y = 800
        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return ContentFile(buffer.read())
    except Exception:
        return ContentFile(_basic_pdf_bytes(title, body))


def render_payout_batch_pdf(batch, payouts, employer_name=""):
    title = f"Payout Batch {batch.id}"
    body_lines = [
        f"Employer: {employer_name}",
        f"Batch type: {batch.batch_type}",
        f"Status: {batch.status}",
        f"Planned date: {batch.planned_date}",
        f"Total amount: {batch.total_amount} {batch.currency}",
        "",
        "Payouts:",
    ]
    for payout in payouts:
        employee_name = getattr(payout.employee, "full_name", None) or getattr(payout.employee, "email", None) or str(payout.employee_id or "")
        line = (
            f"- {employee_name}: {payout.amount} {payout.currency} "
            f"{payout.status} {payout.provider_reference or ''}".strip()
        )
        body_lines.append(line)
    body = "\n".join(body_lines)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from io import BytesIO

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        y = 800
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, title)
        y -= 24
        pdf.setFont("Helvetica", 10)
        for line in body.split("\n"):
            pdf.drawString(40, y, line)
            y -= 14
            if y < 40:
                pdf.showPage()
                y = 800
        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return ContentFile(buffer.read())
    except Exception:
        return ContentFile(_basic_pdf_bytes(title, body))


def render_payout_batch_csv(batch, payouts):
    import csv
    from io import StringIO

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Payout ID",
            "Employee",
            "Category",
            "Amount",
            "Currency",
            "Status",
            "Provider",
            "Provider Reference",
            "Failure Reason",
            "Created At",
        ]
    )
    for payout in payouts:
        employee_name = getattr(payout.employee, "full_name", None) or getattr(payout.employee, "email", None) or ""
        writer.writerow(
            [
                payout.id,
                employee_name,
                payout.category,
                payout.amount,
                payout.currency,
                payout.status,
                payout.provider,
                payout.provider_reference,
                payout.failure_reason,
                payout.created_at.isoformat() if payout.created_at else "",
            ]
        )
    return buffer.getvalue().encode("utf-8")

def _basic_pdf_bytes(title, body):
    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    objects = []

    def _obj(data):
        idx = len(objects) + 1
        objects.append((idx, data))
        return idx

    font_obj = _obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    contents = f"BT /F1 12 Tf 50 750 Td ({title}) Tj\n".encode("ascii", "ignore")
    y = 730
    for line in body.split("\n"):
        safe = line.replace("(", "[").replace(")", "]")
        contents += f"50 {y} Td ({safe}) Tj\n".encode("ascii", "ignore")
        y -= 14
    contents += b"ET"
    contents_obj = _obj(b"<< /Length %d >>\nstream\n" % len(contents) + contents + b"\nendstream")
    page_obj = _obj(
        b"<< /Type /Page /Parent 4 0 R /Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
        % (font_obj, contents_obj)
    )
    pages_obj = _obj(b"<< /Type /Pages /Kids [ %d 0 R ] /Count 1 >>" % page_obj)
    _obj(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj)

    offsets = [0]
    for idx, obj_bytes in objects:
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode("ascii"))
        pdf.extend(obj_bytes)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.extend(b"trailer\n<< /Size %d /Root %d 0 R >>\n" % (len(offsets), len(objects)))
    pdf.extend(b"startxref\n" + str(xref_start).encode("ascii") + b"\n%%EOF\n")
    return bytes(pdf)


def generate_payout_receipt_number(*, employer_id, tenant_db):
    key = timezone.now().strftime("RCT%Y%m")
    with transaction.atomic(using=tenant_db):
        seq, _ = BillingSequence.objects.using(tenant_db).select_for_update().get_or_create(
            employer_id=employer_id,
            key=key,
            defaults={"last_number": 0},
        )
        seq.last_number += 1
        seq.save(using=tenant_db, update_fields=["last_number", "updated_at"])
        return f"RCT-{timezone.now().strftime('%Y%m')}-{seq.last_number:04d}"


def render_payout_receipt_pdf(payout, employer_name="", employee_name=""):
    title = f"Payout Receipt {payout.receipt_number or payout.id}"
    body_lines = [
        f"Employer: {employer_name}",
        f"Employee: {employee_name}",
        f"Payout ID: {payout.id}",
        f"Category: {payout.category}",
        f"Amount: {payout.amount} {payout.currency}",
        f"Status: {payout.status}",
        f"Provider Ref: {payout.provider_reference or ''}",
        f"Processed At: {payout.processed_at or ''}",
    ]
    body = "\n".join(body_lines)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from io import BytesIO

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        y = 800
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, title)
        y -= 24
        pdf.setFont("Helvetica", 10)
        for line in body.split("\n"):
            pdf.drawString(40, y, line)
            y -= 14
            if y < 40:
                pdf.showPage()
                y = 800
        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return ContentFile(buffer.read())
    except Exception:
        return ContentFile(_basic_pdf_bytes(title, body))


def generate_payout_receipt(*, payout, tenant_db):
    if payout.receipt_file:
        return payout
    receipt_number = generate_payout_receipt_number(employer_id=payout.employer_id, tenant_db=tenant_db)
    employer = EmployerProfile.objects.filter(id=payout.employer_id).first()
    employee_name = getattr(payout.employee, "full_name", "") if payout.employee else ""
    pdf_content = render_payout_receipt_pdf(
        payout,
        employer_name=getattr(employer, "company_name", ""),
        employee_name=employee_name,
    )
    payout.receipt_number = receipt_number
    payout.receipt_issued_at = timezone.now()
    payout.receipt_file.save(f"{receipt_number}.pdf", pdf_content)
    payout.save(using=tenant_db, update_fields=["receipt_number", "receipt_file", "receipt_issued_at", "updated_at"])
    return payout


def create_invoice_for_subscription(
    *,
    subscription,
    tenant_db,
    actor_id=None,
    auto_charge=True,
    request=None,
):
    if not isinstance(subscription, EmployerSubscription):
        raise ValidationError("Invalid subscription.")

    plan = subscription.plan
    if not plan:
        raise ValidationError("Subscription plan is missing.")

    start = subscription.current_period_start or subscription.billing_cycle_anchor or timezone.now().date()
    period_end = _add_interval(start, plan.interval, plan.interval_count) - timedelta(days=1)
    next_billing = period_end + timedelta(days=1)

    number = generate_invoice_number(employer_id=subscription.employer_id, tenant_db=tenant_db)
    subtotal = _decimal_amount(plan.price)
    tax_amount = (subtotal * (plan.tax_rate / Decimal("100.00"))).quantize(Decimal("0.01"))
    total = subtotal + tax_amount

    with transaction.atomic(using=tenant_db):
        invoice = BillingInvoice.objects.using(tenant_db).create(
            employer_id=subscription.employer_id,
            subscription=subscription,
            period_start=start,
            period_end=period_end,
            number=number,
            status=BillingInvoice.STATUS_ISSUED,
            currency=plan.currency,
            subtotal=subtotal,
            tax_rate=plan.tax_rate,
            tax_amount=tax_amount,
            total_amount=total,
            issued_at=timezone.now(),
            is_finalized=True,
        )

        BillingInvoiceLine.objects.using(tenant_db).create(
            invoice=invoice,
            description=f"{plan.name} subscription ({plan.interval.lower()})",
            quantity=Decimal("1.00"),
            unit_price=subtotal,
            amount=subtotal,
        )

        employer = EmployerProfile.objects.filter(id=subscription.employer_id).first()
        pdf_content = render_invoice_pdf(invoice, invoice.line_items.all(), employer_name=getattr(employer, "company_name", ""))
        invoice.pdf_file.save(f"{invoice.number}.pdf", pdf_content)
        invoice.save(using=tenant_db, update_fields=["pdf_file", "updated_at"])

        subscription.current_period_start = start
        subscription.current_period_end = period_end
        subscription.next_billing_date = next_billing
        subscription.save(using=tenant_db, update_fields=["current_period_start", "current_period_end", "next_billing_date", "updated_at"])

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.invoice.issued",
        entity_type="BillingInvoice",
        entity_id=invoice.id,
        actor_id=actor_id,
        employer_id=subscription.employer_id,
        meta_new={"invoice_number": invoice.number},
        request=request,
    )

    if auto_charge:
        attempt_subscription_charge(
            invoice=invoice,
            tenant_db=tenant_db,
            actor_id=actor_id,
            request=request,
        )

    return invoice


def attempt_subscription_charge(*, invoice, tenant_db, actor_id=None, request=None):
    subscription = invoice.subscription
    if not subscription:
        raise ValidationError("Invoice is not linked to a subscription.")

    funding_method = subscription.default_funding_method or get_default_funding_method(
        subscription.employer_id,
        tenant_db=tenant_db,
        scope="SUBSCRIPTION",
    )

    with transaction.atomic(using=tenant_db):
        if not funding_method:
            txn = BillingTransaction.objects.using(tenant_db).create(
                employer_id=subscription.employer_id,
                account_role=BillingTransaction.ROLE_EMPLOYER,
                direction=BillingTransaction.DIRECTION_DEBIT,
                category=BillingTransaction.CATEGORY_SUBSCRIPTION,
                status=BillingTransaction.STATUS_FAILED,
                amount=invoice.total_amount,
                currency=invoice.currency,
                description="Subscription charge failed: no default funding method.",
                invoice=invoice,
            )
            BillingPaymentAttempt.objects.using(tenant_db).create(
                employer_id=subscription.employer_id,
                attempt_type=BillingPaymentAttempt.TYPE_SUBSCRIPTION,
                status=BillingPaymentAttempt.STATUS_FAILED,
                funding_method=None,
                invoice=invoice,
                amount=invoice.total_amount,
                currency=invoice.currency,
                failure_message="No default funding method",
            )
            subscription.status = EmployerSubscription.STATUS_PAST_DUE
            subscription.save(using=tenant_db, update_fields=["status", "updated_at"])
            invoice.status = BillingInvoice.STATUS_FAILED
            invoice.save(using=tenant_db, update_fields=["status", "updated_at"])

            log_billing_action(
                tenant_db=tenant_db,
                action="billing.subscription.charge_failed",
                entity_type="BillingInvoice",
                entity_id=invoice.id,
                actor_id=actor_id,
                employer_id=subscription.employer_id,
                meta_new={"reason": "no_funding_method"},
                request=request,
            )
            return txn

        txn = BillingTransaction.objects.using(tenant_db).create(
            employer_id=subscription.employer_id,
            account_role=BillingTransaction.ROLE_EMPLOYER,
            direction=BillingTransaction.DIRECTION_DEBIT,
            category=BillingTransaction.CATEGORY_SUBSCRIPTION,
            status=BillingTransaction.STATUS_PENDING,
            amount=invoice.total_amount,
            currency=invoice.currency,
            description="Subscription charge pending.",
            provider=funding_method.provider,
            invoice=invoice,
        )
        BillingPaymentAttempt.objects.using(tenant_db).create(
            employer_id=subscription.employer_id,
            attempt_type=BillingPaymentAttempt.TYPE_SUBSCRIPTION,
            status=BillingPaymentAttempt.STATUS_PENDING,
            funding_method=funding_method,
            invoice=invoice,
            amount=invoice.total_amount,
            currency=invoice.currency,
            provider=funding_method.provider,
        )

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.subscription.charge_initiated",
        entity_type="BillingInvoice",
        entity_id=invoice.id,
        actor_id=actor_id,
        employer_id=subscription.employer_id,
        meta_new={"funding_method_id": str(funding_method.id)},
        request=request,
    )
    return txn


def mark_invoice_paid(*, invoice, tenant_db, provider_reference=None, actor_id=None, request=None):
    with transaction.atomic(using=tenant_db):
        invoice.status = BillingInvoice.STATUS_PAID
        invoice.paid_at = timezone.now()
        invoice.save(using=tenant_db, update_fields=["status", "paid_at", "updated_at"])

        BillingTransaction.objects.using(tenant_db).filter(
            invoice=invoice,
            status=BillingTransaction.STATUS_PENDING,
        ).update(status=BillingTransaction.STATUS_SUCCESS, provider_reference=provider_reference or "")

        subscription = invoice.subscription
        if subscription:
            subscription.status = EmployerSubscription.STATUS_ACTIVE
            subscription.save(using=tenant_db, update_fields=["status", "updated_at"])

        BillingPaymentAttempt.objects.using(tenant_db).filter(
            invoice=invoice,
            status__in=[BillingPaymentAttempt.STATUS_PENDING, BillingPaymentAttempt.STATUS_RETRYING],
        ).update(status=BillingPaymentAttempt.STATUS_SUCCESS, provider_reference=provider_reference or "")

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.invoice.paid",
        entity_type="BillingInvoice",
        entity_id=invoice.id,
        actor_id=actor_id,
        employer_id=invoice.employer_id,
        meta_new={"provider_reference": provider_reference},
        request=request,
    )


def mark_invoice_failed(*, invoice, tenant_db, failure_reason=None, actor_id=None, request=None):
    with transaction.atomic(using=tenant_db):
        invoice.status = BillingInvoice.STATUS_FAILED
        invoice.save(using=tenant_db, update_fields=["status", "updated_at"])

        BillingTransaction.objects.using(tenant_db).filter(
            invoice=invoice,
            status=BillingTransaction.STATUS_PENDING,
        ).update(status=BillingTransaction.STATUS_FAILED)

        subscription = invoice.subscription
        if subscription:
            subscription.status = EmployerSubscription.STATUS_PAST_DUE
            subscription.save(using=tenant_db, update_fields=["status", "updated_at"])

        BillingPaymentAttempt.objects.using(tenant_db).filter(
            invoice=invoice,
            status__in=[BillingPaymentAttempt.STATUS_PENDING, BillingPaymentAttempt.STATUS_RETRYING],
        ).update(status=BillingPaymentAttempt.STATUS_FAILED, failure_message=failure_reason or "")

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.invoice.failed",
        entity_type="BillingInvoice",
        entity_id=invoice.id,
        actor_id=actor_id,
        employer_id=invoice.employer_id,
        meta_new={"reason": failure_reason},
        request=request,
    )


def create_refund_transaction(*, original_txn, tenant_db, actor_id=None, reason=None):
    if not original_txn:
        raise ValidationError("Original transaction required.")
    if original_txn.status == BillingTransaction.STATUS_REVERSED:
        return None

    reverse_direction = (
        BillingTransaction.DIRECTION_CREDIT
        if original_txn.direction == BillingTransaction.DIRECTION_DEBIT
        else BillingTransaction.DIRECTION_DEBIT
    )

    refund_txn = BillingTransaction.objects.using(tenant_db).create(
        employer_id=original_txn.employer_id,
        employee=original_txn.employee,
        account_role=original_txn.account_role,
        direction=reverse_direction,
        category=BillingTransaction.CATEGORY_REFUND,
        status=BillingTransaction.STATUS_SUCCESS,
        amount=original_txn.amount,
        currency=original_txn.currency,
        description=reason or "Refund",
        reversal_of=original_txn,
        invoice=original_txn.invoice,
    )
    original_txn.status = BillingTransaction.STATUS_REVERSED
    original_txn.save(using=tenant_db, update_fields=["status", "updated_at"])

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.transaction.refund",
        entity_type="BillingTransaction",
        entity_id=original_txn.id,
        actor_id=actor_id,
        employer_id=original_txn.employer_id,
        meta_new={"refund_id": str(refund_txn.id), "reason": reason},
    )
    return refund_txn


def create_payout_with_transactions(
    *,
    tenant_db,
    employer_id,
    employee,
    amount,
    currency,
    category,
    payout_method=None,
    batch=None,
    linked_object_type="NONE",
    linked_object_id=None,
    treasury_payment_line_id=None,
    treasury_batch_id=None,
    actor_id=None,
):
    amount_value = _decimal_amount(amount)
    category = (category or "").upper()
    if category not in {BillingTransaction.CATEGORY_PAYROLL, BillingTransaction.CATEGORY_EXPENSE}:
        raise ValidationError("Invalid payout category.")
    payout_method = payout_method or get_default_payout_method(employee, tenant_db=tenant_db)
    provider = get_payout_provider(employer_id=employer_id, tenant_db=tenant_db, category=category)
    provider = (provider or "").upper()
    payout_metadata = {}
    if provider == BillingPayoutConfiguration.PROVIDER_MANUAL:
        payout_metadata["payout_mode"] = BillingPayoutConfiguration.PROVIDER_MANUAL

    with transaction.atomic(using=tenant_db):
        payout = BillingPayout.objects.using(tenant_db).create(
            employer_id=employer_id,
            employee=employee,
            payout_method=payout_method,
            batch=batch,
            category=category,
            status=BillingPayout.STATUS_PENDING,
            amount=amount_value,
            currency=currency,
            provider=provider or "",
            linked_object_type=linked_object_type,
            linked_object_id=linked_object_id,
            treasury_payment_line_id=treasury_payment_line_id,
            treasury_batch_id=treasury_batch_id,
            metadata=payout_metadata,
        )

        employer_txn = BillingTransaction.objects.using(tenant_db).create(
            employer_id=employer_id,
            employee=employee,
            account_role=BillingTransaction.ROLE_EMPLOYER,
            direction=BillingTransaction.DIRECTION_DEBIT,
            category=category,
            status=BillingTransaction.STATUS_PENDING,
            amount=amount_value,
            currency=currency,
            description="Payout initiated",
            payout=payout,
            provider=provider or "",
        )

        employee_txn = BillingTransaction.objects.using(tenant_db).create(
            employer_id=employer_id,
            employee=employee,
            account_role=BillingTransaction.ROLE_EMPLOYEE,
            direction=BillingTransaction.DIRECTION_CREDIT,
            category=category,
            status=BillingTransaction.STATUS_PENDING,
            amount=amount_value,
            currency=currency,
            description="Payout pending",
            payout=payout,
            provider=provider or "",
        )

        payout.employer_transaction = employer_txn
        payout.employee_transaction = employee_txn
        payout.save(using=tenant_db, update_fields=["employer_transaction", "employee_transaction", "updated_at"])

        if batch:
            batch.total_amount = _decimal_amount(batch.total_amount) + amount_value
            batch.save(using=tenant_db, update_fields=["total_amount", "updated_at"])

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.payout.created",
        entity_type="BillingPayout",
        entity_id=payout.id,
        actor_id=actor_id,
        employer_id=employer_id,
        employee=employee,
        meta_new={"amount": str(amount_value), "currency": currency},
    )
    return payout


def update_payout_status(
    *,
    payout,
    tenant_db,
    status,
    provider_reference=None,
    failure_reason=None,
    idempotency_key=None,
    actor_id=None,
    request=None,
):
    status = (status or "").upper()
    if status not in {"PAID", "FAILED", "REVERSED"}:
        raise ValidationError("Invalid payout status.")

    payout.metadata = payout.metadata or {}
    is_manual_mode = (payout.provider or "").upper() == BillingPayoutConfiguration.PROVIDER_MANUAL or (
        payout.metadata.get("payout_mode") == BillingPayoutConfiguration.PROVIDER_MANUAL
    )
    if is_manual_mode:
        if idempotency_key:
            existing_key = payout.metadata.get("manual_idempotency_key")
            if existing_key and existing_key == idempotency_key and payout.status == status:
                return payout
            if existing_key and existing_key != idempotency_key and payout.status == status:
                raise ValidationError("Payout status already updated.")
            payout.metadata["manual_idempotency_key"] = idempotency_key
        if payout.provider != BillingPayoutConfiguration.PROVIDER_MANUAL:
            payout.provider = BillingPayoutConfiguration.PROVIDER_MANUAL

    with transaction.atomic(using=tenant_db):
        payout.status = status
        payout.processed_at = timezone.now()
        if provider_reference:
            payout.provider_reference = provider_reference
        if failure_reason and status == "FAILED":
            payout.failure_reason = failure_reason
        payout.save(
            using=tenant_db,
            update_fields=[
                "status",
                "processed_at",
                "provider_reference",
                "failure_reason",
                "metadata",
                "provider",
                "updated_at",
            ],
        )

        if payout.employer_transaction:
            payout.employer_transaction.status = (
                BillingTransaction.STATUS_SUCCESS if status == "PAID" else BillingTransaction.STATUS_FAILED
            )
            if status == "REVERSED":
                payout.employer_transaction.status = BillingTransaction.STATUS_REVERSED
            if is_manual_mode and payout.employer_transaction.provider != BillingPayoutConfiguration.PROVIDER_MANUAL:
                payout.employer_transaction.provider = BillingPayoutConfiguration.PROVIDER_MANUAL
            if provider_reference:
                payout.employer_transaction.provider_reference = provider_reference
            payout.employer_transaction.save(
                using=tenant_db,
                update_fields=["status", "provider_reference", "provider", "updated_at"],
            )

        if payout.employee_transaction:
            payout.employee_transaction.status = (
                BillingTransaction.STATUS_SUCCESS if status == "PAID" else BillingTransaction.STATUS_FAILED
            )
            if status == "REVERSED":
                payout.employee_transaction.status = BillingTransaction.STATUS_REVERSED
            if is_manual_mode and payout.employee_transaction.provider != BillingPayoutConfiguration.PROVIDER_MANUAL:
                payout.employee_transaction.provider = BillingPayoutConfiguration.PROVIDER_MANUAL
            if provider_reference:
                payout.employee_transaction.provider_reference = provider_reference
            payout.employee_transaction.save(
                using=tenant_db,
                update_fields=["status", "provider_reference", "provider", "updated_at"],
            )

        if status == "REVERSED":
            if payout.employer_transaction:
                create_refund_transaction(
                    original_txn=payout.employer_transaction,
                    tenant_db=tenant_db,
                    actor_id=actor_id,
                    reason="Payout reversed",
                )
            if payout.employee_transaction:
                create_refund_transaction(
                    original_txn=payout.employee_transaction,
                    tenant_db=tenant_db,
                    actor_id=actor_id,
                    reason="Payout reversed",
                )

    if status == "PAID":
        try:
            generate_payout_receipt(payout=payout, tenant_db=tenant_db)
        except Exception:
            # Receipt generation failure should not block payout status update
            pass

    log_billing_action(
        tenant_db=tenant_db,
        action="billing.payout.status_updated",
        entity_type="BillingPayout",
        entity_id=payout.id,
        actor_id=actor_id,
        employer_id=payout.employer_id,
        employee=payout.employee,
        meta_new={"status": status, "reason": failure_reason},
        request=request,
    )
    return payout


def ensure_payout_batch(
    *,
    tenant_db,
    employer_id,
    batch_type,
    treasury_batch_id=None,
    created_by_id=None,
):
    qs = BillingPayoutBatch.objects.using(tenant_db).filter(
        employer_id=employer_id,
        batch_type=batch_type,
    )
    if treasury_batch_id:
        existing = qs.filter(treasury_batch_id=treasury_batch_id).first()
        if existing:
            return existing

    provider = get_payout_provider(employer_id=employer_id, tenant_db=tenant_db, category=batch_type)
    requires_approval = provider == BillingPayoutConfiguration.PROVIDER_GBPAY
    return BillingPayoutBatch.objects.using(tenant_db).create(
        employer_id=employer_id,
        batch_type=batch_type,
        status=BillingPayoutBatch.STATUS_APPROVAL_PENDING if requires_approval else BillingPayoutBatch.STATUS_DRAFT,
        requires_approval=requires_approval,
        planned_date=timezone.now().date(),
        created_by_id=created_by_id,
        treasury_batch_id=treasury_batch_id,
    )
