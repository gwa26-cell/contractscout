"""SMTP-уведомление о готовом отчёте (этап 5)."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from contract_scout.config import Settings

logger = logging.getLogger("contract_scout.notify")


def notify_review(settings: Settings, *, filename: str, verdict: str, score: int, summary: str) -> bool:
    if settings.local_only or not settings.smtp_enabled:
        logger.info("notify skipped local_only=%s", settings.local_only)
        return False
    body = (
        f"Файл: {filename}\nВердикт: {verdict}\nИндекс риска: {score}/100\n\n{summary}\n\n"
        "Это автоматическое уведомление ContractScout."
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[ContractScout] {filename}: {verdict}"
    msg["From"] = settings.notify_from or settings.smtp_user
    msg["To"] = settings.notify_to
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    logger.info("notified %s", settings.notify_to)
    return True
