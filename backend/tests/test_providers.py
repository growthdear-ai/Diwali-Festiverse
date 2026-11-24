from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.integrations.flight_provider import FlightProvider
from app.integrations.jobs_provider import JobsProvider
from app.integrations.nexconn_client import NexconnClient, build_signature
from app.integrations.serpapi_client import ProviderError, ProviderNotConfigured, SerpApiClient
from app.integrations.stock_provider import StockProvider
from app.schemas.watch import FlightRule, JobRule, StockRule
from app.services.monitoring_service import evaluate_condition


def future_date(days: int = 30) -> date:
    return date.today() + timedelta(days=days)


class FakeSerp:
    def __init__(self, responses: dict, extract_payload: dict | None = None) -> None:
        self.responses = responses
        self.extract_payload = extract_payload or {}
        self.calls: list[tuple[str, dict]] = []

    def search(self, engine: str, params: dict | None = None, use_cache: bool = True) -> dict:
        self.calls.append((engine, params or {}))
        response = self.responses.get(engine, {})
        if isinstance(response, Exception):
            raise response
        return response

    def extract(self, url: str) -> dict:
        if isinstance(self.extract_payload, Exception):
            raise self.extract_payload
        return self.extract_payload


def flight_rule(target: float = 6000) -> FlightRule:
    return FlightRule(
        origin="BLR",
        destination="PAT",
        travel_date=future_date(),
        target_price=target,
        currency="INR",
    )


def test_flight_provider_uses_lowest_real_fare_and_comparison():
    payload = {
        "best_flights": [
            {
                "price": 7000,
                "flights": [
                    {
                        "airline": "IndiGo",
                        "flight_number": "6E 123",
                        "departure_airport": {"id": "BLR"},
                        "arrival_airport": {"id": "PAT"},
                    }
                ],
            },
            {"price": 5640, "flights": [{"airline": "IndiGo", "flight_number": "6E 456"}]},
        ],
        "price_insights": {"lowest_price": 5600, "price_level": "low"},
        "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?q=BLR-PAT"},
    }
    provider = FlightProvider(client=FakeSerp({"google_flights": payload}))
    rule = flight_rule()

    observation = provider.fetch(rule)

    assert observation["current_price"] == 5640
    assert observation["airline"] == "IndiGo"
    assert observation["source_url"].startswith("https://www.google.com/travel/flights")

    evaluation = evaluate_condition("flight", rule.model_dump(mode="json"), observation)
    assert evaluation.triggered is True
    assert evaluation.current_value == 5640


def test_flight_provider_above_condition():
    payload = {"best_flights": [{"price": 8200, "flights": []}]}
    provider = FlightProvider(client=FakeSerp({"google_flights": payload}))
    rule = FlightRule(
        origin="BLR",
        destination="PAT",
        travel_date=future_date(),
        target_price=8000,
        condition="above",
    )
    observation = provider.fetch(rule)
    assert evaluate_condition("flight", rule.model_dump(mode="json"), observation).triggered


def test_missing_flights_raises_safely():
    provider = FlightProvider(client=FakeSerp({"google_flights": {"best_flights": [], "other_flights": []}}))
    with pytest.raises(ProviderError) as exc:
        provider.fetch(flight_rule())
    assert exc.value.retryable is False


def test_stock_provider_normalizes_percentage_and_previous_close():
    payload = {
        "summary": {
            "title": "Tata Motors Ltd",
            "stock": "TATAMOTORS",
            "exchange": "NSE",
            "price": "₹412.50",
            "extracted_price": 412.5,
            "currency": "INR",
            "price_movement": {"percentage": 3.2, "movement": "Down"},
            "date": "Nov 21 2026, 3:30 PM UTC+05:30",
        },
        "knowledge_graph": {
            "key_stats": {"stats": [{"label": "Previous close", "value": "₹427.00"}]}
        },
        "search_metadata": {"google_finance_url": "https://www.google.com/finance/quote/TATAMOTORS:NSE"},
    }
    provider = StockProvider(client=FakeSerp({"google_finance": payload}))
    rule = StockRule(
        symbol="TATAMOTORS",
        condition="absolute_change_greater_than",
        threshold_percent=2,
        direction="down",
    )
    observation = provider.fetch(rule)

    assert observation["percent_change"] == -3.2
    assert observation["absolute_change_percent"] == 3.2
    assert observation["previous_close"] == 427.0
    assert observation["exchange"] == "NSE"
    assert observation["query"] == "TATAMOTORS:NSE"

    evaluation = evaluate_condition("stock", rule.model_dump(mode="json"), observation)
    assert evaluation.triggered is True

    rule_high = rule.model_copy(update={"threshold_percent": 5})
    assert evaluate_condition("stock", rule_high.model_dump(mode="json"), observation).triggered is False

    rule_up = rule.model_copy(update={"direction": "up"})
    assert evaluate_condition("stock", rule_up.model_dump(mode="json"), observation).triggered is False


def test_stock_previous_close_derived_when_live_response_omits_it():
    payload = {
        "summary": {
            "title": "ITC Ltd",
            "stock": "ITC",
            "exchange": "NSE",
            "extracted_price": 299.1,
            "currency": "INR",
            "price_movement": {"percentage": 0.6312272, "value": 1.8999939, "movement": "Down"},
            "date": "Nov 20 2026, 03:59:56 PM UTC+05:30",
        },
        "knowledge_graph": {
            "key_stats": {"stats": [{"label": "Open", "value": "₹299.95"}]}
        },
    }
    observation = StockProvider(client=FakeSerp({"google_finance": payload})).fetch(
        StockRule(symbol="ITC", condition="price_below", target_price=400)
    )

    assert observation["previous_close"] == 301.0
    assert observation["previous_close_source"] == "google_finance_price_movement"
    assert observation["percent_change"] == -0.6312


def test_stock_symbol_resolution_falls_back_to_bse():
    nse_missing = {
        "summary": {"title": "Suzlon", "stock": None, "extracted_price": None},
    }
    bse_ok = {
        "summary": {
            "title": "Suzlon Energy Ltd",
            "stock": "SUZLON",
            "exchange": "BSE",
            "extracted_price": 68.4,
            "currency": "INR",
            "price_movement": {"percentage": 1.1, "movement": "Up"},
            "date": "now",
        }
    }
    fake = FakeSerp({"google_finance": nse_missing})
    # Engine responses are per-call here, so emulate the fallback explicitly.
    responses = []

    def search(engine, params=None, use_cache=True):
        responses.append(params.get("q"))
        return bse_ok if params.get("q", "").endswith(":BSE") else nse_missing

    fake.search = search  # type: ignore[method-assign]
    observation = StockProvider(client=fake).fetch(StockRule(symbol="SUZLON", condition="price_below", target_price=70))
    assert responses == ["SUZLON:NSE", "SUZLON:BSE"]
    assert observation["exchange"] == "BSE"


def test_provider_failure_is_raised():
    provider = FlightProvider(client=FakeSerp({"google_flights": ProviderError("rate limited", retryable=True)}))
    with pytest.raises(ProviderError):
        provider.fetch(flight_rule())


def test_missing_api_key_is_reported_not_fabricated():
    with pytest.raises(ProviderNotConfigured):
        FlightProvider(client=SerpApiClient(api_key="")).fetch(flight_rule())


def job_rule() -> JobRule:
    return JobRule(keywords=["SSC CGL"], organization="SSC", domains=["ssc.gov.in"])


def test_jobs_provider_filters_non_official_and_verifies_official_page():
    google_payload = {
        "organic_results": [
            {
                "title": "SSC CGL 2026 Notification",
                "link": "https://ssc.gov.in/notice/cgl-2026?utm_source=news",
                "snippet": "Official notice",
                "date": "Nov 20, 2026",
                "source": "SSC",
            },
            {
                "title": "SSC CGL coaching blog",
                "link": "https://randomcoaching.blogspot.com/ssc-cgl",
                "snippet": "Unofficial",
            },
        ]
    }
    extract_payload = {"markdown": "Staff Selection Commission ... SSC CGL notification ... apply now"}
    fake = FakeSerp({"google": google_payload, "google_news": {}}, extract_payload)

    observation = JobsProvider(client=fake).fetch(job_rule())

    assert len(observation["notices"]) == 1
    notice = observation["notices"][0]
    assert notice["domain"] == "ssc.gov.in"
    assert notice["verification_status"] == "verified"
    assert notice["official_domain"] is True

    google_call = next(params for engine, params in fake.calls if engine == "google")
    news_call = next(params for engine, params in fake.calls if engine == "google_news")
    assert google_call["tbs"] == "qdr:y"
    assert "so" not in news_call  # SerpApi rejects q + so together


def test_jobs_provider_drops_generic_official_pages_and_irrelevant_results():
    google_payload = {
        "organic_results": [
            {"title": "Home | Staff Selection Commission", "link": "https://ssc.gov.in/"},
            {
                "title": "Notice board",
                "link": "https://ssc.gov.in/notice-board",
                "snippet": "Constable GD examination updates",
            },
            {
                "title": "SSC CGL 2026 notification",
                "link": "https://ssc.gov.in/notice/cgl-2026",
                "snippet": "Combined Graduate Level notice",
            },
        ]
    }
    fake = FakeSerp(
        {"google": google_payload, "google_news": {}},
        {"markdown": "SSC CGL notification apply now"},
    )
    observation = JobsProvider(client=fake).fetch(job_rule())
    assert len(observation["notices"]) == 1
    assert observation["notices"][0]["url"].endswith("/notice/cgl-2026")


def test_job_page_without_matching_content_is_flagged():
    google_payload = {
        "organic_results": [
            {"title": "SSC CGL notice", "link": "https://ssc.gov.in/notice", "snippet": "x"}
        ]
    }
    fake = FakeSerp(
        {"google": google_payload, "google_news": {}},
        {"markdown": "Page not found. Please check the URL."},
    )
    observation = JobsProvider(client=fake).fetch(job_rule())
    assert observation["notices"][0]["verification_status"] == "flagged"


def test_extract_failure_leaves_notice_unverified():
    google_payload = {
        "organic_results": [
            {"title": "SSC CGL notice", "link": "https://ssc.gov.in/notice", "snippet": "x"}
        ]
    }
    fake = FakeSerp(
        {"google": google_payload, "google_news": {}},
        ProviderError("extract failed", retryable=True),
    )
    observation = JobsProvider(client=fake).fetch(job_rule())
    assert observation["notices"][0]["verification_status"] == "unverified"


def test_job_notices_are_deduplicated_by_url():
    google_payload = {
        "organic_results": [
            {"title": "SSC CGL notice", "link": "https://ssc.gov.in/notice?utm_source=a"},
            {"title": "SSC CGL notice", "link": "https://www.ssc.gov.in/notice?utm_source=b"},
        ]
    }
    fake = FakeSerp(
        {"google": google_payload, "google_news": {}},
        {"markdown": "SSC CGL notification"},
    )
    observation = JobsProvider(client=fake).fetch(job_rule())
    assert len(observation["notices"]) == 1


def test_nexconn_signature_and_group_alert_payload(monkeypatch):
    assert build_signature("secret", "123", "456") == hashlib.sha1(b"secret123456").hexdigest()

    client = NexconnClient(
        app_key="app-key",
        app_secret="app-secret",
        host="https://api.example.test",
        bot_user_id="nazar-bot",
    )
    headers = client.auth_headers(nonce="abc", timestamp="1700000000000")
    assert headers["App-Key"] == "app-key"
    assert headers["Signature"] == hashlib.sha1(b"app-secretabc1700000000000").hexdigest()

    captured: dict = {}

    def fake_post(path, payload, timeout=20):
        captured["path"] = path
        captured["payload"] = payload
        return {"messageIds": [{"channelId": "chan-1", "messageId": "m-1"}]}

    monkeypatch.setattr(client, "_post", fake_post)
    client.send_alert_card("chan-1", {"title": "Fare dropped", "alert_id": 7})

    assert captured["path"] == "/v4/group-channel/message/send"
    body = captured["payload"]
    assert body["toChannelIds"] == ["chan-1"]
    assert body["fromUserId"] == "nazar-bot"
    assert body["messageType"] == "NZ:AlertCard"
    assert json.loads(body["content"])["alert_id"] == 7
    assert body["pushContent"].startswith("Nazar alert")


def test_nexconn_search_card_uses_its_registered_custom_type(monkeypatch):
    client = NexconnClient(
        app_key="app-key",
        app_secret="app-secret",
        host="https://api.example.test",
        bot_user_id="nazar-bot",
        search_message_type="NZ:SearchCard",
    )
    captured: dict = {}

    def fake_post(path, payload, timeout=20):
        captured.update(path=path, payload=payload)
        return {}

    monkeypatch.setattr(client, "_post", fake_post)
    client.send_search_card(
        "chan-1",
        {"summary": "Three options found", "results": [{"title": "Phone", "url": "https://shop.example"}]},
    )

    assert captured["path"] == "/v4/group-channel/message/send"
    assert captured["payload"]["messageType"] == "NZ:SearchCard"
    assert json.loads(captured["payload"]["content"])["summary"] == "Three options found"
    assert captured["payload"]["pushContent"] == "Three options found"


def test_nexconn_create_group_uses_documented_request(monkeypatch):
    client = NexconnClient(
        app_key="app-key",
        app_secret="app-secret",
        host="https://api.example.test",
        bot_user_id="nazar-bot",
    )
    captured: dict = {}

    def fake_post(path, payload, timeout=20):
        captured["path"] = path
        captured["payload"] = payload
        return {}

    monkeypatch.setattr(client, "_post", fake_post)
    channel_id = client.create_group("Family Room", "owner-1")

    assert captured["path"] == "/v4/group-channel/create"
    payload = captured["payload"]
    assert payload["owner"] == "owner-1"
    assert payload["name"] == "Family Room"
    assert payload["channelId"] == channel_id
    assert "userId" not in payload
    assert channel_id.isalnum() and len(channel_id) <= 64


def test_nexconn_webhook_signature_verification(monkeypatch):
    monkeypatch.setattr(settings, "nexconn_webhook_secret", "whsec")
    client = NexconnClient(app_key="k", app_secret="s", host="https://api.example.test")
    body = b'{"data":{}}'
    signature = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()

    assert client.verify_webhook(body, {"x-nexconn-signature": signature}) is True
    assert client.verify_webhook(body, {"x-nexconn-signature": "wrong"}) is False
    assert client.verify_webhook(body, {}) is False

    monkeypatch.setattr(settings, "nexconn_webhook_secret", "")
    assert client.verify_webhook(body, {}) is True
