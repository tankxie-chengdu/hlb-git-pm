from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict


@dataclass(frozen=True)
class MemberInfo:
    real_name: str
    department: str = ""


@dataclass(frozen=True)
class Commit:
    repository: str
    sha: str
    author_name: str
    author_email: str
    authored_at: datetime
    subject: str
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0


@dataclass
class RepositoryReport:
    name: str
    branch: str
    commits: list[Commit] = field(default_factory=list)
    error: str | None = None


@dataclass
class DailyReport:
    report_date: str
    generated_at: datetime
    repositories: list[RepositoryReport]
    ai_analysis: str = ""
    total_repositories_count: int = 0  # Total repos in database (for context)

    @property
    def commits(self) -> list[Commit]:
        return [commit for repo in self.repositories for commit in repo.commits]

    @property
    def total_commits(self) -> int:
        return len(self.commits)

    @property
    def total_additions(self) -> int:
        return sum(commit.additions for commit in self.commits)

    @property
    def total_deletions(self) -> int:
        return sum(commit.deletions for commit in self.commits)

    @property
    def scanned_repositories(self) -> int:
        return len(self.repositories)

    @property
    def failed_repositories(self) -> int:
        return sum(1 for repo in self.repositories if repo.error)

    @property
    def active_repositories(self) -> int:
        return sum(1 for repo in self.repositories if repo.commits and not repo.error)

    @property
    def empty_repositories(self) -> int:
        return sum(1 for repo in self.repositories if not repo.commits and not repo.error)

    @property
    def contributor_count(self) -> int:
        return len({(commit.author_email or commit.author_name).lower() for commit in self.commits})

    @property
    def total_files_changed(self) -> int:
        return sum(commit.files_changed for commit in self.commits)

    @property
    def daily_trend(self) -> list[dict[str, int | str]]:
        commits_by_day: dict[str, list[Commit]] = defaultdict(list)
        for commit in self.commits:
            commits_by_day[commit.authored_at.date().isoformat()].append(commit)
        return [
            {
                "date": day,
                "commits": len(commits),
                "repositories": len({commit.repository for commit in commits}),
                "contributors": len({(commit.author_email or commit.author_name).lower() for commit in commits}),
            }
            for day, commits in sorted(commits_by_day.items())
        ]

    @property
    def repository_activity(self) -> list[dict[str, object]]:
        activity = []
        for repo in self.repositories:
            commits = repo.commits
            activity.append(
                {
                    "name": repo.name,
                    "branch": repo.branch,
                    "status": "failed" if repo.error else ("active" if commits else "empty"),
                    "commits": len(commits),
                    "contributors": len({(c.author_email or c.author_name).lower() for c in commits}),
                    "files_changed": sum(c.files_changed for c in commits),
                    "additions": sum(c.additions for c in commits),
                    "deletions": sum(c.deletions for c in commits),
                    "last_commit_at": max((c.authored_at for c in commits), default=None),
                    "error": repo.error,
                }
            )
        return sorted(activity, key=lambda row: (row["status"] != "active", -int(row["commits"])))


@dataclass
class PeriodReport:
    report_type: str  # daily / weekly / monthly
    period_start: str  # ISO date
    period_end: str  # ISO date
    generated_at: datetime
    repositories: list[RepositoryReport]
    ai_analysis: str = ""
    member_mapping: dict[str, MemberInfo] = field(default_factory=dict)
    total_repositories_count: int = 0  # Total repos in database (for context)

    @property
    def commits(self) -> list[Commit]:
        return [commit for repo in self.repositories for commit in repo.commits]

    @property
    def total_commits(self) -> int:
        return len(self.commits)

    @property
    def total_additions(self) -> int:
        return sum(commit.additions for commit in self.commits)

    @property
    def total_deletions(self) -> int:
        return sum(commit.deletions for commit in self.commits)

    @property
    def scanned_repositories(self) -> int:
        return len(self.repositories)

    @property
    def failed_repositories(self) -> int:
        return sum(1 for repo in self.repositories if repo.error)

    @property
    def active_repositories(self) -> int:
        return sum(1 for repo in self.repositories if repo.commits and not repo.error)

    @property
    def empty_repositories(self) -> int:
        return sum(1 for repo in self.repositories if not repo.commits and not repo.error)

    @property
    def contributor_count(self) -> int:
        return len({(commit.author_email or commit.author_name).lower() for commit in self.commits})

    @property
    def total_files_changed(self) -> int:
        return sum(commit.files_changed for commit in self.commits)

    @property
    def daily_trend(self) -> list[dict[str, int | str]]:
        commits_by_day: dict[str, list[Commit]] = defaultdict(list)
        for commit in self.commits:
            commits_by_day[commit.authored_at.date().isoformat()].append(commit)
        return [
            {
                "date": day,
                "commits": len(commits),
                "repositories": len({commit.repository for commit in commits}),
                "contributors": len({(commit.author_email or commit.author_name).lower() for commit in commits}),
            }
            for day, commits in sorted(commits_by_day.items())
        ]

    @property
    def repository_activity(self) -> list[dict[str, object]]:
        activity = []
        for repo in self.repositories:
            commits = repo.commits
            activity.append(
                {
                    "name": repo.name,
                    "branch": repo.branch,
                    "status": "failed" if repo.error else ("active" if commits else "empty"),
                    "commits": len(commits),
                    "contributors": len({(c.author_email or c.author_name).lower() for c in commits}),
                    "files_changed": sum(c.files_changed for c in commits),
                    "additions": sum(c.additions for c in commits),
                    "deletions": sum(c.deletions for c in commits),
                    "last_commit_at": max((c.authored_at for c in commits), default=None),
                    "error": repo.error,
                }
            )
        return sorted(activity, key=lambda row: (row["status"] != "active", -int(row["commits"])))

    def _resolve_name(self, commit: Commit) -> str:
        info = self.member_mapping.get(commit.author_email.lower())
        if info:
            return info.real_name
        for key, info in self.member_mapping.items():
            if key == commit.author_name:
                return info.real_name
        return commit.author_name

    @property
    def commits_by_author(self) -> dict[str, list[Commit]]:
        result: dict[str, list[Commit]] = {}
        for commit in self.commits:
            name = self._resolve_name(commit)
            result.setdefault(name, []).append(commit)
        return result
