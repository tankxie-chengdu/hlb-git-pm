from pathlib import Path
import logging
import os
import tempfile
import unittest

from app.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_with_environment(self):
        old_key = os.environ.get("AI_KEY")
        os.environ["AI_KEY"] = "secret"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_file = Path(temp_dir) / "config.toml"
                config_file.write_text(
                    '''[[repositories]]
name = "demo"
path = "/tmp/demo"

[ai]
api_key = "${AI_KEY}"

[email]
host = "smtp.example.com"
sender = "from@example.com"
recipients = ["to@example.com"]
''',
                    encoding="utf-8",
                )
                config = load_config(config_file)
                self.assertEqual(config.ai.api_key, "secret")
                self.assertEqual(config.repositories[0].name, "demo")
        finally:
            if old_key is None:
                os.environ.pop("AI_KEY", None)
            else:
                os.environ["AI_KEY"] = old_key

    def test_github_config_can_supply_repository_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.toml"
            config_file.write_text(
                '''[github]
organization = "WeFi-HLB"
app_id = 4320314
installation_id = 147107481
private_key_file = "/etc/git-daily-report/github-app.pem"

[email]
host = "smtp.example.com"
sender = "from@example.com"
recipients = ["to@example.com"]
''',
                encoding="utf-8",
            )
            config = load_config(config_file)
            self.assertEqual(config.github.organization, "WeFi-HLB")
            self.assertEqual(config.github.installation_id, 147107481)

    def test_missing_env_var_logs_warning(self):
        os.environ.pop("NONEXISTENT_VAR_FOR_TEST", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.toml"
            config_file.write_text(
                '''[[repositories]]
name = "demo"
path = "/tmp/demo"

[ai]
api_key = "${NONEXISTENT_VAR_FOR_TEST}"

[email]
host = "smtp.example.com"
sender = "from@example.com"
recipients = ["to@example.com"]
''',
                encoding="utf-8",
            )
            with self.assertLogs("git_daily_report.config", level="WARNING") as cm:
                config = load_config(config_file)
            self.assertEqual(config.ai.api_key, "")
            self.assertTrue(any("NONEXISTENT_VAR_FOR_TEST" in msg for msg in cm.output))

    def test_invalid_run_at_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.toml"
            config_file.write_text(
                '''run_at = "99:99"

[[repositories]]
name = "demo"
path = "/tmp/demo"

[email]
host = "smtp.example.com"
sender = "from@example.com"
recipients = ["to@example.com"]
''',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                load_config(config_file)
            self.assertIn("run_at", str(ctx.exception))

    def test_invalid_ai_base_url_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.toml"
            config_file.write_text(
                '''[[repositories]]
name = "demo"
path = "/tmp/demo"

[ai]
base_url = "http://insecure.example.com/v1"

[email]
host = "smtp.example.com"
sender = "from@example.com"
recipients = ["to@example.com"]
''',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                load_config(config_file)
            self.assertIn("HTTPS", str(ctx.exception))
