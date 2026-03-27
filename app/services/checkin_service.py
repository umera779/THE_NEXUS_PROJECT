

"""app/services/checkin_service.py
APScheduler job that runs frequently (e.g. every 30 seconds):
  - Sends reminder emails when check-in is approaching certain thresholds
  - Marks check-ins OVERDUE the moment next_due_date passes
  - Triggers disbursement once the grace period is exceeded
  - Activates backup email access on proof-of-life failure

Intervals and grace periods are stored as total SECONDS so users can set
values as fine-grained as 30 seconds using the DD:HH:MM:SS input format.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.models.models import Checkin, CheckinStatus, User
from app.services import disbursement_service, email_service

logger = logging.getLogger(__name__)

# Reminder thresholds expressed in seconds.
# Each tuple: (lower_bound_seconds, upper_bound_seconds, human_label)
# A reminder fires when seconds_until_due falls inside the window.
# The ±60s / ±30s tolerance ensures the job catches the moment even if it
# doesn't run at exactly the right second.
REMINDER_THRESHOLDS = [
    (2_592_000 - 60, 2_592_000 + 60, "30 days"),   # ~30 days
    (1_209_600 - 60, 1_209_600 + 60, "14 days"),   # ~14 days
    (604_800   - 60, 604_800   + 60, "7 days"),     # ~7 days
    (259_200   - 60, 259_200   + 60, "3 days"),     # ~3 days
    (86_400    - 60, 86_400    + 60, "1 day"),      # ~1 day
    (3_600     - 30, 3_600     + 30, "1 hour"),     # ~1 hour
    (300       - 15, 300       + 15, "5 minutes"),  # ~5 minutes
]


async def run_checkin_job():
    """
    Background job: evaluate all active/overdue check-ins.
    Should be scheduled to run every 30 seconds (or at most every minute)
    so that second-level intervals are honoured promptly.
    """
    logger.info("Running check-in job...")
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

                seconds_until_due = (next_due - now).total_seconds()

                # ── Send reminder emails (only while still ACTIVE) ────────────
                if checkin.status == CheckinStatus.ACTIVE and seconds_until_due > 0:
                    for lo, hi, label in REMINDER_THRESHOLDS:
                        if lo <= seconds_until_due <= hi:
                            try:
                                email_service.send_checkin_reminder_email(
                                    email=user.email,
                                    first_name=user.first_name,
                                    days_left=label,  # human-readable label
                                )
                                logger.info(
                                    "Reminder sent to %s — %s remaining", user.email, label
                                )
                            except email_service.EmailError as e:
                                logger.error("Reminder email failed: %s", e)
                            break  # only one bucket per run

                # ── Mark overdue ──────────────────────────────────────────────
                if seconds_until_due <= 0 and checkin.status == CheckinStatus.ACTIVE:
                    checkin.status = CheckinStatus.OVERDUE
                    await db.flush()
                    logger.info("User %s check-in is now OVERDUE", user.id)

                # ── Grace period exceeded → trigger disbursement ──────────────
                grace_deadline = next_due + timedelta(seconds=checkin.grace_period_seconds)
                if now > grace_deadline and not checkin.disbursement_triggered and checkin.status != CheckinStatus.TRIGGERED:
                    logger.info(
                        "Proof-of-life failed for user %s — triggering disbursement", user.id
                    )

                    # Notify backup email that access has been activated
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

                    # Trigger simulated disbursement
                    await disbursement_service.trigger_disbursement(db=db, user=user)

            await db.commit()
            logger.info("Check-in job complete.")
        except Exception as e:
            logger.error("Check-in job error: %s", e)
            await db.rollback()