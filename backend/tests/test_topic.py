"""General "topic" watches: product prices, private jobs, news, anything searchable."""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import settings
from app.models.alert import Alert
from app.models.watch import Watch
from app.schemas.watch import TopicRule
from app.services import monitoring_service
from app.services.parser_service import parse_message
from app.utils.normalization import utcnow
from tests.test_monitoring import make_room


def make_topic_watch(db, room, **rule) -> Watch:
    watch = Watch(
        room_id=room.id,
        created_by=room.created_by,
        watch_type="topic",
        rule_json=TopicRule(**rule).model_dump(mode="json"),
        status="active",
        check_interval=30,
        next_check_at=utcnow(),
    )
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return watch


def item(key: str, price: float | None = None) -> dict:
    return {"key": key, "title": f"Result {key}", "url": f"https://example.com/{key}", "source": "example.com", "date": None, "price": price}


def topic_obs(items: list[dict], price: float | None = None) -> dict:
    return {"watch_type": "topic", "items": items, "current_price": price, "currency": "INR"}


def alerts(db, watch_id: int) -> list[Alert]:
    return list(db.scalars(select(Alert).where(Alert.watch_id == watch_id).order_by(Alert.id)).all())


def test_parser_routes_everyday_requests_to_topic_watches():
    shopping = parse_message("@Nazar iPhone 16 under ₹60,000 batao")
    assert shopping["understood"] and shopping["watch_type"] == "topic"
    assert shopping["rule"]["query"] == "iPhone 16"
    assert shopping["rule"]["mode"] == "price_below" and shopping["rule"]["target_price"] == 60000

    jobs = parse_message("@Nazar check for infosys jobs for sde1")
    assert jobs["watch_type"] == "topic" and jobs["rule"]["source"] == "jobs"

    news = parse_message("@Nazar Patna airport news")
    assert news["rule"] == {**news["rule"], "source": "news", "query": "Patna airport"}

    # Existing types are unchanged.
    assert parse_message("@Nazar Tata Motors 5% gir jaye toh batao")["watch_type"] == "stock"
    assert parse_message("@Nazar SSC CGL notification aaye toh batao")["watch_type"] == "job_notification"
    # Junk doesn't become a watch.
    assert parse_message("@Nazar 1%")["understood"] is False


def test_price_watch_alerts_on_new_crossing(db, monkeypatch):
    room = make_room(db)
    watch = make_topic_watch(db, room, query="iPhone 16", source="shopping", mode="price_below", target_price=60000)
    monkeypatch.setattr(settings, "max_alerts_per_watch_per_day", 5)

    monkeypatch.setattr(monitoring_service.topic_provider, "fetch", lambda rule: topic_obs([item("a", 64999)], 64999))
    assert monitoring_service.check_watch(db, watch, force=True)["alerts_created"] == []

    monkeypatch.setattr(monitoring_service.topic_provider, "fetch", lambda rule: topic_obs([item("b", 58999)], 58999))
    result = monitoring_service.check_watch(db, watch, force=True)
    assert len(result["alerts_created"]) == 1
    alert = alerts(db, watch.id)[0]
    assert "58,999" in alert.observed_value
    assert alert.sources_json[0]["url"] == "https://example.com/b"  # links to the listing


def test_new_results_watch_posts_baseline_then_only_new_items(db, monkeypatch):
    room = make_room(db)
    watch = make_topic_watch(db, room, query="Patna airport", source="news")
    monkeypatch.setattr(settings, "max_alerts_per_watch_per_day", 5)

    monkeypatch.setattr(monitoring_service.topic_provider, "fetch", lambda rule: topic_obs([item("x"), item("y"), item("z")]))
    first = monitoring_service.check_watch(db, watch, force=True)
    assert len(first["alerts_created"]) == 1  # only the latest result, not all three

    second = monitoring_service.check_watch(db, watch, force=True)
    assert second["alerts_created"] == []  # nothing new

    monkeypatch.setattr(monitoring_service.topic_provider, "fetch", lambda rule: topic_obs([item("new"), item("x"), item("y")]))
    third = monitoring_service.check_watch(db, watch, force=True)
    assert len(third["alerts_created"]) == 1
    assert "Result new" in alerts(db, watch.id)[-1].title


def test_shopping_filters_drop_accessories_and_unrelated_listings():
    from app.integrations.topic_provider import _drop_price_outliers, _matches

    assert _matches("iPhone 16", "Apple iPhone 16 128GB Black")
    assert _matches("iPhone 16", "I phone 16")  # spacing differences still match
    assert not _matches("iPhone 16", "Samsung Galaxy S24")
    listings = [{"price": p} for p in (270, 57999, 63183, 69900, 79900)]
    assert [i["price"] for i in _drop_price_outliers(listings)] == [57999, 63183, 69900, 79900]
