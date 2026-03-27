"""app/api/routes/payment.py

Interswitch payment routes for Legacy Portal.

Endpoints
---------
POST /fund/initiate
    Creates a pending Transaction, returns the checkout parameters the
    front-end widget needs.

GET  /payment/callback
    Interswitch redirects the browser here after the widget flow ends.
    We requery ISW server-side to confirm the payment and credit the wallet.

POST /payment/webhook
    Interswitch POSTs payment events here.
    We verify the signature, requery to confirm, and credit the wallet.
"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.models import Transaction, User, Wallet
from app.models.schemas import FundWalletRequest, InitiatePaymentResponse
from app.services.isw_service import (
    ISWError,
    build_payment_request,
    is_successful_payment,
    requery_transaction,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payment"])

from fastapi.requests import Request
from fastapi.templating import Jinja2Templates

# templates = Jinja2Templates(directory="app/templates")
from app.core.templates import templates
# ─────────────────────────────────────────────────────────────────────────────
# GET /fund  — serve the Fund Wallet HTML page
# ─────────────────────────────────────────────────────────────────────────────



@router.get("/fund", response_class=HTMLResponse)
async def fund_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse("fund.html", {
        "request": request,
        "user": user,
        "inline_script_url": settings.isw_inline_script_url,
        "base_url": settings.BASE_URL,
    })


# ─────────────────────────────────────────────────────────────────────────────
# POST /fund/initiate
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/fund/initiate", response_model=InitiatePaymentResponse)
async def initiate_funding(
    body: FundWalletRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a pending Transaction record and returns the parameters the
    Interswitch Inline Checkout widget needs to open the payment modal.
    """
    txn_ref = f"NXS-{uuid.uuid4().hex[:16].upper()}"

    txn = Transaction(
        user_id=user.id,
        transaction_type="credit",
        amount=body.amount_kobo / 100,       
        txn_ref=txn_ref,
        amount_kobo=body.amount_kobo,
        status="pending",
        narration="Wallet funding via Interswitch",
    )
    db.add(txn)
    await db.flush()   

    payment_params = build_payment_request(
        txn_ref=txn_ref,
        amount_kobo=body.amount_kobo,
        customer_email=user.email,
    )

    logger.info("Payment initiated | user=%d | txn_ref=%s | amount_kobo=%d",
                user.id, txn_ref, body.amount_kobo)

    return InitiatePaymentResponse(
        txn_ref=txn_ref,
        amount_kobo=body.amount_kobo,
        merchant_code=settings.ISW_MERCHANT_CODE,
        pay_item_id=settings.ISW_PAY_ITEM_ID,
        customer_email=user.email,
        mode=settings.ISW_MODE,
        site_redirect_url=payment_params["site_redirect_url"],
        inline_script_url=settings.isw_inline_script_url,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /payment/callback  (browser redirect after widget flow)
# ─────────────────────────────────────────────────────────────────────────────

def _payment_result_html(success: bool, message: str) -> HTMLResponse:
    """
    Returns a self-contained HTML page that redirects to /dashboard client-side.
    This preserves the auth token the frontend holds in localStorage/memory,
    avoiding the 401 that a server-side RedirectResponse causes.
    """
    param = "funded=1" if success else "failed=1"
    icon  = "✅" if success else "❌"
    color = "#22c55e" if success else "#ef4444"
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Payment {"successful" if success else "failed"}</title>
  <style>
    body{{margin:0;display:flex;align-items:center;justify-content:center;
         min-height:100vh;background:#0f172a;font-family:sans-serif;color:#f1f5f9}}
    .card{{text-align:center;padding:2.5rem 3rem;background:#1e293b;
           border-radius:1rem;box-shadow:0 4px 24px #0008}}
    .icon{{font-size:3rem;margin-bottom:.75rem}}
    h2{{margin:.25rem 0;color:{color}}}
    p{{color:#94a3b8;margin:.5rem 0 1.5rem}}
    .bar{{height:4px;background:#334155;border-radius:2px;overflow:hidden}}
    .fill{{height:100%;width:0;background:{color};border-radius:2px;
           animation:fill 3s linear forwards}}
    @keyframes fill{{to{{width:100%}}}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h2>{message}</h2>
    <p>Redirecting you to your dashboard&hellip;</p>
    <div class="bar"><div class="fill"></div></div>
  </div>
  <script>
    setTimeout(() => {{ window.location.href = "/dashboard?{param}"; }}, 3000);
  </script>
</body>
</html>""")


@router.get("/payment/callback")
async def payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Interswitch redirects here after the inline widget finishes.
    We always perform a server-side requery — never trust the callback params.
    """
    txn_ref = request.query_params.get("txnref") or request.query_params.get("txn_ref")
    if not txn_ref:
        return _payment_result_html(False, "Missing transaction reference")

    result = await db.execute(
        select(Transaction).where(Transaction.txn_ref == txn_ref)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        return _payment_result_html(False, "Transaction not found")

    if txn.status == "success":
        return _payment_result_html(True, "Payment already confirmed!")

    try:
        requery = await requery_transaction(txn_ref, txn.amount_kobo)
    except ISWError as exc:
        logger.error("ISW requery failed for %s: %s", txn_ref, exc.message)
        txn.status = "failed"
        await db.commit()
        return _payment_result_html(False, "Payment could not be verified")

    if is_successful_payment(requery):
        txn.status = "success"
        txn.payment_reference = requery.get("PaymentReference")
        txn.confirmed_via = "callback"

        # Credit wallet (balance lives on Wallet, not User)
        wallet_result = await db.execute(
            select(Wallet).where(Wallet.user_id == txn.user_id)
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet:
            wallet.balance = float(wallet.balance) + txn.amount_kobo / 100
            logger.info("Wallet credited | user=%s | amount_kobo=%d | txn_ref=%s",
                        txn.user_id, txn.amount_kobo, txn_ref)

        await db.commit()
        return _payment_result_html(True, "Payment successful!")

    else:
        txn.status = "failed"
        await db.commit()
        logger.warning("Payment not confirmed | txn_ref=%s | ResponseCode=%s",
                       txn_ref, requery.get("ResponseCode"))
        return _payment_result_html(False, "Payment was not completed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /payment/webhook  (server-to-server notification from ISW)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/payment/webhook", status_code=status.HTTP_200_OK)
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Interswitch POSTs a notification here when a payment status changes.

    Security: HMAC-SHA512 signature is verified first.
    We then trust the payload directly — no outbound requery is made,
    which avoids ConnectTimeout issues on restricted networks.
    """
    raw_body = await request.body()
    sig = request.headers.get("x-interswitch-signature", "")

    if not verify_webhook_signature(raw_body, sig):
        logger.warning("Invalid ISW webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Parse payload
    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    logger.info("ISW webhook payload: %s", payload)

    # Extract event and data — ISW may send {event, data} or a flat dict
    event = payload.get("event")
    data = payload.get("data") or payload

    # Only handle completed transactions
    if event and event != "TRANSACTION.COMPLETED":
        return {"status": "not_handled", "event": event}

    # Resolve our txn_ref from the payload
    txn_ref = (
        data.get("MerchantReference")
        or data.get("merchantReference")
        or data.get("txnref")
        or data.get("TransactionReference")
    )

    if not txn_ref:
        logger.warning("ISW webhook missing transaction reference | payload=%s", payload)
        return {"status": "ignored", "reason": "no_txn_ref"}

    # Look up transaction
    result = await db.execute(
        select(Transaction).where(Transaction.txn_ref == txn_ref)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        logger.warning("ISW webhook: txn_ref not found | %s", txn_ref)
        return {"status": "ignored", "reason": "txn_not_found"}

    # Idempotency — skip if already processed
    if txn.status == "success":
        return {"status": "already_processed"}

    # Check response code directly from the payload
    response_code = (
        data.get("ResponseCode")
        or data.get("responseCode")
    )

    if response_code != "00":
        logger.info("Webhook non-success code %s for %s", response_code, txn_ref)
        txn.status = "failed"
        await db.commit()
        return {"status": "failed", "code": response_code}

    # Verify amount matches
    webhook_amount = data.get("Amount") or data.get("amount") or 0
    if webhook_amount and int(webhook_amount) != txn.amount_kobo:
        logger.error(
            "Amount mismatch for %s: expected %d kobo, got %s kobo",
            txn_ref, txn.amount_kobo, webhook_amount,
        )
        txn.status = "failed"
        await db.commit()
        return {"status": "amount_mismatch"}

    # Credit the wallet
    wallet_result = await db.execute(
        select(Wallet).where(Wallet.user_id == txn.user_id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if not wallet:
        logger.error("Wallet not found for user %s | txn_ref %s", txn.user_id, txn_ref)
        return {"status": "wallet_not_found"}

    txn.status = "success"
    txn.payment_reference = data.get("PaymentReference") or data.get("paymentReference")
    txn.confirmed_via = "webhook"
    wallet.balance = float(wallet.balance) + txn.amount_kobo / 100
    await db.commit()

    logger.info(
        "Wallet credited via webhook | user=%s | amount_kobo=%d | txn_ref=%s",
        txn.user_id, txn.amount_kobo, txn_ref,
    )
    return {"status": "success"}


