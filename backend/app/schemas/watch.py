"""Validated watch rules. Every parsed or API-submitted rule passes through here."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from app.utils.normalization import utcnow
from app.utils.validators import OFFICIAL_JOB_DOMAINS


class FlightRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watch_type: Literal["flight"] = "flight"
    origin: str = Field(min_length=3, max_length=3, description="Departure IATA airport code")
    destination: str = Field(min_length=3, max_length=3, description="Arrival IATA airport code")
    travel_date: date
    return_date: date | None = None
    condition: Literal["below", "above"] = "below"
    target_price: float = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    travel_class: Literal["economy", "premium_economy", "business", "first"] | None = None
    passengers: int = Field(default=1, ge=1, le=9)

    @field_validator("origin", "destination")
    @classmethod
    def _airport_code(cls, value: str) -> str:
        code = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("airport code must be a 3-letter IATA code")
        return code

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        code = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("currency must be a 3-letter ISO code")
        return code

    @model_validator(mode="after")
    def _check_dates(self) -> "FlightRule":
        if self.travel_date < utcnow().date():
            # API-submitted rules must be actionable; the parser rolls dates forward.
            raise ValueError("travel_date must not be in the past")
        if self.return_date and self.return_date < self.travel_date:
            raise ValueError("return_date must be on or after travel_date")
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        return self


class StockRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watch_type: Literal["stock"] = "stock"
    symbol: str = Field(min_length=1, max_length=32)
    exchange: Literal["NSE", "BSE"] | None = None
    condition: Literal["absolute_change_greater_than", "price_below", "price_above"] = (
        "absolute_change_greater_than"
    )
    threshold_percent: float | None = Field(default=None, gt=0, le=100)
    target_price: float | None = Field(default=None, gt=0)
    direction: Literal["up", "down", "either"] = "either"

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9&.\-]{0,31}", symbol):
            raise ValueError("symbol must contain only letters, numbers, &, . or -")
        return symbol

    @model_validator(mode="after")
    def _check_condition_fields(self) -> "StockRule":
        if self.condition == "absolute_change_greater_than" and self.threshold_percent is None:
            raise ValueError("threshold_percent is required for absolute_change_greater_than")
        if self.condition in {"price_below", "price_above"} and self.target_price is None:
            raise ValueError("target_price is required for price threshold conditions")
        return self


class JobRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watch_type: Literal["job_notification"] = "job_notification"
    keywords: list[str] = Field(min_length=1, max_length=10)
    organization: str | None = Field(default=None, max_length=120)
    domains: list[str] = Field(
        default_factory=lambda: list(OFFICIAL_JOB_DOMAINS),
        description="Only notices on these domains are considered",
    )

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            text = re.sub(r"\s+", " ", value).strip()
            if text and text.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(text)
        if not cleaned:
            raise ValueError("at least one meaningful keyword is required")
        return cleaned

    @field_validator("domains")
    @classmethod
    def _domains(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            domain = value.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
            domain = domain.removeprefix("www.")
            if domain and "." in domain and domain not in cleaned:
                cleaned.append(domain)
        if not cleaned:
            raise ValueError("at least one search domain is required")
        return cleaned


class TopicRule(BaseModel):
    """Anything else: a product price (Google Shopping) or new results for a search (web, news, jobs)."""

    model_config = ConfigDict(extra="forbid")

    watch_type: Literal["topic"] = "topic"
    query: str = Field(min_length=2, max_length=200)
    source: Literal["web", "news", "shopping", "jobs"] = "web"
    mode: Literal["new_results", "price_below", "price_above"] = "new_results"
    target_price: float | None = Field(default=None, gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("query")
    @classmethod
    def _query(cls, value: str) -> str:
        text = re.sub(r"\s+", " ", value).strip()
        if len(text) < 2:
            raise ValueError("describe what to watch")
        return text

    @model_validator(mode="after")
    def _check_mode(self) -> "TopicRule":
        if self.mode in {"price_below", "price_above"}:
            if self.target_price is None:
                raise ValueError("target_price is required for price watches")
            if self.source != "shopping":
                raise ValueError("price watches use the shopping source")
        return self


WatchRule = Annotated[Union[FlightRule, StockRule, JobRule, TopicRule], Field(discriminator="watch_type")]
WATCH_RULE_ADAPTER: TypeAdapter[FlightRule | StockRule | JobRule | TopicRule] = TypeAdapter(WatchRule)


def parse_watch_rule(data: dict[str, Any]) -> FlightRule | StockRule | JobRule | TopicRule:
    return WATCH_RULE_ADAPTER.validate_python(data)


class WatchCreate(BaseModel):
    watch_type: Literal["flight", "stock", "job_notification", "topic"]
    rule: dict[str, Any]
    check_interval: int | None = Field(default=None, ge=15, le=1440)
    room_id: int | None = Field(default=None, ge=1)


class WatchUpdate(BaseModel):
    rule: dict[str, Any] | None = None
    check_interval: int | None = Field(default=None, ge=15, le=1440)


class ParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    room_id: int | None = None


class ParseResponse(BaseModel):
    understood: bool
    watch_type: str | None = None
    rule: dict[str, Any] | None = None
    missing_fields: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None
    parser: str = "heuristic"


class WatchHistoryOut(BaseModel):
    id: int
    observed_value: float | None = None
    observed_data: dict[str, Any] = Field(default_factory=dict)
    checked_at: Any

    model_config = ConfigDict(from_attributes=True)


class WatchOut(BaseModel):
    id: int
    room_id: int
    created_by: int
    watch_type: str
    rule_json: dict[str, Any]
    status: str
    check_interval: int
    last_checked_at: Any | None = None
    next_check_at: Any | None = None
    last_triggered_at: Any | None = None
    last_alert_at: Any | None = None
    booked_by_id: int | None = None
    completed_at: Any | None = None
    created_at: Any
    latest_value: float | None = None
    history: list[WatchHistoryOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
