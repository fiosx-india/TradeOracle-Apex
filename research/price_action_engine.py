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

class PriceActionEngine:
    """Candle structure, range expansion and rejection analysis."""

    name = "PriceActionEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "PRICE_ACTION"]

    def self_test(self):
        return True

    def analyze(self, context):
        open_, high, low, close = _ohlc(context)
        n = min(map(len, (open_, high, low, close))) if all((open_,high,low,close)) else 0
        if n < 3:
            return _result(self.name, 0.0, "Insufficient OHLC data", 1.0, 0.1)

        o, h, l, c = open_[-n:], high[-n:], low[-n:], close[-n:]
        body = c[-1] - o[-1]
        rng = max(h[-1]-l[-1], 1e-12)
        upper = h[-1] - max(o[-1], c[-1])
        lower = min(o[-1], c[-1]) - l[-1]
        body_ratio = abs(body)/rng

        close_location = ((c[-1]-l[-1]) / rng) * 2.0 - 1.0
        expansion = _safe_ratio(
            rng, _mean([hh-ll for hh,ll in zip(h[-11:-1], l[-11:-1])]),
            1.0
        )
        direction = _clamp(body/rng)

        rejection = 0.0
        if lower > abs(body)*1.5 and close_location > 0.2:
            rejection += 0.45
        if upper > abs(body)*1.5 and close_location < -0.2:
            rejection -= 0.45

        score = _clamp(0.55*direction + 0.25*close_location + 0.20*rejection)
        if expansion > 1.4:
            score = _clamp(score * 1.15)

        confidence = min(0.95, 0.35 + 0.35*body_ratio + 0.15*min(1, expansion/2))

        return _result(
            self.name, score,
            f"body_ratio={body_ratio:.2f}, range_expansion={expansion:.2f}, rejection={rejection:.2f}",
            weight=1.0, confidence=confidence,
            candle={"body_ratio": round(body_ratio,4), "range_expansion": round(expansion,4)}
        )
