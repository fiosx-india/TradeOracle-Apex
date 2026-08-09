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

class VolumeEngine:
    """Volume participation, relative-volume and price-volume confirmation."""

    name = "VolumeEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "VOLUME"]

    def self_test(self):
        return True

    def analyze(self, context):
        close = _series(context, "close", "closes", "price", "prices")
        volume = _series(context, "volume", "volumes", "trade_volume")
        if len(close) < 3 or len(volume) < 3:
            return _result(self.name, 0.0, "Insufficient price/volume history", 0.9, 0.1)

        n = min(len(close), len(volume))
        close, volume = close[-n:], volume[-n:]

        # Index instruments can legitimately have no traded volume. Do not
        # fabricate relative-volume evidence from an all-zero series.
        if not any(v > 0 for v in volume):
            price_change = _safe_ratio(close[-1] - close[-2], abs(close[-2]))
            score = _clamp(price_change * 6.0)
            confidence = min(0.55, 0.20 + min(0.25, n / 100.0))
            return _result(
                self.name,
                score,
                "volume_unavailable_for_instrument; price_only_confirmation",
                weight=0.55,
                confidence=confidence,
                relative_volume=None,
                volume_available=False,
            )
        baseline = _mean(volume[-21:-1]) if len(volume) > 1 else _mean(volume)
        rv = _safe_ratio(volume[-1], baseline, 1.0)
        price_change = _safe_ratio(close[-1]-close[-2], abs(close[-2]))
        participation = _clamp((rv-1.0) * 0.9)

        if price_change > 0 and rv > 1.2:
            confirmation = 0.7
        elif price_change < 0 and rv > 1.2:
            confirmation = -0.7
        else:
            confirmation = _clamp(price_change * 8.0)

        score = 0.55*confirmation + 0.45*participation
        confidence = min(0.95, 0.30 + min(0.45, rv/4.0))

        return _result(
            self.name, score,
            f"relative_volume={rv:.2f}, price_change={price_change:.4f}",
            weight=0.95, confidence=confidence,
            relative_volume=round(rv, 4)
        )
