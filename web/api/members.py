from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db_models import ContributorStat, Member, User
from ..deps import get_current_user, get_db
from ..schemas import MemberCreate, MemberOut, MemberUpdate

router = APIRouter(prefix="/members", tags=["members"])


@router.get("/contributors")
def list_contributors(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Aggregate all contributor_stats rows by git_email.

    Returns every unique committer found across all synced repos, enriched
    with member info (real_name, department) when available.
    """
    rows = db.query(ContributorStat).order_by(ContributorStat.git_email).all()

    # Build member lookup
    members = db.query(Member).all()
    email_to_member: dict[str, Member] = {m.git_email.lower(): m for m in members if m.git_email}

    # Aggregate by email
    agg: dict[str, dict] = {}
    for row in rows:
        key = row.git_email.lower()
        if key not in agg:
            m = email_to_member.get(key)
            agg[key] = {
                "git_email": row.git_email,
                "git_name": row.git_name,
                "real_name": m.real_name if m else "",
                "department": m.department if m else "",
                "member_id": m.id if m else None,
                "total_commits": 0,
                "repos": [],
                "last_commit_at": "",
            }
        entry = agg[key]
        entry["total_commits"] += row.commit_count
        entry["repos"].append({
            "repo_name": row.repo_name,
            "commit_count": row.commit_count,
            "first_commit_at": row.first_commit_at,
            "last_commit_at": row.last_commit_at,
        })
        if row.last_commit_at > entry["last_commit_at"]:
            entry["last_commit_at"] = row.last_commit_at

    result = sorted(agg.values(), key=lambda x: x["total_commits"], reverse=True)
    return result


@router.get("", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return db.query(Member).order_by(Member.id).all()


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(body: MemberCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    member = Member(**body.model_dump())
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.put("/{member_id}", response_model=MemberOut)
def update_member(member_id: int, body: MemberUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人员不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
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
