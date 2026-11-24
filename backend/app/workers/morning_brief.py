"""Optional daily morning brief posted into each mapped Nexconn group."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.integrations.nexconn_client import nexconn_client
from app.integrations.serpapi_client import ProviderError
from app.models.alert import Alert
from app.models.room import Room
from app.models.watch import Watch
from app.utils.normalization import utcnow

logger = logging.getLogger(__name__)

STRINGS = {
    "en": {
        "header": "☀️ Nazar Rakho morning brief — {room}",
        "watches": "Active watches: {count}",
        "changes": "Important changes (last 24h): {count}",
        "jobs": "New verified job notices: {count}",
        "pending": "Pending decisions: {count}",
        "recent": "Recent alerts:",
        "none": "No active watches yet. Mention @Nazar to create one.",
        "alert_line": "• {title} ({value})",
        "pending_line": "• Alert #{alert_id}: YES {yes} / NO {no} / WAIT {wait}",
        "footer": "Reply YES / NO / WAIT to any alert to decide together.",
    },
    "hi": {
        "header": "☀️ नज़र रखो मॉर्निंग ब्रीफ — {room}",
        "watches": "सक्रिय वॉच: {count}",
        "changes": "पिछले 24 घंटे के ज़रूरी बदलाव: {count}",
        "jobs": "नई सत्यापित भर्ती सूचनाएँ: {count}",
        "pending": "बाकी फैसले: {count}",
        "recent": "हाल के अलर्ट:",
        "none": "अभी कोई सक्रिय वॉच नहीं है। बनाने के लिए @Nazar को मेंशन करें।",
        "alert_line": "• {title} ({value})",
        "pending_line": "• अलर्ट #{alert_id}: हाँ {yes} / नहीं {no} / रुको {wait}",
        "footer": "किसी भी अलर्ट पर YES / NO / WAIT भेजकर साथ में फैसला करें।",
    },
}


def build_room_brief(db: Session, room: Room, language: str = "en") -> str:
    strings = STRINGS.get(language, STRINGS["en"])
    now = utcnow()
    since = now - timedelta(hours=24)

    watches = list(
        db.scalars(
            select(Watch).where(Watch.room_id == room.id, Watch.status == "active")
        ).all()
    )
    alerts = list(
        db.scalars(
            select(Alert)
            .where(Alert.room_id == room.id, Alert.created_at >= since)
            .order_by(Alert.created_at.desc())
            .limit(10)
        ).all()
    )
    verified_jobs = [alert for alert in alerts if alert.verification_status == "verified"]
    pending = [alert for alert in alerts if len(alert.votes) > 0 and alert.watch.status == "active"]

    lines = [strings["header"].format(room=room.name)]
    if not watches:
        lines.append(strings["none"])
    else:
        lines.append(strings["watches"].format(count=len(watches)))
    lines.append(strings["changes"].format(count=len(alerts)))
    lines.append(strings["jobs"].format(count=len(verified_jobs)))
    lines.append(strings["pending"].format(count=len(pending)))

    if alerts:
        lines.append("")
        lines.append(strings["recent"])
        for alert in alerts[:5]:
            lines.append(
                strings["alert_line"].format(
                    title=alert.title, value=alert.observed_value or "update"
                )
            )

    if pending:
        lines.append("")
        for alert in pending[:3]:
            counts = {"yes": 0, "no": 0, "wait": 0}
            for vote in alert.votes:
                if vote.choice in counts:
                    counts[vote.choice] += 1
            lines.append(
                strings["pending_line"].format(alert_id=alert.id, **counts)
            )

    lines.append("")
    lines.append(strings["footer"])
    return "\n".join(lines)


def send_morning_briefs(db: Session | None = None, language: str | None = None) -> dict:
    owns_session = db is None
    db = db or SessionLocal()
    sent = 0
    skipped = 0
    try:
        rooms = list(
            db.scalars(select(Room).where(Room.nexconn_conversation_id.is_not(None))).all()
        )
        for room in rooms:
            if not nexconn_client.configured:
                skipped += 1
                continue
            brief = build_room_brief(db, room, language or "en")
            try:
                nexconn_client.send_group_text(
                    room.nexconn_conversation_id, brief, push_content=f"Morning brief: {room.name}"
                )
                sent += 1
            except ProviderError as exc:
                logger.warning("Morning brief failed for room %s: %s", room.id, exc)
                skipped += 1
        return {"rooms": len(rooms), "sent": sent, "skipped": skipped}
    finally:
        if owns_session:
            db.close()
