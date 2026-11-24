from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.room import InviteOut, MemberOut, RoomCreate, RoomOut
from app.services import room_service

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RoomOut:
    return room_service.create_room(db, user, payload)


@router.get("", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[RoomOut]:
    return room_service.list_rooms(db, user)


@router.post("/join/{code}", response_model=RoomOut)
def join_room(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RoomOut:
    return room_service.join_room(db, user, code)


@router.get("/{room_id}", response_model=RoomOut)
def get_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RoomOut:
    room = room_service.get_room_for_user(db, room_id, user)
    return room_service.to_room_out(db, room, user)


@router.post("/{room_id}/invite", response_model=InviteOut)
def invite(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InviteOut:
    return room_service.invite_for_room(db, room_id, user)


@router.get("/{room_id}/members", response_model=list[MemberOut])
def members(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemberOut]:
    return room_service.list_members(db, room_id, user)
