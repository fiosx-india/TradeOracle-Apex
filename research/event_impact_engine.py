from __future__ import annotations
from typing import Any, Iterable, Mapping, Sequence
import math
import statistics


def _data(context: Any) -> dict:
    value = getattr(context, "data", None)
    return value if isinstance(value, dict) else {}


def _series(context: Any, *names: str) -> list[float]:
    data = _data(context)
    for name in names:
        value = data.get(name)
        if isinstance(value, (list, tuple)):
            result = []
            for x in value:
                try:
                    result.append(float(x))
                except (TypeError, ValueError):
                    continue
            if result:
                return result
    return []


def _last(values: Sequence[float], default: float = 0.0) -> float:
    return float(values[-1]) if values else default


def _mean(values: Sequence[float], default: float = 0.0) -> float:
    return statistics.fmean(values) if values else default


def _slope(values: Sequence[float], lookback: int = 10) -> float:
    values = list(values[-lookback:])
    if len(values) < 2:
        return 0.0
    base = values[0]
    if base == 0:
        return 0.0
    return (values[-1] - base) / abs(base)


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _safe_ratio(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def _ohlc(context: Any):
    data = _data(context)
    close = _series(context, "close", "closes", "price", "prices")
    high = _series(context, "high", "highs")
    low = _series(context, "low", "lows")
    open_ = _series(context, "open", "opens")
    if not high and close:
        high = close[:]
    if not low and close:
        low = close[:]
    if not open_ and close:
        open_ = close[:]
    return open_, high, low, close


def _result(name: str, score: float, reason: str, weight: float = 1.0,
            confidence: float = 0.5, **extra):
    payload = {
        "engine": name,
        "score": round(_clamp(score), 6),
        "weight": max(0.0, float(weight)),
        "confidence": round(_clamp(confidence, 0.0, 1.0), 6),
        "reason": reason,
    }
    payload.update(extra)
    return payload

class EventImpactEngine:
    """Scores normalized corporate/macro events by direction and relevance."""

    name = "EventImpactEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "EVENT_IMPACT"]

    def self_test(self):
        return True

    def analyze(self, context):
        data = _data(context)
        events = data.get("events", [])
        if not isinstance(events, list) or not events:
            return _result(self.name, 0.0, "No structured events supplied", 1.0, 0.05)

        symbol = str(getattr(context, "symbol", "")).lower()
        sector = str(getattr(context, "sector", "")).lower()
        weighted, weights = [], []

        for event in events[-100:]:
            if not isinstance(event, Mapping):
                continue

            entity = str(event.get("symbol") or event.get("company") or "").lower()
            item_sector = str(event.get("sector") or "").lower()
            relevance = 1.0
            if symbol and entity and symbol not in entity:
                relevance *= 0.35
            if sector and item_sector and sector not in item_sector:
                relevance *= 0.60

            raw = event.get("impact_score", event.get("direction", 0.0))
            if isinstance(raw, str):
                lookup = {
                    "positive": 1.0, "bullish": 1.0, "up": 1.0,
                    "negative": -1.0, "bearish": -1.0, "down": -1.0,
                }
                impact = lookup.get(raw.lower(), 0.0)
            else:
                try:
                    impact = float(raw)
                except (TypeError, ValueError):
                    impact = 0.0

            if abs(impact) > 1:
                impact /= 100.0

            weighted.append(_clamp(impact) * relevance)
            weights.append(relevance)

        score = _safe_ratio(sum(weighted), sum(weights))
        confidence = min(0.9, 0.2 + 0.08*min(len(weighted), 8))

        return _result(
            self.name, score,
            f"events_considered={len(weighted)}",
            weight=1.0, confidence=confidence
        )
