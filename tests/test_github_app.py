import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from app.github_app import _request_json, GitHubAppError


class RequestJsonRetryTests(unittest.TestCase):
    @patch("app.github_app.time.sleep")
    @patch("app.github_app.urllib.request.urlopen")
    def test_retries_on_429(self, mock_urlopen, mock_sleep):
        error_response = MagicMock()
        error_response.read.return_value = b"rate limited"
        http_error = urllib.error.HTTPError(
            "https://api.github.com/test", 429, "Too Many Requests", {}, error_response
        )

        success_response = MagicMock()
        success_response.read.return_value = json.dumps({"ok": True}).encode()
        success_response.__enter__ = MagicMock(return_value=success_response)
        success_response.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [http_error, success_response]

        result = _request_json("https://api.github.com/test", token="fake")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch("app.github_app.time.sleep")
    @patch("app.github_app.urllib.request.urlopen")
    def test_raises_after_3_failures(self, mock_urlopen, mock_sleep):
        error_response = MagicMock()
        error_response.read.return_value = b"server error"
        http_error = urllib.error.HTTPError(
            "https://api.github.com/test", 500, "Internal Server Error", {}, error_response
        )

        mock_urlopen.side_effect = [http_error, http_error, http_error]

        with self.assertRaises(GitHubAppError) as ctx:
            _request_json("https://api.github.com/test", token="fake")

        self.assertIn("500", str(ctx.exception))
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
