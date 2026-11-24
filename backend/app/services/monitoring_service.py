"""Background monitoring orchestration.

SerpApi supplies live observations, conditions are evaluated against the
previous observation (a new crossing is required), You.com is called only on a
qualifying trigger, and alerts are deduplicated before delivery to Nexconn.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from threading import Lock
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.band_client import (
    get_scout_client,
    get_verifier_client,
    get_band_room_id,
)
from app.integrations.flight_provider import flight_provider
from app.integrations.jobs_provider import jobs_provider
from app.integrations.lyzr_client import lyzr_client
from app.integrations.serpapi_client import ProviderError, ProviderNotConfigured
from app.integrations.stock_provider import stock_provider
from app.integrations.topic_provider import topic_provider
from app.integrations.you_client import you_client
from app.models.alert import Alert
from app.models.watch import Watch
from app.models.watch_history import WatchHistory
from app.schemas.watch import FlightRule, JobRule, StockRule, TopicRule, parse_watch_rule
from app.services import alert_service
from app.utils.deduplication import build_event_key, notice_key
from app.utils.normalization import day_start, format_money, utcnow
from app.utils.validators import is_official_domain

logger = logging.getLogger(__name__)

PROVIDERS = {
    "flight": flight_provider,
    "stock": stock_provider,
    "job_notification": jobs_provider,
    "topic": topic_provider,
}

_inflight: set[int] = set()
_inflight_lock = Lock()


@dataclass
class Evaluation:
    triggered: bool
    current_value: float | None
    target_value: float | None
    observed_text: str


def evaluate_condition(watch_type: str, rule: dict, observation: dict) -> Evaluation:
    if watch_type == "flight":
        current = observation.get("current_price")
        target = rule.get("target_price")
        condition = rule.get("condition", "below")
        if current is None or target is None:
            return Evaluation(False, current, target, "No comparable fare")
        triggered = current <= target if condition == "below" else current >= target
        currency = rule.get("currency", "INR")
        return Evaluation(
            triggered,
            float(current),
            float(target),
            f"Lowest fare {format_money(current, currency)} (target {condition} {format_money(target, currency)})",
        )

    if watch_type == "stock":
        price = observation.get("current_price")
        currency = observation.get("currency") or "INR"
        condition = rule.get("condition")
        if condition == "absolute_change_greater_than":
            change = observation.get("absolute_change_percent")
            signed = observation.get("percent_change") or 0
            threshold = rule.get("threshold_percent")
            direction = rule.get("direction", "either")
            if change is None or threshold is None:
                return Evaluation(False, price, threshold, "No percentage movement")
            direction_ok = (
                direction == "either"
                or (direction == "up" and signed > 0)
                or (direction == "down" and signed < 0)
            )
            triggered = float(change) >= float(threshold) and direction_ok
            return Evaluation(
                triggered,
                float(price) if price is not None else None,
                float(threshold),
                f"{observation.get('symbol')} moved {signed:+.2f}% "
                f"(threshold {threshold}% {direction}), now {format_money(price, currency)}",
            )

        target = rule.get("target_price")
        if price is None or target is None:
            return Evaluation(False, price, target, "No quote")
        triggered = float(price) <= float(target) if condition == "price_below" else float(price) >= float(target)
        return Evaluation(
            triggered,
            float(price),
            float(target),
            f"{observation.get('symbol')} at {format_money(price, currency)} (target {format_money(target, currency)})",
        )

    if watch_type == "job_notification":
        notices = observation.get("notices") or []
        return Evaluation(
            bool(notices),
            None,
            None,
            f"{len(notices)} official notice(s) found",
        )

    if watch_type == "topic":
        mode = rule.get("mode", "new_results")
        if mode in {"price_below", "price_above"}:
            current = observation.get("current_price")
            target = rule.get("target_price")
            currency = rule.get("currency", "INR")
            if current is None or target is None:
                return Evaluation(False, current, target, "No comparable price")
            triggered = current <= target if mode == "price_below" else current >= target
            return Evaluation(
                triggered,
                float(current),
                float(target),
                f"Lowest price {format_money(current, currency)} (target {mode.split('_')[1]} {format_money(target, currency)})",
            )
        items = observation.get("items") or []
        return Evaluation(bool(items), None, None, f"{len(items)} result(s) found")

    return Evaluation(False, None, None, "Unsupported watch type")


def _reschedule(watch: Watch, now) -> None:
    watch.last_checked_at = now
    watch.next_check_at = now + timedelta(minutes=max(15, watch.check_interval))


def _research(
    watch: Watch,
    rule: Any,
    observation: dict,
    notice: dict | None = None,
) -> tuple[str | None, list[dict], str | None]:
    """Return (explanation, sources, error). Only called for real triggers."""

    if not you_client.configured:
        return None, [], "YOU_API_KEY is not configured"

    try:
        if isinstance(rule, FlightRule):
            question = (
                f"The lowest one-way fare for {rule.origin} to {rule.destination} on "
                f"{rule.travel_date.isoformat()} is currently {rule.currency} "
                f"{observation.get('current_price')} according to Google Flights. "
                "Explain likely reasons for fare movement on this route and date "
                "(seasonality, holidays, airline capacity). Do not invent alternate prices; "
                "cite your sources."
            )
            result = you_client.research(question, effort="lite")
        elif isinstance(rule, StockRule):
            question = (
                f"{observation.get('company_name') or rule.symbol} ({rule.symbol}) moved "
                f"{observation.get('percent_change'):+.2f}% from its previous close of "
                f"{observation.get('previous_close')} to {observation.get('current_price')} "
                f"{observation.get('currency')}. Summarize credible reasons and any relevant "
                "company announcements. Cite sources. Do not give financial advice."
            )
            result = you_client.finance_research(question)
        elif isinstance(rule, JobRule) and notice:
            question = (
                f"Verify whether this is an official government recruitment notification: "
                f"'{notice.get('title')}' published on {notice.get('domain')}. "
                "Search only official government recruitment domains and report whether "
                "they confirm this notice, with the official link."
            )
            result = you_client.research(
                question, effort="lite", include_domains=list(rule.domains)
            )
        elif isinstance(rule, TopicRule):
            if rule.mode == "new_results" and notice:
                question = (
                    f"Briefly explain this {rule.source} result about '{rule.query}': "
                    f"'{notice.get('title')}' ({notice.get('url')}). Say why it matters to "
                    "someone tracking this topic. Do not invent details; cite sources."
                )
            else:
                question = (
                    f"The lowest price for '{rule.query}' in India is currently {rule.currency} "
                    f"{observation.get('current_price')} according to Google Shopping. Explain "
                    "whether this is a good price and what drives it. Do not invent other "
                    "prices; cite sources."
                )
            result = you_client.research(question, effort="lite")
        else:
            return None, [], "Unsupported research request"
    except Exception as exc:  # provider failures must never block an alert
        logger.warning("You.com research failed for watch %s: %s", watch.id, exc)
        return None, [], f"Research failed: {exc}"

    if not result.get("available"):
        return None, [], result.get("error") or "Research unavailable"
    return result.get("content"), result.get("sources") or [], None


def _job_verification(notice: dict, sources: list[dict], rule: JobRule, research_error: str | None) -> str:
    base = notice.get("verification_status", "unverified")
    official_sources = [
        source for source in sources if is_official_domain(source.get("url", ""), rule.domains)
    ]
    if base == "verified":
        # The official page was extracted and matched the keywords. If You.com
        # returned only non-official sources, surface that as flagged.
        if sources and not official_sources:
            return "flagged"
        return "verified"
    if base == "flagged":
        return "flagged"
    if research_error is None and official_sources and not sources:
        return "unverified"
    return "unverified"


async def _run_verification_flow(
    watch: Watch,
    rule: Any,
    observation: dict,
    sources: list[dict],
    correlation_id: str,
) -> tuple[str, str | None, list[dict], float | None]:
    """Run the Lyzr/BAND verification flow for a triggered watch.

    Returns:
        (final_decision, explanation, verified_sources, confidence)
        final_decision: "alert_sent", "no_alert", "needs_human_review"
    """
    # If Lyzr/BAND not configured, fall back to original behavior (send alert)
    if not settings.lyzr_configured or not settings.band_configured:
        return "alert_sent", None, sources, None

    try:
        # Step 1: Scout posts candidate to BAND room
        scout_client = get_scout_client()
        band_room_id = get_band_room_id()

        if scout_client.configured and band_room_id:
            await scout_client.send_scout_candidate(
                room_id=band_room_id,
                watch_type=watch.watch_type,
                rule=watch.rule_json,
                observation=observation,
                sources=sources,
                correlation_id=correlation_id,
            )
            logger.info("Scout posted candidate to BAND room for correlation_id=%s", correlation_id)

        # Step 2: Verifier invokes Lyzr for structured analysis
        if not lyzr_client.configured:
            logger.warning("Lyzr not configured; skipping verification for correlation_id=%s", correlation_id)
            return "alert_sent", None, sources, None

        verification_result = await lyzr_client.verify_observation(
            watch_type=watch.watch_type,
            rule=watch.rule_json,
            observation=observation,
            sources=sources,
            correlation_id=correlation_id,
        )

        logger.info(
            "Lyzr verification result for correlation_id=%s: %s (confidence=%.2f)",
            correlation_id,
            verification_result.status,
            verification_result.confidence,
        )

        # Step 3: Verifier posts result to BAND room
        verifier_client = get_verifier_client()
        if verifier_client.configured and band_room_id:
            # Determine final decision based on verification result
            if verification_result.status == "verified" and verification_result.confidence >= 0.7:
                final_decision = "alert_sent"
            elif verification_result.status == "no_change":
                final_decision = "no_alert"
            else:
                final_decision = "needs_human_review"

            await verifier_client.send_verifier_result(
                room_id=band_room_id,
                correlation_id=correlation_id,
                verification_result=verification_result,
                final_decision=final_decision,
            )
            logger.info("Verifier posted result to BAND room for correlation_id=%s", correlation_id)

        # Step 4: Validate Lyzr response - require source evidence for verified
        if verification_result.status == "verified":
            if not verification_result.source_evidence:
                logger.warning(
                    "Lyzr returned 'verified' but no source evidence for correlation_id=%s; treating as needs_review",
                    correlation_id,
                )
                if verifier_client.configured and band_room_id:
                    await verifier_client.send_disagreement_notice(
                        room_id=band_room_id,
                        correlation_id=correlation_id,
                        scout_observation=observation,
                        verifier_result=verification_result,
                        reason="Verified status but no source evidence provided",
                    )
                return "needs_human_review", verification_result.explanation, [], verification_result.confidence

            # Use only the verified sources cited by Lyzr
            verified_sources = verification_result.source_evidence
            return final_decision, verification_result.explanation, verified_sources, verification_result.confidence

        elif verification_result.status == "no_change":
            return "no_alert", verification_result.explanation, [], verification_result.confidence

        else:  # needs_review
            return "needs_human_review", verification_result.explanation, [], verification_result.confidence

    except Exception as exc:
        logger.exception("Verification flow failed for correlation_id=%s", correlation_id)
        # On any verification failure, fall back to sending alert but log the issue
        # This preserves Nazar's existing behavior while making the failure visible
        return "alert_sent", f"Verification flow failed: {exc}", sources, None


def _flight_title(rule: FlightRule, observation: dict, evaluation: Evaluation) -> str:
    direction = "dropped" if rule.condition == "below" else "rose"
    return (
        f"Flight fare {direction}: {rule.origin} → {rule.destination} "
        f"({format_money(observation.get('current_price'), rule.currency)})"
    )


def _stock_title(rule: StockRule, observation: dict) -> str:
    if rule.condition == "absolute_change_greater_than":
        return (
            f"{rule.symbol} moved {observation.get('percent_change'):+.2f}% "
            f"(threshold {rule.threshold_percent}%)"
        )
    return (
        f"{rule.symbol} price alert at "
        f"{format_money(observation.get('current_price'), observation.get('currency', 'INR'))}"
    )


def _create_job_alerts(
    db: Session,
    watch: Watch,
    rule: JobRule,
    observation: dict,
) -> list[Alert]:
    created: list[Alert] = []
    for notice in observation.get("notices") or []:
        if alert_service._daily_alert_count(db, watch.id) >= settings.max_alerts_per_watch_per_day:
            break
        key = build_event_key(watch.id, "job", notice["notice_key"])
        existing = db.scalar(
            select(Alert).where(Alert.watch_id == watch.id, Alert.event_key == key)
        )
        if existing is not None:
            continue

        explanation, sources, research_error = _research(watch, rule, observation, notice)
        verification = _job_verification(notice, sources, rule, research_error)
        notice_source = {
            "url": notice["url"],
            "title": notice["title"],
            "domain": notice["domain"],
        }
        all_sources = [notice_source] + [
            source for source in sources if source.get("url") != notice["url"]
        ]
        if research_error:
            explanation = (
                f"{explanation}\n\nNote: research explanation unavailable ({research_error})."
                if explanation
                else f"Research explanation unavailable ({research_error}). The notice link above is from an official domain."
            )

        alert = alert_service.create_alert(
            db,
            watch,
            title=f"New job notification: {notice['title'][:120]}",
            event_key=key,
            observed_value_text=notice["title"][:120],
            explanation=explanation,
            sources=all_sources,
            verification_status=verification,
        )
        if alert is not None:
            created.append(alert)
    return created


def _create_topic_alerts(db: Session, watch: Watch, rule: TopicRule, observation: dict, previous: WatchHistory | None) -> list[Alert]:
    """First check: post the latest result as a baseline. Later checks: only results not seen before."""
    items = observation.get("items") or []
    if previous is None:
        fresh = items[:1]
    else:
        seen = {i.get("key") for i in (previous.observed_data or {}).get("items") or []}
        fresh = [i for i in items if i.get("key") not in seen]

    created: list[Alert] = []
    for item in fresh:
        explanation, sources, research_error = _research(watch, rule, observation, item)
        if research_error:
            explanation = explanation or f"Research explanation unavailable ({research_error}). The link above is the original result."
        label = {"news": "New update", "jobs": "New opening", "web": "New result"}.get(rule.source, "New result")
        alert = alert_service.create_alert(
            db,
            watch,
            title=f"{label} for “{rule.query}”: {item['title'][:120]}",
            event_key=build_event_key(watch.id, "topic", item["key"]),
            observed_value_text=item["title"][:120],
            explanation=explanation,
            sources=[{"url": item["url"], "title": item["title"], "domain": item.get("source")}] + [s for s in sources if s.get("url") != item["url"]],
            verification_status="not_applicable",
        )
        if alert is not None:
            created.append(alert)
    return created


async def check_watch(db: Session, watch: Watch, *, now=None, force: bool = False) -> dict:
    now = now or utcnow()

    if watch.status != "active":
        return {"status": "skipped", "reason": "watch_not_active"}
    if not force and watch.next_check_at and watch.next_check_at > now:
        return {"status": "skipped", "reason": "not_due"}

    try:
        rule = parse_watch_rule(watch.rule_json)
    except ValueError as exc:
        _reschedule(watch, now)
        db.commit()
        return {"status": "error", "reason": "invalid_rule", "error": str(exc)}

    provider = PROVIDERS.get(watch.watch_type)
    if provider is None:
        return {"status": "error", "reason": "unsupported_watch_type"}

    previous = db.scalar(
        select(WatchHistory)
        .where(WatchHistory.watch_id == watch.id)
        .order_by(WatchHistory.checked_at.desc(), WatchHistory.id.desc())
        .limit(1)
    )

    try:
        observation = provider.fetch(rule)
    except ProviderNotConfigured as exc:
        _reschedule(watch, now)
        db.commit()
        logger.warning("Watch %s unavailable: %s", watch.id, exc.message)
        return {"status": "unavailable", "error": exc.message}
    except ProviderError as exc:
        _reschedule(watch, now)
        db.commit()
        logger.warning("Provider failure for watch %s: %s", watch.id, exc.message)
        return {
            "status": "error",
            "reason": "provider_failed",
            "error": exc.message,
            "retryable": exc.retryable,
        }
    except Exception as exc:  # defensive: a single watch must not kill the scheduler
        db.rollback()
        logger.exception("Unexpected provider error for watch %s", watch.id)
        return {"status": "error", "reason": "provider_exception", "error": str(exc)}

    evaluation = evaluate_condition(watch.watch_type, watch.rule_json, observation)
    history = WatchHistory(
        watch_id=watch.id,
        observed_value=evaluation.current_value,
        observed_data=observation,
        checked_at=now,
    )
    db.add(history)
    _reschedule(watch, now)
    db.commit()

    previous_triggered = False
    if previous is not None:
        previous_evaluation = evaluate_condition(
            watch.watch_type, watch.rule_json, previous.observed_data or {}
        )
        previous_triggered = previous_evaluation.triggered

    new_crossing = evaluation.triggered and not previous_triggered
    created: list[Alert] = []

    if watch.watch_type == "job_notification":
        if evaluation.triggered:
            created = _create_job_alerts(db, watch, rule, observation)
    elif isinstance(rule, TopicRule) and rule.mode == "new_results":
        created = _create_topic_alerts(db, watch, rule, observation, previous)
    elif evaluation.triggered and new_crossing:
        explanation, sources, research_error = _research(watch, rule, observation)
        if research_error:
            explanation = (
                f"{explanation}\n\nNote: research explanation unavailable ({research_error})."
                if explanation
                else f"Research explanation unavailable ({research_error}). The observed value above is from the live provider."
            )
        currency = (
            rule.currency if isinstance(rule, (FlightRule, TopicRule)) else observation.get("currency", "INR")
        )
        if isinstance(rule, FlightRule):
            title = _flight_title(rule, observation, evaluation)
        elif isinstance(rule, TopicRule):
            moved = "dropped" if rule.mode == "price_below" else "rose"
            title = f"Price {moved}: {rule.query} at {format_money(evaluation.current_value, currency)}"
        else:
            title = _stock_title(rule, observation)
        observed_value_text = format_money(evaluation.current_value, currency)
        if isinstance(rule, FlightRule):
            flight_url = observation.get("source_url")
            if isinstance(flight_url, str) and flight_url.startswith(("http://", "https://")):
                sources = [
                    {"url": flight_url, "title": "Book or compare flights on Google Flights"},
                    *[source for source in sources if source.get("url") != flight_url],
                ]
        elif isinstance(rule, TopicRule) and observation.get("items"):
            cheapest = observation["items"][0]
            sources = [{"url": cheapest["url"], "title": f"{cheapest['title']} ({cheapest.get('source') or 'listing'})"}] + sources

        # Run Lyzr/BAND verification flow for threshold-based watches
        correlation_id = str(uuid.uuid4())
        final_decision, verified_explanation, verified_sources, confidence = await _run_verification_flow(
            watch=watch,
            rule=rule,
            observation=observation,
            sources=sources,
            correlation_id=correlation_id,
        )

        if final_decision == "alert_sent":
            # Use Lyzr-verified explanation and sources if available
            final_explanation = verified_explanation or explanation
            final_sources = verified_sources if verified_sources else sources
            verification_status = "verified" if confidence is not None else "not_applicable"

            event_value = f"{watch.rule_json.get('condition') or watch.rule_json.get('mode')}:{evaluation.current_value}:{day_start(now).isoformat()}"
            alert = alert_service.create_alert(
                db,
                watch,
                title=title,
                event_key=build_event_key(watch.id, "threshold", event_value),
                observed_value_text=observed_value_text,
                explanation=final_explanation,
                sources=final_sources,
                verification_status=verification_status,
            )
            if alert is not None:
                created.append(alert)
                logger.info("Alert created after verification for watch %s (correlation_id=%s)", watch.id, correlation_id)
        elif final_decision == "no_alert":
            logger.info("No alert sent - Lyzr verified no change for watch %s (correlation_id=%s)", watch.id, correlation_id)
        else:  # needs_human_review
            logger.warning("Alert held for human review for watch %s (correlation_id=%s)", watch.id, correlation_id)
            # Record the uncertainty in watch history but don't create an alert
            # The BAND room already has the disagreement notice

    return {
        "status": "ok",
        "triggered": evaluation.triggered,
        "new_crossing": new_crossing,
        "observed_value": evaluation.current_value,
        "observed_text": evaluation.observed_text,
        "alerts_created": [alert.id for alert in created],
        "checked_at": now.isoformat() + "Z",
    }


def get_watch_by_id(db: Session, watch_id: int) -> Watch:
    watch = db.get(Watch, watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    return watch


async def run_due_watches(db: Session, limit: int | None = None) -> dict:
    now = utcnow()
    watches = list(
        db.scalars(
            select(Watch)
            .where(
                Watch.status == "active",
                or_(Watch.next_check_at.is_(None), Watch.next_check_at <= now),
            )
            .order_by(Watch.next_check_at.asc())
            .limit(limit or settings.max_watches_per_run)
        ).all()
    )

    results: list[dict] = []
    for watch in watches:
        with _inflight_lock:
            if watch.id in _inflight:
                results.append({"watch_id": watch.id, "status": "skipped", "reason": "in_flight"})
                continue
            _inflight.add(watch.id)
        try:
            result = await check_watch(db, watch, force=True)
            results.append({"watch_id": watch.id, **result})
        except Exception as exc:
            db.rollback()
            logger.exception("Watch %s check crashed", watch.id)
            results.append({"watch_id": watch.id, "status": "error", "error": str(exc)})
        finally:
            with _inflight_lock:
                _inflight.discard(watch.id)

    return {
        "checked": len(results),
        "alerts_created": sum(len(item.get("alerts_created") or []) for item in results),
        "results": results,
        "ran_at": now.isoformat() + "Z",
    }


def in_flight_count() -> int:
    with _inflight_lock:
        return len(_inflight)
