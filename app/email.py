from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def smtp_is_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from_email)


def _send_password_reset_email_sync(recipient: str, reset_url: str) -> None:
    settings = get_settings()
    if not smtp_is_configured():
        raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL must be configured")

    message = EmailMessage()
    message["Subject"] = "Reset your ATM Predictive Maintenance password"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your ATM Predictive Maintenance account.\n\n"
        f"Use this link within {settings.password_reset_expiration_minutes} minutes:\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can safely ignore this email."
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as server:
        if settings.smtp_use_tls:
            server.starttls(context=context)
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(message)


async def send_password_reset_email(recipient: str, reset_url: str) -> None:
    await asyncio.to_thread(_send_password_reset_email_sync, recipient, reset_url)