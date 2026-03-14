"""Notification service — deduplication, template rendering, SMTP sending."""

import logging
from email.message import EmailMessage

import aiosmtplib

from src.core.config import settings
from src.core.metrics import notifications_deduplicated_total, notifications_sent_total
from src.core.redis_client import has_dedup_key, set_dedup_key
from src.core.template_renderer import render_template

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Raised when SMTP delivery fails."""


async def send_notification(
    job_id: str,
    user_email: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Send a notification email for the given job, if not already sent.

    Args:
        job_id: Unique job identifier (used for deduplication key).
        user_email: Recipient email address.
        status: ``"DONE"`` or ``"ERROR"``.
        error_message: Optional error details (included in template context).
    """
    # --- Deduplication check ---
    if await has_dedup_key(job_id):
        logger.info(
            "Duplicate notification skipped",
            extra={"job_id": job_id, "status": status},
        )
        notifications_deduplicated_total.inc()
        return

    # --- Render template ---
    context = {"job_id": job_id}
    if error_message:
        context["error_message"] = error_message
    body_html = render_template(status, context)

    # --- Send via SMTP (STARTTLS) ---
    try:
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = user_email
        message["Subject"] = _subject(status)
        message.set_content(body_html, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user if settings.smtp_user else None,
            password=settings.smtp_password if settings.smtp_password else None,
            start_tls=settings.smtp_start_tls,
        )
    except Exception as exc:
        logger.error(
            "Failed to send notification email",
            extra={
                "job_id": job_id,
                "status": status,
                "recipient_domain": (
                    user_email.split("@")[-1] if "@" in user_email else "unknown"
                ),
                "error": str(exc),
            },
        )
        raise EmailSendError(str(exc)) from exc

    # --- Mark as sent in Redis ---
    await set_dedup_key(job_id)
    notifications_sent_total.labels(status="success").inc()

    logger.info(
        "Notification sent",
        extra={
            "job_id": job_id,
            "status": status,
            "recipient_domain": (
                user_email.split("@")[-1] if "@" in user_email else "unknown"
            ),
        },
    )


def _subject(status: str) -> str:
    if status == "DONE":
        return "Seu vídeo foi processado com sucesso"
    return "Falha ao processar seu vídeo"
