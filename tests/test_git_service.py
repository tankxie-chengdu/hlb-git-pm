import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import RepositoryConfig
from app.git_service import ensure_repository, scan_repository


class GitServiceTests(unittest.TestCase):
    def test_scan_filters_day_and_collects_numstat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.name", "Alice")
            self._git(repo, "config", "user.email", "alice@example.com")
            (repo / "README.md").write_text("one\n", encoding="utf-8")
            self._git_commit(repo, "first", "2026-07-14T10:00:00+08:00")
            (repo / "README.md").write_text("one\ntwo\n", encoding="utf-8")
            self._git_commit(repo, "second", "2026-07-15T10:00:00+08:00")
            result = scan_repository(
                RepositoryConfig(name="demo", path=str(repo), branch="main", fetch=False),
                Path(temp_dir) / "workspace",
                date(2026, 7, 15),
                ZoneInfo("Asia/Shanghai"),
            )
            self.assertIsNone(result.error)
            self.assertEqual(len(result.commits), 1)
            self.assertEqual(result.commits[0].subject, "second")
            self.assertEqual(result.commits[0].additions, 1)
            self.assertEqual(result.commits[0].deletions, 0)

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    @classmethod
    def _git_commit(cls, repo: Path, message: str, timestamp: str) -> None:
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = timestamp
        env["GIT_COMMITTER_DATE"] = timestamp
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True, env=env)

    def test_scan_logs_warning_on_bad_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = scan_repository(
                RepositoryConfig(name="nonexistent", path="/tmp/nonexistent-repo-path-xyz", branch="main", fetch=False),
                Path(temp_dir) / "workspace",
                date(2026, 7, 15),
                ZoneInfo("Asia/Shanghai"),
            )
            self.assertIsNotNone(result.error)
            self.assertIn("nonexistent", result.name)

    def test_skip_clone_does_not_create_missing_mirror(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            config = RepositoryConfig(
                name="org/missing",
                url="https://github.com/org/missing.git",
                fetch=False,
            )
            with self.assertRaisesRegex(RuntimeError, "尚未同步本地 mirror"):
                ensure_repository(config, workspace, allow_clone=False)
            self.assertFalse((workspace / "org" / "missing").exists())
