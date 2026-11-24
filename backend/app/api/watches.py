from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, rate_limit
from app.models.room import Room
from app.models.user import User
from app.models.watch import Watch
from app.schemas.watch import (
    ParseRequest,
    ParseResponse,
    WatchCreate,
    WatchOut,
    WatchUpdate,
)
from app.services import room_service, watch_service

router = APIRouter(prefix="/watches", tags=["watches"])


def _resolve_watch(db: Session, watch_id: int, user: User) -> tuple[Watch, Room]:
    watch = db.get(Watch, watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    room = room_service.get_room_for_user(db, watch.room_id, user)
    return watch, room


@router.post(
    "/parse",
    response_model=ParseResponse,
    dependencies=[Depends(rate_limit("watch-parse", 60))],
)
def parse_watch(
    payload: ParseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ParseResponse:
    if payload.room_id is not None:
        room_service.get_room_for_user(db, payload.room_id, user)
    return watch_service.preview_parse(payload.text)


@router.post("", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
def create_watch(
    payload: WatchCreate,
    room_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    target_room_id = payload.room_id or room_id
    if target_room_id is None:
        raise HTTPException(status_code=422, detail="room_id is required (query or body)")
    room = room_service.get_room_for_user(db, target_room_id, user)
    watch = watch_service.create_from_parsed(db, room, user, payload)
    return watch_service.to_watch_out(db, watch)


@router.get("", response_model=list[WatchOut])
def list_watches(
    room_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    watch_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WatchOut]:
    if room_id is not None:
        room = room_service.get_room_for_user(db, room_id, user)
        watches = watch_service.list_watches(db, room, status_filter, watch_type)
    else:
        watches = watch_service.list_watches_for_user(db, user, status_filter, watch_type)
    return [watch_service.to_watch_out(db, watch) for watch in watches]


@router.get("/{watch_id}", response_model=WatchOut)
def get_watch(
    watch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    watch, _room = _resolve_watch(db, watch_id, user)
    return watch_service.to_watch_out(db, watch)


@router.patch("/{watch_id}", response_model=WatchOut)
def update_watch(
    watch_id: int,
    payload: WatchUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    _watch, room = _resolve_watch(db, watch_id, user)
    updated = watch_service.update_watch(db, room, watch_id, payload)
    return watch_service.to_watch_out(db, updated)


@router.post("/{watch_id}/pause", response_model=WatchOut)
def pause_watch(
    watch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    _watch, room = _resolve_watch(db, watch_id, user)
    paused = watch_service.set_watch_status(db, room, watch_id, "paused")
    return watch_service.to_watch_out(db, paused)


@router.post("/{watch_id}/resume", response_model=WatchOut)
def resume_watch(
    watch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    _watch, room = _resolve_watch(db, watch_id, user)
    resumed = watch_service.set_watch_status(db, room, watch_id, "active")
    return watch_service.to_watch_out(db, resumed)


@router.delete("/{watch_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_watch(
    watch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    _watch, room = _resolve_watch(db, watch_id, user)
    watch_service.delete_watch(db, room, watch_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
