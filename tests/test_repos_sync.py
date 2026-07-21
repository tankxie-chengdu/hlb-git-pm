from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from web.api import repos as repos_api
from web.db_models import Repository, SyncJob


class RepositorySyncApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Repository.__table__.create(self.engine)
        SyncJob.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.user = SimpleNamespace(id=1)
        self.previous_config = repos_api._app_config
        repos_api._app_config = SimpleNamespace(github=object())
        with repos_api._sync_lock:
            repos_api._sync_jobs.clear()

    def tearDown(self):
        with repos_api._sync_lock:
            repos_api._sync_jobs.clear()
        repos_api._app_config = self.previous_config
        self.session.close()
        self.engine.dispose()

    def add_repo(self, name: str, *, deleted: bool = False) -> None:
        self.session.add(
            Repository(
                full_name=name,
                clone_url=f"https://github.com/{name}.git",
                pushed_at="2026-07-21T01:00:00Z",
                is_deleted=deleted,
            )
        )
        self.session.commit()

    @patch("web.api.repos.threading.Thread")
    def test_force_sequential_flags_are_passed_to_background_worker(self, thread_class):
        self.add_repo("WeFi-HLB/demo")

        result = repos_api.sync_repos(
            full_names=["WeFi-HLB/demo"],
            force=True,
            sequential=True,
            db=self.session,
            _user=self.user,
        )

        self.assertEqual(result["queued"], ["WeFi-HLB/demo"])
        self.assertTrue(result["force"])
        self.assertTrue(result["sequential"])
        self.assertEqual(thread_class.call_args.kwargs["kwargs"], {"force": True, "sequential": True})
        thread_class.return_value.start.assert_called_once_with()

    @patch("web.api.repos.threading.Thread")
    def test_full_sync_excludes_deleted_repositories(self, _thread_class):
        self.add_repo("WeFi-HLB/active")
        self.add_repo("WeFi-HLB/deleted", deleted=True)

        result = repos_api.sync_repos(
            full_names=[],
            force=True,
            sequential=True,
            db=self.session,
            _user=self.user,
        )

        self.assertEqual(result["queued"], ["WeFi-HLB/active"])

    @patch("web.api.repos.threading.Thread")
    def test_repository_already_running_is_not_queued_twice(self, thread_class):
        self.add_repo("WeFi-HLB/demo")
        with repos_api._sync_lock:
            repos_api._sync_jobs["WeFi-HLB/demo"] = {"status": "syncing", "error": None}

        result = repos_api.sync_repos(
            full_names=["WeFi-HLB/demo"],
            force=True,
            sequential=True,
            db=self.session,
            _user=self.user,
        )

        self.assertEqual(result["queued"], [])
        self.assertEqual(result["skipped"], ["WeFi-HLB/demo"])
        thread_class.assert_not_called()

    def test_in_memory_status_overrides_stale_database_status(self):
        self.session.add(SyncJob(repo_name="WeFi-HLB/demo", status="done"))
        self.session.commit()
        with repos_api._sync_lock:
            repos_api._sync_jobs["WeFi-HLB/demo"] = {"status": "queued", "error": None}

        result = repos_api.sync_status(db=self.session, _user=self.user)

        self.assertEqual(result["WeFi-HLB/demo"]["status"], "queued")


if __name__ == "__main__":
    unittest.main()
