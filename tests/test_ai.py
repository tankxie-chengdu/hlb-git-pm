import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.ai import analyze
from app.config import AiConfig
from app.models import DailyReport


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class AiTests(unittest.TestCase):
    def test_zai_thinking_flag_is_sent(self):
        config = AiConfig(
            base_url="https://api.z.ai/api/coding/paas/v4",
            api_key="test-key",
            model="glm-5.2",
            thinking_enabled=False,
        )
        response = _Response({"choices": [{"message": {"content": "分析完成"}}]})
        with patch("app.ai.urllib.request.urlopen", return_value=response) as request:
            result = analyze(DailyReport("2026-07-15", datetime.now(timezone.utc), []), config)
        body = json.loads(request.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(result, "分析完成")
        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_empty_content_falls_back_instead_of_returning_blank(self):
        config = AiConfig(api_key="test-key", thinking_enabled=False)
        response = _Response({"choices": [{"message": {"content": "", "reasoning_content": "..."}}]})
        with patch("app.ai.urllib.request.urlopen", return_value=response):
            result = analyze(DailyReport("2026-07-15", datetime.now(timezone.utc), []), config)
        self.assertIn("AI 返回空正文", result)

