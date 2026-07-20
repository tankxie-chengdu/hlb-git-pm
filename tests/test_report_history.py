import unittest

from web.db_models import ReportHistory


class ReportHistoryTests(unittest.TestCase):
    def test_email_recipients_are_deserialized(self):
        report = ReportHistory(email_recipients_json='["a@example.com", "b@example.com"]')
        self.assertEqual(report.email_recipients, ["a@example.com", "b@example.com"])

    def test_invalid_email_recipients_are_safe(self):
        report = ReportHistory(email_recipients_json="invalid")
        self.assertEqual(report.email_recipients, [])
