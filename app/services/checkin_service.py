"""app/services/checkin_service.py
APScheduler job that runs daily:
  - Sends reminder emails when check-in is approaching
  - Triggers disbursement when proof-of-life fails (overdue + grace exceeded)
  - Activates backup email access on proof-of-life failure
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.models.models import Checkin, CheckinStatus, User
from app.services import disbursement_service, email_service

logger = logging.getLogger(__name__)

REMINDER_DAYS = [30, 14, 7, 3, 1]  # send reminders this many days before due


async def run_checkin_job():
    """Daily background job: check all active check-ins."""
    logger.info("Running daily check-in job...")
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Checkin).where(
                    Checkin.status.in_([CheckinStatus.ACTIVE, CheckinStatus.OVERDUE])
                )
            )
            checkins = result.scalars().all()
            now = datetime.now(timezone.utc)

            for checkin in checkins:
                user_result = await db.execute(
                    select(User).where(User.id == checkin.user_id)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    continue

                next_due = checkin.next_due_date
                if next_due.tzinfo is None:
                    next_due = next_due.replace(tzinfo=timezone.utc)

                days_until_due = (next_due - now).days

                # ── Send reminder emails ──────────────────────────────────────
                if days_until_due in REMINDER_DAYS and checkin.status == CheckinStatus.ACTIVE:
                    try:
                        email_service.send_checkin_reminder_email(
                            email=user.email,
                            first_name=user.first_name,
                            days_left=days_until_due,
                        )
                        logger.info("Reminder sent to %s — %d days left", user.email, days_until_due)
                    except email_service.EmailError as e:
                        logger.error("Reminder email failed: %s", e)

                # ── Mark overdue ──────────────────────────────────────────────
                if now > next_due and checkin.status == CheckinStatus.ACTIVE:
                    checkin.status = CheckinStatus.OVERDUE
                    await db.flush()
                    logger.info("User %s check-in is now OVERDUE", user.id)

                # ── Grace period exceeded → trigger disbursement ──────────────
                grace_deadline = next_due + timedelta(days=checkin.grace_period_days)
                if now > grace_deadline and not checkin.disbursement_triggered:
                    logger.info(
                        "Proof-of-life failed for user %s — triggering disbursement", user.id
                    )

                    # Activate backup email access
                    if user.backup_email and user.is_backup_email_verified:
                        try:
                            reset_link = "https://legacyportal.app/reset-password"
                            email_service.send_proof_of_life_failed_email(
                                backup_email=user.backup_email,
                                first_name=user.first_name,
                                reset_link=reset_link,
                            )
                        except email_service.EmailError as e:
                            logger.error("Backup email notification failed: %s", e)

                    # Trigger disbursement
                    await disbursement_service.trigger_disbursement(db=db, user=user)

            await db.commit()
            logger.info("Check-in job complete.")
        except Exception as e:
            logger.error("Check-in job error: %s", e)
            await db.rollback()
