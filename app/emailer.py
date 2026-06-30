from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any


def send_email(payload: dict[str, Any]) -> dict[str, Any]:
    to = payload.get("to")
    subject = payload.get("subject")
    body = payload.get("body")

    host = os.getenv("EMAIL_HOST") or os.getenv("SMTP_HOST")
    user = os.getenv("EMAIL_USER") or os.getenv("SMTP_USER")
    password = os.getenv("EMAIL_PASS") or os.getenv("SMTP_PASS")
    port = int(os.getenv("EMAIL_PORT") or os.getenv("SMTP_PORT") or "587")
    secure = (os.getenv("EMAIL_SECURE") or "").lower() == "true"

    if not host or not user or not password:
        return {
            "mode": "mock",
            "message": "SMTP is not configured. Email was not sent, but payload was prepared.",
            "payload": {"to": to, "subject": subject, "body": body},
        }

    message = EmailMessage()
    message["From"] = os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM") or user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body or "")

    if secure:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)

    return {"mode": "smtp", "messageId": message["Message-ID"] or "sent"}

