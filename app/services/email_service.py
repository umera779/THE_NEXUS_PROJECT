import logging
from typing import Optional

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)
resend.api_key = settings.RESEND_API_KEY


class EmailError(Exception):
    pass


def _send(to: str, subject: str, html: str) -> dict:
    try:
        params: resend.Emails.SendParams = {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        response = resend.Emails.send(params)
        logger.info("Email sent to %s | %s", to, subject)
        return response
    except Exception as e:
        logger.error("Email failed to %s: %s", to, e)
        raise EmailError(str(e))


def send_verification_email(email: str, first_name: str, code: str) -> dict:
    return _send(
        email,
        "Verify Your Legacy PortalAccount",
        f"""
        <p>Hi {first_name},</p>
        <p>Use the code below to verify your email address. It expires in 15 minutes.</p>
        <h2 style="letter-spacing:8px">{code}</h2>
        <p>If you did not sign up, please ignore this email.</p>
        <p>— Legacy Portal Team<</p>
        """,
    )


def send_welcome_email(email: str, first_name: str) -> dict:
    return _send(
        email,
        "Welcome to Legacy Portal",
        f"""
        <p>Hi {first_name},</p>
        <p>Your account is ready. Log in to set up your beneficiaries and check-in schedule.</p>
        <p>Legacy Portal ensure your loved ones can claim your investments if anything happens to you.</p>
        <p>— Legacy Portal Team<</p>
        """,
    )


def send_password_reset_email(email: str, first_name: str, code: str) -> dict:
    return _send(
        email,
        "Reset Your Legacy PortalPassword",
        f"""
        <p>Hi {first_name},</p>
        <p>Use the code below to reset your password. It expires in 15 minutes.</p>
        <h2 style="letter-spacing:8px">{code}</h2>
        <p>If you did not request a password reset, please secure your account immediately.</p>
        <p>— Legacy Portal Team<</p>
        """,
    )


def send_pin_otp_email(email: str, first_name: str, otp: str) -> dict:
    return _send(
        email,
        "Your Legacy PortalPIN Setup OTP",
        f"""
        <p>Hi {first_name},</p>
        <p>Use this OTP to confirm your transaction PIN setup. It expires in 10 minutes.</p>
        <h2 style="letter-spacing:8px">{otp}</h2>
        <p>—Legacy Portal Team<</p>
        """,
    )


def send_backup_email_otp(email: str, first_name: str, otp: str) -> dict:
    return _send(
        email,
        "Verify Your Backup Email — Legacy Portal",
        f"""
        <p>Hi {first_name},</p>
        <p>Use this OTP to verify your backup email address. It expires in 10 minutes.</p>
        <h2 style="letter-spacing:8px">{otp}</h2>
        <p>— Legacy Portal Team<</p>
        """,
    )


def send_checkin_reminder_email(email: str, first_name: str, days_left: str) -> dict:
    return _send(
        email,
        "Legacy Portal — Check-In Reminder",
        f"""
        <p>Hi {first_name},</p>
        <p>Your proof-of-life check-in is due in <strong>{days_left}</strong>.</p>
        <p>Please log in to your Legacy Portal Account to confirm you are active to prevent automatic disbursement to your beneficiaries.</p>
        <p>— Legacy Portal Team</p>
        """,
    )


def send_disbursement_notification_email(
    email: str,
    first_name: str,
    beneficiary_name: str,
    amount: float,
    reference: str,
) -> dict:
    return _send(
        email,
        "Legacy Portal— Disbursement Initiated",
        f"""
        <p>A disbursement has been initiated from the your Legacy Portal Account .</p>
        <p>Beneficiary: {beneficiary_name}<br>
        Amount: ₦{amount:,.2f}<br>
        Reference: {reference}</p>
        <p>— Legacy Portal Team<</p>
        """,
    )


def send_proof_of_life_failed_email(backup_email: str, first_name: str, reset_link: str) -> dict:
    return _send(
        backup_email,
        "Legacy Portal— Account Access (Proof-of-Life Not Completed)",
        f"""
        <p>Hi {first_name},</p>
        <p>The Legacy Portal Account associated with this backup email did not complete a check-in in time.</p>
        <p>If you need to regain access, you can reset the account password using this backup email:</p>
        <p><a href="{reset_link}">Reset Password</a></p>
        <p>— Legacy Portal Team</p>
        """,
    )