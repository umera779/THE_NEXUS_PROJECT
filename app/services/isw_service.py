from __future__ import annotations

import difflib
import hashlib
import hmac
import logging
import time
import uuid
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── ISW base URLs ─────────────────────────────────────────────────────────────
# The requery / transfer API always points at the configured base URL.
_REQUERY_BASE = settings.ISW_REQUERY_BASE_URL.rstrip("/")

# OAuth2 token endpoint (same host as requery in both TEST and LIVE)
_PASSPORT_URL = f"{_REQUERY_BASE}/passport/oauth/token"

# Transfer / funds-disbursement endpoint
_TRANSFER_URL = f"{_REQUERY_BASE}/api/v2/quickteller/payments/disbursements"

# ── ISW Marketplace Identity API (account resolve + bank list) ────────────────
# Separate host from the core Quickteller APIs.
_MARKETPLACE_BASE = getattr(
    settings,
    "ISW_MARKETPLACE_BASE_URL",
    "https://api-marketplace-routing.k8.isw.la",
).rstrip("/")

_BANK_LIST_URL   = f"{_MARKETPLACE_BASE}/marketplace-routing/api/v1/verify/identity/account-number/bank-list"
_RESOLVE_ACC_URL = f"{_MARKETPLACE_BASE}/marketplace-routing/api/v1/verify/identity/account-number/resolve"



class ISWError(Exception):
    """Raised when Interswitch returns an error or an unexpected response."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)



def verify_webhook_signature(payload_bytes: bytes, header_hash: str) -> bool:
    """
    Interswitch signs the raw JSON body with HMAC-SHA512 using the webhook secret.
    The hex-encoded result is sent in the X-Interswitch-Signature header.
    """
    if not header_hash:
        return False
    if not settings.ISW_WEBHOOK_SECRET:
        logger.warning("ISW_WEBHOOK_SECRET not set — skipping webhook signature check")
        return True

    # hmac imported at top
    expected = hmac.new(
        key=settings.ISW_WEBHOOK_SECRET.encode(),
        msg=payload_bytes,
        digestmod=hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, header_hash.lower())


def build_payment_request(
    txn_ref: str,
    amount_kobo: int,
    customer_email: str,
) -> dict:
    """
    Returns the dict that the front-end passes to ``window.webpayCheckout()``.
    The ``onComplete`` callback and script URL are handled in the Jinja template.
    """
    return {
        "merchant_code": settings.ISW_MERCHANT_CODE,
        "pay_item_id": settings.ISW_PAY_ITEM_ID,
        "txn_ref": txn_ref,
        "amount": amount_kobo,          # in kobo (lowest denomination)
        "currency": 566,                # NGN ISO 4217 numeric code
        "cust_email": customer_email,
        "pay_item_name": "Legacy Portal — Wallet Funding",
        "site_redirect_url": f"{settings.BASE_URL}/payment/callback",
        "mode": settings.ISW_MODE,
    }



async def requery_transaction(txn_ref: str, amount_kobo: int) -> dict:
    """
    Calls the Interswitch requery endpoint to confirm a payment.

    Returns the raw ``data`` dict from the response.
    Raises :class:`ISWError` on network or API errors.

    Response fields of interest:
        - ``ResponseCode``  — "00" means success
        - ``Amount``        — amount in kobo; verify it matches what we expect
        - ``MerchantReference`` — should equal our txn_ref
        - ``PaymentReference``  — ISW's own reference (store for reconciliation)
    """
    url = (
        f"{_REQUERY_BASE}/collections?merchantcode={settings.ISW_MERCHANT_CODE}"
        f"&transactionreference={txn_ref}&amount={amount_kobo}"
    )

    logger.info("ISW requery → %s", url)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(
            url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    logger.info("ISW requery ← HTTP %s", r.status_code)

    if r.status_code not in (200, 201):
        raise ISWError(f"Requery HTTP {r.status_code}", r.status_code)

    body = r.json()
    return body  # caller inspects ResponseCode


def is_successful_payment(requery_response: dict) -> bool:
    """Returns True only when Interswitch confirms the payment succeeded."""
    return requery_response.get("ResponseCode") == "00"




_token_cache: dict = {}  


async def _get_access_token() -> str:
    """
    Obtains (or returns a cached) OAuth2 client_credentials token from ISW Passport.
    Caches the token until 60 seconds before its expiry.
    """
    now = time.monotonic()
    cached = _token_cache.get("token")
    expires_at = _token_cache.get("expires_at", 0)

    if cached and now < expires_at:
        return cached

    if not settings.ISW_CLIENT_ID or not settings.ISW_CLIENT_SECRET:
        raise ISWError("ISW_CLIENT_ID / ISW_CLIENT_SECRET not configured", 500)

    logger.info("Requesting new ISW OAuth2 token from %s", _PASSPORT_URL)

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            _PASSPORT_URL,
            data={
                "grant_type": "client_credentials",
                "scope": "profile",
            },
            auth=(settings.ISW_CLIENT_ID, settings.ISW_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if r.status_code not in (200, 201):
        raise ISWError(f"ISW OAuth2 error HTTP {r.status_code}: {r.text}", r.status_code)

    body = r.json()
    token = body.get("access_token")
    expires_in = int(body.get("expires_in", 3600))

    if not token:
        raise ISWError("ISW OAuth2 response missing access_token")

    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expires_in - 60   # refresh 60 s early

    logger.info("ISW OAuth2 token acquired, expires in %d s", expires_in)
    return token


# ─────────────────────────────────────────────────────────────────────────────
# Funds Transfer / Disbursement
# ─────────────────────────────────────────────────────────────────────────────

async def initiate_transfer(
    amount_kobo: int,
    beneficiary_name: str,
    account_number: str,
    bank_code: str,
    narration: str = "Legacy Portal — Inheritance Disbursement",
    reference: Optional[str] = None,
) -> dict:
    """
    Sends money to a beneficiary bank account via the Interswitch
    Quickteller disbursement API.

    Args:
        amount_kobo:      Amount in kobo (₦1 = 100 kobo).
        beneficiary_name: Full name on the destination account.
        account_number:   10-digit NUBAN account number.
        bank_code:        ISW / CBN bank code (e.g. "058" for GTBank).
        narration:        Payment narration (max ~50 chars).
        reference:        Unique transfer reference; auto-generated if omitted.

    Returns:
        The parsed JSON response body from ISW.

    Raises:
        ISWError: On any non-2xx response or missing fields.
    """
    if reference is None:
        reference = f"NXS-{uuid.uuid4().hex[:16].upper()}"

    token = await _get_access_token()

    payload = {
        "terminalId": settings.ISW_TERMINAL_ID,
        "initiatingEntityCode": settings.ISW_INITIATING_ENTITY_CODE,
        "beneficiaries": [
            {
                "uniqueReference": reference,
                "beneficiaryName": beneficiary_name,
                "beneficiaryAccountNumber": account_number,
                "beneficiaryBankCode": bank_code,
                "narration": narration,
                "amount": str(amount_kobo),   # ISW expects a string here
                "currencyCode": "566",        # NGN
            }
        ],
    }

    logger.info("ISW transfer → %s | ref=%s | amount_kobo=%d", _TRANSFER_URL, reference, amount_kobo)

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            _TRANSFER_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    logger.info("ISW transfer ← HTTP %s | ref=%s", r.status_code, reference)

    if r.status_code not in (200, 201, 202):
        raise ISWError(
            f"ISW transfer HTTP {r.status_code}: {r.text[:200]}",
            r.status_code,
        )

    body = r.json()
    return body


async def verify_transfer(reference: str) -> dict:
    """
    Re-queries the status of a previously initiated transfer.
    Returns the raw ISW response body.
    """
    token = await _get_access_token()
    url = f"{_TRANSFER_URL}/{reference}"

    logger.info("ISW transfer verify → %s", url)

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )

    if r.status_code not in (200, 201):
        raise ISWError(f"ISW transfer verify HTTP {r.status_code}", r.status_code)

    return r.json()



# ─────────────────────────────────────────────────────────────────────────────
# Bank list (live from ISW Marketplace) + fuzzy name matching
# ─────────────────────────────────────────────────────────────────────────────

# Module-level cache: {"banks": [...], "fetched_at": float}
_bank_list_cache: dict = {}
_BANK_LIST_TTL = 3600  # re-fetch at most once per hour


async def get_supported_banks(*, force_refresh: bool = False) -> list[dict]:
    """
    Fetches the list of banks supported by the ISW Marketplace Identity API.

    The result is cached for ``_BANK_LIST_TTL`` seconds so repeated calls
    within a session do not hit the network.

    Each entry in the returned list contains at least:
        ``code``  — bank code to use in :func:`resolve_account`
        ``name``  — human-readable bank name

    Args:
        force_refresh: Bypass the cache and always hit the API.

    Returns:
        List of bank dicts as returned by ISW.

    Raises:
        ISWError: On network or API errors.
    """
    now = time.monotonic()
    if (
        not force_refresh
        and _bank_list_cache.get("banks")
        and now - _bank_list_cache.get("fetched_at", 0) < _BANK_LIST_TTL
    ):
        return _bank_list_cache["banks"]

    token = await _get_access_token()

    logger.info("ISW bank-list → %s", _BANK_LIST_URL)

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _BANK_LIST_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )

    logger.info("ISW bank-list ← HTTP %s", r.status_code)

    if r.status_code not in (200, 201):
        raise ISWError(f"ISW bank-list HTTP {r.status_code}: {r.text[:200]}", r.status_code)

    body = r.json()

    # ISW wraps the list in {"success": true, "data": [...]}
    banks: list[dict] = body.get("data") or body  # handle both shapes
    if not isinstance(banks, list):
        raise ISWError("ISW bank-list response has unexpected shape")

    _bank_list_cache["banks"] = banks
    _bank_list_cache["fetched_at"] = now

    logger.info("ISW bank-list: %d banks cached", len(banks))
    return banks


async def match_bank_name(user_input: str) -> tuple[str, str]:
    """
    Resolves a free-text bank name typed by the user to an ISW bank code.

    Strategy (in order):
      1. Exact case-insensitive match on ``name``.
      2. Check if the user's input is a substring of any bank name (or vice-versa).
      3. Fall back to the static ``_BANK_CODE_MAP`` (covers abbreviations like
         "gtb", "fbn", "uba", etc.).
      4. Fuzzy match via :mod:`difflib` with a similarity threshold of 0.6.

    Args:
        user_input: Bank name as typed by the user (e.g. "GTBank", "First Bank").

    Returns:
        ``(bank_code, canonical_bank_name)`` — the ISW code and the official name.

    Raises:
        ISWError(400): If no bank can be matched with sufficient confidence.
    """
    query = user_input.strip().lower()

    # ── Step 1 & 2: exact / substring match against live list ─────────────────
    banks = await get_supported_banks()

    for bank in banks:
        name_lower = bank["name"].lower()
        if name_lower == query or query in name_lower or name_lower in query:
            return bank["code"], bank["name"]

    # ── Step 3: static abbreviation map (gtb, uba, fbn, etc.) ─────────────────
    static_code = find_bank_code(user_input)
    if static_code:
        # Try to resolve the canonical name from the live list
        for bank in banks:
            if bank["code"] == static_code:
                return static_code, bank["name"]
        # Static map matched but bank wasn't in live list — still usable
        return static_code, user_input.title()

    # ── Step 4: fuzzy match ────────────────────────────────────────────────────
    names = [b["name"] for b in banks]
    close = difflib.get_close_matches(query, [n.lower() for n in names], n=1, cutoff=0.6)
    if close:
        for bank in banks:
            if bank["name"].lower() == close[0]:
                return bank["code"], bank["name"]

    raise ISWError(
        f"Could not identify a bank matching '{user_input}'. "
        "Please check the name or select from the supported bank list.",
        400,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Account resolution / name enquiry
# ─────────────────────────────────────────────────────────────────────────────

async def resolve_account(
    account_number: str,
    bank_name: str,
) -> dict:
    """
    Resolves an account number against the ISW Marketplace Identity API and
    returns the account holder's details for front-end confirmation before
    the user enters their PIN.

    Flow:
      1. ``bank_name`` is matched (live list + fuzzy) → ``bank_code``.
      2. A POST to the resolve endpoint is made with ``accountNumber`` + ``bankCode``.
      3. On success the caller receives a clean summary dict:

         .. code-block:: python

             {
                 "accountName":   "MICHAEL JOHN DOE",
                 "accountNumber": "1000000000",
                 "bankName":      "Guaranty Trust Bank",
                 "bankCode":      "058",
             }

    Args:
        account_number: 10-digit NUBAN account number.
        bank_name:      Bank name as typed by the user.

    Returns:
        Dict with ``accountName``, ``accountNumber``, ``bankName``, ``bankCode``.

    Raises:
        ISWError: If the bank cannot be matched, the account is not found, or
                  the API returns a non-2xx status.
    """
    bank_code, canonical_bank_name = await match_bank_name(bank_name)

    token = await _get_access_token()

    payload = {
        "accountNumber": account_number,
        "bankCode": bank_code,
    }

    logger.info(
        "ISW resolve-account → acct=%s bank=%s (%s)",
        account_number, canonical_bank_name, bank_code,
    )

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            _RESOLVE_ACC_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    logger.info("ISW resolve-account ← HTTP %s | acct=%s", r.status_code, account_number)

    if r.status_code not in (200, 201):
        raise ISWError(
            f"ISW resolve-account HTTP {r.status_code}: {r.text[:200]}",
            r.status_code,
        )

    body = r.json()

    # ISW shape: {"success": true, "data": {"status": "found", "bankDetails": {...}}}
    if not body.get("success"):
        raise ISWError(
            f"ISW resolve-account unsuccessful: {body.get('message', 'unknown error')}",
            400,
        )

    data = body.get("data", {})
    status = data.get("status", "")

    if status != "found":
        raise ISWError(
            f"Account not found: {account_number} at {canonical_bank_name}.",
            404,
        )

    bank_details: dict = data.get("bankDetails", {})

    return {
        "accountName":   bank_details.get("accountName", ""),
        "accountNumber": bank_details.get("accountNumber", account_number),
        "bankName":      bank_details.get("bankName", canonical_bank_name),
        "bankCode":      bank_code,
    }


_BANK_CODE_MAP: dict[str, str] = {
    "access": "044",
    "access bank": "044",
    "citibank": "023",
    "diamond": "063",
    "ecobank": "050",
    "fcmb": "214",
    "fidelity": "070",
    "first bank": "011",
    "firstbank": "011",
    "fbn": "011",
    "gtb": "058",
    "gtbank": "058",
    "guaranty trust": "058",
    "heritage": "030",
    "keystone": "082",
    "kuda": "90267",
    "moniepoint": "50515",
    "opay": "999992",
    "palmpay": "999991",
    "polaris": "076",
    "providus": "101",
    "stanbic": "221",
    "stanbic ibtc": "221",
    "standard chartered": "068",
    "sterling": "232",
    "suntrust": "100",
    "uba": "033",
    "union bank": "032",
    "unionbank": "032",
    "unity bank": "215",
    "wema": "035",
    "zenith": "057",
    "zenith bank": "057",
    "Guranty Trust Bank": "058",
}


def find_bank_code(bank_name: str) -> Optional[str]:
    name = bank_name.lower().strip()
    # Exact match
    if name in _BANK_CODE_MAP:
        return _BANK_CODE_MAP[name]
    # Substring match — bank name contains one of our keys
    for key, code in _BANK_CODE_MAP.items():
        if key in name or name in key:
            return code
    return None