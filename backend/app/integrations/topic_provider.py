"""General-purpose watches through SerpApi.

- shopping: Google Shopping lowest price (price_below / price_above), like a flight fare.
- news / jobs / web: Google News, Google Jobs or Google Search results; new items are alerted.
"""

from __future__ import annotations

import re

from app.integrations.serpapi_client import ProviderError, SerpApiClient
from app.schemas.watch import TopicRule
from app.utils.deduplication import notice_key
from app.utils.normalization import to_utc_iso
from app.utils.validators import domain_from_url

MAX_ITEMS = 10

ENGINES = {
    "shopping": ("google_shopping", "Google Shopping (SerpApi)"),
    "news": ("google_news", "Google News (SerpApi)"),
    "jobs": ("google_jobs", "Google Jobs (SerpApi)"),
    "web": ("google", "Google Search (SerpApi)"),
}


def _item(title: str | None, url: str | None, source: str | None = None, date: str | None = None, price: float | None = None) -> dict | None:
    if not title or not url or not url.startswith(("http://", "https://")):
        return None
    return {
        "key": notice_key(url, title),
        "title": title.strip()[:200],
        "url": url.strip(),
        "source": source or domain_from_url(url),
        "date": date,
        "price": price,
    }


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _matches(query: str, title: str) -> bool:
    """Every query word appears in the title (spaces ignored, so "I phone 16" matches "iPhone 16")."""
    squashed = "".join(_tokens(title))
    return all(token in squashed for token in _tokens(query))


def _drop_price_outliers(items: list[dict]) -> list[dict]:
    """Drop listings priced far below the typical one (covers, accessories, scams)."""
    prices = sorted(i["price"] for i in items)
    if len(prices) < 3:
        return items
    median = prices[len(prices) // 2]
    return [i for i in items if i["price"] >= 0.5 * median]


class TopicProvider:
    def __init__(self, client: SerpApiClient | None = None) -> None:
        self.client = client or SerpApiClient()

    def _search(self, engine: str, query: str, extra: dict | None = None) -> dict:
        try:
            return self.client.search(engine, {"q": query, "hl": "en", "gl": "in", **(extra or {})})
        except ProviderError as exc:
            # SerpApi reports an empty result set as an error; for a watch that just means "nothing yet".
            if "hasn't returned any results" in exc.message:
                return {}
            raise

    def fetch(self, rule: TopicRule) -> dict:
        engine, source_name = ENGINES[rule.source]
        query = rule.query
        if rule.source == "jobs":
            query = re.sub(r"\bjobs?\b", " ", query, flags=re.IGNORECASE).strip() or rule.query
        data = self._search(engine, query, {"num": 10, "tbs": "qdr:w"} if rule.source == "web" else None)
        if rule.source == "jobs" and not data.get("jobs_results"):
            # Google Jobs is thin for niche roles; fall back to recent web results for openings.
            data = self._search("google", f"{query} jobs openings", {"num": 10, "tbs": "qdr:w"})
            source_name = "Google Search (SerpApi)"

        items: list[dict] = []
        if rule.source == "shopping":
            for r in data.get("shopping_results") or []:
                price = r.get("extracted_price")
                item = _item(r.get("title"), r.get("product_link") or r.get("link"), r.get("source"), price=float(price) if isinstance(price, (int, float)) else None)
                if item and item["price"] and _matches(rule.query, item["title"]):
                    items.append(item)
            items = _drop_price_outliers(items)
            items.sort(key=lambda i: i["price"])
        elif rule.source == "news":
            for r in data.get("news_results") or []:
                src = r.get("source")
                items.append(_item(r.get("title"), r.get("link"), src.get("name") if isinstance(src, dict) else src, r.get("iso_date") or r.get("date")))
        elif rule.source == "jobs":
            for r in data.get("jobs_results") or []:
                apply = (r.get("apply_options") or [{}])[0]
                title = " · ".join(x for x in (r.get("title"), r.get("company_name"), r.get("location")) if x)
                items.append(_item(title, apply.get("link") or r.get("share_link"), r.get("via") or r.get("company_name"), (r.get("detected_extensions") or {}).get("posted_at")))
        items = [i for i in items if i]
        if rule.source != "shopping" and not items:
            for r in data.get("organic_results") or []:
                items.append(_item(r.get("title"), r.get("link"), r.get("source"), r.get("date")))

        items = [i for i in items if i][:MAX_ITEMS]
        return {
            "watch_type": "topic",
            "query": rule.query,
            "source": rule.source,
            "current_price": items[0]["price"] if rule.source == "shopping" and items else None,
            "currency": rule.currency,
            "items": items,
            "provider": source_name,
            "checked_at": to_utc_iso(),
        }


topic_provider = TopicProvider()
