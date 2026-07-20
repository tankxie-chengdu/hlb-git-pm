from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict


@dataclass(frozen=True)
class MemberInfo:
    real_name: str
    department: str = ""
    is_outsourced: bool | None = None


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
    committed_at: datetime | None = None

    @property
    def activity_at(self) -> datetime:
        """Timestamp used for report period and trend calculations."""
        return self.committed_at or self.authored_at


@dataclass
class RepositoryReport:
    name: str
    branch: str
    commits: list[Commit] = field(default_factory=list)
    error: str | None = None


def _resolve_member(mapping: dict[str, MemberInfo], commit: Commit) -> MemberInfo:
    email = (commit.author_email or "").strip().casefold()
    local = email.split("@", 1)[0] if "@" in email else email
    name = (commit.author_name or "").strip().casefold()
    return mapping.get(email) or mapping.get(local) or mapping.get(name) or MemberInfo(commit.author_name)


def _person_contributions(repositories: list[RepositoryReport], mapping: dict[str, MemberInfo]) -> list[dict[str, object]]:
    people: dict[str, dict[str, object]] = {}
    for info in mapping.values():
        people.setdefault(
            info.real_name,
            {"name": info.real_name, "department": info.department, "is_outsourced": info.is_outsourced, "commits": []},
        )
    for repo in repositories:
        for commit in repo.commits:
            info = _resolve_member(mapping, commit)
            entry = people.setdefault(
                info.real_name,
                {"name": info.real_name, "department": info.department, "is_outsourced": info.is_outsourced, "commits": []},
            )
            entry["commits"].append(commit)
    result = []
    for entry in people.values():
        commits = entry.pop("commits")
        by_project: dict[str, list[Commit]] = {}
        for commit in commits:
            by_project.setdefault(commit.repository, []).append(commit)
        result.append(
            {
                **entry,
                "commit_count": len(commits),
                "active_days": len({commit.activity_at.date() for commit in commits}),
                "repository_count": len(by_project),
                "files_changed": sum(commit.files_changed for commit in commits),
                "additions": sum(commit.additions for commit in commits),
                "deletions": sum(commit.deletions for commit in commits),
                "last_commit_at": max((commit.activity_at for commit in commits), default=None),
                "projects": [
                    {"name": name, "commits": len(project_commits)}
                    for name, project_commits in sorted(by_project.items(), key=lambda item: (-len(item[1]), item[0]))
                ],
            }
        )
    return sorted(result, key=lambda row: (-int(row["commit_count"]), str(row["name"])))


def _project_contributions(repositories: list[RepositoryReport], mapping: dict[str, MemberInfo]) -> list[dict[str, object]]:
    result = []
    for repo in repositories:
        by_person: dict[str, dict[str, object]] = {}
        for commit in repo.commits:
            info = _resolve_member(mapping, commit)
            entry = by_person.setdefault(
                info.real_name,
                {"name": info.real_name, "department": info.department, "is_outsourced": info.is_outsourced, "commits": []},
            )
            entry["commits"].append(commit)
        contributors = []
        for entry in by_person.values():
            commits = entry.pop("commits")
            contributors.append(
                {
                    **entry,
                    "commit_count": len(commits),
                    "active_days": len({commit.activity_at.date() for commit in commits}),
                    "files_changed": sum(commit.files_changed for commit in commits),
                    "additions": sum(commit.additions for commit in commits),
                    "deletions": sum(commit.deletions for commit in commits),
                    "last_commit_at": max((commit.activity_at for commit in commits), default=None),
                }
            )
        result.append(
            {
                "name": repo.name,
                "branch": repo.branch,
                "status": "failed" if repo.error else ("active" if repo.commits else "empty"),
                "commit_count": len(repo.commits),
                "contributor_count": len(contributors),
                "files_changed": sum(commit.files_changed for commit in repo.commits),
                "additions": sum(commit.additions for commit in repo.commits),
                "deletions": sum(commit.deletions for commit in repo.commits),
                "last_commit_at": max((commit.activity_at for commit in repo.commits), default=None),
                "contributors": sorted(contributors, key=lambda row: (-int(row["commit_count"]), str(row["name"]))),
                "error": repo.error,
            }
        )
    return sorted(result, key=lambda row: (row["status"] != "active", -int(row["commit_count"]), str(row["name"])))


@dataclass
class DailyReport:
    report_date: str
    generated_at: datetime
    repositories: list[RepositoryReport]
    ai_analysis: str = ""
    project_analyses: list[dict[str, object]] = field(default_factory=list)
    member_mapping: dict[str, MemberInfo] = field(default_factory=dict)
    total_repositories_count: int = 0  # Total repos in database (for context)
    organization: str = "WeFi-HLB"
    trend_chart_png: bytes | None = None

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
        return sum(1 for row in self.person_contributions if row["commit_count"])

    @property
    def total_files_changed(self) -> int:
        return sum(commit.files_changed for commit in self.commits)

    @property
    def daily_trend(self) -> list[dict[str, int | str]]:
        commits_by_day: dict[str, list[Commit]] = defaultdict(list)
        for commit in self.commits:
            commits_by_day[commit.activity_at.date().isoformat()].append(commit)
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
                    "last_commit_at": max((c.activity_at for c in commits), default=None),
                    "error": repo.error,
                }
            )
        return sorted(activity, key=lambda row: (row["status"] != "active", -int(row["commits"])))

    def _resolve_name(self, commit: Commit) -> str:
        return _resolve_member(self.member_mapping, commit).real_name

    def _resolve_member_info(self, commit: Commit) -> MemberInfo:
        return _resolve_member(self.member_mapping, commit)

    def display_repository_name(self, name: str) -> str:
        prefix = f"{self.organization}/" if self.organization else ""
        return name[len(prefix):] if prefix and name.startswith(prefix) else name

    @property
    def commits_by_author(self) -> dict[str, list[Commit]]:
        result: dict[str, list[Commit]] = {}
        for commit in self.commits:
            result.setdefault(self._resolve_name(commit), []).append(commit)
        return result

    @property
    def person_contributions(self) -> list[dict[str, object]]:
        return _person_contributions(self.repositories, self.member_mapping)

    @property
    def project_contributions(self) -> list[dict[str, object]]:
        return _project_contributions(self.repositories, self.member_mapping)


@dataclass
class PeriodReport:
    report_type: str  # daily / weekly / monthly
    period_start: str  # ISO date
    period_end: str  # ISO date
    generated_at: datetime
    repositories: list[RepositoryReport]
    ai_analysis: str = ""
    project_analyses: list[dict[str, object]] = field(default_factory=list)
    member_mapping: dict[str, MemberInfo] = field(default_factory=dict)
    total_repositories_count: int = 0  # Total repos in database (for context)
    organization: str = "WeFi-HLB"
    trend_chart_png: bytes | None = None

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
        return sum(1 for row in self.person_contributions if row["commit_count"])

    @property
    def total_files_changed(self) -> int:
        return sum(commit.files_changed for commit in self.commits)

    @property
    def daily_trend(self) -> list[dict[str, int | str]]:
        commits_by_day: dict[str, list[Commit]] = defaultdict(list)
        for commit in self.commits:
            commits_by_day[commit.activity_at.date().isoformat()].append(commit)
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
                    "last_commit_at": max((c.activity_at for c in commits), default=None),
                    "error": repo.error,
                }
            )
        return sorted(activity, key=lambda row: (row["status"] != "active", -int(row["commits"])))

    def _resolve_name(self, commit: Commit) -> str:
        return _resolve_member(self.member_mapping, commit).real_name

    def _resolve_member_info(self, commit: Commit) -> MemberInfo:
        return _resolve_member(self.member_mapping, commit)

    def display_repository_name(self, name: str) -> str:
        prefix = f"{self.organization}/" if self.organization else ""
        return name[len(prefix):] if prefix and name.startswith(prefix) else name

    @property
    def commits_by_author(self) -> dict[str, list[Commit]]:
        result: dict[str, list[Commit]] = {}
        for commit in self.commits:
            name = self._resolve_name(commit)
            result.setdefault(name, []).append(commit)
        return result

    @property
    def person_contributions(self) -> list[dict[str, object]]:
        return _person_contributions(self.repositories, self.member_mapping)

    @property
    def project_contributions(self) -> list[dict[str, object]]:
        return _project_contributions(self.repositories, self.member_mapping)
