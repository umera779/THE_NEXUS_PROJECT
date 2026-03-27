"""app/services/disbursement_service.py
SIMULATION MODE — No real payment processor is used.

When a user's check-in grace period expires this service:
  1. Looks up all verified beneficiaries for that user.
  2. Calculates each beneficiary's share of the wallet balance.
  3. Deducts the full balance from the wallet (sets it to 0.00).
  4. Creates a SUCCESS Transaction receipt for every beneficiary.
  5. Marks the check-in as TRIGGERED / disbursement_triggered = True.
  6. Notifies the backup email address if one is configured.

"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import generate_reference
from app.models.models import (
    Beneficiary,
    Checkin,
    CheckinStatus,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
    Wallet,
)
from app.services import email_service

logger = logging.getLogger(__name__)


async def trigger_disbursement(db: AsyncSession, user: User) -> list[dict]:
    """
    Simulate disbursement of wallet balance to all verified beneficiaries.
    Deducts the balance and records SUCCESS receipts. Returns a list of
    per-beneficiary result dicts.
    """
    # ── Load wallet ───────────────────────────────────────────────────────────
    wallet_result = await db.execute(
        select(Wallet).where(Wallet.user_id == user.id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if not wallet or float(wallet.balance) <= 0:
        logger.warning(
            "Disbursement skipped for user %s — zero or missing balance", user.id
        )
        return []

    # ── Load verified beneficiaries ───────────────────────────────────────────
    bene_result = await db.execute(
        select(Beneficiary).where(
            Beneficiary.user_id == user.id,
            Beneficiary.is_verified == True,  # noqa: E712
        )
    )
    beneficiaries = bene_result.scalars().all()
    if not beneficiaries:
        logger.warning(
            "Disbursement skipped for user %s — no verified beneficiaries", user.id
        )
        return []

    total_balance = float(wallet.balance)
    disbursed_at = datetime.now(timezone.utc)
    total_disbursed = 0.0
    results = []

    for bene in beneficiaries:
        share_amount = round((float(bene.percentage_share) / 100) * total_balance, 2)
        if share_amount <= 0:
            continue
            

        total_disbursed += share_amount

        reference = generate_reference("DISB-SIM")
        # ── Create a SUCCESS receipt immediately (simulation) ─────────────────
        txn = Transaction(
            user_id=user.id,
            wallet_id=wallet.id,
            transaction_type=TransactionType.DISBURSEMENT,
            amount=share_amount,
            status=TransactionStatus.SUCCESS,         # always succeeds in demo
            reference_id=reference,
            recipient_name=bene.full_name,
            recipient_account=bene.account_number,
            recipient_bank=bene.bank_name,
            narration=(
                f"[SIMULATED] Inheritance disbursement — "
                f"{bene.percentage_share}% to {bene.full_name}"
            ),
            meta={
                "simulation": True,
                "beneficiary_id": str(bene.id),
                "percentage_share": float(bene.percentage_share),
                "disbursed_at": disbursed_at.isoformat(),
                "bank_code": bene.bank_code,
            },
        )
        db.add(txn)
        #--- send email to users to notify them of the disbursement ---
        try:
            email_service.send_disbursement_notification_email(
                email=user.email,
                first_name=user.first_name,
                beneficiary_name=bene.full_name,
                amount=share_amount,
                reference=reference
            )
        except Exception:
            pass

        # ── Notify backup email ───────────────────────────────────────────────
        if user.backup_email and user.is_backup_email_verified:
            try:
                email_service.send_disbursement_notification_email(
                    email=user.backup_email,
                    first_name=user.first_name,
                    beneficiary_name=bene.full_name,
                    amount=share_amount,
                    reference=reference,
                )

            except email_service.EmailError:
                pass  # notification failure must not block the receipt

        results.append({
            "beneficiary": bene.full_name,
            "bank": bene.bank_name,
            "account": bene.account_number,
            "amount": share_amount,
            "percentage": float(bene.percentage_share),
            "reference": reference,
            "status": "success",
            "simulated": True,
        })


        logger.info(
            "[SIM] Disbursement receipt created: %s → %s ₦%.2f",
            reference, bene.full_name, share_amount,
        )

    # ── Deduct allocated from  wallet ───────────────────────────────────────
    
    wallet.balance = float(wallet.balance) - total_disbursed
    await db.flush()

    # ── Update check-in record ────────────────────────────────────────────────
    checkin_result = await db.execute(
        select(Checkin).where(Checkin.user_id == user.id)
    )
    checkin = checkin_result.scalar_one_or_none()
    if checkin:
        checkin.status = CheckinStatus.TRIGGERED
        checkin.disbursement_triggered = True

    await db.flush()

    logger.info(
        "[SIM] Disbursement complete for user %s — ₦%.2f distributed across %d beneficiaries",
        user.id, total_balance, len(results),
    )
    return results