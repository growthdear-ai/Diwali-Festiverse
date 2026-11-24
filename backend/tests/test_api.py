from __future__ import annotations

import json
from datetime import date, timedelta

from app.models.alert import Alert
from app.models.watch import Watch
from app.models.watch_history import WatchHistory


def flight_rule(days: int = 60) -> dict:
    return {
        "origin": "BLR",
        "destination": "PAT",
        "travel_date": (date.today() + timedelta(days=days)).isoformat(),
        "condition": "below",
        "target_price": 6000,
        "currency": "INR",
    }


def create_room(client, headers, name: str = "Family", conversation: str | None = None) -> dict:
    payload = {"name": name}
    if conversation:
        payload["nexconn_conversation_id"] = conversation
    response = client.post("/api/v1/rooms", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def create_watch(client, headers, room_id: int) -> dict:
    response = client.post(
        f"/api/v1/watches?room_id={room_id}",
        json={"watch_type": "flight", "rule": flight_rule()},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_room_level_authorization(client, user_a, user_b):
    room = create_room(client, user_a["headers"])
    watch = create_watch(client, user_a["headers"], room["id"])

    assert client.get(f"/api/v1/rooms/{room['id']}", headers=user_b["headers"]).status_code == 403
    assert client.get("/api/v1/rooms", headers=user_b["headers"]).json() == []
    assert client.get(f"/api/v1/watches?room_id={room['id']}", headers=user_b["headers"]).status_code == 403
    assert client.get(f"/api/v1/watches/{watch['id']}", headers=user_b["headers"]).status_code == 403
    assert client.get(f"/api/v1/alerts?room_id={room['id']}", headers=user_b["headers"]).status_code == 403
    assert (
        client.delete(f"/api/v1/watches/{watch['id']}", headers=user_b["headers"]).status_code
        == 403
    )


def test_account_wide_lists_and_watch_history(client, db, user_a, user_b):
    response = client.post(
        "/api/v1/rooms",
        json={"name": "Family", "description": "Trip planning and Papa's stocks"},
        headers=user_a["headers"],
    )
    assert response.status_code == 201, response.text
    room = response.json()
    assert room["description"] == "Trip planning and Papa's stocks"
    assert room["members"][0]["name"] == "Asha"

    watch = create_watch(client, user_a["headers"], room["id"])
    db.add(
        WatchHistory(
            watch_id=watch["id"],
            observed_value=5640,
            observed_data={"currency": "INR"},
        )
    )
    db.add(
        Alert(
            room_id=room["id"],
            watch_id=watch["id"],
            title="Flight fare dropped: BLR → PAT",
            observed_value="₹5,640",
            sources_json=[],
            verification_status="not_applicable",
            event_key="account-wide-event",
        )
    )
    db.commit()

    watches = client.get("/api/v1/watches", headers=user_a["headers"])
    assert watches.status_code == 200, watches.text
    body = watches.json()
    assert [item["id"] for item in body] == [watch["id"]]
    assert body[0]["latest_value"] == 5640
    assert body[0]["history"][-1]["observed_value"] == 5640

    alerts = client.get("/api/v1/alerts", headers=user_a["headers"])
    assert alerts.status_code == 200, alerts.text
    assert [item["watch_id"] for item in alerts.json()] == [watch["id"]]

    filtered = client.get(
        f"/api/v1/alerts?watch_id={watch['id']}", headers=user_a["headers"]
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1

    # Another account sees no rooms, watches or alerts.
    assert client.get("/api/v1/watches", headers=user_b["headers"]).json() == []
    assert client.get("/api/v1/alerts", headers=user_b["headers"]).json() == []


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/api/v1/rooms").status_code == 401
    assert client.get("/api/v1/watches?room_id=1").status_code == 401


def test_duplicate_registration_conflicts(client, user_a):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Asha", "email": "asha@example.com", "password": "password123"},
    )
    assert response.status_code == 409


def test_parse_endpoint_returns_structured_rule(client, user_a):
    response = client.post(
        "/api/v1/watches/parse",
        json={"text": "@Nazar Bangalore se Patna 30 Nov 2027 flight 6000 se kam ho toh batao"},
        headers=user_a["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["understood"] is True
    assert body["rule"]["origin"] == "BLR"
    assert body["rule"]["travel_date"] == "2027-11-30"


def test_join_room_with_invite_code(client, user_a, user_b):
    room = create_room(client, user_a["headers"])
    invite = client.post(f"/api/v1/rooms/{room['id']}/invite", headers=user_a["headers"]).json()
    assert invite["invite_code"] == room["invite_code"]
    assert "wa.me" in invite["whatsapp_url"]

    joined = client.post(
        f"/api/v1/rooms/join/{invite['invite_code']}", headers=user_b["headers"]
    )
    assert joined.status_code == 200
    assert joined.json()["my_role"] == "member"
    members = client.get(f"/api/v1/rooms/{room['id']}/members", headers=user_b["headers"]).json()
    assert len(members) == 2


def _seed_alert(client, db, user) -> tuple[dict, dict]:
    room = create_room(client, user["headers"])
    watch = create_watch(client, user["headers"], room["id"])
    alert = Alert(
        room_id=room["id"],
        watch_id=watch["id"],
        title="Flight fare dropped: BLR → PAT",
        observed_value="₹5,640",
        explanation="Fares often soften closer to the date.",
        sources_json=[],
        verification_status="not_applicable",
        event_key="test-event-1",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return room, {"alert_id": alert.id, "watch_id": watch["id"]}


def test_room_message_can_vote_with_nazar_mention(client, db, user_a):
    room, seeded = _seed_alert(client, db, user_a)

    response = client.post(
        f"/api/v1/rooms/{room['id']}/messages",
        json={"message_text": "@Nazar YES"},
        headers=user_a["headers"],
    )

    assert response.status_code == 201, response.text
    assert response.json()["bot_reply"]["action"] == "vote_cast"
    assert response.json()["bot_reply"]["alert_id"] == seeded["alert_id"]
    assert response.json()["bot_reply"]["choice"] == "yes"


def test_vote_creation_and_update(client, db, user_a):
    room, seeded = _seed_alert(client, db, user_a)
    alert_id = seeded["alert_id"]

    first = client.post(
        f"/api/v1/alerts/{alert_id}/vote", json={"choice": "yes"}, headers=user_a["headers"]
    )
    assert first.status_code == 200, first.text
    assert first.json()["yes"] == 1
    assert first.json()["my_vote"] == "yes"

    second = client.post(
        f"/api/v1/alerts/{alert_id}/vote", json={"choice": "wait"}, headers=user_a["headers"]
    )
    body = second.json()
    assert body["yes"] == 0
    assert body["wait"] == 1
    assert body["total_votes"] == 1
    assert body["total_members"] == 1

    tally = client.get(f"/api/v1/alerts/{alert_id}/votes", headers=user_a["headers"]).json()
    assert tally["wait"] == 1
    assert tally["my_vote"] == "wait"


def test_non_member_cannot_vote(client, db, user_a, user_b):
    room, seeded = _seed_alert(client, db, user_a)
    response = client.post(
        f"/api/v1/alerts/{seeded['alert_id']}/vote",
        json={"choice": "yes"},
        headers=user_b["headers"],
    )
    assert response.status_code == 403


def test_booked_completion_stops_future_checks(client, db, user_a):
    room, seeded = _seed_alert(client, db, user_a)

    response = client.post(
        f"/api/v1/alerts/{seeded['alert_id']}/complete",
        json={"action": "booked"},
        headers=user_a["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["watch_status"] == "completed"
    assert body["booked_by"] == "Asha"

    watch = client.get(f"/api/v1/watches/{seeded['watch_id']}", headers=user_a["headers"]).json()
    assert watch["status"] == "completed"
    assert watch["next_check_at"] is None
    assert watch["booked_by_id"] == user_a["user"]["id"]

    # The scheduler must now skip this watch.
    db_watch = db.get(Watch, seeded["watch_id"])
    from app.services.monitoring_service import check_watch

    result = check_watch(db, db_watch, force=True)
    assert result["status"] == "skipped"


def test_nexconn_webhook_creates_watch_and_is_idempotent(client, db, user_a):
    room = create_room(client, user_a["headers"], conversation="conv-123")
    nexconn_user_id = user_a["user"]["nexconn_user_id"]
    payload = {
        "type": "message",
        "data": {
            "message": {
                "channelId": "conv-123",
                "fromUserId": nexconn_user_id,
                "messageId": "msg-1",
                "content": json.dumps(
                    {
                        "content": "@Nazar Bangalore se Patna 30 Nov 2027 flight 6000 se kam ho toh batao"
                    }
                ),
            }
        },
    }

    first = client.post("/api/v1/webhooks/nexconn", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["result"]["action"] == "watch_created"

    duplicate = client.post("/api/v1/webhooks/nexconn", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["result"] == "duplicate"

    watches = client.get(f"/api/v1/watches?room_id={room['id']}", headers=user_a["headers"]).json()
    assert len(watches) == 1
    assert watches[0]["watch_type"] == "flight"


def test_nexconn_room_history_saves_chat_and_nazar_replies(client, user_a):
    room = create_room(client, user_a["headers"], conversation="history-conv")
    external_id = user_a["user"]["nexconn_user_id"]

    def post_message(message_id: str, text: str):
        return client.post(
            "/api/v1/webhooks/nexconn",
            json={
                "data": {
                    "message": {
                        "channelId": "history-conv",
                        "fromUserId": external_id,
                        "messageId": message_id,
                        "content": json.dumps({"content": text}),
                    }
                }
            },
        )

    chat = post_message("history-chat", "Anyone free to travel this weekend?")
    assert chat.status_code == 200
    assert chat.json()["result"]["action"] == "ignored"

    ask = post_message("history-ask", "@Nazar Tata Motors 5% gir jaye toh batao")
    assert ask.status_code == 200
    assert ask.json()["result"]["action"] == "watch_created"

    messages = client.get(
        f"/api/v1/rooms/{room['id']}/messages", headers=user_a["headers"]
    ).json()
    assert [message["message_text"] for message in messages[:2]] == [
        "Anyone free to travel this weekend?",
        "@Nazar Tata Motors 5% gir jaye toh batao",
    ]
    assert messages[2]["sender_id"] is None
    assert messages[2]["message_type"] == "bot"
    assert json.loads(messages[2]["message_text"])["action"] == "watch_created"


def test_nexconn_search_follow_up_refines_previous_query(client, user_a, monkeypatch):
    room = create_room(client, user_a["headers"], conversation="search-conv")
    external_id = user_a["user"]["nexconn_user_id"]
    queries: list[str] = []

    def fake_search(text, parsed):
        queries.append(text)
        return {
            "action": "search_results",
            "reply": "Here are current phones. Any preferred brand?",
            "sources": [],
            "context": text,
        }

    monkeypatch.setattr("app.services.search_service.search", fake_search)

    def post_message(message_id: str, text: str):
        return client.post(
            "/api/v1/webhooks/nexconn",
            json={
                "data": {
                    "message": {
                        "channelId": "search-conv",
                        "fromUserId": external_id,
                        "messageId": message_id,
                        "content": json.dumps({"content": text}),
                    }
                }
            },
        )

    first = post_message("search-1", "@Nazar phones under 60000")
    assert first.status_code == 200
    assert first.json()["result"]["action"] == "search_results"

    second = post_message("search-2", "Samsung")
    assert second.status_code == 200
    assert second.json()["result"]["action"] == "search_results"
    assert queries == ["@Nazar phones under 60000", "@Nazar phones under 60000 Samsung"]


def test_webhook_ignores_unmapped_conversation(client):
    response = client.post(
        "/api/v1/webhooks/nexconn",
        json={
            "data": {
                "message": {
                    "channelId": "unknown",
                    "fromUserId": "x",
                    "content": "{\"content\": \"hello\"}",
                }
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["result"] == "conversation_not_mapped"


def test_health_endpoint_reports_provider_state_without_secrets(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["providers"]["serpapi"] == "missing_key"
    assert body["llm"]["provider"] == "openai"
    assert "demo_mode" not in body
    assert "SERPAPI_API_KEY" not in response.text
