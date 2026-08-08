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

class SentimentEngine:
    """Aggregates normalized sentiment from news/social/event inputs."""

    name = "SentimentEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "SENTIMENT"]

    def self_test(self):
        return True

    def analyze(self, context):
        data = _data(context)
        values = []

        for key in ("sentiment_scores", "sentiment", "news_sentiment"):
            value = data.get(key)
            if isinstance(value, (list, tuple)):
                for item in value:
                    try:
                        x = float(item)
                        if abs(x) > 1:
                            x /= 100.0
                        values.append(_clamp(x))
                    except (TypeError, ValueError):
                        pass
                if values:
                    break
            elif isinstance(value, (int, float)):
                x = float(value)
                if abs(x) > 1:
                    x /= 100.0
                values.append(_clamp(x))
                break

        if not values:
            return _result(self.name, 0.0, "No normalized sentiment supplied", 0.8, 0.05)

        mean = _mean(values)
        dispersion = statistics.pstdev(values) if len(values) > 1 else 0.0
        agreement = _clamp(1.0 - dispersion*1.5, 0.0, 1.0)
        confidence = min(0.9, 0.2 + 0.55*agreement + 0.1*min(len(values), 10)/10)

        return _result(
            self.name, mean,
            f"sentiment_mean={mean:.3f}, dispersion={dispersion:.3f}",
            weight=0.8, confidence=confidence,
            sample_count=len(values)
        )
