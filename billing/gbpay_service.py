import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache

try:
    import requests
except Exception:  # pragma: no cover - dependency managed via requirements
    requests = None

logger = logging.getLogger(__name__)


class GbPayApiError(Exception):
    def __init__(self, message: str, *, status_code: Optional[int] = None, code: str = "", payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code or ""
        self.payload = payload


@dataclass
class EmployerGbPayContext:
    employer_id: int
    connection_id: str
    credentials: Dict[str, Any]
    environment: str
    base_url: str


class GbPayTokenStore:
    def __init__(self, cache_backend=None):
        self.cache = cache_backend or cache

    def _key(self, connection_id: str) -> str:
        return f"gbpay:token:{connection_id}"

    def get(self, connection_id: str) -> Optional[str]:
        data = self.cache.get(self._key(connection_id))
        if not data:
            return None
        expires_at = data.get("expires_at")
        if not expires_at or expires_at <= time.time() + 30:
            return None
        return data.get("token")

    def set(self, connection_id: str, token: str, expires_in: int):
        expires_in = max(60, int(expires_in or 3600))
        payload = {"token": token, "expires_at": time.time() + expires_in}
        self.cache.set(self._key(connection_id), payload, timeout=expires_in)


class GbPayService:
    def __init__(self, context: EmployerGbPayContext, token_store: Optional[GbPayTokenStore] = None, session=None):
        if requests is None:
            raise RuntimeError("requests is required for GbPayService but is not installed.")
        self.context = context
        self.token_store = token_store or GbPayTokenStore()
        self.session = session or requests.Session()
        self.timeout = 30
        self.endpoints = getattr(
            settings,
            "GBPAY_ENDPOINTS",
            {
                "authenticate": "",
                "countries": "/countries",
                "category_products": "/categories/{category}/products",
                "banks": "/banks",
                "operators": "/operators",
                "lookup": "/accounts/lookup",
                "initiate_transfer": "/transfers/initiate",
                "execute_transfer": "/transfers/execute",
                "transaction_status": "/transfers/{transactionReference}/status",
                "cancel_cashout": "/transfers/cancel",
                "transfer_fee": "/transfers/fee",
                "supported_currencies": "/countries/{countryCode}/currencies",
            },
        )

    def _build_url(self, path: str) -> str:
        base = (self.context.base_url or "").rstrip("/")
        raw_path = path or ""
        if raw_path == "/":
            return f"{base}/"
        path = raw_path.lstrip("/")
        if not path:
            return base
        return f"{base}/{path}"

    def _auth_fallback_paths(self, primary: str) -> list:
        candidates = []
        primary = primary or ""
        if primary in ("", "/"):
            candidates.extend(["/", "/authenticate", "/auth"])
        else:
            candidates.extend(["", "/", "/authenticate", "/auth"])
        seen = set()
        ordered = []
        for item in candidates:
            if item == primary:
                continue
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        url = self._build_url(path)
        hdrs = {"Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        if auth:
            hdrs.update(self.createAuthenticatedHeaders())
        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                headers=hdrs,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise GbPayApiError(f"GbPay request failed: {exc}") from exc

        payload = {}
        if response.content:
            try:
                payload = response.json()
            except Exception:
                payload = {"raw": response.text}

        if response.status_code >= 400:
            code = ""
            if isinstance(payload, dict):
                code = payload.get("code") or payload.get("errorCode") or payload.get("error_code") or ""
            raise GbPayApiError(
                f"GbPay request failed with status {response.status_code}.",
                status_code=response.status_code,
                code=code,
                payload=payload,
            )

        return payload

    def authenticate(self) -> str:
        token = self.token_store.get(self.context.connection_id)
        if token:
            return token

        creds = self.context.credentials or {}
        payload = {
            "username": creds.get("api_key") or creds.get("apiKey") or creds.get("username"),
            "password": creds.get("secret_key") or creds.get("secretKey") or creds.get("password"),
            "scope": creds.get("scope") or creds.get("auth_scope"),
        }
        payload = {key: value for key, value in payload.items() if value not in (None, "")}
        response = None
        primary_path = self.endpoints.get("authenticate", "")
        try:
            response = self._request(
                "post",
                primary_path,
                json=payload,
                auth=False,
            )
        except GbPayApiError as exc:
            if exc.status_code != 404:
                raise
            last_exc = exc
            for alt_path in self._auth_fallback_paths(primary_path):
                try:
                    response = self._request(
                        "post",
                        alt_path,
                        json=payload,
                        auth=False,
                    )
                    primary_path = alt_path
                    break
                except GbPayApiError as alt_exc:
                    last_exc = alt_exc
                    if alt_exc.status_code != 404:
                        raise
            if response is None:
                raise last_exc
        token = response.get("accessToken") or response.get("token") or response.get("access_token")
        if not token:
            raise GbPayApiError("GbPay authentication did not return an access token.", payload=response)
        expires_in = response.get("expiresIn") or response.get("expires_in") or 3600
        self.token_store.set(self.context.connection_id, token, int(expires_in))
        return token

    def createAuthenticatedHeaders(self) -> Dict[str, str]:
        token = self.authenticate()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def getCountries(self, providerType: Optional[str] = None) -> Dict[str, Any]:
        if getattr(settings, "GBPAY_MOCK_MODE", False):
            return {"data": getattr(settings, "GBPAY_MOCK_COUNTRIES", [])}
        params = {"type": providerType} if providerType else None
        return self._request("get", self.endpoints["countries"], params=params)

    def getCategoryProducts(self, category: str, countryId: str) -> Dict[str, Any]:
        params = {"category": category, "countryId": countryId}
        return self._request("get", self.endpoints["category_products"], params=params)

    def getSimplifiedBanksByCountry(self, countryId: str) -> Dict[str, Any]:
        if getattr(settings, "GBPAY_MOCK_MODE", False):
            return {"data": getattr(settings, "GBPAY_MOCK_BANKS", [])}
        response = self.getCategoryProducts("ACCOUNT_TRANSFER", countryId)
        items = response
        if isinstance(response, dict):
            items = response.get("data") or response.get("content") or response
        banks = []
        if isinstance(items, list):
            for product in items:
                if not isinstance(product, dict):
                    continue
                provider = product.get("gimacProviderReference") or {}
                if not isinstance(provider, dict):
                    provider = {}
                provider_id = provider.get("id") or provider.get("providerId")
                provider_code = provider.get("code") or provider.get("bankCode")
                bank_code = provider_code or provider_id
                name = provider.get("name") or product.get("name")
                emitter = product.get("emitterType") or {}
                if not isinstance(emitter, dict):
                    emitter = {}
                banks.append(
                    {
                        "bankCode": bank_code,
                        "code": provider_code or bank_code,
                        "name": name,
                        "providerId": provider_id,
                        "providerCountry": provider.get("country"),
                        "providerType": provider.get("type"),
                        "entityProductUuid": product.get("entityProduct") or product.get("entityProductUuid"),
                        "emitterType": emitter.get("uuid") or emitter.get("id"),
                    }
                )
        return {"data": banks}

    def getSimplifiedOperatorsByCountry(self, countryId: str) -> Dict[str, Any]:
        if getattr(settings, "GBPAY_MOCK_MODE", False):
            return {"data": getattr(settings, "GBPAY_MOCK_OPERATORS", [])}
        response = self.getCategoryProducts("ACCOUNT_TO_WALLET", countryId)
        items = response
        if isinstance(response, dict):
            items = response.get("data") or response.get("content") or response
        operators = []
        if isinstance(items, list):
            for product in items:
                if not isinstance(product, dict):
                    continue
                provider = product.get("gimacProviderReference") or {}
                if not isinstance(provider, dict):
                    provider = {}
                provider_id = provider.get("id") or provider.get("providerId")
                provider_code = provider.get("code") or provider.get("operatorCode")
                operator_code = provider_code or provider_id
                name = provider.get("name") or product.get("name")
                emitter = product.get("emitterType") or {}
                if not isinstance(emitter, dict):
                    emitter = {}
                operators.append(
                    {
                        "operatorCode": operator_code,
                        "code": provider_code or operator_code,
                        "name": name,
                        "providerId": provider_id,
                        "providerCountry": provider.get("country"),
                        "providerType": provider.get("type"),
                        "entityProductUuid": product.get("entityProduct") or product.get("entityProductUuid"),
                        "emitterType": emitter.get("uuid") or emitter.get("id"),
                    }
                )
        return {"data": operators}

    def lookupAccount(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "bankAccountDestination": payload.get("bankAccountDestination") or payload.get("accountNumber"),
            "walletDestination": payload.get("walletDestination"),
            "entityProduct": payload.get("entityProduct") or payload.get("entityProductUuid"),
            "bankCode": payload.get("bankCode"),
            "operatorCode": payload.get("operatorCode"),
            "country": payload.get("country") or payload.get("countryCode"),
        }
        params = {key: value for key, value in params.items() if value not in (None, "")}
        return self._request("get", self.endpoints["lookup"], params=params)

    def initiateTransfer(self, transferRequest: Dict[str, Any], categoryType: str) -> Dict[str, Any]:
        return self._request("post", self.endpoints["initiate_transfer"], json=transferRequest)

    def executeTransfer(self, quoteId: str) -> Dict[str, Any]:
        return self._request("post", self.endpoints["execute_transfer"], json={"quote": quoteId})

    def getTransactionStatus(self, transactionReference: str) -> Dict[str, Any]:
        path = self.endpoints["transaction_status"].format(transactionReference=transactionReference)
        return self._request("get", path)

    def cancelCashOut(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("post", self.endpoints["cancel_cashout"], json=payload)

    def calculateTransferFee(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("post", self.endpoints["transfer_fee"], json=payload)

    def getSupportedCurrencies(self, countryCode: str) -> Dict[str, Any]:
        path = self.endpoints["supported_currencies"].format(countryCode=countryCode)
        return self._request("get", path)
