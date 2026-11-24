from __future__ import annotations

import logging
import secrets
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.nexconn_client import nexconn_client
from app.integrations.serpapi_client import ProviderError
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.user import User
from app.schemas.room import InviteOut, MemberOut, RoomCreate, RoomOut

logger = logging.getLogger(__name__)

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_invite_code(db: Session) -> str:
    for _ in range(10):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
        if not db.scalar(select(Room).where(Room.invite_code == code)):
            return code
    raise HTTPException(status_code=500, detail="Could not generate a unique invite code")


def get_membership(db: Session, room_id: int, user_id: int) -> RoomMember | None:
    return db.scalar(
        select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
    )


def get_room_for_user(db: Session, room_id: int, user: User) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    if get_membership(db, room_id, user.id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this room"
        )
    return room


def _member_rows(db: Session, room_id: int) -> list[MemberOut]:
    rows = db.execute(
        select(RoomMember, User)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == room_id)
        .order_by(RoomMember.joined_at)
    ).all()
    return [
        MemberOut(
            id=membership.id,
            user_id=member.id,
            name=member.name,
            email=member.email,
            role=membership.role,
            joined_at=membership.joined_at,
        )
        for membership, member in rows
    ]


def to_room_out(db: Session, room: Room, user: User | None = None) -> RoomOut:
    members = _member_rows(db, room.id)
    role = None
    if user is not None:
        membership = get_membership(db, room.id, user.id)
        role = membership.role if membership else None
    return RoomOut(
        id=room.id,
        name=room.name,
        description=room.description,
        invite_code=room.invite_code,
        created_by=room.created_by,
        nexconn_conversation_id=room.nexconn_conversation_id,
        created_at=room.created_at,
        member_count=len(members),
        my_role=role,
        members=members,
    )


def create_room(db: Session, user: User, payload: RoomCreate) -> RoomOut:
    room = Room(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        invite_code=_generate_invite_code(db),
        created_by=user.id,
        nexconn_conversation_id=payload.nexconn_conversation_id,
    )
    db.add(room)
    db.flush()
    db.add(RoomMember(room_id=room.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(room)

    if (
        settings.nexconn_auto_create_groups
        and not room.nexconn_conversation_id
        and nexconn_client.configured
    ):
        try:
            channel_id = nexconn_client.create_group(
                room.name, user.nexconn_user_id or f"nz{user.id:06d}"
            )
            if channel_id:
                room.nexconn_conversation_id = channel_id
                db.commit()
                db.refresh(room)
        except ProviderError as exc:
            logger.warning("Nexconn group creation failed for room %s: %s", room.id, exc)

    return to_room_out(db, room, user)


def list_rooms(db: Session, user: User) -> list[RoomOut]:
    rooms = db.scalars(
        select(Room)
        .join(RoomMember, RoomMember.room_id == Room.id)
        .where(RoomMember.user_id == user.id)
        .order_by(Room.created_at.desc())
    ).all()
    return [to_room_out(db, room, user) for room in rooms]


def join_room(db: Session, user: User, code: str) -> RoomOut:
    room = db.scalar(select(Room).where(Room.invite_code == code.strip().upper()))
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite code")

    membership = get_membership(db, room.id, user.id)
    if membership is None:
        db.add(RoomMember(room_id=room.id, user_id=user.id, role="member"))
        db.commit()
    return to_room_out(db, room, user)


def invite_for_room(db: Session, room_id: int, user: User) -> InviteOut:
    room = get_room_for_user(db, room_id, user)
    invite_url = f"{settings.frontend_url.rstrip('/')}/join/{room.invite_code}"
    message = (
        f"Join our Nazar Rakho room '{room.name}' so we can track prices and official "
        f"notifications together: {invite_url}"
    )
    return InviteOut(
        room_id=room.id,
        invite_code=room.invite_code,
        invite_url=invite_url,
        whatsapp_url=f"https://wa.me/?text={quote(message)}",
        message=message,
    )


def list_members(db: Session, room_id: int, user: User) -> list[MemberOut]:
    room = get_room_for_user(db, room_id, user)
    return _member_rows(db, room.id)


def member_count(db: Session, room_id: int) -> int:
    return int(
        db.scalar(select(func.count(RoomMember.id)).where(RoomMember.room_id == room_id)) or 0
    )
