from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.alert import Alert
from app.models.user import User
from app.schemas.vote import VoteSummary
from app.services import room_service, voting_service

router = APIRouter(prefix="/alerts", tags=["votes"])


@router.get("/{alert_id}/votes", response_model=VoteSummary)
def get_votes(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoteSummary:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    room_service.get_room_for_user(db, alert.room_id, user)
    return VoteSummary(**voting_service.summary(db, alert, user))
