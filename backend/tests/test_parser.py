import json
from datetime import date

import httpx

from app.core.config import settings
from app.services.parser_service import parse_message, refine_search_request

TODAY = date(2026, 11, 21)


def test_hinglish_flight_rule_extracts_airports_price_and_future_date():
    result = parse_message(
        "@Nazar Bangalore se Patna 4 Nov ka flight 6000 se kam ho toh batao.", today=TODAY
    )

    assert result["understood"] is True
    assert result["watch_type"] == "flight"
    rule = result["rule"]
    assert rule["origin"] == "BLR"
    assert rule["destination"] == "PAT"
    assert rule["condition"] == "below"
    assert rule["target_price"] == 6000
    assert rule["currency"] == "INR"
    # 4 Nov has already passed on 21 Nov, so it resolves to the upcoming year.
    assert rule["travel_date"] == "2027-11-04"
    assert result["parser"] == "heuristic"


def test_upcoming_date_stays_in_current_year():
    result = parse_message(
        "@Nazar Bangalore se Patna 30 Nov flight 6000 se kam", today=TODAY
    )
    assert result["rule"]["travel_date"] == "2026-11-30"


def test_explicit_year_is_respected():
    result = parse_message(
        "Delhi to Mumbai flight on 15 Mar 2027 under 4500", today=TODAY
    )
    assert result["rule"]["origin"] == "DEL"
    assert result["rule"]["destination"] == "BOM"
    assert result["rule"]["travel_date"] == "2027-03-15"


def test_missing_fields_trigger_follow_up():
    result = parse_message("Patna flight ka price batao", today=TODAY)

    assert result["understood"] is False
    assert result["watch_type"] == "flight"
    assert "origin" in result["missing_fields"]
    assert "destination" in result["missing_fields"]
    assert "target_price" in result["missing_fields"]
    assert result["follow_up_question"]


def test_hinglish_stock_rule():
    result = parse_message("@Nazar Tata Motors 5% gir jaye toh batao", today=TODAY)

    assert result["understood"] is True
    assert result["watch_type"] == "stock"
    rule = result["rule"]
    assert rule["symbol"] == "TATAMOTORS"
    assert rule["condition"] == "absolute_change_greater_than"
    assert rule["threshold_percent"] == 5
    assert rule["direction"] == "down"


def test_english_stock_price_threshold():
    result = parse_message("Alert me if ITC goes below 400", today=TODAY)

    assert result["watch_type"] == "stock"
    assert result["rule"]["symbol"] == "ITC"
    assert result["rule"]["condition"] == "price_below"
    assert result["rule"]["target_price"] == 400


def test_job_notification_rule_uses_official_domains():
    result = parse_message("@Nazar SSC CGL notification aaye toh batao", today=TODAY)

    assert result["understood"] is True
    assert result["watch_type"] == "job_notification"
    rule = result["rule"]
    assert "SSC CGL" in rule["keywords"]
    assert rule["organization"] == "SSC"
    assert "ssc.gov.in" in rule["domains"]


def test_unknown_message_asks_for_supported_types():
    result = parse_message("@Nazar hello, kya haal hai?", today=TODAY)

    assert result["understood"] is False
    assert result["watch_type"] is None
    assert "flight" in result["follow_up_question"].lower()


class FakeOllamaResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"message": {"role": "assistant", "content": self._content}, "done": True}


def test_ambiguous_message_uses_ollama_native_chat(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    monkeypatch.setattr(settings, "llm_model", "gpt-4o-mini")
    monkeypatch.setattr(settings, "llm_ollama_model", "llama3.2:3b")
    monkeypatch.setattr(settings, "llm_api_key", "")

    rule = {
        "watch_type": "flight",
        "origin": "BLR",
        "destination": "PAT",
        "travel_date": "2027-11-30",
        "condition": "below",
        "target_price": 6000,
        "currency": "INR",
        "passengers": 1,
    }
    llm_content = "```json\n" + json.dumps(
        {
            "watch_type": "flight",
            "rule": rule,
            "missing_fields": [],
            "follow_up_question": None,
        }
    ) + "\n```"
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return FakeOllamaResponse(llm_content)

    monkeypatch.setattr("app.services.parser_service.httpx.post", fake_post)
    result = parse_message(
        "Please keep an eye on the Bangalore to Patna trip on 30 Nov 2027 and ping the group if it costs under 6000.",
        today=TODAY,
    )

    assert result["parser"] == "llm"
    assert result["understood"] is True
    assert result["rule"]["origin"] == "BLR"
    assert result["rule"]["destination"] == "PAT"
    assert result["rule"]["target_price"] == 6000
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] == "json"
    assert captured["payload"]["options"] == {"temperature": 0}
    # An OpenAI model name is remapped to the configured Ollama model.
    assert captured["payload"]["model"] == "llama3.2:3b"
    assert "Authorization" not in captured["headers"]


def test_llm_cannot_overwrite_deterministic_values(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    monkeypatch.setattr(settings, "llm_model", "llama3.2:3b")
    monkeypatch.setattr(settings, "llm_api_key", "")

    # The model hallucinates a different airport and year here.
    llm_rule = {
        "watch_type": "flight",
        "origin": "BAG",
        "destination": "PAT",
        "travel_date": "2028-11-30",
        "condition": "below",
        "target_price": 6000,
        "currency": "INR",
    }
    llm_content = json.dumps(
        {
            "watch_type": "flight",
            "rule": llm_rule,
            "missing_fields": [],
            "follow_up_question": None,
        }
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"role": "assistant", "content": llm_content}}

    def fake_post(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.services.parser_service.httpx.post", fake_post)
    result = parse_message(
        "@Nazar yaar Patna jaana hai 30 Nov 2027 ko Bangalore se, ticket 6000 se upar na ho toh batana.",
        today=TODAY,
    )

    assert result["parser"] == "llm"
    assert result["understood"] is True
    assert result["rule"]["origin"] == "BLR"  # deterministic city extraction wins
    assert result["rule"]["destination"] == "PAT"  # LLM value backed by "Patna"
    assert result["rule"]["travel_date"] == "2027-11-30"  # not the hallucinated 2028
    assert result["rule"]["target_price"] == 6000
    assert result["rule"]["condition"] == "below"


def test_ollama_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    monkeypatch.setattr(settings, "llm_model", "llama3.2:3b")
    monkeypatch.setattr(settings, "llm_api_key", "")

    def fail(**_kwargs):
        raise httpx.ConnectError("Ollama is not running")

    monkeypatch.setattr("app.services.parser_service.httpx.post", fail)
    result = parse_message(
        "Please keep an eye on the Bangalore to Patna trip on 30 Nov 2027 and ping the group if it costs under 6000.",
        today=TODAY,
    )

    assert result["parser"] == "heuristic"
    assert result["understood"] is False
    assert result["follow_up_question"]


def test_search_refinement_uses_ollama_and_keeps_budget_constraint(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    monkeypatch.setattr(settings, "llm_model", "llama3.2:3b")
    monkeypatch.setattr(settings, "llm_api_key", "")
    captured: dict = {}

    def fake_chat(messages):
        captured["messages"] = messages
        return json.dumps(
            {
                "query": "best smartphones in India",
                "follow_up_question": "Do you prefer Android or iPhone?",
            }
        )

    monkeypatch.setattr("app.services.parser_service._llm_chat", fake_chat)
    parsed = parse_message("@Nazar phones under 60000")

    result = refine_search_request("@Nazar phones under 60000", parsed)

    assert result["query"] == "best smartphones in India under 60000 INR"
    assert result["follow_up_question"] == "Do you prefer Android or iPhone?"
    assert "60000" in captured["messages"][1]["content"]


def test_search_refinement_preserves_institution_and_semester(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    monkeypatch.setattr(settings, "llm_model", "llama3.2:3b")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(
        "app.services.parser_service._llm_chat",
        lambda _messages: json.dumps(
            {"query": "exam timetable students", "follow_up_question": "Which branch?"},
        ),
    )

    result = refine_search_request(
        "@Nazar VTU exam time table for 7th sem students",
        {"rule": {"source": "web", "query": "exam time table students"}},
    )

    assert "VTU" in result["query"]
    assert "7th" in result["query"]
    assert "semester" in result["query"]
