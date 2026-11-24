"""Lyzr Enterprise Agent client for structured analysis of watch results.

Docs:
- https://docs.lyzr.ai/enterprise/get-started/concepts/agents
- https://docs.lyzr.ai/agent-apis/agents/Create%20Agent

Lyzr agents are invoked via REST. We use structured output to guarantee a JSON
response conforming to our verification schema. The agent does NOT fetch data;
it only analyzes the observation and sources already collected by Nazar's providers.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LyzrVerificationResult:
    """Structured result from the Lyzr Verifier agent."""

    status: str  # "verified" | "no_change" | "needs_review"
    explanation: str
    source_evidence: list[dict[str, str]]  # each: {"url": "...", "title": "..."}
    confidence: float  # 0.0 - 1.0
    raw_response: dict | None = None


class LyzrClient:
    """Client for invoking a Lyzr agent with structured output.

    The agent must be pre-created in Lyzr with a system prompt that instructs it to:
    - Analyze the provided observation and source links
    - Return ONLY structured JSON matching the verification schema
    - Not invent prices, dates, or facts not in the supplied evidence
    """

    # Lyzr Enterprise API endpoints (from documentation)
    BASE_URL = "https://api.lyzr.ai"  # Adjust if docs specify a different base
    CHAT_ENDPOINT = "/v3/chat"  # Typical chat/invoke endpoint
    AGENT_ENDPOINT = "/v3/agents"  # For agent management if needed

    VERIFICATION_SCHEMA = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["verified", "no_change", "needs_review"],
                "description": "Verification outcome",
            },
            "explanation": {
                "type": "string",
                "description": "Short human-readable explanation citing the specific source evidence",
            },
            "source_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "format": "uri"},
                        "title": {"type": "string"},
                    },
                    "required": ["url", "title"],
                },
                "description": "Sources that support the conclusion; must be subset of provided sources",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence in the verification (0.0-1.0)",
            },
        },
        "required": ["status", "explanation", "source_evidence", "confidence"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key or settings.lyzr_api_key if hasattr(settings, "lyzr_api_key") else None
        self.agent_id = agent_id or settings.lyzr_agent_id if hasattr(settings, "lyzr_agent_id") else None
        self.base_url = (base_url or settings.lyzr_agent_url if hasattr(settings, "lyzr_agent_url") else None) or self.BASE_URL
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.agent_id)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Agent-ID": self.agent_id,
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _build_verification_prompt(
        self,
        watch_type: str,
        rule: dict[str, Any],
        observation: dict[str, Any],
        sources: list[dict[str, Any]],
        correlation_id: str,
    ) -> str:
        """Build the prompt for the Lyzr Verifier agent.

        The agent receives the observation and source links collected by Nazar.
        It must NOT fetch new data - only analyze what's provided.
        """
        # Format the observation for the agent
        obs_summary = self._summarize_observation(watch_type, rule, observation)

        # Format sources as a numbered list for citation
        source_list = "\n".join(
            f"{i+1}. {s.get('title', 'Untitled')} - {s.get('url', 'No URL')}"
            for i, s in enumerate(sources)
        )

        return f"""Correlation ID: {correlation_id}

You are the Nazar Verifier agent. Analyze the following watch check result and determine if it represents a genuine, verified change that warrants an alert.

WATCH TYPE: {watch_type}
WATCH RULE: {json.dumps(rule, indent=2)}

OBSERVATION SUMMARY:
{obs_summary}

FULL OBSERVATION DATA:
{json.dumps(observation, indent=2)}

AVAILABLE SOURCES (numbered for citation):
{source_list}

INSTRUCTIONS:
1. Analyze whether the observation represents a real, verified change per the watch rule.
2. ONLY use the provided sources as evidence. Do NOT fetch or invent any new data.
3. Return ONLY valid JSON matching the verification schema.
4. The source_evidence array must contain ONLY sources from the provided list above.
5. If evidence is insufficient or contradictory, return "needs_review".
6. If the observation shows no meaningful change from the rule's perspective, return "no_change".
7. If the observation clearly crosses the threshold with official/credible sources, return "verified".

OUTPUT FORMAT (JSON only, no extra text):
{{
  "status": "verified" | "no_change" | "needs_review",
  "explanation": "Brief explanation citing specific source numbers from the list above",
  "source_evidence": [
    {{"url": "...", "title": "..."}}
  ],
  "confidence": 0.0-1.0
}}"""

    def _summarize_observation(
        self, watch_type: str, rule: dict[str, Any], observation: dict[str, Any]
    ) -> str:
        """Create a human-readable summary of the observation."""
        if watch_type == "flight":
            return (
                f"Flight {rule.get('origin')} → {rule.get('destination')} on {rule.get('travel_date')}: "
                f"lowest fare {observation.get('current_price')} {rule.get('currency', 'INR')} "
                f"(target {rule.get('condition', 'below')} {rule.get('target_price')} {rule.get('currency', 'INR')})"
            )
        elif watch_type == "stock":
            symbol = rule.get("symbol")
            condition = rule.get("condition")
            if condition == "absolute_change_greater_than":
                return (
                    f"{symbol} moved {observation.get('percent_change', 0):+.2f}% "
                    f"(threshold {rule.get('threshold_percent')}% {rule.get('direction', 'either')}), "
                    f"now {observation.get('current_price')} {observation.get('currency', 'INR')}"
                )
            else:
                return (
                    f"{symbol} at {observation.get('current_price')} {observation.get('currency', 'INR')} "
                    f"(target {condition} {rule.get('target_price')} {observation.get('currency', 'INR')})"
                )
        elif watch_type == "job_notification":
            notices = observation.get("notices") or []
            return f"{len(notices)} official notice(s) found for keywords: {rule.get('keywords')}"
        elif watch_type == "topic":
            mode = rule.get("mode", "new_results")
            if mode in {"price_below", "price_above"}:
                return (
                    f"Price for '{rule.get('query')}': {observation.get('current_price')} "
                    f"{rule.get('currency', 'INR')} (target {mode.split('_')[1]} "
                    f"{rule.get('target_price')} {rule.get('currency', 'INR')})"
                )
            items = observation.get("items") or []
            return f"{len(items)} new result(s) found for '{rule.get('query')}' on {rule.get('source')}"
        return f"{watch_type} observation: {json.dumps(observation)}"

    async def verify_observation(
        self,
        watch_type: str,
        rule: dict[str, Any],
        observation: dict[str, Any],
        sources: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> LyzrVerificationResult:
        """Invoke the Lyzr Verifier agent to analyze the observation.

        Args:
            watch_type: Type of watch (flight, stock, job_notification, topic)
            rule: The watch rule configuration
            observation: Raw observation from the provider
            sources: List of source dicts with url and title
            correlation_id: Optional correlation ID for tracing

        Returns:
            LyzrVerificationResult with structured verification output
        """
        if not self.configured:
            raise RuntimeError("Lyzr client not configured (missing LYZR_API_KEY or LYZR_AGENT_ID)")

        correlation_id = correlation_id or str(uuid.uuid4())
        prompt = self._build_verification_prompt(watch_type, rule, observation, sources, correlation_id)

        client = await self._get_client()
        payload = {
            "agent_id": self.agent_id,
            "messages": [
                {"role": "system", "content": "You are the Nazar Verifier agent. Output only valid JSON matching the verification schema."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "verification_result",
                    "schema": self.VERIFICATION_SCHEMA,
                    "strict": True,
                },
            },
            "temperature": 0.1,
            "max_tokens": 1000,
        }

        try:
            logger.info("Invoking Lyzr Verifier agent for correlation_id=%s", correlation_id)
            response = await client.post(self.CHAT_ENDPOINT, json=payload)
            response.raise_for_status()
            data = response.json()

            # Parse structured output from Lyzr response
            # Lyzr typically returns content in choices[0].message.content
            content = None
            if "choices" in data and data["choices"]:
                msg = data["choices"][0].get("message", {})
                content = msg.get("content")
            elif "content" in data:
                content = data["content"]

            if not content:
                raise ValueError("Lyzr response missing content")

            # Parse the JSON content
            try:
                result_data = json.loads(content)
            except json.JSONDecodeError as exc:
                logger.error("Lyzr returned invalid JSON for correlation_id=%s: %s", correlation_id, content[:500])
                raise ValueError(f"Lyzr returned invalid JSON: {exc}") from exc

            # Validate required fields
            required = ["status", "explanation", "source_evidence", "confidence"]
            for field in required:
                if field not in result_data:
                    raise ValueError(f"Lyzr response missing required field: {field}")

            # Validate status enum
            if result_data["status"] not in ("verified", "no_change", "needs_review"):
                raise ValueError(f"Invalid status: {result_data['status']}")

            # Validate source_evidence URLs are subset of provided sources
            provided_urls = {s.get("url") for s in sources if s.get("url")}
            for evidence in result_data["source_evidence"]:
                if evidence.get("url") not in provided_urls:
                    logger.warning(
                        "Lyzr cited unknown source URL for correlation_id=%s: %s",
                        correlation_id,
                        evidence.get("url"),
                    )

            return LyzrVerificationResult(
                status=result_data["status"],
                explanation=result_data["explanation"],
                source_evidence=result_data["source_evidence"],
                confidence=float(result_data["confidence"]),
                raw_response=data,
            )

        except httpx.HTTPError as exc:
            logger.error("Lyzr API request failed for correlation_id=%s: %s", correlation_id, exc)
            raise RuntimeError(f"Lyzr API request failed: {exc}") from exc
        except Exception as exc:
            logger.exception("Lyzr verification failed for correlation_id=%s", correlation_id)
            raise


lyzr_client = LyzrClient()