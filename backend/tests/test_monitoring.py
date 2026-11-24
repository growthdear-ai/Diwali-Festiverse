from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.config import settings
from app.integrations.serpapi_client import ProviderError
from app.models.alert import Alert
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.user import User
from app.models.watch import Watch
from app.schemas.watch import FlightRule, JobRule
from app.services import monitoring_service
from app.utils.normalization import utcnow


def make_room(db, email: str = "asha@example.com") -> Room:
    user = User(name="Asha", email=email, password_hash="x")
    db.add(user)
    db.flush()
    room = Room(name="Family", invite_code="ABCD1234", created_by=user.id)
    db.add(room)
    db.flush()
    db.add(RoomMember(room_id=room.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(room)
    return room


def make_flight_watch(db, room: Room, target: float = 6000) -> Watch:
    rule = FlightRule(
        origin="BLR",
        destination="PAT",
        travel_date=date.today() + timedelta(days=30),
        target_price=target,
        currency="INR",
    )
    watch = Watch(
        room_id=room.id,
        created_by=room.created_by,
        watch_type="flight",
        rule_json=rule.model_dump(mode="json"),
        status="active",
        check_interval=30,
        next_check_at=utcnow(),
    )
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return watch


def observation(price: float) -> dict:
    return {
        "watch_type": "flight",
        "origin": "BLR",
        "destination": "PAT",
        "travel_date": "2027-01-10",
        "current_price": price,
        "currency": "INR",
        "source": "Google Flights (SerpApi)",
        "source_url": "https://www.google.com/travel/flights",
        "checked_at": utcnow().isoformat() + "Z",
    }


def alert_count(db, watch_id: int) -> int:
    return int(db.scalar(select(func.count(Alert.id)).where(Alert.watch_id == watch_id)) or 0)


def test_alert_only_on_new_crossing(db, monkeypatch):
    room = make_room(db)
    watch = make_flight_watch(db, room)
    monkeypatch.setattr(settings, "max_alerts_per_watch_per_day", 5)

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", lambda rule: observation(7000))
    first = monitoring_service.check_watch(db, watch, force=True)
    assert first["triggered"] is False
    assert alert_count(db, watch.id) == 0

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", lambda rule: observation(5640))
    second = monitoring_service.check_watch(db, watch, force=True)
    assert second["triggered"] is True
    assert second["new_crossing"] is True
    assert len(second["alerts_created"]) == 1
    alert = db.get(Alert, second["alerts_created"][0])
    assert alert.sources_json[0]["url"] == "https://www.google.com/travel/flights"

    third = monitoring_service.check_watch(db, watch, force=True)
    assert third["triggered"] is True
    assert third["new_crossing"] is False
    assert third["alerts_created"] == []

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", lambda rule: observation(7200))
    fourth = monitoring_service.check_watch(db, watch, force=True)
    assert fourth["triggered"] is False

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", lambda rule: observation(5500))
    fifth = monitoring_service.check_watch(db, watch, force=True)
    assert fifth["new_crossing"] is True
    assert len(fifth["alerts_created"]) == 1
    assert alert_count(db, watch.id) == 2


def test_daily_alert_cap_suppresses_extra_crossings(db, monkeypatch):
    room = make_room(db)
    watch = make_flight_watch(db, room)
    monkeypatch.setattr(settings, "max_alerts_per_watch_per_day", 1)

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", lambda rule: observation(5640))
    assert len(monitoring_service.check_watch(db, watch, force=True)["alerts_created"]) == 1

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", lambda rule: observation(7200))
    monitoring_service.check_watch(db, watch, force=True)

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", lambda rule: observation(5500))
    result = monitoring_service.check_watch(db, watch, force=True)
    assert result["new_crossing"] is True
    assert result["alerts_created"] == []
    assert alert_count(db, watch.id) == 1


def test_provider_failure_does_not_crash_or_alert(db, monkeypatch):
    room = make_room(db)
    watch = make_flight_watch(db, room)

    def fail(rule):
        raise ProviderError("SerpApi temporary failure", retryable=True, provider="serpapi")

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", fail)
    result = monitoring_service.check_watch(db, watch, force=True)

    assert result["status"] == "error"
    assert result["retryable"] is True
    assert alert_count(db, watch.id) == 0
    db.refresh(watch)
    assert watch.next_check_at is not None


def test_job_notification_alert_is_deduplicated(db, monkeypatch):
    room = make_room(db)
    rule = JobRule(keywords=["SSC CGL"], organization="SSC", domains=["ssc.gov.in"])
    watch = Watch(
        room_id=room.id,
        created_by=room.created_by,
        watch_type="job_notification",
        rule_json=rule.model_dump(mode="json"),
        status="active",
        check_interval=30,
        next_check_at=utcnow(),
    )
    db.add(watch)
    db.commit()
    db.refresh(watch)

    notice = {
        "notice_key": "notice-key-1",
        "title": "SSC CGL 2026 Notification",
        "url": "https://ssc.gov.in/notice/cgl-2026",
        "domain": "ssc.gov.in",
        "source_name": "SSC",
        "publication_date": "2026-11-20",
        "description": "Official notice",
        "keywords": ["SSC CGL"],
        "official_domain": True,
        "verification_status": "verified",
    }
    payload = {
        "watch_type": "job_notification",
        "notices": [notice],
        "source": "Google Search (SerpApi)",
        "checked_at": utcnow().isoformat() + "Z",
    }
    monkeypatch.setattr(monitoring_service.jobs_provider, "fetch", lambda rule: payload)

    first = monitoring_service.check_watch(db, watch, force=True)
    assert len(first["alerts_created"]) == 1
    alert = db.get(Alert, first["alerts_created"][0])
    assert alert.verification_status == "verified"
    assert alert.sources_json[0]["url"] == notice["url"]

    second = monitoring_service.check_watch(db, watch, force=True)
    assert second["alerts_created"] == []
    assert alert_count(db, watch.id) == 1


def test_completed_watch_is_not_checked(db, monkeypatch):
    room = make_room(db)
    watch = make_flight_watch(db, room)
    watch.status = "completed"
    db.commit()

    called = {"count": 0}

    def should_not_run(rule):
        called["count"] += 1
        return observation(100)

    monkeypatch.setattr(monitoring_service.flight_provider, "fetch", should_not_run)
    result = monitoring_service.check_watch(db, watch, force=True)
    assert result["status"] == "skipped"
    assert called["count"] == 0
