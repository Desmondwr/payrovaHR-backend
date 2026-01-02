import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

def notify_sent_for_signature(contract):
    """
    Notify relevant parties that a contract has been sent for signature.
    """
    subject = f"Contract {contract.contract_id} Sent for Signature"
    message = f"The contract for {contract.employee} has been sent for signature."
    recipient_list = [contract.employee.email] if hasattr(contract.employee, 'email') and contract.employee.email else []
    
    logger.info(f"Sending notification: {subject}")
    
    config = contract.get_config()
    if config and not config.enable_notifications:
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return
    
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

    config = contract.get_config()
    if config and not config.enable_notifications:
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return

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

    config = contract.get_config()
    if config and not config.enable_notifications:
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return

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

    config = contract.get_config()
    if config and not config.enable_notifications:
        logger.info(f"Notifications disabled for employer {contract.employer_id}. Skipping.")
        return

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
