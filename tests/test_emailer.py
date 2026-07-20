from unittest.mock import patch
import unittest

from app.config import EmailConfig
from app.emailer import send_email


class EmailerTests(unittest.TestCase):
    @patch("app.emailer.smtplib.SMTP_SSL")
    def test_bare_sender_is_formatted_with_login_mailbox(self, smtp_class):
        client = smtp_class.return_value.__enter__.return_value
        config = EmailConfig(
            host="smtp.qq.com",
            port=465,
            username="sender@example.com",
            password="secret",
            sender="notifications",
            recipients=("recipient@example.com",),
            use_ssl=True,
        )

        send_email(config, "subject", "plain", "<p>html</p>")

        message = client.send_message.call_args.args[0]
        self.assertEqual(message["From"], "notifications <sender@example.com>")
        client.login.assert_called_once_with("sender@example.com", "secret")

    @patch("app.emailer.smtplib.SMTP_SSL")
    def test_invalid_sender_without_login_mailbox_fails_before_smtp(self, smtp_class):
        config = EmailConfig(
            host="smtp.qq.com",
            port=465,
            sender="notifications",
            recipients=("recipient@example.com",),
            use_ssl=True,
        )

        with self.assertRaisesRegex(ValueError, "有效邮箱地址"):
            send_email(config, "subject", "plain", "<p>html</p>")
        smtp_class.assert_not_called()

    @patch("app.emailer.smtplib.SMTP_SSL")
    def test_inline_images_are_attached_to_html_alternative(self, smtp_class):
        client = smtp_class.return_value.__enter__.return_value
        config = EmailConfig(
            host="smtp.qq.com",
            port=465,
            username="sender@example.com",
            password="secret",
            sender="sender@example.com",
            recipients=("recipient@example.com",),
            use_ssl=True,
        )

        send_email(config, "subject", "plain", '<img src="cid:trend-chart">', {"trend-chart": b"png"})

        message = client.send_message.call_args.args[0]
        self.assertIn("trend-chart", message.as_string())
