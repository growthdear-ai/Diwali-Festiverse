from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.alert import Alert
from app.models.user import User
from app.models.watch import Watch
from app.schemas.alert import AlertOut, CompleteRequest, CompleteResponse, ShareOut
from app.schemas.vote import VoteRequest, VoteSummary
from app.services import alert_service, room_service, voting_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _alert_for_user(db: Session, alert_id: int, user: User) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    room_service.get_room_for_user(db, alert.room_id, user)
    return alert


@router.get("", response_model=list[AlertOut])
def list_alerts(
    room_id: int | None = Query(default=None, ge=1),
    watch_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AlertOut]:
    if watch_id is not None:
        watch = db.get(Watch, watch_id)
        if watch is None:
            raise HTTPException(status_code=404, detail="Watch not found")
        room = room_service.get_room_for_user(db, watch.room_id, user)
        if room_id is not None and room_id != room.id:
            raise HTTPException(status_code=422, detail="watch_id does not belong to room_id")
        alerts = alert_service.list_alerts(db, room.id, limit, watch_id=watch_id)
    elif room_id is not None:
        room = room_service.get_room_for_user(db, room_id, user)
        alerts = alert_service.list_alerts(db, room.id, limit)
    else:
        alerts = alert_service.list_alerts_for_user(db, user, limit)
    return [alert_service.to_alert_out(db, alert, include_votes=True) for alert in alerts]


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertOut:
    alert = _alert_for_user(db, alert_id, user)
    return alert_service.to_alert_out(db, alert, include_votes=True)


@router.post("/{alert_id}/vote", response_model=VoteSummary)
def vote(
    alert_id: int,
    payload: VoteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoteSummary:
    alert = _alert_for_user(db, alert_id, user)
    voting_service.cast_vote(db, alert, user, payload.choice)
    return VoteSummary(**voting_service.summary(db, alert, user))


@router.post("/{alert_id}/complete", response_model=CompleteResponse)
def complete(
    alert_id: int,
    payload: CompleteRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompleteResponse:
    alert = _alert_for_user(db, alert_id, user)
    result = voting_service.complete_watch(db, alert, user)
    return CompleteResponse(**result)


@router.get("/{alert_id}/share", response_model=ShareOut)
def share(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareOut:
    alert = _alert_for_user(db, alert_id, user)
    return alert_service.share_alert(db, alert.room_id, alert.id)
