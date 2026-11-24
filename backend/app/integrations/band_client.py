"""BAND collaboration client for Scout-to-Verifier agent handoff.

Docs:
- https://docs.band.ai/quickstart
- https://docs.band.ai/connect/choose-integration-path

BAND agents connect via WebSocket to receive live mentions and room messages,
and use REST API to send messages. We implement two agent identities:
- Nazar Scout: posts candidate changes with evidence to the BAND room
- Nazar Verifier: receives handoff, invokes Lyzr, posts verification result

This module provides the REST sending capability. WebSocket listening for live
mentions would run as a separate long-lived worker process.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class BandMessage:
    """A message to send to a BAND room."""

    room_id: str
    text: str
    message_type: str = "text"  # "text", "card", etc.
    metadata: dict[str, Any] | None = None


@dataclass
class BandAgentConfig:
    """Configuration for a BAND agent identity."""

    agent_id: str
    api_key: str
    name: str


class BandClient:
    """Client for sending messages to BAND rooms via REST API.

    For receiving live messages (mentions, replies), a separate WebSocket
    connection is required. See BandWebSocketListener for that.
    """

    # BAND API base URL (from documentation)
    BASE_URL = "https://api.band.ai"  # Adjust per current docs
    SEND_MESSAGE_ENDPOINT = "/v1/rooms/{room_id}/messages"

    def __init__(
        self,
        agent_config: BandAgentConfig,
        base_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.agent_config = agent_config
        self.base_url = (base_url or settings.band_api_host if hasattr(settings, "band_api_host") else None) or self.BASE_URL
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.agent_config.agent_id and self.agent_config.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.agent_config.api_key}",
                    "Content-Type": "application/json",
                    "X-Agent-ID": self.agent_config.agent_id,
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def send_message(self, message: BandMessage) -> dict[str, Any]:
        """Send a message to a BAND room via REST API.

        Args:
            message: BandMessage with room_id, text, and optional metadata

        Returns:
            API response dict with message_id and timestamp
        """
        if not self.configured:
            raise RuntimeError(f"BAND agent {self.agent_config.name} not configured")

        client = await self._get_client()
        url = self.SEND_MESSAGE_ENDPOINT.format(room_id=message.room_id)
        payload = {
            "text": message.text,
            "message_type": message.message_type,
        }
        if message.metadata:
            payload["metadata"] = message.metadata

        try:
            logger.info(
                "Sending BAND message from %s to room %s",
                self.agent_config.name,
                message.room_id,
            )
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "BAND send_message failed for agent %s: %s",
                self.agent_config.name,
                exc,
            )
            raise RuntimeError(f"BAND send failed: {exc}") from exc

    async def send_scout_candidate(
        self,
        room_id: str,
        watch_type: str,
        rule: dict[str, Any],
        observation: dict[str, Any],
        sources: list[dict[str, Any]],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Post a candidate change from the Scout agent to the BAND room.

        This is the first step in the collaboration flow: Scout presents the
        raw observation and evidence for the Verifier (and humans) to review.
        """
        # Build a structured card/message for the Scout
        summary = self._format_scout_summary(watch_type, rule, observation)

        # Format sources as a list
        sources_text = "\n".join(
            f"  • {s.get('title', 'Source')} — {s.get('url', 'No URL')}"
            for s in sources[:5]  # Limit to first 5 sources
        )

        text = (
            f"🔍 **Nazar Scout — Candidate Change**\n"
            f"Correlation ID: `{correlation_id}`\n\n"
            f"**Watch Type:** {watch_type}\n"
            f"**Summary:** {summary}\n\n"
            f"**Sources:**\n{sources_text}\n\n"
            f"⏳ Handing off to **Nazar Verifier** for structured analysis..."
        )

        message = BandMessage(
            room_id=room_id,
            text=text,
            message_type="card",
            metadata={
                "nazar_type": "scout_candidate",
                "correlation_id": correlation_id,
                "watch_type": watch_type,
                "rule": rule,
                "observation": observation,
                "sources": sources,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        return await self.send_message(message)

    async def send_verifier_result(
        self,
        room_id: str,
        correlation_id: str,
        verification_result: Any,  # LyzrVerificationResult
        final_decision: str,  # "alert_sent", "no_alert", "needs_human_review"
    ) -> dict[str, Any]:
        """Post the Verifier agent's analysis result to the BAND room.

        This completes the Scout→Verifier handoff in the BAND room.
        """
        status_emoji = {
            "verified": "✅",
            "no_change": "➖",
            "needs_review": "⚠️",
        }.get(verification_result.status, "❓")

        decision_text = {
            "alert_sent": "Alert created and delivered",
            "no_alert": "No alert — no verified change",
            "needs_human_review": "Flagged for human review in this room",
        }.get(final_decision, final_decision)

        # Format cited evidence
        evidence_text = "\n".join(
            f"  • {e.get('title', 'Evidence')} — {e.get('url', 'No URL')}"
            for e in verification_result.source_evidence
        )

        text = (
            f"{status_emoji} **Nazar Verifier — Analysis Complete**\n"
            f"Correlation ID: `{correlation_id}`\n\n"
            f"**Status:** {verification_result.status.upper()}\n"
            f"**Confidence:** {verification_result.confidence:.0%}\n"
            f"**Explanation:** {verification_result.explanation}\n\n"
            f"**Cited Evidence:**\n{evidence_text}\n\n"
            f"**Decision:** {decision_text}"
        )

        message = BandMessage(
            room_id=room_id,
            text=text,
            message_type="card",
            metadata={
                "nazar_type": "verifier_result",
                "correlation_id": correlation_id,
                "verification_status": verification_result.status,
                "confidence": verification_result.confidence,
                "explanation": verification_result.explanation,
                "source_evidence": verification_result.source_evidence,
                "final_decision": final_decision,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        return await self.send_message(message)

    async def send_disagreement_notice(
        self,
        room_id: str,
        correlation_id: str,
        scout_observation: dict[str, Any],
        verifier_result: Any,
        reason: str,
    ) -> dict[str, Any]:
        """Post a notice when agents disagree or evidence is missing."""
        text = (
            f"⚠️ **Nazar — Agent Disagreement / Uncertainty**\n"
            f"Correlation ID: `{correlation_id}`\n\n"
            f"**Reason:** {reason}\n\n"
            f"**Scout Observation:** {json.dumps(scout_observation, indent=2)[:500]}...\n"
            f"**Verifier Result:** {verifier_result.status} ({verifier_result.confidence:.0%})\n\n"
            f"👥 **Human review required.** No automatic alert will be sent."
        )

        message = BandMessage(
            room_id=room_id,
            text=text,
            message_type="card",
            metadata={
                "nazar_type": "disagreement",
                "correlation_id": correlation_id,
                "reason": reason,
                "scout_observation": scout_observation,
                "verifier_result": {
                    "status": verifier_result.status,
                    "confidence": verifier_result.confidence,
                },
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        return await self.send_message(message)

    def _format_scout_summary(self, watch_type: str, rule: dict[str, Any], observation: dict[str, Any]) -> str:
        """Format a human-readable summary for the Scout message."""
        if watch_type == "flight":
            return (
                f"Flight {rule.get('origin')} → {rule.get('destination')} on {rule.get('travel_date')}: "
                f"fare {observation.get('current_price')} {rule.get('currency', 'INR')} "
                f"(target {rule.get('condition', 'below')} {rule.get('target_price')})"
            )
        elif watch_type == "stock":
            symbol = rule.get("symbol")
            condition = rule.get("condition")
            if condition == "absolute_change_greater_than":
                return (
                    f"{symbol} moved {observation.get('percent_change', 0):+.2f}% "
                    f"(threshold {rule.get('threshold_percent')}%)"
                )
            else:
                return f"{symbol} at {observation.get('current_price')} {observation.get('currency', 'INR')}"
        elif watch_type == "job_notification":
            notices = observation.get("notices") or []
            return f"{len(notices)} official notice(s) for '{', '.join(rule.get('keywords', []))}'"
        elif watch_type == "topic":
            mode = rule.get("mode", "new_results")
            if mode in {"price_below", "price_above"}:
                return f"Price for '{rule.get('query')}': {observation.get('current_price')} {rule.get('currency', 'INR')}"
            items = observation.get("items") or []
            return f"{len(items)} new result(s) for '{rule.get('query')}'"
        return f"{watch_type}: {json.dumps(observation)[:200]}"


# --- WebSocket Listener for Live Mentions ---

class BandWebSocketListener:
    """WebSocket listener for receiving live BAND room messages and mentions.

    This runs as a background task/worker. It connects to BAND's WebSocket
    endpoint, authenticates with the agent credentials, and handles incoming
    messages (e.g., human replies, @mentions to trigger re-verification).

    Docs: "Receiving mentions live takes a WebSocket connection, because Band
    pushes each message that mentions the agent over it."
    """

    def __init__(
        self,
        agent_config: BandAgentConfig,
        room_id: str,
        on_message_callback: callable,
        base_url: str | None = None,
    ) -> None:
        self.agent_config = agent_config
        self.room_id = room_id
        self.on_message_callback = on_message_callback
        self.base_url = (base_url or settings.band_ws_host if hasattr(settings, "band_ws_host") else None) or "wss://api.band.ai"
        self._ws: Any = None
        self._running = False

    async def connect(self) -> None:
        """Establish WebSocket connection to BAND."""
        # Note: Exact WebSocket endpoint and auth flow per BAND docs
        # Typically: wss://api.band.ai/v1/ws?agent_id=...&api_key=...&room_id=...
        import websockets

        ws_url = f"{self.base_url}/v1/ws?agent_id={self.agent_config.agent_id}&api_key={self.agent_config.api_key}&room_id={self.room_id}"
        logger.info("Connecting BAND WebSocket for agent %s to room %s", self.agent_config.name, self.room_id)
        self._ws = await websockets.connect(ws_url)
        self._running = True

    async def listen(self) -> None:
        """Listen for incoming messages and dispatch to callback."""
        if not self._ws:
            await self.connect()

        try:
            async for message in self._ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    await self.on_message_callback(data)
                except json.JSONDecodeError:
                    logger.warning("Received non-JSON WebSocket message: %s", message[:200])
                except Exception as exc:
                    logger.exception("Error handling BAND WebSocket message")
        except Exception as exc:
            logger.error("BAND WebSocket connection error: %s", exc)
            self._running = False
            raise

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None


# --- Pre-configured Agent Instances ---

def get_scout_agent() -> BandAgentConfig:
    """Get the Scout agent configuration from settings."""
    return BandAgentConfig(
        agent_id=settings.band_scout_agent_id if hasattr(settings, "band_scout_agent_id") else "",
        api_key=settings.band_scout_api_key if hasattr(settings, "band_scout_api_key") else "",
        name="Nazar Scout",
    )


def get_verifier_agent() -> BandAgentConfig:
    """Get the Verifier agent configuration from settings."""
    return BandAgentConfig(
        agent_id=settings.band_verifier_agent_id if hasattr(settings, "band_verifier_agent_id") else "",
        api_key=settings.band_verifier_api_key if hasattr(settings, "band_verifier_api_key") else "",
        name="Nazar Verifier",
    )


def get_band_room_id() -> str:
    """Get the BAND room ID from settings."""
    return settings.band_room_id if hasattr(settings, "band_room_id") else ""


# Convenience clients (lazy-initialized)
_scout_client: BandClient | None = None
_verifier_client: BandClient | None = None


def get_scout_client() -> BandClient:
    global _scout_client
    if _scout_client is None:
        _scout_client = BandClient(get_scout_agent())
    return _scout_client


def get_verifier_client() -> BandClient:
    global _verifier_client
    if _verifier_client is None:
        _verifier_client = BandClient(get_verifier_agent())
    return _verifier_client


async def close_band_clients() -> None:
    global _scout_client, _verifier_client
    if _scout_client:
        await _scout_client.close()
        _scout_client = None
    if _verifier_client:
        await _verifier_client.close()
        _verifier_client = None