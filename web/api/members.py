from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db_models import ContributorStat, Member, User
from ..deps import get_current_user, get_db
from ..schemas import MemberCreate, MemberOut, MemberUpdate

router = APIRouter(prefix="/members", tags=["members"])


def _is_outsourced_name(real_name: str) -> bool:
    return (real_name or "").strip().casefold().startswith("v_")


def _match_member(
    git_email: str,
    git_name: str,
    email_to_member: dict[str, Member],
    name_to_member: dict[str, Member],
) -> Member | None:
    email_key = (git_email or "").strip().casefold()
    name_key = (git_name or "").strip().casefold()
    email_local = email_key.split("@", 1)[0] if "@" in email_key else email_key
    return email_to_member.get(email_key) or name_to_member.get(name_key) or name_to_member.get(email_local)


def _member_name_lookup(members: list[Member]) -> dict[str, Member]:
    lookup: dict[str, Member] = {}
    for member in members:
        if member.git_name:
            lookup[member.git_name.strip().casefold()] = member
        # The roster account is intentionally retained in real_name, for
        # example rookietang(汤加伟), even when git_name is an alias.
        roster_account, separator, _ = (member.real_name or "").partition("(")
        if separator and roster_account.strip():
            lookup[roster_account.strip().casefold()] = member
    return lookup


def _member_last_commits(
    rows: list[ContributorStat],
    email_to_member: dict[str, Member],
    name_to_member: dict[str, Member],
) -> dict[int, str]:
    latest: dict[int, str] = {}
    for row in rows:
        member = _match_member(row.git_email, row.git_name, email_to_member, name_to_member)
        if member and row.last_commit_at > latest.get(member.id, ""):
            latest[member.id] = row.last_commit_at
    return latest


@router.get("/contributors")
def list_contributors(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Aggregate all contributor_stats rows by git_email.

    Returns every unique committer found across all synced repos, enriched
    with member info (real_name, department) when available.
    """
    rows = db.query(ContributorStat).order_by(ContributorStat.git_email).all()

    # Build member lookup
    members = db.query(Member).all()
    email_to_member: dict[str, Member] = {m.git_email.strip().casefold(): m for m in members if m.git_email}
    name_to_member = _member_name_lookup(members)

    # Aggregate by email
    agg: dict[str, dict] = {}
    for row in rows:
        key = row.git_email.lower()
        member = _match_member(row.git_email, row.git_name, email_to_member, name_to_member)
        if key not in agg:
            agg[key] = {
                "git_email": row.git_email,
                "git_name": row.git_name,
                "real_name": member.real_name if member else "",
                "department": member.department if member else "",
                "is_outsourced": member.is_outsourced if member else False,
                "member_id": member.id if member else None,
                "total_commits": 0,
                "repos": [],
                "last_commit_at": "",
            }
        entry = agg[key]
        if member and entry["member_id"] is None:
            entry.update(
                real_name=member.real_name,
                department=member.department,
                is_outsourced=member.is_outsourced,
                member_id=member.id,
            )
        entry["total_commits"] += row.commit_count
        entry["repos"].append({
            "repo_name": row.repo_name,
            "commit_count": row.commit_count,
            "first_commit_at": row.first_commit_at,
            "last_commit_at": row.last_commit_at,
        })
        if row.last_commit_at > entry["last_commit_at"]:
            entry["last_commit_at"] = row.last_commit_at

    result = sorted(
        agg.values(),
        key=lambda item: (item["last_commit_at"], item["total_commits"]),
        reverse=True,
    )
    return result


@router.get("", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    members = db.query(Member).all()
    contributor_rows = db.query(ContributorStat).all()
    email_to_member = {member.git_email.strip().casefold(): member for member in members if member.git_email}
    name_to_member = _member_name_lookup(members)
    latest = _member_last_commits(contributor_rows, email_to_member, name_to_member)
    result = [
        {
            "id": member.id,
            "git_email": member.git_email,
            "git_name": member.git_name,
            "real_name": member.real_name,
            "department": member.department,
            "is_outsourced": member.is_outsourced,
            "last_commit_at": latest.get(member.id, ""),
        }
        for member in members
    ]
    return sorted(result, key=lambda item: (item["last_commit_at"], item["real_name"]), reverse=True)


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(body: MemberCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    values = body.model_dump()
    if values["is_outsourced"] is None:
        values["is_outsourced"] = _is_outsourced_name(values["real_name"])
    member = Member(**values)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.put("/{member_id}", response_model=MemberOut)
def update_member(member_id: int, body: MemberUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人员不存在")
    values = body.model_dump(exclude_unset=True)
    if "real_name" in values and "is_outsourced" not in values:
        values["is_outsourced"] = _is_outsourced_name(values["real_name"] or "")
    for key, value in values.items():
        setattr(member, key, value)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人员不存在")
    db.delete(member)
    db.commit()
