from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db_models import Recipient, User
from ..deps import get_current_user, get_db
from ..schemas import RecipientCreate, RecipientOut, RecipientUpdate

router = APIRouter(prefix="/recipients", tags=["recipients"])


@router.get("", response_model=list[RecipientOut])
def list_recipients(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return db.query(Recipient).order_by(Recipient.id).all()


@router.post("", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
def create_recipient(body: RecipientCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    existing = db.query(Recipient).filter(Recipient.email == body.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已存在")
    recipient = Recipient(**body.model_dump())
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


@router.put("/{recipient_id}", response_model=RecipientOut)
def update_recipient(recipient_id: int, body: RecipientUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    recipient = db.query(Recipient).filter(Recipient.id == recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="收件人不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(recipient, key, value)
    db.commit()
    db.refresh(recipient)
    return recipient


@router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipient(recipient_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    recipient = db.query(Recipient).filter(Recipient.id == recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="收件人不存在")
    db.delete(recipient)
    db.commit()
