import base64
import hashlib
import json
import logging
from typing import Any, Dict

from django.conf import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - runtime dependency handled by requirements
    Fernet = None
    InvalidToken = Exception

logger = logging.getLogger(__name__)


def _derive_key_from_secret(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_encryption_key() -> bytes:
    key = getattr(settings, "GBPAY_ENCRYPTION_KEY", "") or getattr(settings, "ENCRYPTION_KEY", "")
    if not key:
        key = _derive_key_from_secret(getattr(settings, "SECRET_KEY", ""))
        logger.warning("GBPAY_ENCRYPTION_KEY not set; using derived key from SECRET_KEY.")
    if isinstance(key, str):
        key = key.encode("utf-8")
    return key


_FERNET = None


def _get_fernet():
    global _FERNET
    if _FERNET is None:
        if Fernet is None:
            raise RuntimeError("cryptography is required for encryption but is not installed.")
        _FERNET = Fernet(_get_encryption_key())
    return _FERNET


def encrypt_value(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    return _get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str) -> str:
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt value with provided key.")
        return ""


def encrypt_json(data: Dict[str, Any]) -> str:
    try:
        payload = json.dumps(data or {})
    except Exception:
        payload = "{}"
    return encrypt_value(payload)


def decrypt_json(token: str) -> Dict[str, Any]:
    raw = decrypt_value(token)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}
