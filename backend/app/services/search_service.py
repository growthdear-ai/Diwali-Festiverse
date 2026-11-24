"""One-shot web searches for questions sent to Nazar."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from app.integrations.serpapi_client import ProviderError, SerpApiClient
from app.integrations.flight_provider import TRAVEL_CLASS_CODES
from app.integrations.topic_provider import ENGINES
from app.integrations.you_client import you_client
from app.services.parser_service import refine_search_request
from app.utils.normalization import format_money, utcnow

logger = logging.getLogger(__name__)

serpapi_client = SerpApiClient()
SEARCH_ENGINES = {source: provider[0] for source, provider in ENGINES.items()}
MAX_RESULTS = 5
KNOWN_INSTITUTIONS = {
    "aktu", "anna university", "bits", "bput", "iit", "jntua", "jntuh", "jntuk",
    "ku", "makaut", "nit", "osmania university", "sppu", "vtu",
}


def _result(
    title: Any,
    url: Any,
    *,
    source: Any = None,
    snippet: Any = None,
    price: Any = None,
) -> dict[str, Any] | None:
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    return {
        "title": title.strip()[:200],
        "url": url.strip(),
        "source": source.strip()[:120] if isinstance(source, str) and source.strip() else "",
        "snippet": snippet.strip()[:500] if isinstance(snippet, str) and snippet.strip() else "",
        "price": float(price) if isinstance(price, (int, float)) else None,
    }


def _results(data: dict[str, Any], source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if source == "shopping":
        rows = data.get("shopping_results") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _result(
                row.get("title"),
                row.get("product_link") or row.get("link"),
                source=row.get("source"),
                price=row.get("extracted_price"),
            )
            if item:
                items.append(item)
    elif source == "news":
        rows = data.get("news_results") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            publisher = row.get("source")
            item = _result(
                row.get("title"),
                row.get("link"),
                source=publisher.get("name") if isinstance(publisher, dict) else publisher,
                snippet=row.get("snippet") or row.get("date"),
            )
            if item:
                items.append(item)
    elif source == "jobs":
        rows = data.get("jobs_results") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            application = (row.get("apply_options") or [{}])[0]
            title = " · ".join(
                value for value in (row.get("title"), row.get("company_name"), row.get("location")) if value
            )
            item = _result(
                title,
                application.get("link") or row.get("share_link"),
                source=row.get("via") or row.get("company_name"),
                snippet=(row.get("detected_extensions") or {}).get("posted_at"),
            )
            if item:
                items.append(item)
    else:
        rows = data.get("organic_results") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _result(
                row.get("title"),
                row.get("link"),
                source=row.get("source"),
                snippet=row.get("snippet"),
            )
            if item:
                items.append(item)
    return items


def _sources(items: list[dict[str, Any]], research: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in [*items, *(research.get("sources") or [])]:
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        sources.append({"url": url, "title": str(source.get("title") or source.get("source") or url)})
        if len(sources) == 10:
            break
    return sources


def _serp_search(engine: str, query: str, source: str) -> dict[str, Any]:
    params: dict[str, Any] = {"q": query, "hl": "en", "gl": "in"}
    if source == "web":
        params["num"] = 10
    try:
        return serpapi_client.search(engine, params)
    except ProviderError as exc:
        if "hasn't returned any results" not in exc.message.lower():
            raise
        return {}


def _event_or_ground_ticket_query(text: str) -> bool:
    return bool(
        re.search(r"\b(?:train|rail|bus|concert|event|movie|cinema|match|cricket|football|show)\b", text, re.I)
        and not re.search(r"\b(?:flight|airfare|airline|airport|fly)\b", text, re.I)
    )


def _is_exam_timetable_query(text: str) -> bool:
    return bool(
        re.search(r"\b(?:exam|examination)\b", text, re.I)
        and re.search(r"\b(?:time[\s-]*table|timetable|schedule)\b", text, re.I)
    )


def _exam_timetable_needs_institution(text: str) -> bool:
    if not _is_exam_timetable_query(text):
        return False
    cleaned = re.sub(r"@nazar\b", " ", text, flags=re.I)
    if any(re.search(rf"\b{re.escape(name)}\b", cleaned, re.I) for name in KNOWN_INSTITUTIONS):
        return False
    if re.search(r"\b[A-Z]{3,}\b", cleaned):
        return False
    return not re.search(
        r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+(?:University|College|Institute)|"
        r"University of [A-Z][a-z]+)\b",
        cleaned,
    )


def _relevance_groups(text: str, rule: dict[str, Any]) -> list[set[str]]:
    cleaned = re.sub(r"@nazar\b", " ", text, flags=re.I)
    groups = [
        {token.lower()}
        for token in re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", cleaned)
        if token.lower() not in {"nazar", "exam", "inr", "usd", "eur", "gbp"}
    ]
    for institution in KNOWN_INSTITUTIONS:
        if re.search(rf"\b{re.escape(institution)}\b", cleaned, re.I):
            groups.extend({word} for word in institution.split() if len(word) > 2)
    for ordinal in re.findall(r"\b(\d+)(st|nd|rd|th)\b", cleaned, re.I):
        number, suffix = ordinal
        roman = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x"}.get(number)
        alternatives = {f"{number}{suffix.lower()}", number}
        if roman:
            alternatives.add(roman)
        groups.append(alternatives)
    if re.search(r"\b(?:sem|semester)\b", cleaned, re.I):
        groups.append({"semester", "sem"})
    target_price = rule.get("target_price")
    for year in re.findall(r"\b(?:19|20)\d{2}\b", cleaned):
        if target_price is None or str(target_price).split(".")[0] != year:
            groups.append({year})
    return groups


def _matches_relevance(item: dict[str, Any], groups: list[set[str]]) -> bool:
    if not groups:
        return True
    words = set(re.findall(r"[a-z0-9]+", " ".join(
        str(item.get(field) or "") for field in ("title", "snippet", "source", "url")
    ).lower()))
    for group in groups:
        if not any(
            alternative in words
            or alternative == "sem" and any(word.startswith("sem") for word in words)
            for alternative in group
        ):
            return False
    return True


def _filter_research(research: dict[str, Any], groups: list[set[str]]) -> dict[str, Any]:
    if not groups:
        return research
    sources = [
        source for source in research.get("sources") or []
        if isinstance(source, dict) and _matches_relevance(source, groups)
    ]
    if not sources:
        return {"available": False, "content": None, "sources": [], "error": None}
    return {**research, "sources": sources}


def _flight_search(text: str, parsed: dict, refined: dict[str, str]) -> dict[str, Any]:
    rule = parsed.get("rule") if isinstance(parsed.get("rule"), dict) else {}
    missing = [field for field in ("origin", "destination", "travel_date") if not rule.get(field)]
    for field in ("origin", "destination"):
        value = rule.get(field)
        if value and not re.fullmatch(r"[A-Z]{3}", str(value)):
            missing.append(field)
    if rule.get("origin") and rule.get("origin") == rule.get("destination"):
        missing.extend(("origin", "destination"))
    try:
        travel_date = date.fromisoformat(str(rule.get("travel_date")))
    except ValueError:
        travel_date = None
    if travel_date is None or travel_date < utcnow().date():
        if "travel_date" not in missing:
            missing.append("travel_date")
    if missing:
        question = "What are your departure city, destination, and travel date?"
        if "origin" not in missing and "destination" not in missing:
            question = "What is your travel date?"
        elif "travel_date" not in missing and "origin" in missing:
            question = "Which city are you flying from?"
        elif "travel_date" not in missing and "destination" in missing:
            question = "Which city are you flying to?"
        elif missing == ["travel_date"]:
            question = "What future date should I search?"
        summary = "I can find live flight options once I have the trip details."
        return {
            "action": "search_results",
            "reply": f"{summary} {question}",
            "summary": summary,
            "follow_up_question": question,
            "search_query": refined["query"],
            "result_count": 0,
            "results": [],
            "sources": [],
            "context": text,
        }

    params: dict[str, Any] = {
        "departure_id": rule["origin"],
        "arrival_id": rule["destination"],
        "outbound_date": travel_date.isoformat(),
        "type": 2,
        "currency": rule.get("currency", "INR"),
        "hl": "en",
        "gl": "in",
        "adults": rule.get("passengers", 1),
    }
    if rule.get("return_date"):
        params["type"] = 1
        params["return_date"] = rule["return_date"]
    if rule.get("travel_class") in TRAVEL_CLASS_CODES:
        params["travel_class"] = TRAVEL_CLASS_CODES[rule["travel_class"]]

    data = serpapi_client.search("google_flights", params)
    flight_url = (data.get("search_metadata") or {}).get("google_flights_url")
    options = list(data.get("best_flights") or []) + list(data.get("other_flights") or [])
    results: list[dict[str, Any]] = []
    for option in options:
        price = option.get("price")
        if not isinstance(price, (int, float)):
            continue
        legs = option.get("flights") or []
        airlines = list(dict.fromkeys(leg.get("airline") for leg in legs if leg.get("airline")))
        flight_numbers = [leg.get("flight_number") for leg in legs if leg.get("flight_number")]
        first_leg = legs[0] if legs else {}
        last_leg = legs[-1] if legs else {}
        departure = first_leg.get("departure_airport") or {}
        arrival = last_leg.get("arrival_airport") or {}
        details = [f"{max(len(legs) - 1, 0)} stop" + ("s" if len(legs) != 2 else "") if legs else ""]
        duration = option.get("total_duration")
        if isinstance(duration, (int, float)):
            hours, minutes = divmod(int(duration), 60)
            details.append(f"{hours}h {minutes}m" if hours else f"{minutes}m")
        depart_at, arrive_at = departure.get("time"), arrival.get("time")
        times = " → ".join(
            value for value in (
                f"{departure.get('id')} {depart_at}" if departure.get("id") and depart_at else depart_at,
                f"{arrival.get('id')} {arrive_at}" if arrival.get("id") and arrive_at else arrive_at,
            ) if isinstance(value, str)
        )
        if times:
            details.append(times)
        title = " · ".join([", ".join(airlines) or "Flight option", ", ".join(flight_numbers)]).strip(" ·")
        results.append(
            {
                "title": title,
                "url": flight_url if isinstance(flight_url, str) else None,
                "source": "Google Flights",
                "snippet": " · ".join(details),
                "price": float(price),
                "currency": rule.get("currency", "INR"),
                "action_label": "Book on Google Flights",
            }
        )
    results.sort(key=lambda result: result["price"])
    results = results[:MAX_RESULTS]
    source_results = [result for result in results if result["url"]]
    follow_up = "Prefer nonstop flights, a specific airline, or a departure time?"
    if results:
        cheapest = results[0]
        option_label = "option" if len(results) == 1 else "options"
        summary = (
            f"Found {len(results)} live {option_label} for {rule['origin']} → {rule['destination']} on "
            f"{rule['travel_date']}. Lowest: {format_money(cheapest['price'], cheapest['currency'])}."
        )
        lines = [summary, *(f"- {r['title']} — {format_money(r['price'], r['currency'])}" for r in results)]
    else:
        summary = f"No live fares were returned for {rule['origin']} → {rule['destination']} on {rule['travel_date']}."
        lines = [summary]
    return {
        "action": "search_results",
        "reply": "\n".join(lines) + f"\n\n{follow_up}",
        "summary": summary,
        "follow_up_question": follow_up,
        "search_query": refined["query"],
        "result_count": len(results),
        "results": results,
        "sources": _sources(source_results, {}),
        "context": text,
    }


def _shopping_reply(
    query: str,
    items: list[dict[str, Any]],
    rule: dict[str, Any],
) -> str:
    selected = _shopping_display_items(items, rule)
    target = rule.get("target_price")
    mode = rule.get("mode")
    currency = rule.get("currency", "INR")

    if _matching_shopping_items(items, rule):
        heading = f"Here are current shopping results for {query}:"
    elif target is not None and items:
        side = "under" if mode == "price_below" else "over"
        heading = (
            f"I couldn't find listings {side} {format_money(target, currency)}. "
            "Here are the closest current listings:"
        )
    else:
        heading = f"I couldn't find current shopping listings for {query}."

    lines = [heading]
    for item in selected:
        price = format_money(item["price"], currency) if item["price"] is not None else "price not listed"
        publisher = f" ({item['source']})" if item["source"] else ""
        lines.append(f"- {item['title']} — {price}{publisher}")
    return "\n".join(lines)


def _matching_shopping_items(
    items: list[dict[str, Any]], rule: dict[str, Any]
) -> list[dict[str, Any]]:
    target = rule.get("target_price")
    mode = rule.get("mode")
    if target is not None and mode == "price_below":
        return [item for item in items if item["price"] is not None and item["price"] <= target]
    if target is not None and mode == "price_above":
        return [item for item in items if item["price"] is not None and item["price"] >= target]
    return items


def _shopping_display_items(
    items: list[dict[str, Any]], rule: dict[str, Any]
) -> list[dict[str, Any]]:
    matching = _matching_shopping_items(items, rule)
    if matching:
        return matching[:MAX_RESULTS]
    target = rule.get("target_price")
    if target is not None:
        closest = sorted(
            items,
            key=lambda item: abs(item["price"] - target) if item["price"] is not None else float("inf"),
        )
        return closest[:MAX_RESULTS]
    return []


def _web_reply(query: str, items: list[dict[str, Any]], research: dict[str, Any]) -> str:
    lines: list[str] = []
    content = research.get("content")
    if isinstance(content, str) and content.strip():
        lines.append(f"Here’s a research summary for “{query}”:\n\n{content.strip()}")
    if items:
        lines.append(f"Top live search results for “{query}”:")
        for item in items[:MAX_RESULTS]:
            snippet = f" — {item['snippet']}" if item["snippet"] else ""
            lines.append(f"- {item['title']}{snippet}")
    elif not lines:
        lines.append(f"I couldn't find current web results for “{query}”. Try adding a location or another keyword.")
    if not research.get("available") and research.get("error"):
        logger.warning("You.com research unavailable: %s", research["error"])
        if items:
            lines.append("(The research summary is unavailable; these are direct search results.)")
    return "\n\n".join(lines)


def search(text: str, parsed: dict) -> dict[str, Any]:
    """Fetch current results and return a cited response with a refinement question."""

    if _exam_timetable_needs_institution(text):
        summary = "Exam timetables depend on the university and branch, so I don't want to guess."
        question = "Which university/college and branch should I check? For example, VTU CSE."
        query = re.sub(r"@nazar\b", " ", text, flags=re.I).strip()
        return {
            "action": "search_results",
            "reply": f"{summary}\n\n{question}",
            "summary": summary,
            "follow_up_question": question,
            "search_query": query,
            "result_count": 0,
            "results": [],
            "sources": [],
            "context": text,
        }

    refined = refine_search_request(text, parsed)
    query = refined["query"]
    rule = parsed.get("rule") if isinstance(parsed.get("rule"), dict) else {}
    if parsed.get("watch_type") == "flight" and not _event_or_ground_ticket_query(text):
        return _flight_search(text, parsed, refined)

    source = rule.get("source", "web")
    if source not in SEARCH_ENGINES:
        source = "web"

    data = _serp_search(SEARCH_ENGINES[source], query, source)
    items = _results(data, source)
    if source == "jobs" and not items:
        query = f"{query} jobs openings"
        data = _serp_search(SEARCH_ENGINES["web"], query, "web")
        items = _results(data, "web")
    relevance = _relevance_groups(text, rule)
    items = [item for item in items if _matches_relevance(item, relevance)]
    ticket_query = bool(re.search(r"\b(?:ticket|tickets|concert|event|match)\b", text, re.I))
    for item in items:
        if source == "shopping":
            item["action_label"] = "View deal"
        elif ticket_query:
            item["action_label"] = "View tickets"
    timetable_query = _is_exam_timetable_query(text)
    research: dict[str, Any] = {"available": False, "content": None, "sources": [], "error": None}
    if source != "shopping" and not timetable_query:
        research = you_client.research(query, effort="lite")
        research = _filter_research(research, relevance)

    follow_up = refined["follow_up_question"]
    if timetable_query:
        follow_up = (
            "Which branch should I narrow this to?"
            if items
            else "Can you share the official exam portal or your exact course and branch?"
        )
    reply = (
        _shopping_reply(rule.get("query") or query, items, rule)
        if source == "shopping"
        else _web_reply(query, items, research)
    )
    reply = f"{reply}\n\n{follow_up}"
    cited_items = _shopping_display_items(items, rule) if source == "shopping" else items
    displayed_items = cited_items[:MAX_RESULTS]
    if source == "shopping":
        matching = _matching_shopping_items(items, rule)
        if matching:
            lowest = min(matching, key=lambda item: item["price"])
            summary = (
                f"{len(matching)} listings for {rule.get('query')}; lowest is "
                f"{format_money(lowest['price'], rule.get('currency', 'INR'))}."
            )
        elif rule.get("target_price") is not None:
            closest = _shopping_display_items(items, rule)
            if closest and closest[0]["price"] is not None:
                summary = (
                    f"Nothing matched {format_money(rule['target_price'], rule.get('currency', 'INR'))}; "
                    f"closest listing is {format_money(closest[0]['price'], rule.get('currency', 'INR'))}."
                )
            else:
                summary = f"No current listings matched {format_money(rule['target_price'], rule.get('currency', 'INR'))}."
        else:
            summary = f"Found {len(displayed_items)} current shopping listings for {rule.get('query') or query}."
    elif timetable_query:
        summary = (
            f"Found {len(displayed_items)} timetable result(s). Best match: {displayed_items[0]['title']}."
            if displayed_items
            else "I couldn't verify a timetable matching those details, so I won't guess."
        )
    else:
        content = research.get("content")
        first_snippet = next((item["snippet"] for item in items if item["snippet"]), "")
        summary_source = content.strip() if isinstance(content, str) and content.strip() else first_snippet
        summary = summary_source[:280].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…" if len(summary_source) > 280 else summary_source
        if not summary:
            summary = f"Found {len(displayed_items)} live results for “{query}”." if items else f"No current results found for “{query}”."
    return {
        "action": "search_results",
        "reply": reply,
        "summary": summary,
        "follow_up_question": follow_up,
        "search_query": query,
        "result_count": len(displayed_items),
        "results": displayed_items,
        "sources": _sources(displayed_items, research),
        "context": text,
    }
