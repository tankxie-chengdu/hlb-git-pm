from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import EmailConfig


def send_email(config: EmailConfig, subject: str, plain_text: str, html: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message.set_content(plain_text)
    message.add_alternative(html, subtype="html")
    client_class = smtplib.SMTP_SSL if config.use_ssl else smtplib.SMTP
    with client_class(config.host, config.port, timeout=30) as client:
        if config.use_tls and not config.use_ssl:
            client.starttls()
        if config.username:
            client.login(config.username, config.password)
        client.send_message(message)

