"""M-Pesa Daraja (Safaricom) behind a Protocol (ADR-0015).

``DarajaClient`` talks to the sandbox or production API with the tenant's own app keys; ``SimulatorClient``
behaves like the sandbox without the network (local development, tests, demos; refused in production).
Amounts are whole shillings: M-Pesa does not take cents.
"""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

import httpx

Environment = Literal["sandbox", "production", "simulator"]
BASE_URLS = {
    "sandbox": "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}


# Result codes that mean "the customer has not answered yet" (seen on the sandbox and in production).
STILL_PROCESSING = frozenset({4999})


class DarajaError(RuntimeError):
    """Daraja refused or failed a request; ``detail`` is safe to show to the tenant."""

    def __init__(self, detail: str, *, status: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


@dataclass(frozen=True, slots=True)
class Credentials:
    environment: Environment
    consumer_key: str
    consumer_secret: str
    business_shortcode: str  # Paybill number, or the store number of a Till
    passkey: str
    party_b: str  # Paybill: the same shortcode; Till: the till number
    transaction_type: Literal["CustomerPayBillOnline", "CustomerBuyGoodsOnline"]


@dataclass(frozen=True, slots=True)
class StkAccepted:
    merchant_request_id: str
    checkout_request_id: str
    customer_message: str


@dataclass(frozen=True, slots=True)
class StkStatus:
    """``result_code`` 0 = paid; 1032 = cancelled by the customer; 1037 = no response; None = still pending."""

    result_code: int | None
    result_desc: str


class MpesaClient(Protocol):
    async def check_credentials(self) -> None: ...

    async def stk_push(
        self,
        *,
        phone: str,
        amount: int,
        account_reference: str,
        description: str,
        callback_url: str,
    ) -> StkAccepted: ...

    async def stk_query(self, checkout_request_id: str) -> StkStatus: ...

    async def register_c2b(self, *, confirmation_url: str, validation_url: str) -> None: ...


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%Y%m%d%H%M%S")


def stk_password(shortcode: str, passkey: str, timestamp: str) -> str:
    return base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()


# Tokens are cached per app key for their lifetime (~1 hour) minus a margin.
_TOKENS: dict[tuple[str, str], tuple[str, float]] = {}


@dataclass
class DarajaClient:
    credentials: Credentials
    http: httpx.AsyncClient
    timeout: float = 15.0

    @property
    def _base(self) -> str:
        return BASE_URLS[self.credentials.environment]

    async def _token(self) -> str:
        key = (self.credentials.environment, self.credentials.consumer_key)
        cached = _TOKENS.get(key)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        try:
            response = await self.http.get(
                f"{self._base}/oauth/v1/generate",
                params={"grant_type": "client_credentials"},
                auth=(self.credentials.consumer_key, self.credentials.consumer_secret),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise DarajaError(f"M-Pesa could not be reached ({type(exc).__name__})") from None
        if response.status_code != httpx.codes.OK:
            raise DarajaError(
                "M-Pesa rejected the consumer key or secret", status=response.status_code
            )
        data = response.json()
        token = str(data["access_token"])
        _TOKENS[key] = (token, time.monotonic() + int(data.get("expires_in", 3599)) - 60)
        return token

    async def _post(self, path: str, body: dict[str, object]) -> dict[str, Any]:
        token = await self._token()
        try:
            response = await self.http.post(
                f"{self._base}{path}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise DarajaError(f"M-Pesa could not be reached ({type(exc).__name__})") from None
        try:
            data: dict[str, Any] = response.json() if response.content else {}
        except ValueError:
            data = {}
        if response.status_code >= httpx.codes.BAD_REQUEST:
            fault = data.get("fault") if isinstance(data.get("fault"), dict) else {}
            message = str(
                data.get("errorMessage")
                or data.get("ResultDesc")
                or (fault or {}).get("faultstring")
                or f"request refused (HTTP {response.status_code})"
            )
            raise DarajaError(f"M-Pesa: {message}", status=response.status_code)
        return data

    async def check_credentials(self) -> None:
        await self._token()

    async def stk_push(
        self,
        *,
        phone: str,
        amount: int,
        account_reference: str,
        description: str,
        callback_url: str,
    ) -> StkAccepted:
        c = self.credentials
        timestamp = _timestamp()
        data = await self._post(
            "/mpesa/stkpush/v1/processrequest",
            {
                "BusinessShortCode": c.business_shortcode,
                "Password": stk_password(c.business_shortcode, c.passkey, timestamp),
                "Timestamp": timestamp,
                "TransactionType": c.transaction_type,
                "Amount": amount,
                "PartyA": phone,
                "PartyB": c.party_b,
                "PhoneNumber": phone,
                "CallBackURL": callback_url,
                "AccountReference": account_reference[:12],
                "TransactionDesc": description[:13],
            },
        )
        if str(data.get("ResponseCode")) != "0":
            raise DarajaError(f"M-Pesa: {data.get('ResponseDescription', 'prompt not sent')}")
        return StkAccepted(
            merchant_request_id=str(data["MerchantRequestID"]),
            checkout_request_id=str(data["CheckoutRequestID"]),
            customer_message=str(data.get("CustomerMessage", "")),
        )

    async def stk_query(self, checkout_request_id: str) -> StkStatus:
        c = self.credentials
        timestamp = _timestamp()
        try:
            data = await self._post(
                "/mpesa/stkpushquery/v1/query",
                {
                    "BusinessShortCode": c.business_shortcode,
                    "Password": stk_password(c.business_shortcode, c.passkey, timestamp),
                    "Timestamp": timestamp,
                    "CheckoutRequestID": checkout_request_id,
                },
            )
        except DarajaError as exc:
            # "The transaction is being processed" comes back as an error until the customer answers.
            if "being processed" in exc.detail.lower():
                return StkStatus(result_code=None, result_desc="Waiting for the customer")
            raise
        code = int(str(data["ResultCode"])) if data.get("ResultCode") is not None else None
        if code in STILL_PROCESSING:
            code = None
        return StkStatus(result_code=code, result_desc=str(data.get("ResultDesc", "")))

    async def register_c2b(self, *, confirmation_url: str, validation_url: str) -> None:
        await self._post(
            "/mpesa/c2b/v2/registerurl",
            {
                "ShortCode": self.credentials.party_b,
                "ResponseType": "Completed",
                "ConfirmationURL": confirmation_url,
                "ValidationURL": validation_url,
            },
        )


@dataclass
class SimulatorClient:
    """Answers like Daraja without a network. Every prompt is paid ("1" in the description: cancelled)."""

    requests: dict[str, tuple[int, str]] = field(default_factory=dict)

    async def check_credentials(self) -> None:
        return None

    async def stk_push(
        self,
        *,
        phone: str,
        amount: int,
        account_reference: str,
        description: str,
        callback_url: str,
    ) -> StkAccepted:
        checkout = f"ws_CO_SIM_{secrets.token_hex(8)}"
        self.requests[checkout] = (amount, phone)
        return StkAccepted(
            merchant_request_id=f"SIM-{secrets.token_hex(4)}",
            checkout_request_id=checkout,
            customer_message="Success. Request accepted for processing",
        )

    async def stk_query(self, checkout_request_id: str) -> StkStatus:
        if not checkout_request_id.startswith("ws_CO_SIM_"):
            raise DarajaError("M-Pesa: unknown request")
        return StkStatus(
            result_code=0, result_desc="The service request is processed successfully."
        )

    async def register_c2b(self, *, confirmation_url: str, validation_url: str) -> None:
        return None


def simulated_receipt(checkout_request_id: str) -> str:
    """A receipt-like code for a simulated payment ('SIM' + 7 characters derived from the prompt): the same
    prompt always gets the same receipt, so it is recorded once."""
    return "SIM" + hashlib.sha256(checkout_request_id.encode()).hexdigest()[:7].upper()


def client_for(credentials: Credentials, http: httpx.AsyncClient) -> MpesaClient:
    if credentials.environment == "simulator":
        return SimulatorClient()
    return DarajaClient(credentials, http)
