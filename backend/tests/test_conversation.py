"""Nazar chat behaviour: saved replies, follow-up memory, greetings, unsupported requests."""

from __future__ import annotations

import json

API = "/api/v1"


def _room(client, user) -> int:
    response = client.post(f"{API}/rooms", json={"name": "Sharma Family"}, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _say(client, user, room_id: int, text: str) -> dict:
    response = client.post(f"{API}/rooms/{room_id}/messages", json={"message_text": text}, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()["bot_reply"]


def _bot_messages(client, user, room_id: int) -> list[dict]:
    messages = client.get(f"{API}/rooms/{room_id}/messages", headers=user["headers"]).json()
    return [json.loads(m["message_text"]) for m in messages if m["sender_id"] is None]


def test_bot_reply_is_saved_in_the_room(client, user_a):
    room_id = _room(client, user_a)
    reply = _say(client, user_a, room_id, "@Nazar Tata Motors 5% gir jaye toh batao")
    assert reply["action"] == "watch_created"
    saved = _bot_messages(client, user_a, room_id)
    assert saved[-1]["action"] == "watch_created"
    assert saved[-1]["watch_id"] == reply["watch_id"]


def test_follow_up_answer_completes_the_watch_without_mention(client, user_a):
    room_id = _room(client, user_a)
    first = _say(client, user_a, room_id, "@Nazar Tata Motors pe nazar rakho")
    assert first["action"] == "follow_up"
    second = _say(client, user_a, room_id, "3%")
    assert second["action"] == "watch_created"
    assert second["watch_type"] == "stock"


def test_other_members_messages_are_not_taken_as_answers(client, user_a, user_b):
    room_id = _room(client, user_a)
    invite = client.post(f"{API}/rooms/{room_id}/invite", headers=user_a["headers"]).json()
    client.post(f"{API}/rooms/join/{invite['invite_code']}", headers=user_b["headers"])
    assert _say(client, user_a, room_id, "@Nazar Tata Motors pe nazar rakho")["action"] == "follow_up"
    assert _say(client, user_b, room_id, "3%")["action"] == "ignored"


def test_greeting_gets_help_instantly(client, user_a):
    room_id = _room(client, user_a)
    reply = _say(client, user_a, room_id, "@Nazar hello")
    assert reply["action"] == "follow_up"
    assert reply["unsupported"] is True
    assert "flight" in reply["reply"].lower()


def test_private_company_jobs_become_a_jobs_watch(client, user_a):
    room_id = _room(client, user_a)
    reply = _say(client, user_a, room_id, "@Nazar check for infosys jobs for sde1")
    assert reply["action"] == "watch_created"
    assert reply["watch_type"] == "topic"
    # A finished request isn't reopened by the next short message.
    assert _say(client, user_a, room_id, "1%")["action"] == "ignored"


def test_plain_budget_question_searches_now_and_keeps_context(client, user_a, monkeypatch):
    room_id = _room(client, user_a)
    queries: list[str] = []

    def fake_search(text, parsed):
        queries.append(text)
        return {
            "action": "search_results",
            "reply": "Here are current phones under ₹60,000. Any preferred brand?",
            "summary": "3 phones under ₹60,000; lowest price is ₹54,999.",
            "follow_up_question": "Any preferred brand?",
            "sources": [{"title": "Phone listing", "url": "https://shop.example/phone"}],
            "results": [
                {
                    "title": "Phone A",
                    "url": "https://shop.example/phone",
                    "price": 54999,
                    "currency": "INR",
                    "action_label": "View deal",
                }
            ],
            "context": text,
        }

    monkeypatch.setattr("app.services.search_service.search", fake_search)

    first = _say(client, user_a, room_id, "@Nazar phones under 60000")
    assert first["action"] == "search_results"
    assert client.get(f"{API}/watches?room_id={room_id}", headers=user_a["headers"]).json() == []
    saved = _bot_messages(client, user_a, room_id)[-1]
    assert saved["sources"][0]["url"] == "https://shop.example/phone"
    assert saved["results"][0]["action_label"] == "View deal"

    second = _say(client, user_a, room_id, "Samsung")
    assert second["action"] == "search_results"
    assert queries == ["@Nazar phones under 60000", "@Nazar phones under 60000 Samsung"]


def test_greeting_reply_is_not_joined_to_the_next_message(client, user_a):
    room_id = _room(client, user_a)
    assert _say(client, user_a, room_id, "@Nazar hello")["unsupported"] is True
    assert _say(client, user_a, room_id, "theek hai")["action"] == "ignored"


def test_government_job_still_works(client, user_a):
    room_id = _room(client, user_a)
    reply = _say(client, user_a, room_id, "@Nazar SSC CGL notification aaye toh batao")
    assert reply["action"] == "watch_created"
    assert reply["watch_type"] == "job_notification"


def test_mention_vote_without_an_alert_does_not_create_a_watch(client, user_a, monkeypatch):
    room_id = _room(client, user_a)
    search_calls: list[str] = []

    def fake_search(text, _parsed):
        search_calls.append(text)
        return {"action": "search_results", "reply": "Unexpected search"}

    monkeypatch.setattr("app.services.search_service.search", fake_search)

    reply = _say(client, user_a, room_id, "@Nazar YES")

    assert reply["action"] == "ignored"
    assert reply["reason"] == "no_open_alert"
    assert search_calls == []
    assert client.get(
        f"{API}/watches?room_id={room_id}", headers=user_a["headers"]
    ).json() == []
