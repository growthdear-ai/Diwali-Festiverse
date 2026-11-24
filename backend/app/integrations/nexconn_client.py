"""Nexconn Platform Chat API adapter.

Verified against https://docs.nexconn.ai:
- Signature: SHA1(App Secret + Nonce + Timestamp-ms) in App-Key/Nonce/Timestamp/Signature headers.
- Group message: POST {host}/v4/group-channel/message/send with JSON body
  fromUserId, toChannelIds, messageType, content (serialized JSON string).
- User registration/token: POST {host}/v4/auth/access-token/issue.

Server credentials stay in the backend; clients only receive short-lived tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
import uuid

import httpx

from app.core.config import settings
from app.integrations.serpapi_client import ProviderError, ProviderNotConfigured


class NexconnError(ProviderError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message, retryable=retryable, provider="nexconn")


def build_signature(app_secret: str, nonce: str, timestamp: str) -> str:
    """SHA1(App Secret + Nonce + Timestamp). Documented Nexconn signing rule."""

    return hashlib.sha1(f"{app_secret}{nonce}{timestamp}".encode("utf-8")).hexdigest()


class NexconnClient:
    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        host: str | None = None,
        bot_user_id: str | None = None,
        bot_name: str | None = None,
        alert_message_type: str | None = None,
        search_message_type: str | None = None,
    ) -> None:
        self.app_key = settings.nexconn_app_key if app_key is None else app_key
        self.app_secret = settings.nexconn_app_secret if app_secret is None else app_secret
        self.host = (settings.nexconn_api_host if host is None else host).rstrip("/")
        self.bot_user_id = settings.nexconn_bot_user_id if bot_user_id is None else bot_user_id
        self.bot_name = settings.nexconn_bot_name if bot_name is None else bot_name
        self.alert_message_type = (
            settings.nexconn_alert_message_type if alert_message_type is None else alert_message_type
        )
        self.search_message_type = (
            settings.nexconn_search_message_type if search_message_type is None else search_message_type
        )

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret and self.host)

    def auth_headers(self, *, nonce: str | None = None, timestamp: str | None = None) -> dict[str, str]:
        nonce = nonce or str(random.randint(100000, 999999999))
        timestamp = timestamp or str(int(time.time() * 1000))
        return {
            "App-Key": self.app_key,
            "Nonce": nonce,
            "Timestamp": timestamp,
            "Signature": build_signature(self.app_secret, nonce, timestamp),
            "Content-Type": "application/json",
            "X-Request-ID": uuid.uuid4().hex,
        }

    def _post(self, path: str, payload: dict, *, timeout: int = 20) -> dict:
        if not self.configured:
            raise ProviderNotConfigured(
                "Nexconn is not configured (NEXCONN_APP_KEY/SECRET/HOST)", provider="nexconn"
            )
        normalized_path = path if path.startswith("/") else f"/{path}"
        try:
            response = httpx.post(
                f"{self.host}{normalized_path}",
                json=payload,
                headers=self.auth_headers(),
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise NexconnError(f"Nexconn request failed: {exc}", retryable=True) from exc

        if response.status_code == 401:
            raise NexconnError("Nexconn rejected the request signature (HTTP 401)")
        if response.status_code >= 400:
            raise NexconnError(
                f"Nexconn HTTP {response.status_code}: {response.text[:200]}",
                retryable=response.status_code in {429, 500, 502, 503, 504},
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise NexconnError("Nexconn returned non-JSON content") from exc

        code = data.get("code")
        if code not in (0, "0", None):
            raise NexconnError(f"Nexconn error {code}: {data.get('msg') or data.get('message') or data}")
        return data.get("result") or {}

    def issue_access_token(self, user_id: str, name: str, avatar_url: str | None = None) -> dict:
        payload: dict = {"userId": user_id, "name": name or user_id}
        if avatar_url:
            payload["avatarUrl"] = avatar_url
        return self._post("/v4/auth/access-token/issue", payload)

    def send_group_text(
        self,
        channel_id: str,
        text: str,
        *,
        push_content: str | None = None,
        mention_user_ids: list[str] | None = None,
    ) -> dict:
        content: dict = {"content": text}
        if mention_user_ids:
            content["mentionedInfo"] = {"type": 2, "userIdList": mention_user_ids, "mentionedContent": ""}
        return self._post(
            "/v4/group-channel/message/send",
            {
                "fromUserId": self.bot_user_id,
                "toChannelIds": [channel_id],
                "messageType": "RC:TxtMsg",
                "content": json.dumps(content, ensure_ascii=False),
                "pushContent": push_content or text[:120],
                "shouldPersist": 1,
                "isEchoToSender": 1,
                "hasMention": 1 if mention_user_ids else 0,
            },
        )

    def send_custom_message(
        self,
        channel_id: str,
        message_type: str,
        payload: dict,
        *,
        push_content: str | None = None,
    ) -> dict:
        return self._post(
            "/v4/group-channel/message/send",
            {
                "fromUserId": self.bot_user_id,
                "toChannelIds": [channel_id],
                "messageType": message_type,
                "content": json.dumps(payload, ensure_ascii=False, default=str),
                "pushContent": push_content or str(payload.get("title") or "Nazar alert")[:120],
                "shouldPersist": 1,
                "isEchoToSender": 1,
            },
        )

    def send_alert_card(self, channel_id: str, card: dict) -> dict:
        """Custom message type; the Web ChatUI must register this objectName."""

        return self.send_custom_message(
            channel_id,
            self.alert_message_type,
            card,
            push_content=f"Nazar alert: {card.get('title', 'update')}",
        )

    def send_search_card(self, channel_id: str, card: dict) -> dict:
        """Send a rich search result for the Web ChatUI's registered custom message."""

        return self.send_custom_message(
            channel_id,
            self.search_message_type,
            card,
            push_content=str(card.get("summary") or "Nazar found search results")[:120],
        )

    def send_vote_prompt(self, channel_id: str, alert_id: int, title: str, options: list[str]) -> dict:
        text = (
            f"Vote on alert #{alert_id}: {title}\n"
            f"Reply with {', '.join(options[:-1])} or {options[-1]}, "
            f"or tap a button in the alert card."
        )
        return self.send_group_text(channel_id, text, push_content=f"Vote: {title}")

    def create_group(
        self, name: str, owner_user_id: str, channel_id: str | None = None
    ) -> str:
        """Create a group channel and return its channel id.

        Documented body: channelId, name, owner, optional userIds. The API returns
        a code-only response, so the client-provided channelId is the canonical id.
        Used only when auto-create is explicitly enabled.
        """

        channel_id = channel_id or f"nz{uuid.uuid4().hex[:24]}"
        self._post(
            "/v4/group-channel/create",
            {"channelId": channel_id, "name": name[:64], "owner": owner_user_id},
        )
        return channel_id

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Optional HMAC-SHA256 verification for inbound Nexconn callbacks.

        Nexconn's public docs do not specify a webhook signature algorithm, so
        this is opt-in via NEXCONN_WEBHOOK_SECRET. When no secret is configured
        the endpoint must be protected by network controls / a shared token.
        """

        if not settings.nexconn_webhook_secret:
            return True
        header = (
            headers.get("x-nexconn-signature")
            or headers.get("x-signature")
            or headers.get("X-Nexconn-Signature")
            or ""
        )
        provided = header.removeprefix("sha256=").strip()
        if not provided:
            return False
        expected = hmac.new(
            settings.nexconn_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, provided)


nexconn_client = NexconnClient()
