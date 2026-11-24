from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.user import User
from app.models.watch import Watch
from app.models.watch_history import WatchHistory
from app.schemas.watch import (
    ParseResponse,
    WatchCreate,
    WatchHistoryOut,
    WatchOut,
    WatchUpdate,
    parse_watch_rule,
)
from app.services.parser_service import parse_message
from app.utils.normalization import utcnow
from app.utils.validators import clamp_interval


def create_watch(
    db: Session,
    room: Room,
    user: User,
    watch_type: str,
    rule: dict,
    check_interval: int | None = None,
) -> Watch:
    try:
        validated = parse_watch_rule({**rule, "watch_type": watch_type})
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid watch rule: {exc}",
        ) from exc

    if validated.watch_type != watch_type:
        raise HTTPException(status_code=422, detail="watch_type does not match rule")

    interval = clamp_interval(check_interval or settings.watch_interval_minutes)
    watch = Watch(
        room_id=room.id,
        created_by=user.id,
        watch_type=watch_type,
        rule_json=validated.model_dump(mode="json"),
        status="active",
        check_interval=interval,
        next_check_at=utcnow(),
    )
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return watch


def create_from_parsed(
    db: Session, room: Room, user: User, payload: WatchCreate
) -> Watch:
    return create_watch(db, room, user, payload.watch_type, payload.rule, payload.check_interval)


def _validate_filters(status_filter: str | None, watch_type: str | None) -> None:
    if status_filter and status_filter not in {"active", "paused", "completed", "deleted"}:
        raise HTTPException(status_code=422, detail="Invalid status filter")
    if watch_type and watch_type not in {"flight", "stock", "job_notification", "topic"}:
        raise HTTPException(status_code=422, detail="Invalid watch_type filter")


def list_watches(
    db: Session,
    room: Room,
    status_filter: str | None = None,
    watch_type: str | None = None,
) -> list[Watch]:
    _validate_filters(status_filter, watch_type)
    query = select(Watch).where(Watch.room_id == room.id)
    if status_filter:
        query = query.where(Watch.status == status_filter)
    if watch_type:
        query = query.where(Watch.watch_type == watch_type)
    return list(db.scalars(query.order_by(Watch.created_at.desc())).all())


def list_watches_for_user(
    db: Session,
    user: User,
    status_filter: str | None = None,
    watch_type: str | None = None,
) -> list[Watch]:
    """List watches across every room the user belongs to."""

    _validate_filters(status_filter, watch_type)
    query = (
        select(Watch)
        .join(RoomMember, RoomMember.room_id == Watch.room_id)
        .where(RoomMember.user_id == user.id)
    )
    if status_filter:
        query = query.where(Watch.status == status_filter)
    if watch_type:
        query = query.where(Watch.watch_type == watch_type)
    return list(db.scalars(query.order_by(Watch.created_at.desc())).all())


def to_watch_out(db: Session, watch: Watch, history_limit: int = 60) -> WatchOut:
    """Serialize a watch with its real observation history for charts."""

    rows = list(
        db.scalars(
            select(WatchHistory)
            .where(WatchHistory.watch_id == watch.id)
            .order_by(WatchHistory.checked_at.desc())
            .limit(max(1, min(history_limit, 200)))
        ).all()
    )
    ordered = list(reversed(rows))
    latest = next(
        (row.observed_value for row in reversed(ordered) if row.observed_value is not None),
        None,
    )
    out = WatchOut.model_validate(watch)
    out.latest_value = latest
    out.history = [WatchHistoryOut.model_validate(row) for row in ordered]
    return out


def get_watch_for_room(db: Session, room: Room, watch_id: int) -> Watch:
    watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.room_id == room.id))
    if watch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    return watch


def update_watch(db: Session, room: Room, watch_id: int, payload: WatchUpdate) -> Watch:
    watch = get_watch_for_room(db, room, watch_id)
    if watch.status == "completed":
        raise HTTPException(status_code=409, detail="Completed watches cannot be edited")

    if payload.rule is not None:
        try:
            validated = parse_watch_rule({**payload.rule, "watch_type": watch.watch_type})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid watch rule: {exc}") from exc
        watch.rule_json = validated.model_dump(mode="json")
        watch.last_triggered_at = None
        watch.next_check_at = utcnow()
    if payload.check_interval is not None:
        watch.check_interval = clamp_interval(payload.check_interval)

    db.commit()
    db.refresh(watch)
    return watch


def set_watch_status(db: Session, room: Room, watch_id: int, new_status: str) -> Watch:
    watch = get_watch_for_room(db, room, watch_id)
    if new_status == "active":
        if watch.status == "completed":
            raise HTTPException(status_code=409, detail="Completed watches cannot be resumed")
        watch.status = "active"
        watch.next_check_at = utcnow()
    elif new_status == "paused":
        if watch.status == "completed":
            raise HTTPException(status_code=409, detail="Completed watches cannot be paused")
        watch.status = "paused"
        watch.next_check_at = None
    else:
        raise HTTPException(status_code=422, detail="Unsupported status")
    db.commit()
    db.refresh(watch)
    return watch


def delete_watch(db: Session, room: Room, watch_id: int) -> None:
    watch = get_watch_for_room(db, room, watch_id)
    db.delete(watch)
    db.commit()


def preview_parse(text: str) -> ParseResponse:
    return ParseResponse(**parse_message(text))
