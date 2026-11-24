from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.nexconn_client import nexconn_client
from app.integrations.serpapi_client import ProviderError
from app.models.alert import Alert
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.user import User
from app.models.watch import Watch
from app.models.watch_history import WatchHistory
from app.schemas.alert import AlertOut, ShareOut
from app.schemas.vote import VoteSummary
from app.services import voting_service
from app.utils.normalization import day_start, format_money, utcnow

logger = logging.getLogger(__name__)

ACTIONS = ["yes", "no", "wait"]
ALERT_TYPES = {
    "flight": "flight_alert",
    "stock": "stock_alert",
    "job_notification": "job_alert",
    "topic": "topic_alert",
}


def recent_numeric_observations(db: Session, watch_id: int, limit: int = 2) -> list[float]:
    rows = db.scalars(
        select(WatchHistory.observed_value)
        .where(WatchHistory.watch_id == watch_id, WatchHistory.observed_value.is_not(None))
        .order_by(WatchHistory.checked_at.desc())
        .limit(max(1, min(limit, 20)))
    ).all()
    return [float(value) for value in rows if value is not None]


def latest_numeric_observation(db: Session, watch_id: int) -> float | None:
    values = recent_numeric_observations(db, watch_id, 1)
    return values[0] if values else None


def build_alert_payload(alert: Alert, watch: Watch, db: Session | None = None) -> dict[str, Any]:
    rule = watch.rule_json or {}
    current_value = alert.observed_value
    numeric: float | None = None
    previous: float | None = None
    if db is not None:
        observations = recent_numeric_observations(db, watch.id, 2)
        numeric = observations[0] if observations else None
        previous = observations[1] if len(observations) > 1 else None

    currency = rule.get("currency", "INR")
    target_value = rule.get("target_price")
    payload: dict[str, Any] = {
        "type": ALERT_TYPES.get(watch.watch_type, "alert"),
        "watch_type": watch.watch_type,
        "alert_id": alert.id,
        "room_id": alert.room_id,
        "watch_id": alert.watch_id,
        "title": alert.title,
        "current_value": numeric,
        "observed_value": current_value,
        "target_value": target_value,
        "currency": currency,
        "explanation": alert.explanation
        or "A research-backed explanation is unavailable for this alert. The observed data above is from the live provider.",
        "sources": alert.sources_json or [],
        "verification_status": alert.verification_status,
        "actions": ACTIONS,
        "share_url": f"{settings.frontend_url.rstrip('/')}/alerts/{alert.id}",
        "created_at": alert.created_at.isoformat() + "Z",
    }
    if numeric is not None and previous not in (None, 0):
        payload["previous_value"] = format_money(previous, currency)
        payload["change_percent"] = round((numeric - previous) / previous * 100, 2)
    if watch.watch_type == "flight":
        payload["route"] = f"{rule.get('origin')} → {rule.get('destination')}"
        payload["travel_date"] = rule.get("travel_date")
        payload["condition"] = rule.get("condition")
        if target_value not in (None, ""):
            label = "Below" if rule.get("condition", "below") == "below" else "Above"
            payload["target"] = f"{label} {format_money(float(target_value), currency)}"
    elif watch.watch_type == "stock":
        payload["symbol"] = rule.get("symbol")
        payload["condition"] = rule.get("condition")
        payload["threshold_percent"] = rule.get("threshold_percent")
        if rule.get("threshold_percent") is not None:
            payload["target"] = f"Moves more than {rule['threshold_percent']}%"
        elif target_value not in (None, ""):
            payload["target"] = f"{format_money(float(target_value), currency)}"
        payload["disclaimer"] = "Information only, not financial advice."
    elif watch.watch_type == "job_notification":
        payload["organization"] = rule.get("organization")
        payload["keywords"] = rule.get("keywords", [])
    elif watch.watch_type == "topic":
        payload["query"] = rule.get("query")
        payload["source"] = rule.get("source")
        payload["mode"] = rule.get("mode")
        if rule.get("target_price") is not None:
            label = "Below" if rule.get("mode") == "price_below" else "Above"
            payload["target"] = f"{label} {format_money(float(rule['target_price']), rule.get('currency', 'INR'))}"
    return payload


def _daily_alert_count(db: Session, watch_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(Alert.id)).where(
                Alert.watch_id == watch_id, Alert.created_at >= day_start(utcnow())
            )
        )
        or 0
    )


def create_alert(
    db: Session,
    watch: Watch,
    *,
    title: str,
    event_key: str,
    observed_value_text: str,
    explanation: str | None,
    sources: list[dict[str, Any]],
    verification_status: str = "not_applicable",
) -> Alert | None:
    """Create an alert unless it duplicates an event or exceeds the daily cap."""

    existing = db.scalar(
        select(Alert).where(Alert.watch_id == watch.id, Alert.event_key == event_key)
    )
    if existing is not None:
        logger.info("Suppressed duplicate alert for watch %s (%s)", watch.id, event_key)
        return None

    if _daily_alert_count(db, watch.id) >= settings.max_alerts_per_watch_per_day:
        logger.info(
            "Daily alert cap reached for watch %s (%s/day)",
            watch.id,
            settings.max_alerts_per_watch_per_day,
        )
        return None

    alert = Alert(
        room_id=watch.room_id,
        watch_id=watch.id,
        title=title,
        observed_value=observed_value_text,
        explanation=explanation,
        sources_json=sources,
        verification_status=verification_status,
        event_key=event_key,
    )
    db.add(alert)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Alert insert raced on event key %s; suppressed", event_key)
        return None

    db.refresh(alert)
    watch.last_alert_at = utcnow()
    watch.last_triggered_at = utcnow()
    db.commit()

    deliver_alert(db, alert, watch)
    return alert


def deliver_alert(db: Session, alert: Alert, watch: Watch) -> dict[str, Any]:
    room = db.get(Room, alert.room_id)
    if room is None or not room.nexconn_conversation_id:
        logger.info("Alert %s not sent: room has no Nexconn conversation id", alert.id)
        return {"delivered": False, "reason": "room_not_mapped"}
    if not nexconn_client.configured:
        logger.info("Alert %s not sent: Nexconn is not configured", alert.id)
        return {"delivered": False, "reason": "nexconn_not_configured"}

    payload = build_alert_payload(alert, watch, db)
    try:
        result = nexconn_client.send_alert_card(room.nexconn_conversation_id, payload)
        nexconn_client.send_vote_prompt(
            room.nexconn_conversation_id, alert.id, alert.title, ["YES", "NO", "WAIT"]
        )
        return {"delivered": True, "result": result}
    except ProviderError as exc:
        logger.warning("Nexconn alert delivery failed for alert %s: %s", alert.id, exc)
        return {"delivered": False, "reason": "delivery_failed", "error": exc.message}


def list_alerts(
    db: Session,
    room_id: int,
    limit: int = 50,
    watch_id: int | None = None,
) -> list[Alert]:
    query = select(Alert).where(Alert.room_id == room_id)
    if watch_id is not None:
        query = query.where(Alert.watch_id == watch_id)
    return list(
        db.scalars(
            query.order_by(Alert.created_at.desc()).limit(max(1, min(limit, 200)))
        ).all()
    )


def list_alerts_for_user(
    db: Session,
    user: User,
    limit: int = 50,
    watch_id: int | None = None,
) -> list[Alert]:
    """List alerts across every room the user belongs to."""

    query = (
        select(Alert)
        .join(RoomMember, RoomMember.room_id == Alert.room_id)
        .where(RoomMember.user_id == user.id)
    )
    if watch_id is not None:
        query = query.where(Alert.watch_id == watch_id)
    return list(
        db.scalars(
            query.order_by(Alert.created_at.desc()).limit(max(1, min(limit, 200)))
        ).all()
    )


def get_alert_for_room(db: Session, room_id: int, alert_id: int) -> Alert:
    alert = db.scalar(select(Alert).where(Alert.id == alert_id, Alert.room_id == room_id))
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


def to_alert_out(db: Session, alert: Alert, include_votes: bool = False) -> AlertOut:
    votes = None
    if include_votes:
        votes = VoteSummary(**voting_service.summary(db, alert))
    return AlertOut(
        id=alert.id,
        room_id=alert.room_id,
        watch_id=alert.watch_id,
        title=alert.title,
        observed_value=alert.observed_value,
        explanation=alert.explanation,
        sources=alert.sources_json or [],
        verification_status=alert.verification_status,
        event_key=alert.event_key,
        created_at=alert.created_at,
        payload=build_alert_payload(alert, alert.watch, db),
        votes=votes,
    )


def share_alert(db: Session, room_id: int, alert_id: int) -> ShareOut:
    alert = get_alert_for_room(db, room_id, alert_id)
    watch = alert.watch
    payload = build_alert_payload(alert, watch, db)
    summary = (
        f"Nazar alert: {alert.title}\n"
        f"{alert.observed_value or ''}\n"
        f"{alert.explanation or 'Explanation unavailable.'}\n"
        f"Decide together: YES / NO / WAIT"
    ).strip()
    share_url = payload["share_url"]
    text = f"{summary}\n\nSee the alert: {share_url}"
    return ShareOut(
        alert_id=alert.id,
        summary=summary,
        share_url=share_url,
        whatsapp_url=f"https://wa.me/?text={quote(text)}",
    )
