"""Google Flights monitoring through SerpApi's google_flights engine."""

from __future__ import annotations

from app.integrations.serpapi_client import ProviderError, SerpApiClient
from app.schemas.watch import FlightRule
from app.utils.normalization import to_utc_iso

TRAVEL_CLASS_CODES = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}


class FlightProvider:
    source = "Google Flights (SerpApi)"

    def __init__(self, client: SerpApiClient | None = None) -> None:
        self.client = client or SerpApiClient()

    def fetch(self, rule: FlightRule) -> dict:
        params: dict[str, object] = {
            "departure_id": rule.origin,
            "arrival_id": rule.destination,
            "outbound_date": rule.travel_date.isoformat(),
            "type": 2,  # one-way
            "currency": rule.currency,
            "hl": "en",
            "gl": "in",
            "adults": rule.passengers,
        }
        if rule.return_date:
            params["type"] = 1
            params["return_date"] = rule.return_date.isoformat()
        if rule.travel_class:
            params["travel_class"] = TRAVEL_CLASS_CODES[rule.travel_class]

        data = self.client.search("google_flights", params)
        itineraries = list(data.get("best_flights") or []) + list(data.get("other_flights") or [])
        priced = [item for item in itineraries if isinstance(item.get("price"), (int, float))]

        price_insights = data.get("price_insights") or {}
        lowest_insight = price_insights.get("lowest_price")
        if not priced and not isinstance(lowest_insight, (int, float)):
            raise ProviderError(
                f"No comparable fares returned for {rule.origin}->{rule.destination} "
                f"on {rule.travel_date.isoformat()}",
                retryable=False,
                provider="serpapi:google_flights",
            )

        cheapest = min(priced, key=lambda item: item["price"]) if priced else {}
        current_price = (
            float(cheapest["price"])
            if priced
            else float(lowest_insight)  # real Google price insight, not a guess
        )
        legs = cheapest.get("flights") or []
        first_leg = legs[0] if legs else {}
        departure_airport = first_leg.get("departure_airport") or {}
        arrival_airport = first_leg.get("arrival_airport") or {}
        airlines = [leg.get("airline") for leg in legs if leg.get("airline")]

        return {
            "watch_type": "flight",
            "origin": rule.origin,
            "destination": rule.destination,
            "travel_date": rule.travel_date.isoformat(),
            "return_date": rule.return_date.isoformat() if rule.return_date else None,
            "current_price": round(current_price, 2),
            "currency": rule.currency,
            "source": self.source,
            "source_url": (data.get("search_metadata") or {}).get("google_flights_url"),
            "airline": airlines[0] if airlines else None,
            "flight_number": first_leg.get("flight_number"),
            "stops": max(len(legs) - 1, 0) if legs else None,
            "departure_airport": departure_airport.get("id"),
            "arrival_airport": arrival_airport.get("id"),
            "price_level": price_insights.get("price_level"),
            "comparable_fares": len(priced),
            "checked_at": to_utc_iso(),
        }


flight_provider = FlightProvider()
