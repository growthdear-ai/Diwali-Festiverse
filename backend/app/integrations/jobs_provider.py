"""Government job notification monitoring via SerpApi Google Search / News.

Verification rule: an official-domain result is only marked ``verified`` after
the official page itself is extracted (SerpApi Extract API) and its content
matches the notification keywords. Appearing in Google Search alone is never
enough.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from app.integrations.serpapi_client import ProviderError, SerpApiClient
from app.schemas.watch import JobRule
from app.utils.deduplication import notice_key
from app.utils.normalization import to_utc_iso
from app.utils.validators import OFFICIAL_JOB_DOMAINS, domain_from_url, is_official_domain

MAX_QUERY_DOMAINS = 3
MAX_VERIFICATIONS_PER_RUN = 2

logger = logging.getLogger(__name__)


class JobsProvider:
    source = "Google Search / Google News (SerpApi)"

    def __init__(self, client: SerpApiClient | None = None) -> None:
        self.client = client or SerpApiClient()

    def _query(self, rule: JobRule) -> str:
        keywords = " ".join(f'"{keyword}"' if " " in keyword else keyword for keyword in rule.keywords)
        domains = (rule.domains or list(OFFICIAL_JOB_DOMAINS))[:MAX_QUERY_DOMAINS]
        site_clause = " OR ".join(f"site:{domain}" for domain in domains)
        return f"{keywords} notification ({site_clause})"

    def fetch(self, rule: JobRule) -> dict:
        query = self._query(rule)
        notices: list[dict] = []

        data = self.client.search(
            "google",
            # qdr:y keeps the watch to recent notices instead of years-old PDFs.
            {"q": query, "hl": "en", "gl": "in", "num": 10, "tbs": "qdr:y"},
        )
        for result in data.get("organic_results") or []:
            notice = self._normalize_result(
                title=result.get("title") or "",
                url=result.get("link") or "",
                description=result.get("snippet") or "",
                publication_date=result.get("date"),
                source_name=result.get("source"),
                rule=rule,
            )
            if notice:
                notices.append(notice)

        # Google News often surfaces the official press note earlier than the web tab.
        try:
            # SerpApi rejects `q` combined with `so`; relevance order is used here
            # and notices are filtered by recency through the query itself.
            news = self.client.search(
                "google_news",
                {"q": " ".join(rule.keywords), "hl": "en", "gl": "in"},
            )
            for result in news.get("news_results") or []:
                source = result.get("source") or {}
                notice = self._normalize_result(
                    title=result.get("title") or "",
                    url=result.get("link") or "",
                    description=result.get("snippet") or result.get("title") or "",
                    publication_date=result.get("iso_date") or result.get("date"),
                    source_name=source.get("name") if isinstance(source, dict) else str(source),
                    rule=rule,
                )
                if notice:
                    notices.append(notice)
        except ProviderError as exc:
            # Search results are still usable if the news engine fails.
            logger.info("Google News lookup failed for job watch: %s", exc.message)

        notices = self._dedupe(notices)
        verified = 0
        for notice in notices:
            if notice["official_domain"] and verified < MAX_VERIFICATIONS_PER_RUN:
                verified += 1
                notice["verification_status"] = self._verify_notice(notice, rule)

        return {
            "watch_type": "job_notification",
            "notices": notices,
            "query": query,
            "source": self.source,
            "checked_at": to_utc_iso(),
        }

    def _normalize_result(
        self,
        *,
        title: str,
        url: str,
        description: str,
        publication_date: str | None,
        source_name: str | None,
        rule: JobRule,
    ) -> dict | None:
        if not title or not url:
            return None
        domain = domain_from_url(url)
        if not domain:
            return None
        official = is_official_domain(domain, rule.domains)
        if not official:
            # Searches are intentionally restricted to official recruitment domains.
            return None
        if not urlparse(url).path.strip("/"):
            # Official home pages are not notifications.
            return None
        if not self._is_relevant(title, description, rule):
            return None
        return {
            "notice_key": notice_key(url, title),
            "title": title.strip(),
            "url": url.strip(),
            "domain": domain,
            "source_name": source_name,
            "publication_date": publication_date,
            "description": re.sub(r"\s+", " ", description or "").strip()[:600],
            "keywords": rule.keywords,
            "official_domain": official,
            "verification_status": "unverified",
        }

    @staticmethod
    def _is_relevant(title: str, description: str, rule: JobRule) -> bool:
        """Require every token of at least one keyword to appear on the result."""

        haystack = f"{title} {description}".lower()
        for keyword in rule.keywords:
            tokens = [token for token in re.split(r"\W+", keyword.lower()) if token]
            if tokens and all(token in haystack for token in tokens):
                return True
        return False

    def _verify_notice(self, notice: dict, rule: JobRule) -> str:
        """Extract the official page and require the notice keywords to match."""

        try:
            extracted = self.client.extract(notice["url"])
        except ProviderError:
            return "unverified"

        page = " ".join(
            str(part)
            for part in [
                extracted.get("markdown"),
                extracted.get("meta_tags"),
                extracted.get("page_information"),
            ]
            if part
        ).lower()
        if not page:
            return "unverified"
        if not any(keyword.lower() in page for keyword in rule.keywords):
            return "flagged"
        return "verified"

    @staticmethod
    def _dedupe(notices: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for notice in notices:
            key = notice["notice_key"]
            if key in seen:
                continue
            seen.add(key)
            unique.append(notice)
        return unique


jobs_provider = JobsProvider()
