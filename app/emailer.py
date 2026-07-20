from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from .config import EmailConfig


def send_email(
    config: EmailConfig,
    subject: str,
    plain_text: str,
    html: str,
    inline_images: dict[str, bytes] | None = None,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    sender_name, sender_address = parseaddr(config.sender or "")
    # SMTP providers generally require the envelope sender to be a valid
    # mailbox. Treat a bare sender value as a display name and use the login
    # account as the actual address (e.g. QQ SMTP rejects `notifications`).
    if "@" not in sender_address:
        sender_name = (config.sender or "").strip() or sender_name
        sender_address = (config.username or "").strip()
    if "@" not in sender_address:
        raise ValueError("email.sender 或 email.username 必须是有效邮箱地址")
    message["From"] = formataddr((sender_name, sender_address)) if sender_name else sender_address
    message["To"] = ", ".join(config.recipients)
    message.set_content(plain_text)
    message.add_alternative(html, subtype="html")
    if inline_images:
        html_part = message.get_payload()[-1]
        for content_id, image in inline_images.items():
            html_part.add_related(
                image,
                maintype="image",
                subtype="png",
                cid=f"<{content_id}>",
                filename=f"{content_id}.png",
            )
    client_class = smtplib.SMTP_SSL if config.use_ssl else smtplib.SMTP
    with client_class(config.host, config.port, timeout=30) as client:
        if config.use_tls and not config.use_ssl:
            client.starttls()
        if config.username:
            client.login(config.username, config.password)
        client.send_message(message)
