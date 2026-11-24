"""Normalization helpers shared by the parser and provider adapters."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))

# City / alias -> IATA airport code. Google Flights requires airport codes (city
# aggregations such as LON/PAR are not accepted).
CITY_TO_IATA = {
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "blr": "BLR",
    "patna": "PAT",
    "pat": "PAT",
    "delhi": "DEL",
    "new delhi": "DEL",
    "ncr": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "pune": "PNQ",
    "chennai": "MAA",
    "madras": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "hyderabad": "HYD",
    "ahmedabad": "AMD",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "varanasi": "VNS",
    "banaras": "VNS",
    "goa": "GOI",
    "kochi": "COC",
    "cochin": "COC",
    "trivandrum": "TRV",
    "guwahati": "GAU",
    "bhopal": "BHO",
    "indore": "IDR",
    "nagpur": "NAG",
    "surat": "STV",
    "chandigarh": "IXC",
    "srinagar": "SXR",
    "ranchi": "IXR",
    "raipur": "RPR",
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "singapore": "SIN",
    "bangkok": "BKK",
    "doha": "DOH",
    "kathmandu": "KTM",
    "colombo": "CMB",
    "london": "LHR",
    "new york": "JFK",
    "san francisco": "SFO",
    "toronto": "YYZ",
    "sydney": "SYD",
}

IATA_TO_CITY = {code: name.title() for name, code in reversed(list(CITY_TO_IATA.items()))}


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores naive datetimes; compare consistently)."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_iso(value: datetime | None = None) -> str:
    moment = value or utcnow()
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.replace(microsecond=0).isoformat() + "Z"


def day_start(value: datetime | None = None) -> datetime:
    moment = value or utcnow()
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(DEVANAGARI_DIGITS)).strip()


def parse_number(raw: str) -> float | None:
    cleaned = raw.replace(",", "").replace("₹", "").replace("$", "").strip()
    multiplier = 1.0
    if cleaned.lower().endswith("k"):
        cleaned = cleaned[:-1]
        multiplier = 1000.0
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def extract_price(text: str) -> tuple[float | None, str | None]:
    """Return the first currency-annotated price and the matched text."""

    normalized = normalize_text(text)
    match = re.search(
        r"(?:₹|rs\.?|inr|\$|usd)\s*([0-9][0-9,]*(?:\.\d+)?)\s*(k)?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        value = parse_number(match.group(1) + ("k" if match.group(2) else ""))
        return value, match.group(0)
    match = re.search(
        r"\b([0-9][0-9,]{2,}(?:\.\d+)?)\s*(k)?\s*(?:se\s+kam|kam|se\s+zyada|under|below|less than|above|over)\b",
        normalized,
        re.IGNORECASE,
    )
    if match:
        value = parse_number(match.group(1) + ("k" if match.group(2) else ""))
        return value, match.group(0)
    # "under 4500" / "below ₹400" style phrasing puts the comparator first.
    match = re.search(
        r"\b(?:under|below|less than|above|over|more than|se\s+kam|se\s+zyada)\s*"
        r"(?:₹|rs\.?|inr|\$|usd)?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(k)?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        value = parse_number(match.group(1) + ("k" if match.group(2) else ""))
        return value, match.group(0)
    return None, None


def extract_percentage(text: str) -> tuple[float | None, str | None]:
    normalized = normalize_text(text)
    match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:%|percent|pct|pratishat|प्रतिशत)",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    return float(match.group(1)), match.group(0)


def resolve_airport(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^a-zA-Z ]", "", value).strip().lower()
    if not cleaned:
        return None
    if cleaned.upper() in {code for code in CITY_TO_IATA.values()} and len(cleaned) == 3:
        return cleaned.upper()
    return CITY_TO_IATA.get(cleaned)


def _build_date(day: int, month: int, year: int | None, today: date) -> date | None:
    candidate_year = year if year is not None else today.year
    try:
        candidate = date(candidate_year, month, day)
    except ValueError:
        return None
    if year is None and candidate < today:
        try:
            candidate = date(candidate_year + 1, month, day)
        except ValueError:
            return None
    return candidate


def parse_date_expression(text: str, today: date | None = None) -> tuple[date | None, str | None]:
    """Parse an explicit date from free text and return the matched substring.

    A day/month without a year rolls into next year once that date has passed,
    so "4 Nov" spoken on 21 Nov means the upcoming 4 Nov.
    """

    today = today or utcnow().date()
    normalized = normalize_text(text)

    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", normalized)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), iso.group(0)
        except ValueError:
            return None, None

    day_month = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_PATTERN})\b\.?\s*,?\s*(\d{{4}})?",
        normalized,
        re.IGNORECASE,
    )
    if day_month:
        month = MONTHS[day_month.group(2).lower().rstrip(".")]
        year = int(day_month.group(3)) if day_month.group(3) else None
        parsed = _build_date(int(day_month.group(1)), month, year, today)
        if parsed:
            return parsed, day_month.group(0)

    month_day = re.search(
        rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b\.?\s*,?\s*(\d{{4}})?",
        normalized,
        re.IGNORECASE,
    )
    if month_day:
        month = MONTHS[month_day.group(1).lower().rstrip(".")]
        year = int(month_day.group(3)) if month_day.group(3) else None
        parsed = _build_date(int(month_day.group(2)), month, year, today)
        if parsed:
            return parsed, month_day.group(0)

    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", normalized)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        year = numeric.group(3)
        year_value = None
        if year:
            year_value = int(year)
            if year_value < 100:
                year_value += 2000
        parsed = _build_date(day, month, year_value, today)
        if parsed:
            return parsed, numeric.group(0)

    relative = re.search(r"\b(today|tomorrow|aaj|kal|day after tomorrow)\b", normalized, re.IGNORECASE)
    if relative:
        token = relative.group(1).lower()
        if token in {"today", "aaj"}:
            return today, relative.group(0)
        if token == "tomorrow":
            return today + timedelta(days=1), relative.group(0)
        if token == "day after tomorrow":
            return today + timedelta(days=2), relative.group(0)

    return None, None


def strip_span(text: str, span: str | None) -> str:
    if not span:
        return text
    return text.replace(span, " ", 1)


def format_money(value: float | None, currency: str = "INR") -> str:
    if value is None:
        return "n/a"
    symbol = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency.upper(), "")
    if value >= 1000 and float(value).is_integer():
        formatted = f"{value:,.0f}"
    else:
        formatted = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{symbol}{formatted}" if symbol else f"{formatted} {currency.upper()}"
