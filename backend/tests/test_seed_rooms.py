from __future__ import annotations

import json

from sqlalchemy import func, select

from app.models.message import Message
from app.models.room import Room
from app.models.user import User
from scripts.seed_rooms import seed


def test_seed_rooms_adds_marked_example_chats_only_once(db):
    seed("rooms@example.com", "password123", "Room Owner")
    owner = db.scalar(select(User).where(User.email == "rooms@example.com"))
    assert owner is not None
    rooms = db.scalars(select(Room).where(Room.created_by == owner.id)).all()

    assert {room.name for room in rooms} == {"Family Travel", "Money & Jobs"}
    for room in rooms:
        messages = db.scalars(
            select(Message).where(Message.room_id == room.id).order_by(Message.id)
        ).all()
        assert any(message.message_text.startswith("[Sample]") for message in messages)
        sample_replies = [
            json.loads(message.message_text)
            for message in messages
            if message.message_type == "bot"
        ]
        assert len(sample_replies) == 1
        assert sample_replies[0]["text"].startswith("[Sample reply]")

    seed("rooms@example.com", "password123", "Room Owner")
    sample_count = db.scalar(
        select(func.count(Message.id))
        .join(Room, Room.id == Message.room_id)
        .where(Room.created_by == owner.id, Message.message_text.like("[Sample]%"))
    )
    assert sample_count == 4
