import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

def _notifications_enabled(contract):
    try:
        return bool(contract.get_effective_config('enable_notifications', True))
    except Exception:
        return True

def _notify_employer(contract, title, body='', *, type='INFO', data=None):
    try:
        from accounts.models import EmployerProfile
        from employees.utils import notify_employer_users
        employer = EmployerProfile.objects.using('default').filter(id=contract.employer_id).first()
        if employer:
            notify_employer_users(
                employer,
                title,
                body=body,
                type=type,
                data=data or {},
            )
    except Exception:
        logger.exception("Failed to send employer notification for contract %s", getattr(contract, "contract_id", None))

def _notify_employee(contract, title, body='', *, type='INFO', data=None):
    try:
        from accounts.models import EmployerProfile
        from employees.utils import notify_employee_user
        employer = EmployerProfile.objects.using('default').filter(id=contract.employer_id).first()
        notify_employee_user(
            contract.employee,
            title,
            body=body,
            type=type,
            data=data or {},
            employer_profile=employer,
        )
    except Exception:
        logger.exception("Failed to send employee notification for contract %s", getattr(contract, "contract_id", None))

def _base_payload(contract, extra=None):
    payload = {
        "contract_id": str(getattr(contract, "id", "")),
        "contract_display_id": getattr(contract, "contract_id", None),
        "employee_id": str(getattr(contract, "employee_id", "")) if getattr(contract, "employee_id", None) else None,
        "status": getattr(contract, "status", None),
    }
    if extra:
        payload.update(extra)
    return payload

def notify_contract_created(contract):
    """Notify employer and employee that a contract was created."""
    if not _notifications_enabled(contract):
        return

    title = f"Contract {contract.contract_id} created"
    body = f"New contract created for {contract.employee}."
    data = _base_payload(contract, {"event": "contracts.created"})
    _notify_employer(contract, title, body, type="INFO", data=data)
    _notify_employee(contract, title, body, type="INFO", data=data)

def notify_sent_for_approval(contract):
    """Notify employer-side approvers that a contract is pending approval."""
    if not _notifications_enabled(contract):
        return

    title = f"Contract {contract.contract_id} pending approval"
    body = f"Contract for {contract.employee} requires approval."
    data = _base_payload(contract, {"event": "contracts.sent_for_approval"})
    _notify_employer(contract, title, body, type="ALERT", data=data)

def notify_signature_captured(contract, role=None):
    """Notify employer/employee when a signature is captured."""
    if not _notifications_enabled(contract):
        return

    role_label = (role or '').upper()
    title = f"Contract {contract.contract_id} signature received"
    body = f"{role_label or 'A party'} signed the contract for {contract.employee}."
    data = _base_payload(contract, {"event": "contracts.signature_captured", "role": role_label})
    _notify_employer(contract, title, body, type="INFO", data=data)
    _notify_employee(contract, title, body, type="INFO", data=data)

def notify_signature_reminder(contract, days_left=None, expires_on=None):
    """Notify parties that a contract signature is still pending."""
    if not _notifications_enabled(contract):
        return

    title = f"Signature reminder: {contract.contract_id}"
    body = f"Signature is still pending for {contract.employee}."
    data = _base_payload(
        contract,
        {
            "event": "contracts.signature_reminder",
            "days_left": days_left,
            "expires_on": str(expires_on) if expires_on else None,
        },
    )
    _notify_employer(contract, title, body, type="ALERT", data=data)
    _notify_employee(contract, title, body, type="ALERT", data=data)

def notify_signature_expired(contract, expired_on=None):
    """Notify parties that a contract signature request expired."""
    if not _notifications_enabled(contract):
        return

    title = f"Signature expired: {contract.contract_id}"
    body = f"Signature request for {contract.employee} has expired."
    data = _base_payload(
        contract,
        {
            "event": "contracts.signature_expired",
            "expired_on": str(expired_on) if expired_on else None,
        },
    )
    _notify_employer(contract, title, body, type="ALERT", data=data)
    _notify_employee(contract, title, body, type="ALERT", data=data)

def notify_terminated(contract):
    """Notify parties that a contract was terminated."""
    if not _notifications_enabled(contract):
        return

    title = f"Contract {contract.contract_id} terminated"
    body = f"Contract for {contract.employee} has been terminated."
    data = _base_payload(contract, {"event": "contracts.terminated"})
    _notify_employer(contract, title, body, type="ALERT", data=data)
    _notify_employee(contract, title, body, type="ALERT", data=data)

def notify_expired(contract):
    """Notify parties that a contract expired."""
    if not _notifications_enabled(contract):
        return

    title = f"Contract {contract.contract_id} expired"
    body = f"Contract for {contract.employee} has expired."
    data = _base_payload(contract, {"event": "contracts.expired"})
    _notify_employer(contract, title, body, type="INFO", data=data)
    _notify_employee(contract, title, body, type="INFO", data=data)

def notify_renewed(contract, *, mode=None):
    """Notify parties that a contract was renewed or extended."""
    if not _notifications_enabled(contract):
        return

    title = f"Contract {contract.contract_id} renewed"
    body = f"Contract for {contract.employee} was renewed."
    data = _base_payload(contract, {"event": "contracts.renewed", "mode": mode})
    _notify_employer(contract, title, body, type="INFO", data=data)
    _notify_employee(contract, title, body, type="INFO", data=data)

def notify_sent_for_signature(contract):
    """
    Notify relevant parties that a contract has been sent for signature.
    """
    subject = f"Contract {contract.contract_id} Sent for Signature"
    message = f"The contract for {contract.employee} has been sent for signature."
    recipient_list = [contract.employee.email] if hasattr(contract.employee, 'email') and contract.employee.email else []
    
    logger.info(f"Sending notification: {subject}")
    
    if not _notifications_enabled(contract):
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return

    data = _base_payload(contract, {"event": "contracts.sent_for_signature"})
    _notify_employer(contract, subject, message, type="ALERT", data=data)
    _notify_employee(contract, subject, message, type="ALERT", data=data)
    
    # In a real app, we might check settings.DEBUG or similar before sending
    try:
        # Fail silently to avoid breaking the flow if mail server isn't configured
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=True
        )
    except Exception as e:
        logger.error(f"Failed to send notification for contract {contract.contract_id}: {e}")

def notify_signed(contract):
    """
    Notify relevant parties that a contract has been signed.
    """
    subject = f"Contract {contract.contract_id} Signed"
    message = f"The contract for {contract.employee} has been signed."
    recipient_list = [] # Add HR or manager emails here
    
    if hasattr(contract.employee, 'email') and contract.employee.email:
        recipient_list.append(contract.employee.email)

    logger.info(f"Sending notification: {subject}")

    if not _notifications_enabled(contract):
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return

    data = _base_payload(contract, {"event": "contracts.signed"})
    _notify_employer(contract, subject, message, type="INFO", data=data)
    _notify_employee(contract, subject, message, type="INFO", data=data)

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=True
        )
    except Exception as e:
        logger.error(f"Failed to send notification for contract {contract.contract_id}: {e}")

def notify_activated(contract):
    """
    Notify relevant parties that a contract has been activated.
    """
    subject = f"Contract {contract.contract_id} Activated"
    message = f"The contract for {contract.employee} is now active."
    recipient_list = []
    
    if hasattr(contract.employee, 'email') and contract.employee.email:
        recipient_list.append(contract.employee.email)

    logger.info(f"Sending notification: {subject}")

    if not _notifications_enabled(contract):
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return

    data = _base_payload(contract, {"event": "contracts.activated"})
    _notify_employer(contract, subject, message, type="INFO", data=data)
    _notify_employee(contract, subject, message, type="INFO", data=data)

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=True
        )
    except Exception as e:
        logger.error(f"Failed to send notification for contract {contract.contract_id}: {e}")

def notify_expiring_soon(contract):
    """
    Notify relevant parties that a contract is expiring soon.
    """
    subject = f"Contract {contract.contract_id} Expiring Soon"
    message = f"The contract for {contract.employee} is expiring on {contract.end_date}."
    recipient_list = []
    
    if hasattr(contract.employee, 'email') and contract.employee.email:
        recipient_list.append(contract.employee.email)

    logger.info(f"Sending notification: {subject}")

    if not _notifications_enabled(contract):
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return

    days_left = None
    try:
        if contract.end_date:
            from django.utils import timezone as _tz
            days_left = (contract.end_date - _tz.now().date()).days
    except Exception:
        days_left = None

    data = _base_payload(
        contract,
        {"event": "contracts.expiring_soon", "end_date": str(contract.end_date), "days_left": days_left},
    )
    _notify_employer(contract, subject, message, type="ALERT", data=data)
    _notify_employee(contract, subject, message, type="ALERT", data=data)

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=True
        )
    except Exception as e:
        logger.error(f"Failed to send notification for contract {contract.contract_id}: {e}")
