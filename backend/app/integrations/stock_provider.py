"""Google Finance monitoring through SerpApi's google_finance engine.

Ticker identifiers are resolved against live SerpApi responses (NSE first, then
BSE) instead of assuming a ticker format.
"""

from __future__ import annotations

import re

from app.integrations.serpapi_client import ProviderError, SerpApiClient
from app.schemas.watch import StockRule
from app.utils.normalization import parse_number, to_utc_iso


def _previous_close(knowledge_graph: dict) -> float | None:
    for stat in ((knowledge_graph.get("key_stats") or {}).get("stats") or []):
        if str(stat.get("label", "")).lower() == "previous close":
            return parse_number(str(stat.get("value", "")).replace("$", "").replace(",", ""))
    return None


class StockProvider:
    source = "Google Finance (SerpApi)"

    def __init__(self, client: SerpApiClient | None = None) -> None:
        self.client = client or SerpApiClient()

    def _candidate_queries(self, rule: StockRule) -> list[str]:
        if ":" in rule.symbol:
            return [rule.symbol]
        exchanges = [rule.exchange] if rule.exchange else ["NSE", "BSE"]
        return [f"{rule.symbol}:{exchange}" for exchange in exchanges]

    def fetch(self, rule: StockRule) -> dict:
        errors: list[str] = []
        for query in self._candidate_queries(rule):
            try:
                data = self.client.search("google_finance", {"q": query, "hl": "en"})
            except ProviderError as exc:
                errors.append(f"{query}: {exc.message}")
                if not exc.retryable:
                    continue
                continue

            summary = data.get("summary") or {}
            price = summary.get("extracted_price")
            if not isinstance(price, (int, float)):
                errors.append(f"{query}: no quote in response")
                continue

            movement = summary.get("price_movement") or {}
            raw_percentage = movement.get("percentage")
            percentage = float(raw_percentage) if isinstance(raw_percentage, (int, float)) else None
            if percentage is not None and str(movement.get("movement", "")).lower() == "down":
                percentage = -abs(percentage)
            elif percentage is not None:
                percentage = abs(percentage)

            knowledge_graph = data.get("knowledge_graph") or {}
            previous_close = _previous_close(knowledge_graph)
            previous_close_source = "knowledge_graph.key_stats"
            if previous_close is None:
                # Live Google Finance responses do not always include a
                # "Previous close" stat. Derive it arithmetically from the real
                # day-change value instead of guessing.
                change_value = movement.get("value")
                if isinstance(change_value, (int, float)):
                    change = abs(float(change_value))
                    candidate = (
                        float(price) + change
                        if str(movement.get("movement", "")).lower() == "down"
                        else float(price) - change
                    )
                    if candidate > 0:
                        previous_close = round(candidate, 4)
                        previous_close_source = "google_finance_price_movement"

            # Baseline is explicitly the previous close returned by (or derived
            # from) Google Finance's live quote.
            return {
                "watch_type": "stock",
                "symbol": summary.get("stock") or rule.symbol,
                "company_name": summary.get("title"),
                "exchange": summary.get("exchange"),
                "query": query,
                "current_price": round(float(price), 2),
                "currency": summary.get("currency") or "INR",
                "percent_change": round(percentage, 4) if percentage is not None else None,
                "absolute_change_percent": round(abs(percentage), 4) if percentage is not None else None,
                "previous_close": previous_close,
                "previous_close_source": previous_close_source,
                "baseline": "previous_close",
                "market_time": summary.get("date"),
                "source": self.source,
                "source_url": (data.get("search_metadata") or {}).get("google_finance_url"),
                "checked_at": to_utc_iso(),
            }

        detail = "; ".join(errors[:3]) if errors else "no response"
        raise ProviderError(
            f"Could not resolve a Google Finance quote for {rule.symbol} ({detail})",
            retryable=False,
            provider="serpapi:google_finance",
        )


stock_provider = StockProvider()
