"""SMTP email sending for job applications.

Configured via SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM
in .env. For Gmail use smtp.gmail.com:587 with an App Password
(myaccount.google.com/apppasswords) — never the account password.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from core.config import get_settings
from core.exceptions import ResumeBuilderError
from core.logging_config import get_logger

logger = get_logger("email")


def email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user and s.smtp_password)


def masked_sender() -> str:
    s = get_settings()
    sender = s.smtp_from or s.smtp_user
    if "@" in sender:
        local, _, domain = sender.partition("@")
        visible = local[:2] if len(local) > 2 else local[:1]
        return f"{visible}***@{domain}"
    return sender[:3] + "***"


def send_email(to: str, subject: str, body: str,
               attachment_path: str = "", attachment_name: str = "") -> dict:
    s = get_settings()
    if not email_configured():
        raise ResumeBuilderError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER and SMTP_PASSWORD in backend/.env "
            "(for Gmail: smtp.gmail.com, port 587, and an App Password).",
            status_code=503,
        )
    if not to.strip() or "@" not in to:
        raise ResumeBuilderError("A valid recipient email address is required", status_code=422)

    message = EmailMessage()
    message["From"] = s.smtp_from or s.smtp_user
    message["To"] = to.strip()
    message["Subject"] = subject.strip() or "Job application"
    message.set_content(body)

    attached = ""
    if attachment_path:
        path = Path(attachment_path)
        if not path.is_file():
            raise ResumeBuilderError("Resume attachment could not be generated", status_code=500)
        message.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=attachment_name or path.name,
        )
        attached = attachment_name or path.name

    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as server:
            if s.smtp_use_tls:
                server.starttls()
            server.login(s.smtp_user, s.smtp_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise ResumeBuilderError(
            "SMTP login failed — check SMTP_USER/SMTP_PASSWORD (Gmail needs an App Password).",
            status_code=502,
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise ResumeBuilderError(f"Email sending failed: {exc}", status_code=502) from exc

    logger.info("Application email sent to %s (subject: %s, attachment: %s)",
                to, subject[:60], attached or "none")
    return {"sent": True, "to": to, "from": message["From"], "attachment": attached}
