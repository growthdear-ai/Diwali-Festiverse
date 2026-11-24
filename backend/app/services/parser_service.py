"""Natural-language parser: message -> structured watch rule.

Deterministic extraction runs first, so common English/Hinglish requests never
need an LLM. When essential fields are still missing, an OpenAI-compatible LLM
is asked to interpret the message; the LLM never supplies live prices or dates
of its own and every resulting rule is re-validated with Pydantic.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

import httpx

from app.core.config import settings
from app.schemas.watch import JobRule, parse_watch_rule
from app.utils.normalization import (
    CITY_TO_IATA,
    extract_percentage,
    extract_price,
    normalize_text,
    parse_date_expression,
    resolve_airport,
    strip_span,
    utcnow,
)
from app.utils.validators import OFFICIAL_JOB_DOMAINS

logger = logging.getLogger(__name__)

FLIGHT_WORDS = {
    "flight",
    "flights",
    "fare",
    "airfare",
    "air ticket",
    "ticket",
    "hawai",
    "hawaii",
    "udaan",
    "plane",
    "fly",
}
STOCK_WORDS = {
    "stock",
    "stocks",
    "share",
    "shares",
    "nifty",
    "sensex",
    "equity",
    "scrip",
    "ticker",
    "price",
}
JOB_WORDS = {
    "job",
    "jobs",
    "notification",
    "notifications",
    "vacancy",
    "vacancies",
    "recruitment",
    "bharti",
    "naukri",
    "sarkari",
    "exam",
    "admit card",
    "result",
    "apply",
}

STOCK_ALIASES = {
    "tata motors": "TATAMOTORS",
    "tatamotors": "TATAMOTORS",
    "itc": "ITC",
    "suzlon": "SUZLON",
    "reliance": "RELIANCE",
    "ril": "RELIANCE",
    "infosys": "INFY",
    "infy": "INFY",
    "tcs": "TCS",
    "hdfc bank": "HDFCBANK",
    "hdfc": "HDFCBANK",
    "sbi": "SBIN",
    "state bank": "SBIN",
    "adani enterprises": "ADANIENT",
    "adani": "ADANIENT",
    "airtel": "BHARTIARTL",
    "wipro": "WIPRO",
    "maruti": "MARUTI",
    "mahindra": "M&M",
    "zomato": "ZOMATO",
    "paytm": "PAYTM",
    "ongc": "ONGC",
    "ntpc": "NTPC",
    "powergrid": "POWERGRID",
    "lic": "LICI",
}

EXAM_PHRASES = {
    "ssc cgl": "SSC CGL",
    "ssc chsl": "SSC CHSL",
    "ssc gd": "SSC GD",
    "ssc mts": "SSC MTS",
    "ibps po": "IBPS PO",
    "ibps clerk": "IBPS Clerk",
    "sbi po": "SBI PO",
    "sbi clerk": "SBI Clerk",
    "rrb ntpc": "RRB NTPC",
    "rrb group d": "RRB Group D",
    "rrb alp": "RRB ALP",
    "upsc": "UPSC",
    "rrb": "RRB",
    "ssc": "SSC",
    "ibps": "IBPS",
    "railway": "Railway",
}

ORG_DOMAINS = {
    "SSC": ["ssc.gov.in", "ssc.nic.in"],
    "IBPS": ["ibps.in"],
    "SBI": ["bank.sbi", "sbi.co.in"],
    "RRB": ["rrbcdg.gov.in", "rrbapply.gov.in", "indianrailways.gov.in"],
    "Railway": ["rrbcdg.gov.in", "rrbapply.gov.in", "indianrailways.gov.in"],
    "UPSC": ["upsc.gov.in", "upsconline.nic.in"],
}

SUPPORTED_TYPES_MESSAGE = (
    "I can watch flights, stocks, or government job notifications. "
    'Try: "@Nazar Bangalore se Patna 30 Nov flight 6000 se kam ho toh batao" '
    'or "@Nazar Tata Motors 5% gir jaye toh batao" '
    'or "@Nazar SSC CGL notification aaye toh batao".'
)


def _contains_any(text: str, phrases: set[str]) -> bool:
    return any(re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) for phrase in phrases)


def _has_exam_phrase(lower: str) -> bool:
    return any(re.search(rf"\b{re.escape(phrase)}\b", lower) for phrase in EXAM_PHRASES)


def _has_company_alias(lower: str) -> bool:
    return any(re.search(rf"\b{re.escape(alias)}\b", lower) for alias in STOCK_ALIASES)


def classify(text: str) -> str | None:
    lower = text.lower()
    if _contains_any(lower, FLIGHT_WORDS):
        return "flight"
    job_hit = _has_exam_phrase(lower) or _contains_any(lower, JOB_WORDS)
    stock_word_hit = _contains_any(lower, STOCK_WORDS)
    # "Infosys jobs" is a job request even though Infosys is also a stock.
    if job_hit and not stock_word_hit:
        return "job_notification"
    if stock_word_hit or _has_company_alias(lower):
        return "stock"
    if job_hit:
        return "job_notification"
    return None


GREETINGS = {
    "hi", "hii", "hello", "hey", "namaste", "namaskar", "help", "start", "kya kar sakte ho", "what can you do",
    "ok", "okay", "thanks", "thank you", "thankyou", "shukriya", "dhanyavad", "great", "cool", "nice", "good",
}

HELP_MESSAGE = (
    "Hi! I keep an eye on things for this group: flight fares, stock moves, government job "
    "notifications, product prices, company openings, news, or anything you can search for. "
    'Try: "@Nazar Bangalore se Patna 30 Nov flight 6000 se kam ho toh batao", '
    '"@Nazar iPhone 16 60000 se kam ho toh batao" or "@Nazar Patna airport news".'
)

_PRICE_NUM = r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(k|lakh|lac)?"
PRICE_BELOW_RE = re.compile(
    rf"(?:under|below|less than|within|upto|up to|<)\s*{_PRICE_NUM}|{_PRICE_NUM}\s*(?:se kam|se neeche|se sasta|ke neeche|ke andar|or less)",
    re.IGNORECASE,
)
PRICE_ABOVE_RE = re.compile(
    rf"(?:above|over|more than|>)\s*{_PRICE_NUM}|{_PRICE_NUM}\s*(?:se zyada|se upar|ke upar|or more)",
    re.IGNORECASE,
)
NEWS_WORDS = {"news", "khabar", "update", "updates", "headlines", "announcement", "announcements"}
OPENING_WORDS = {"job", "jobs", "hiring", "opening", "openings", "vacancy", "vacancies", "internship", "careers"}
TOPIC_FILLER = {
    "batao", "bata", "batana", "dena", "do", "toh", "to", "ho", "hai", "jaye", "jab", "bhi", "aaye", "aye", "check", "for",
    "track", "karo", "kar", "rakho", "nazar", "pe", "par", "me", "mein", "ka", "ki", "ke", "ko", "se", "kam", "please",
    "pls", "watch", "alert", "notify", "mujhe", "hume", "let", "know", "tell", "when", "if", "the", "a", "an", "any",
    "about", "on", "of", "price", "cost", "rate", "rs", "inr", "and", "is", "are", "keep", "eye", "us", "kuch", "koi",
    "search", "find", "show", "list", "give", "tell", "fetch",
} | NEWS_WORDS | OPENING_WORDS


def _amount(number: str, unit: str | None) -> float:
    value = float(number.replace(",", ""))
    unit = (unit or "").lower()
    return value * (1000 if unit == "k" else 100000 if unit in {"lakh", "lac"} else 1)


def _parse_topic(text: str, *, force_source: str | None = None) -> tuple[dict, list[str]]:
    """Anything that isn't a flight, stock or government job: a price or new-results watch."""
    lower = text.lower()
    rule: dict = {"watch_type": "topic", "source": force_source or "web", "mode": "new_results", "currency": "INR"}
    remainder = text
    if not force_source:
        for regex, mode in ((PRICE_BELOW_RE, "price_below"), (PRICE_ABOVE_RE, "price_above")):
            match = regex.search(text)
            if match:
                groups = match.groups()
                number, unit = (groups[0], groups[1]) if groups[0] else (groups[2], groups[3])
                rule.update({"mode": mode, "source": "shopping", "target_price": _amount(number, unit)})
                remainder = text[: match.start()] + " " + text[match.end():]
                break
        if rule["mode"] == "new_results":
            if _contains_any(lower, NEWS_WORDS):
                rule["source"] = "news"
            elif _contains_any(lower, OPENING_WORDS):
                rule["source"] = "jobs"
    words = re.findall(r"[\w&+.#-]+", re.sub(r"@nazar\b", " ", remainder, flags=re.IGNORECASE))
    query = " ".join(w for w in words if w.lower() not in TOPIC_FILLER and not re.fullmatch(r"\d+%", w))
    if rule["source"] == "jobs" and query:
        query = f"{query} jobs"
    rule["query"] = query.strip()
    # Needs at least one real word, so "@Nazar 1%" doesn't become a watch.
    missing = [] if re.search(r"[^\W\d_]{3,}", rule["query"]) else ["query"]
    return rule, missing


def _is_greeting(text: str) -> bool:
    cleaned = re.sub(r"@nazar\b", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or cleaned in GREETINGS:
        return True
    # "hello, kya haal hai?" is small talk, not something to watch.
    first, *rest = cleaned.split()
    return first in GREETINGS and all(word in SMALL_TALK for word in rest)


SMALL_TALK = {
    "kya", "haal", "hai", "kaise", "ho", "how", "are", "you", "there", "bhai", "ji", "sab", "theek", "accha",
    "nazar", "doing", "whats", "what", "up", "sup", "dost", "buddy", "again",
}


def _extract_route(text: str) -> tuple[str | None, str | None]:
    words = re.findall(r"[A-Za-z]+", text.lower())
    origin: str | None = None
    destination: str | None = None

    if "from" in words:
        index = words.index("from")
        for size in (2, 1):
            candidate = " ".join(words[index + 1 : index + 1 + size])
            if candidate in CITY_TO_IATA:
                origin = candidate
                break
        if "to" in words[index:]:
            to_index = words.index("to", index)
            for size in (2, 1):
                candidate = " ".join(words[to_index + 1 : to_index + 1 + size])
                if candidate in CITY_TO_IATA:
                    destination = candidate
                    break
        if origin and destination:
            return origin, destination

    for index, word in enumerate(words):
        if word not in {"se", "to"}:
            continue
        if word in {"se", "to"}:
            for size in (2, 1):
                candidate = " ".join(words[max(0, index - size) : index])
                if candidate in CITY_TO_IATA:
                    origin = candidate
                    break
        for size in (2, 1):
            candidate = " ".join(words[index + 1 : index + 1 + size])
            if candidate in CITY_TO_IATA:
                destination = candidate
                break
        if origin and destination:
            break

    return origin, destination


def _parse_flight(text: str, today: date) -> tuple[dict, list[str]]:
    remaining = text
    travel_date, date_span = parse_date_expression(remaining, today)
    remaining = strip_span(remaining, date_span)
    price, price_span = extract_price(remaining)
    remaining = strip_span(remaining, price_span)

    lower = text.lower()
    condition = "below"
    if re.search(r"\b(zyada|above|over|more than|mehnga|mehngi|expensive|greater)\b", lower):
        condition = "above"
    if re.search(r"\b(kam|below|under|less than|sasta|sasti|cheap|drop|gir)\b", lower):
        condition = "below"

    origin_name, destination_name = _extract_route(remaining)
    origin = resolve_airport(origin_name)
    destination = resolve_airport(destination_name)

    currency = "INR"
    if re.search(r"(\$|usd|dollar)", lower):
        currency = "USD"
    elif re.search(r"(€|eur|euro)", lower):
        currency = "EUR"

    travel_class = None
    if re.search(r"\b(business class|business)\b", lower):
        travel_class = "business"
    elif re.search(r"\b(first class|first)\b", lower):
        travel_class = "first"
    elif re.search(r"\b(premium economy)\b", lower):
        travel_class = "premium_economy"
    elif re.search(r"\b(economy)\b", lower):
        travel_class = "economy"

    passengers = 1
    passenger_match = re.search(r"\b(\d{1,2})\s*(?:log|passengers?|people|adults?|bandar)\b", lower)
    if passenger_match:
        passengers = max(1, min(9, int(passenger_match.group(1))))

    rule: dict = {
        "watch_type": "flight",
        "condition": condition,
        "currency": currency,
        "passengers": passengers,
    }
    if origin:
        rule["origin"] = origin
    if destination:
        rule["destination"] = destination
    if travel_date:
        rule["travel_date"] = travel_date.isoformat()
    if price:
        rule["target_price"] = price
    if travel_class:
        rule["travel_class"] = travel_class

    missing: list[str] = []
    if not origin:
        missing.append("origin")
    if not destination:
        missing.append("destination")
    if not travel_date:
        missing.append("travel_date")
    if not price:
        missing.append("target_price")
    return rule, missing


def _parse_stock(text: str) -> tuple[dict, list[str]]:
    lower = text.lower()
    symbol: str | None = None
    exchange: str | None = None

    for alias in sorted(STOCK_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            symbol = STOCK_ALIASES[alias]
            break

    explicit = re.search(r"\b(NSE|BSE)[:\s]([A-Za-z0-9&.\-]{1,32})\b", text, re.IGNORECASE)
    if explicit:
        exchange = explicit.group(1).upper()
        symbol = explicit.group(2).upper()
    elif re.search(r"\bNSE\b", text):
        exchange = "NSE"
    elif re.search(r"\bBSE\b", text):
        exchange = "BSE"

    if not symbol:
        cashtag = re.search(r"\$([A-Za-z][A-Za-z0-9&.\-]{1,20})\b", text)
        if cashtag:
            symbol = cashtag.group(1).upper()

    percentage, _ = extract_percentage(text)
    price, _ = extract_price(text)

    direction = "either"
    if re.search(r"\b(up|badh|badhe|badh jaye|rise|rises|gain|increase|zyada)\b", lower):
        direction = "up"
    if re.search(r"\b(down|gir|gire|gir jaye|fall|falls|drop|decrease|kam)\b", lower):
        direction = "down"

    if percentage:
        condition = "absolute_change_greater_than"
        target_price = None
    elif price and re.search(r"\b(above|zyada|over|more than)\b", lower):
        condition = "price_above"
        target_price = price
    elif price:
        condition = "price_below"
        target_price = price
    else:
        condition = "absolute_change_greater_than"
        target_price = None

    rule: dict = {
        "watch_type": "stock",
        "condition": condition,
        "direction": direction,
    }
    if symbol:
        rule["symbol"] = symbol
    if exchange:
        rule["exchange"] = exchange
    if percentage:
        rule["threshold_percent"] = percentage
    if target_price:
        rule["target_price"] = target_price

    missing: list[str] = []
    if not symbol:
        missing.append("symbol")
    if condition == "absolute_change_greater_than" and not percentage:
        missing.append("threshold_percent")
    if condition in {"price_below", "price_above"} and not target_price:
        missing.append("target_price")
    return rule, missing


def _parse_job(text: str) -> tuple[dict, list[str]]:
    lower = text.lower()
    keywords: list[str] = []
    organization: str | None = None

    for phrase in sorted(EXAM_PHRASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", lower):
            canonical = EXAM_PHRASES[phrase]
            if canonical not in keywords:
                keywords.append(canonical)
            if not organization:
                organization = canonical.split()[0]
            if organization == "Railway":
                organization = "RRB"

    if not keywords:
        for word in ("notification", "vacancy", "recruitment", "bharti", "naukri", "job"):
            if re.search(rf"\b{word}\b", lower):
                keywords.append(word)
                break
        if not keywords:
            org_match = re.search(r"\b(SSC|IBPS|RRB|UPSC|SBI|RBI|ISRO|DRDO)\b", text)
            if org_match:
                keywords.append(org_match.group(1))
                organization = org_match.group(1)

    domains = list(OFFICIAL_JOB_DOMAINS)
    if organization and organization in ORG_DOMAINS:
        domains = ORG_DOMAINS[organization]

    rule: dict = {
        "watch_type": "job_notification",
        "keywords": keywords,
        "domains": domains,
    }
    if organization:
        rule["organization"] = organization

    missing = [] if keywords else ["keywords"]
    return rule, missing


def _missing_fields(watch_type: str, rule: dict) -> list[str]:
    if watch_type == "flight":
        missing = []
        for field in ("origin", "destination", "travel_date", "target_price"):
            if not rule.get(field):
                missing.append(field)
        return missing
    if watch_type == "stock":
        missing = []
        if not rule.get("symbol"):
            missing.append("symbol")
        if rule.get("condition") == "absolute_change_greater_than" and not rule.get("threshold_percent"):
            missing.append("threshold_percent")
        if rule.get("condition") in {"price_below", "price_above"} and not rule.get("target_price"):
            missing.append("target_price")
        return missing
    if watch_type == "job_notification":
        return [] if rule.get("keywords") else ["keywords"]
    if watch_type == "topic":
        return [] if rule.get("query") else ["query"]
    return ["watch_type"]


FOLLOW_UPS = {
    "origin": "Which city are you flying from?",
    "destination": "Which city are you flying to?",
    "travel_date": "Which travel date should I watch (for example 30 Nov)?",
    "target_price": "What is your target fare (for example 6000)?",
    "symbol": "Which stock or ticker should I watch (for example Tata Motors)?",
    "threshold_percent": "At what percentage move should I alert the group (for example 5%)?",
    "target_price_stock": "At what price should I alert the group?",
    "keywords": "Which exam or job notification should I track (for example SSC CGL)?",
    "watch_type": "Should I watch a flight, a stock, or a government job notification?",
    "query": "What should I keep an eye on? For example: iPhone 16 under 60000, Infosys SDE jobs, or Patna airport news.",
}


def _follow_up(missing: list[str], watch_type: str | None) -> str:
    questions = []
    for field in missing:
        key = field
        if field == "target_price" and watch_type == "stock":
            key = "target_price_stock"
        question = FOLLOW_UPS.get(key)
        if question and question not in questions:
            questions.append(question)
    if not questions:
        questions.append(SUPPORTED_TYPES_MESSAGE)
    return "To set up this watch I still need: " + " ".join(questions)


def heuristic_parse(text: str, today: date | None = None) -> dict:
    today = today or utcnow().date()
    normalized = re.sub(r"@nazar\b", " ", text, flags=re.IGNORECASE)
    normalized = normalize_text(normalized)
    watch_type = classify(normalized)

    origin, destination = _extract_route(normalized)
    if watch_type is None and origin and destination:
        # Two known cities without the word "flight": leave it to the LLM / follow-up, not a web search.
        return {
            "understood": False,
            "watch_type": None,
            "rule": None,
            "missing_fields": ["watch_type"],
            "follow_up_question": SUPPORTED_TYPES_MESSAGE,
            "parser": "heuristic",
        }

    if watch_type is None:
        # Not a flight, stock or government job: watch it as a general topic.
        rule, missing = _parse_topic(normalized)
        return {
            "understood": not missing,
            "watch_type": "topic",
            "rule": rule,
            "missing_fields": missing,
            "follow_up_question": None if not missing else _follow_up(missing, "topic"),
            "parser": "heuristic",
        }

    lower = normalized.lower()
    if (
        watch_type == "job_notification"
        and not _has_exam_phrase(lower)
        and not re.search(r"\b(ssc|ibps|rrb|upsc|sbi|rbi|isro|drdo|sarkari|government|govt)\b", lower)
        and _has_company_alias(lower)
    ):
        # A private company's openings: search Google Jobs instead of government sites.
        rule, missing = _parse_topic(normalized, force_source="jobs")
        return {
            "understood": not missing,
            "watch_type": "topic",
            "rule": rule,
            "missing_fields": missing,
            "follow_up_question": None if not missing else _follow_up(missing, "topic"),
            "parser": "heuristic",
        }

    if watch_type == "flight":
        rule, missing = _parse_flight(normalized, today)
    elif watch_type == "stock":
        rule, missing = _parse_stock(normalized)
    else:
        rule, missing = _parse_job(normalized)

    return {
        "understood": not missing,
        "watch_type": watch_type,
        "rule": rule,
        "missing_fields": missing,
        "follow_up_question": None if not missing else _follow_up(missing, watch_type),
        "parser": "heuristic",
    }


def _extract_json_object(content: str) -> dict:
    """Parse JSON even when an LLM wraps it in markdown fences or prose."""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass

    start = text.find("{")
    if start >= 0:
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : index + 1])
                        if isinstance(parsed, dict):
                            return parsed
                    except ValueError:
                        break
    raise ValueError("LLM response did not contain a JSON object")


def _llm_chat(messages: list[dict[str, str]]) -> str:
    """Call Ollama natively or any OpenAI-compatible chat endpoint."""

    provider = settings.resolved_llm_provider
    base_url = settings.effective_llm_base_url
    model = settings.effective_llm_model
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    if provider == "ollama" and not base_url.endswith("/v1"):
        response = httpx.post(
            f"{base_url}/api/chat",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
    else:
        payload = {"model": model, "temperature": 0, "messages": messages}
        if provider == "openai":
            payload["response_format"] = {"type": "json_object"}
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM returned an empty response")
    return content


def _number_mentioned(value: float, text: str) -> bool:
    normalized = normalize_text(text).replace(",", "")
    token = f"{value:g}"
    return bool(re.search(rf"(?<!\d){re.escape(token)}(?!\d)", normalized))


def _airport_mentioned(code: str, text: str) -> bool:
    lower = normalize_text(text).lower()
    if re.search(rf"\b{re.escape(code.lower())}\b", lower):
        return True
    return any(
        mapped == code and re.search(rf"\b{re.escape(alias)}\b", lower)
        for alias, mapped in CITY_TO_IATA.items()
    )


def _merge_llm_rule(
    llm_rule: dict,
    heuristic_rule: dict,
    watch_type: str,
    text: str,
    today: date,
) -> dict:
    """Keep deterministic extractions authoritative over LLM output.

    The LLM may only fill fields the deterministic parser could not extract, and
    every such value must be evidenced by the user's message.
    """

    merged = dict(llm_rule)
    merged["watch_type"] = watch_type

    anchored_fields = (
        "origin",
        "destination",
        "travel_date",
        "return_date",
        "target_price",
        "currency",
        "travel_class",
        "passengers",
        "symbol",
        "exchange",
        "threshold_percent",
        "keywords",
        "domains",
        "organization",
    )
    for field in anchored_fields:
        value = heuristic_rule.get(field)
        if value not in (None, "", [], {}):
            merged[field] = value

    if not heuristic_rule.get("travel_date") and merged.get("travel_date"):
        parsed_date, _span = parse_date_expression(text, today)
        if not parsed_date or parsed_date.isoformat() != merged["travel_date"]:
            merged.pop("travel_date", None)

    for field in ("origin", "destination"):
        code = merged.get(field)
        if code and not heuristic_rule.get(field) and not _airport_mentioned(code, text):
            merged.pop(field, None)

    for field in ("target_price", "threshold_percent"):
        value = merged.get(field)
        if value is not None and not heuristic_rule.get(field):
            try:
                mentioned = _number_mentioned(float(value), text)
            except (TypeError, ValueError):
                mentioned = False
            if not mentioned:
                merged.pop(field, None)

    if merged.get("symbol") and not heuristic_rule.get("symbol"):
        lower = text.lower()
        symbol = str(merged["symbol"]).lower()
        alias_match = any(
            mapped == str(merged["symbol"]).upper() and re.search(rf"\b{re.escape(alias)}\b", lower)
            for alias, mapped in STOCK_ALIASES.items()
        )
        if symbol not in lower and not alias_match:
            merged.pop("symbol", None)

    if merged.get("keywords") and not heuristic_rule.get("keywords"):
        lower = text.lower()
        if not any(
            all(token in lower for token in re.split(r"\W+", str(keyword).lower()) if token)
            for keyword in merged["keywords"]
        ):
            merged.pop("keywords", None)

    return merged


def _llm_parse(text: str, today: date, heuristic: dict) -> dict | None:
    """Ask an LLM to interpret an ambiguous message. Never invents live data."""

    if not settings.llm_configured:
        return None

    system_prompt = f"""You convert family group-chat messages into structured monitoring rules for Nazar Rakho.
Today is {today.isoformat()} (UTC).

Supported watch types and rule fields:
- flight: watch_type, origin (IATA 3-letter), destination (IATA 3-letter), travel_date (YYYY-MM-DD),
  return_date (optional), condition ("below"|"above"), target_price (number), currency (ISO),
  travel_class (optional), passengers (optional)
- stock: watch_type, symbol (uppercase), exchange ("NSE"|"BSE", optional),
  condition ("absolute_change_greater_than"|"price_below"|"price_above"),
  threshold_percent (number, optional), target_price (number, optional),
  direction ("up"|"down"|"either")
- job_notification: watch_type, keywords (array of exam/notification names),
  organization (optional), domains (array of official domains)

Rules:
- Understand English, Hindi and Hinglish.
- Extract only values the user actually stated. NEVER invent prices, stock values, dates or notification dates.
- Resolve relative dates against today; a day/month that has passed means next year.
- If essential information is missing, list it in missing_fields and ask a short follow-up.
- Return JSON only, shaped as:
{{"watch_type": "...", "rule": {{...}}, "missing_fields": ["..."], "follow_up_question": "..."}}"""

    try:
        content = _llm_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ]
        )
        parsed = _extract_json_object(content)
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning(
            "LLM parser failed (%s/%s), using heuristic result: %s",
            settings.resolved_llm_provider,
            settings.effective_llm_model,
            exc,
        )
        return None

    watch_type = parsed.get("watch_type")
    rule = parsed.get("rule")
    if watch_type not in {"flight", "stock", "job_notification"} or not isinstance(rule, dict):
        return None

    rule = _merge_llm_rule(
        rule,
        heuristic.get("rule") or {},
        watch_type,
        text,
        today,
    )
    missing = _missing_fields(watch_type, rule)

    if not missing:
        try:
            validated = parse_watch_rule(rule)
        except ValueError as exc:
            logger.info("LLM rule rejected by validation: %s", exc)
            return None
        rule = validated.model_dump(mode="json")

    follow_up = parsed.get("follow_up_question")
    if missing and isinstance(follow_up, str) and follow_up.strip():
        question = follow_up.strip()
    else:
        question = None if not missing else _follow_up(missing, watch_type)

    return {
        "understood": not missing,
        "watch_type": watch_type,
        "rule": rule,
        "missing_fields": missing,
        "follow_up_question": question,
        "parser": "llm",
    }


def parse_message(text: str, today: date | None = None) -> dict:
    """Parse a message, preferring deterministic extraction and validating rules."""

    today = today or utcnow().date()
    if _is_greeting(text):
        return {
            "understood": False,
            "unsupported": True,
            "watch_type": None,
            "rule": None,
            "missing_fields": [],
            "follow_up_question": HELP_MESSAGE,
            "parser": "heuristic",
        }

    result = heuristic_parse(text, today)
    if result.get("unsupported"):
        return result  # a definite answer; asking the LLM would only guess

    if result["understood"]:
        try:
            validated = parse_watch_rule(result["rule"])
            result["rule"] = validated.model_dump(mode="json")
            return result
        except ValueError:
            # Heuristic produced an invalid rule (e.g. past date); let the LLM try.
            logger.info("Heuristic rule failed validation, trying LLM")

    llm_result = _llm_parse(text, today, result)
    return llm_result or result


def _search_query_anchors(text: str) -> list[str]:
    cleaned = re.sub(r"@nazar\b", " ", text, flags=re.IGNORECASE)
    anchors = [
        token
        for token in re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", cleaned)
        if token.lower() not in {"inr", "usd", "eur", "gbp", "nazar"}
    ]
    anchors.extend(re.findall(r"\b\d+(?:st|nd|rd|th)\b", cleaned, flags=re.IGNORECASE))
    anchors.extend(re.findall(r"\b(?:19|20)\d{2}\b", cleaned))
    if re.search(r"\b(?:sem|semester)\b", cleaned, re.IGNORECASE):
        anchors.append("semester")
    return list(dict.fromkeys(anchors))


def _preserve_search_anchors(query: str, text: str) -> str:
    for anchor in _search_query_anchors(text):
        if re.search(rf"\b{re.escape(anchor)}\b", query, re.IGNORECASE):
            continue
        query = f"{query[: max(0, 199 - len(anchor))].rstrip()} {anchor}"
    return query


def refine_search_request(text: str, parsed: dict) -> dict[str, str]:
    """Turn a request into a focused web query and a useful refinement question."""

    rule = parsed.get("rule") or {}
    query = rule.get("query") if isinstance(rule, dict) else None
    query = query if isinstance(query, str) and query.strip() else re.sub(
        r"@nazar\b", " ", text, flags=re.IGNORECASE
    ).strip()

    price = rule.get("target_price") if isinstance(rule, dict) else None
    mode = rule.get("mode") if isinstance(rule, dict) else None
    currency = rule.get("currency", "INR") if isinstance(rule, dict) else "INR"
    constraint = None
    if price is not None and mode in {"price_below", "price_above"}:
        direction = "under" if mode == "price_below" else "over"
        constraint = f"{direction} {price:g} {currency}"
        if not re.search(rf"(?<!\d){re.escape(f'{price:g}')}(?!\d)", query):
            query = f"{query} {constraint}"

    source = rule.get("source") if isinstance(rule, dict) else None
    if source == "shopping":
        default_question = "Would you prefer a specific brand, operating system, or storage size?"
    elif source == "jobs":
        default_question = "Would you like to narrow these by role, location, or experience level?"
    else:
        default_question = "Would you like me to narrow these results by location, date, or another preference?"

    fallback = {
        "query": _preserve_search_anchors(query[:200], text),
        "follow_up_question": default_question,
    }
    if not settings.llm_configured:
        return fallback

    system_prompt = """You refine a user's web-search request.
Return JSON only with string fields "query" and "follow_up_question".
Keep all user-stated names, locations, dates, and budget limits in the query.
Do not add facts or answer the request. Ask one short, relevant question that could narrow the results."""
    try:
        content = _llm_chat(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({"request": text, "parsed_rule": rule, "query": query}),
                },
            ]
        )
        refined = _extract_json_object(content)
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning(
            "LLM search refinement failed (%s/%s), using the original query: %s",
            settings.resolved_llm_provider,
            settings.effective_llm_model,
            exc,
        )
        return fallback

    refined_query = refined.get("query")
    follow_up = refined.get("follow_up_question")
    if not isinstance(refined_query, str) or not refined_query.strip():
        return fallback
    refined_query = refined_query.strip()[:200]
    if constraint and not re.search(rf"(?<!\d){re.escape(f'{price:g}')}(?!\d)", refined_query):
        refined_query = f"{refined_query} {constraint}"[:200]
    refined_query = _preserve_search_anchors(refined_query, text)
    if not isinstance(follow_up, str) or not follow_up.strip():
        follow_up = default_question
    return {"query": refined_query, "follow_up_question": follow_up.strip()[:300]}
