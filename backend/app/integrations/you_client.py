"""You.com Research API and Finance Research API.

Docs:
- https://you.com/docs/api-reference/research/v1-research
- https://you.com/docs/guides/finance-research

SerpApi supplies the live numbers. You.com is only called after a threshold is
crossed or a new notice is found, and its output is treated as explanation, not
as a price/notice source.
"""

from __future__ import annotations

import httpx

from app.core.config import settings


class YouClient:
    RESEARCH_URL = "https://api.you.com/v1/research"
    FINANCE_URL = "https://api.you.com/v1/finance_research"
    MAX_EXPLANATION_CHARS = 4000

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = settings.you_api_key if api_key is None else api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, url: str, payload: dict, timeout: int) -> dict:
        if not self.api_key:
            return {
                "available": False,
                "content": None,
                "sources": [],
                "error": "YOU_API_KEY is not configured",
            }
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            return {
                "available": False,
                "content": None,
                "sources": [],
                "error": f"You.com request failed: {exc}",
            }

        if response.status_code >= 400:
            return {
                "available": False,
                "content": None,
                "sources": [],
                "error": f"You.com HTTP {response.status_code}: {response.text[:200]}",
            }

        try:
            data = response.json()
        except ValueError:
            return {
                "available": False,
                "content": None,
                "sources": [],
                "error": "You.com returned non-JSON content",
            }

        output = data.get("output") if isinstance(data.get("output"), dict) else data
        content = output.get("content")
        if isinstance(content, dict):
            content = str(content)
        if isinstance(content, str):
            content = content.strip()[: self.MAX_EXPLANATION_CHARS] or None

        sources: list[dict] = []
        seen: set[str] = set()
        for source in output.get("sources") or []:
            if not isinstance(source, dict):
                continue
            url_value = source.get("url")
            if not url_value or url_value in seen:
                continue
            seen.add(url_value)
            sources.append({"url": url_value, "title": source.get("title") or url_value})

        return {
            "available": content is not None,
            "content": content,
            "sources": sources,
            "error": None if content else "You.com returned no explanation",
        }

    def research(
        self,
        question: str,
        *,
        effort: str = "lite",
        include_domains: list[str] | None = None,
    ) -> dict:
        payload: dict = {"input": question, "research_effort": effort}
        if include_domains:
            payload["source_control"] = {"include_domains": include_domains}
        return self._request(self.RESEARCH_URL, payload, settings.you_research_timeout_seconds)

    def finance_research(self, question: str, *, effort: str = "deep") -> dict:
        payload = {"input": question, "research_effort": effort}
        return self._request(self.FINANCE_URL, payload, settings.you_finance_timeout_seconds)


you_client = YouClient()
