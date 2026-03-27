
import logging
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
    Disburse wallet balance to all verified beneficiaries according to their
    percentage shares. Creates a Paystack transfer for each beneficiary.
    Returns list of disbursement results.
    """
    wallet_result = await db.execute(
        select(Wallet).where(Wallet.user_id == user.id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if not wallet or float(wallet.balance) <= 0:
        logger.warning("Disbursement skipped for user %s — zero balance", user.id)
        return []

    bene_result = await db.execute(
        select(Beneficiary).where(
            Beneficiary.user_id == user.id,
            Beneficiary.is_verified == True,
        )
    )
    beneficiaries = bene_result.scalars().all()
    if not beneficiaries:
        logger.warning("Disbursement skipped for user %s — no verified beneficiaries", user.id)
        return []

    total_balance = float(wallet.balance)
    results = []

    for bene in beneficiaries:
        share_amount = total_balance * (float(bene.percentage_share) / 100)
        amount_kobo = int(round(share_amount * 100))
        if amount_kobo <= 0:
            continue

        reference = generate_reference("DISB")

        # Ensure recipient code exists
        try:
            if not bene.paystack_recipient_code:
                bank_code = await paystack_service.find_bank_code(bene.bank_name)
                if not bank_code:
                    bank_code = bene.bank_code
                recipient_data = await paystack_service.create_transfer_recipient(
                    name=bene.full_name,
                    account_number=bene.account_number,
                    bank_code=bank_code,
                )
                bene.paystack_recipient_code = recipient_data.get("recipient_code")
                await db.flush()

            transfer_data = await paystack_service.initiate_transfer(
                amount_kobo=amount_kobo,
                recipient_code=bene.paystack_recipient_code,
                reference=reference,
                reason=f"The Nexusinheritance disbursement for {user.first_name} {user.last_name}",
            )

            txn = Transaction(
                user_id=user.id,
                wallet_id=wallet.id,
                transaction_type=TransactionType.DISBURSEMENT,
                amount=share_amount,
                status=TransactionStatus.PENDING,
                reference_id=reference,
                recipient_name=bene.full_name,
                recipient_account=bene.account_number,
                recipient_bank=bene.bank_name,
                narration=f"Inheritance disbursement — {bene.percentage_share}%",
                meta={"transfer_code": transfer_data.get("transfer_code"), "beneficiary_id": bene.id},
            )
            db.add(txn)

            # Notify backup email
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
                    pass

            results.append({
                "beneficiary": bene.full_name,
                "amount": share_amount,
                "reference": reference,
                "status": "initiated",
            })
            logger.info("Disbursement initiated: %s → %s ₦%.2f", reference, bene.full_name, share_amount)

        except paystack_service.PaystackError as e:
            logger.error("Disbursement failed for beneficiary %s: %s", bene.full_name, e.message)
            txn = Transaction(
                user_id=user.id,
                wallet_id=wallet.id,
                transaction_type=TransactionType.DISBURSEMENT,
                amount=share_amount,
                status=TransactionStatus.FAILED,
                reference_id=reference,
                recipient_name=bene.full_name,
                narration=f"Disbursement failed: {e.message}",
            )
            db.add(txn)
            results.append({
                "beneficiary": bene.full_name,
                "amount": share_amount,
                "reference": reference,
                "status": "failed",
                "reason": e.message,
            })

    # Update checkin status
    checkin_result = await db.execute(
        select(Checkin).where(Checkin.user_id == user.id)
    )
    checkin = checkin_result.scalar_one_or_none()
    if checkin:
        checkin.status = CheckinStatus.TRIGGERED
        checkin.disbursement_triggered = True

    await db.flush()
    return results
