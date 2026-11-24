"""Deduplication helpers: SerpApi query cache, notice keys and alert event keys."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class TTLCache:
    """Small thread-safe TTL cache used to respect provider quotas."""

    def __init__(self, ttl_seconds: int = 600, max_entries: int = 512) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> object | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at < now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: object) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._store) >= self.max_entries:
                oldest = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest, None)
            self._store[key] = (now + self.ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "ref", "source")


def normalize_url(url: str) -> str:
    """Canonical URL for deduplication (drops fragments and tracking params)."""

    if not url:
        return ""
    parsed = urlparse(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(TRACKING_PREFIXES)
    ]
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme or "https", host, path, "", urlencode(query), ""))


def notice_key(url: str, title: str = "") -> str:
    base = normalize_url(url) or title.strip().lower()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def hashable_query(engine: str, params: dict) -> str:
    filtered = {k: v for k, v in params.items() if k not in {"api_key"} and v is not None}
    return f"{engine}:{json.dumps(filtered, sort_keys=True, default=str)}"


def build_event_key(watch_id: int, kind: str, value: str) -> str:
    digest = hashlib.sha256(f"{watch_id}:{kind}:{value}".encode("utf-8")).hexdigest()[:24]
    return f"w{watch_id}:{kind}:{digest}"
