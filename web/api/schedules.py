from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db_models import Schedule, User
from ..deps import get_current_user, get_db
from ..schemas import ScheduleCreate, ScheduleOut, ScheduleUpdate

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _sync_scheduler():
    """Notify the scheduler engine to reload jobs from DB."""
    try:
        from scheduler.engine import sync_jobs
        sync_jobs()
    except Exception:
        pass  # scheduler may not be running (e.g. during tests)


@router.get("", response_model=list[ScheduleOut])
def list_schedules(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return db.query(Schedule).order_by(Schedule.id).all()


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(body: ScheduleCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    schedule = Schedule(**body.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    _sync_scheduler()
    return schedule


@router.put("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, body: ScheduleUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调度计划不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(schedule, key, value)
    db.commit()
    db.refresh(schedule)
    _sync_scheduler()
    return schedule


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调度计划不存在")
    db.delete(schedule)
    db.commit()
    _sync_scheduler()
