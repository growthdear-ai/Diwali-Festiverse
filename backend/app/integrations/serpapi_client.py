"""Centralized SerpApi client shared by all live-data providers.

Docs: https://serpapi.com/search-api
"""

from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.utils.deduplication import TTLCache, hashable_query


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, provider: str = "provider") -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.provider = provider


class ProviderNotConfigured(ProviderError):
    def __init__(self, message: str, *, provider: str = "provider") -> None:
        super().__init__(message, retryable=False, provider=provider)


class SerpApiClient:
    BASE_URL = "https://serpapi.com/search"
    MAX_ATTEMPTS = 3

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        self.api_key = settings.serpapi_api_key if api_key is None else api_key
        self.timeout = timeout or settings.serpapi_timeout_seconds
        self._cache = TTLCache(ttl_seconds=cache_ttl or settings.serpapi_cache_ttl_seconds)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, engine: str, params: dict | None = None, *, use_cache: bool = True) -> dict:
        if not self.api_key:
            raise ProviderNotConfigured(
                "SERPAPI_API_KEY is not configured; live monitoring is unavailable",
                provider="serpapi",
            )

        query = {**(params or {}), "engine": engine, "output": "json"}
        cache_key = hashable_query(engine, query)
        if use_cache:
            cached = self._cache.get(cache_key)
            if isinstance(cached, dict):
                return cached

        last_error: ProviderError | None = None
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                response = httpx.get(
                    self.BASE_URL,
                    params={**query, "api_key": self.api_key},
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                last_error = ProviderError(
                    f"SerpApi request failed: {exc}", retryable=True, provider="serpapi"
                )
                time.sleep(2**attempt)
                continue

            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = ProviderError(
                    f"SerpApi temporary failure (HTTP {response.status_code})",
                    retryable=True,
                    provider="serpapi",
                )
                time.sleep(2**attempt)
                continue

            if response.status_code >= 400:
                raise ProviderError(
                    f"SerpApi HTTP {response.status_code}: {response.text[:200]}",
                    retryable=False,
                    provider="serpapi",
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise ProviderError(
                    "SerpApi returned a non-JSON response", retryable=False, provider="serpapi"
                ) from exc

            if isinstance(data, dict) and data.get("error"):
                message = str(data["error"])
                raise ProviderError(
                    f"SerpApi error: {message}",
                    retryable="rate" in message.lower() or "limit" in message.lower(),
                    provider="serpapi",
                )

            if use_cache:
                self._cache.set(cache_key, data)
            return data

        raise last_error or ProviderError(
            "SerpApi request failed after retries", retryable=True, provider="serpapi"
        )

    def extract(self, url: str) -> dict:
        """SerpApi Extract API, used to inspect an official notice page.

        Documented endpoint: https://serpapi.com/search?engine=extract&url=...
        """

        return self.search("extract", {"url": url}, use_cache=True)
