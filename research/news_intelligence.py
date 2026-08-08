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

class NewsIntelligence:
    """Maps structured news/event records to company/sector evidence.

    This engine intentionally consumes normalized records supplied by data.news_data;
    it does not invent headlines or perform an external search by itself.
    """

    name = "NewsIntelligence"
    version = "2.0.0"
    capabilities = ["RESEARCH", "NEWS", "EVENTS"]

    def self_test(self):
        return True

    def _items(self, context):
        data = _data(context)
        for key in ("news", "news_items", "articles", "headlines"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return []

    def analyze(self, context):
        items = self._items(context)
        if not items:
            return _result(self.name, 0.0, "No normalized news records supplied", 0.9, 0.05)

        symbol = str(getattr(context, "symbol", "")).lower()
        sector = str(getattr(context, "sector", "")).lower()
        score_sum = 0.0
        weight_sum = 0.0
        relevant = 0

        for item in items[-100:]:
            if not isinstance(item, Mapping):
                continue

            text = str(item.get("text") or item.get("headline") or "").lower()
            entity = str(item.get("symbol") or item.get("company") or "").lower()
            item_sector = str(item.get("sector") or "").lower()

            relevance = 1.0
            if symbol and entity and symbol not in entity:
                relevance *= 0.35
            if sector and item_sector and sector not in item_sector:
                relevance *= 0.55

            raw = item.get("impact_score", item.get("score", item.get("sentiment", 0.0)))
            try:
                impact = float(raw)
            except (TypeError, ValueError):
                impact = 0.0

            # Permit 0..100 sentiment as an input convention.
            if abs(impact) > 1:
                impact = impact / 100.0
            impact = _clamp(impact)

            if text or entity or item_sector:
                relevant += 1
                score_sum += impact * relevance
                weight_sum += relevance

        score = _safe_ratio(score_sum, weight_sum)
        confidence = min(0.9, 0.15 + 0.08*min(relevant, 8))

        return _result(
            self.name, score,
            f"normalized_news_records={len(items)}, relevant_records={relevant}",
            weight=0.9, confidence=confidence,
            relevant_records=relevant
        )
