"""app/services/paystack_service.py"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


async def _post(path: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{settings.PAYSTACK_BASE_URL}{path}",
            headers=_headers(),
            json=data,
        )
    body = r.json()
    logger.info("Paystack POST %s → HTTP %s", path, r.status_code)
    if not body.get("status"):
        raise PaystackError(body.get("message", "Paystack error"), r.status_code)
    return body.get("data") or {}


async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{settings.PAYSTACK_BASE_URL}{path}",
            headers=_headers(),
            params=params,
        )
    body = r.json()
    logger.info("Paystack GET %s → HTTP %s", path, r.status_code)
    if not body.get("status"):
        raise PaystackError(body.get("message", "Paystack error"), r.status_code)
    return body.get("data") or {}


# ─── Customer ─────────────────────────────────────────────────────────────────

async def create_customer(email: str, first_name: str, last_name: str, phone: str) -> dict:
    return await _post("/customer", {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
    })


# ─── Bank Resolution ──────────────────────────────────────────────────────────

async def list_banks(country: str = "nigeria") -> list:
    data = await _get("/bank", {"country": country, "perPage": 100})
    return data if isinstance(data, list) else []


async def find_bank_code(bank_name: str) -> Optional[str]:
    aliases = {
        "opay": "999992", "kuda": "90267", "palmpay": "999991",
        "moniepoint": "50515", "access": "044", "gtb": "058",
        "gtbank": "058", "zenith": "057", "uba": "033",
        "first bank": "011", "firstbank": "011", "union bank": "032",
        "sterling": "232", "fcmb": "214", "wema": "035",
        "fidelity": "070", "stanbic": "221",
        "test-bank": "001", "test bank": "001",
    }
    name_lower = bank_name.lower().strip()
    for alias, code in aliases.items():
        if alias in name_lower or name_lower in alias:
            return code
    try:
        banks = await list_banks()
        for bank in banks:
            if bank["name"].lower() == name_lower:
                return bank["code"]
        for bank in banks:
            if name_lower in bank["name"].lower():
                return bank["code"]
    except PaystackError:
        pass
    return None


async def resolve_account(account_number: str, bank_code: str) -> dict:
    return await _get("/bank/resolve", {
        "account_number": account_number,
        "bank_code": bank_code,
    })


# ─── Transfer Recipient ───────────────────────────────────────────────────────

async def create_transfer_recipient(
    name: str, account_number: str, bank_code: str, currency: str = "NGN"
) -> dict:
    return await _post("/transferrecipient", {
        "type": "nuban",
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": currency,
    })


# ─── Transfer ─────────────────────────────────────────────────────────────────

async def initiate_transfer(
    amount_kobo: int,
    recipient_code: str,
    reference: str,
    reason: str = "The NexusInheritance Disbursement",
) -> dict:
    return await _post("/transfer", {
        "source": "balance",
        "amount": amount_kobo,
        "recipient": recipient_code,
        "reason": reason,
        "reference": reference,
    })


async def verify_transfer(reference: str) -> dict:
    return await _get(f"/transfer/verify/{reference}")
