"""Validation helpers for job domains, URLs and watch intervals."""

from __future__ import annotations

from urllib.parse import urlparse

# Verified Indian government recruitment / exam portals used for job watches.
OFFICIAL_JOB_DOMAINS: tuple[str, ...] = (
    "ssc.gov.in",
    "ssc.nic.in",
    "ibps.in",
    "rrbcdg.gov.in",
    "rrbapply.gov.in",
    "indianrailways.gov.in",
    "upsc.gov.in",
    "upsconline.nic.in",
    "bank.sbi",
    "sbi.co.in",
    "rbi.org.in",
    "opportunities.rbi.org.in",
    "isro.gov.in",
    "drdo.gov.in",
    "aiims.edu",
    "nta.ac.in",
    "ntaexam.nic.in",
)

MIN_CHECK_INTERVAL_MINUTES = 15
MAX_CHECK_INTERVAL_MINUTES = 24 * 60


def domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def is_official_domain(url_or_domain: str, allowed: list[str] | tuple[str, ...] | None = None) -> bool:
    """True when the host equals or is a subdomain of an allowed official domain."""

    host = url_or_domain.lower().removeprefix("www.")
    if "://" in host:
        host = domain_from_url(host)
    domains = list(allowed) if allowed else list(OFFICIAL_JOB_DOMAINS)
    for domain in domains:
        normalized = domain.lower().removeprefix("www.").strip()
        if host == normalized or host.endswith(f".{normalized}"):
            return True
    return False


def is_https_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def clamp_interval(minutes: int) -> int:
    return max(MIN_CHECK_INTERVAL_MINUTES, min(MAX_CHECK_INTERVAL_MINUTES, minutes))
