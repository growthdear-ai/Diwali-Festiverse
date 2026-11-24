"""Create two starter rooms so a new install has something to explore.

This is an explicit setup command, not a runtime data source. It creates a user
(if needed), two rooms, clearly marked example chats, and live watch rules. It
never fabricates prices, fares or notices; those only arrive from configured
providers when the scheduler runs.

Usage (from backend/):
    python -m scripts.seed_rooms
    python -m scripts.seed_rooms --email you@example.com --password "your-password"
"""

from __future__ import annotations

import argparse
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models.message import Message
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.user import User
from app.models.watch import Watch
from app.services import room_service, watch_service
from app.utils.normalization import utcnow

ROOMS = (
    {
        "name": "Family Travel",
        "description": "Flight fares the family is watching together.",
        "welcome": (
            "Namaste! This room is ready. Mention @Nazar with a route, date and "
            "target fare, and I will check it on schedule."
        ),
        "example_chat": (
            {"sender": "member", "text": "[Sample] Let's pick dates for a family trip next month."},
            {"sender": "member", "text": "[Sample] @Nazar, look for Bengaluru-to-Patna flights under INR 6,000."},
            {
                "sender": "nazar",
                "text": "[Sample reply] I can check live fares and share booking links. Which travel date should I use?",
            },
        ),
        "watches": (
            {
                "watch_type": "flight",
                "rule": {
                    "origin": "BLR",
                    "destination": "PAT",
                    "travel_date": (utcnow().date() + timedelta(days=45)).isoformat(),
                    "condition": "below",
                    "target_price": 6000,
                    "currency": "INR",
                    "passengers": 1,
                },
            },
        ),
    },
    {
        "name": "Money & Jobs",
        "description": "Stocks for the family and official government job notices.",
        "welcome": (
            "This room is ready too. I can watch a stock move or an official "
            "government job notice. Only notices on official domains are marked verified."
        ),
        "example_chat": (
            {"sender": "member", "text": "[Sample] We should review the monthly budget this weekend."},
            {"sender": "member", "text": "[Sample] @Nazar, check the latest ITC share information and link the sources."},
            {
                "sender": "nazar",
                "text": "[Sample reply] I can look up current market information and share source links. Want an alert for a percentage move?",
            },
        ),
        "watches": (
            {
                "watch_type": "stock",
                "rule": {
                    "symbol": "ITC",
                    "exchange": "NSE",
                    "condition": "absolute_change_greater_than",
                    "threshold_percent": 3,
                    "direction": "either",
                },
            },
            {
                "watch_type": "job_notification",
                "rule": {
                    "keywords": ["SSC CGL"],
                    "organization": "SSC",
                    "domains": ["ssc.gov.in", "ssc.nic.in"],
                },
            },
        ),
    },
)


def _get_or_create_user(db: Session, email: str, password: str, name: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is not None:
        return user
    user = User(name=name, email=email.lower(), password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_or_create_room(db: Session, user: User, name: str, description: str) -> tuple[Room, bool]:
    room = db.scalar(
        select(Room)
        .join(RoomMember, RoomMember.room_id == Room.id)
        .where(RoomMember.user_id == user.id, Room.name == name)
    )
    if room is not None:
        return room, False

    room = Room(
        name=name,
        description=description,
        invite_code=room_service._generate_invite_code(db),
        created_by=user.id,
    )
    db.add(room)
    db.flush()
    db.add(RoomMember(room_id=room.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(room)
    return room, True


def seed(email: str, password: str, name: str) -> list[str]:
    init_db()
    db = SessionLocal()
    summary: list[str] = []
    try:
        user = _get_or_create_user(db, email, password, name)
        for spec in ROOMS:
            room, created = _get_or_create_room(db, user, spec["name"], spec["description"])
            if created:
                db.add(
                    Message(
                        room_id=room.id,
                        sender_id=None,
                        message_text=json.dumps(
                            {"kind": "research", "text": spec["welcome"]}
                        ),
                        message_type="text",
                    )
                )
                for example in spec["example_chat"]:
                    is_nazar = example["sender"] == "nazar"
                    message_text = (
                        json.dumps(
                            {"kind": "research", "text": example["text"]},
                            ensure_ascii=True,
                        )
                        if is_nazar
                        else example["text"]
                    )
                    db.add(
                        Message(
                            room_id=room.id,
                            sender_id=None if is_nazar else user.id,
                            message_text=message_text,
                            message_type="bot" if is_nazar else "text",
                        )
                    )
                db.commit()

            existing = db.scalar(select(Watch.id).where(Watch.room_id == room.id).limit(1))
            if existing is None:
                for item in spec["watches"]:
                    watch_service.create_watch(
                        db,
                        room,
                        user,
                        item["watch_type"],
                        item["rule"],
                    )
            summary.append(f"{room.name}: {room.id} ({room.invite_code})")
        summary.append(f"Login: {user.email}")
    finally:
        db.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed two live starter rooms for Nazar Rakho.")
    parser.add_argument("--email", default="munazir@nazar.local", help="Account email")
    parser.add_argument("--password", default="nazar-local-2026", help="Password used only if the account is new")
    parser.add_argument("--name", default="Mohammed Munazir", help="Display name used only if the account is new")
    args = parser.parse_args()

    print("Seeding starter rooms with clearly marked example chats (no live prices or notices are fabricated).")
    for line in seed(args.email, args.password, args.name):
        print(f"  {line}")
    if args.email == "munazir@nazar.local":
        print("  Password: nazar-local-2026 (change it after logging in)")
    print("Start the backend and open the frontend: the scheduler will fill real history.")


if __name__ == "__main__":
    main()
