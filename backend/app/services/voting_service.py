from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.nexconn_client import nexconn_client
from app.integrations.serpapi_client import ProviderError
from app.models.alert import Alert
from app.models.room import Room
from app.models.user import User
from app.models.vote import Vote
from app.utils.normalization import utcnow

logger = logging.getLogger(__name__)

VALID_CHOICES = {"yes", "no", "wait"}

# Group-chat shortcuts. Numeric replies map to the alert's action order.
VOTE_ALIASES = {
    "yes": "yes",
    "y": "yes",
    "haan": "yes",
    "han": "yes",
    "ha": "yes",
    "1": "yes",
    "no": "no",
    "n": "no",
    "nahi": "no",
    "na": "no",
    "2": "no",
    "wait": "wait",
    "ruk": "wait",
    "ruko": "wait",
    "later": "wait",
    "3": "wait",
}
BOOKED_ALIASES = {"booked", "book", "done", "kar liya", "book kar liya"}


def parse_vote_token(text: str) -> str | None:
    token = text.strip().lower().strip(".!?, ")
    if token in BOOKED_ALIASES:
        return "booked"
    return VOTE_ALIASES.get(token)


def cast_vote(db: Session, alert: Alert, user: User, choice: str) -> Vote:
    if choice not in VALID_CHOICES:
        raise HTTPException(status_code=422, detail="choice must be yes, no or wait")

    vote = db.scalar(
        select(Vote).where(Vote.alert_id == alert.id, Vote.user_id == user.id)
    )
    if vote is None:
        vote = Vote(alert_id=alert.id, user_id=user.id, choice=choice)
        db.add(vote)
    else:
        vote.choice = choice
        vote.created_at = utcnow()
    db.commit()
    db.refresh(vote)
    return vote


def summary(db: Session, alert: Alert, user: User | None = None) -> dict:
    rows = db.execute(
        select(Vote.choice, func.count(Vote.id)).where(Vote.alert_id == alert.id).group_by(Vote.choice)
    ).all()
    counts = {"yes": 0, "no": 0, "wait": 0}
    for choice, count in rows:
        if choice in counts:
            counts[choice] = int(count)

    from app.services.room_service import member_count

    user_votes = {
        str(vote.user_id): vote.choice
        for vote in db.scalars(select(Vote).where(Vote.alert_id == alert.id)).all()
    }
    my_vote = user_votes.get(str(user.id)) if user else None
    return {
        "alert_id": alert.id,
        **counts,
        "total_votes": sum(counts.values()),
        "total_members": member_count(db, alert.room_id),
        "my_vote": my_vote,
        "user_votes": user_votes,
    }


def vote_notification(summary_data: dict) -> str:
    return (
        f"Votes: YES {summary_data['yes']} · NO {summary_data['no']} · "
        f"WAIT {summary_data['wait']} ({summary_data['total_votes']}/{summary_data['total_members']} members)"
    )


def complete_watch(db: Session, alert: Alert, user: User) -> dict:
    watch = alert.watch
    if watch.status == "completed":
        return {
            "alert_id": alert.id,
            "watch_id": watch.id,
            "watch_status": watch.status,
            "booked_by": watch.booked_by.name if watch.booked_by else "unknown",
            "message": "This watch was already marked as booked.",
        }

    watch.status = "completed"
    watch.booked_by_id = user.id
    watch.completed_at = utcnow()
    watch.next_check_at = None
    db.commit()
    db.refresh(watch)

    message = f"{user.name} marked this watch as BOOKED. Nazar has stopped checking it."
    room = db.get(Room, alert.room_id)
    if room and room.nexconn_conversation_id and nexconn_client.configured:
        try:
            nexconn_client.send_group_text(room.nexconn_conversation_id, message)
        except ProviderError as exc:
            logger.warning("Could not notify group about completion: %s", exc)

    return {
        "alert_id": alert.id,
        "watch_id": watch.id,
        "watch_status": watch.status,
        "booked_by": user.name,
        "message": message,
    }
