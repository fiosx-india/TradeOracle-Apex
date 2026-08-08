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

class MomentumEngine:
    """Multi-horizon momentum and acceleration engine."""

    name = "MomentumEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "MOMENTUM"]

    def self_test(self):
        return True

    def analyze(self, context):
        close = _series(context, "close", "closes", "price", "prices")
        if len(close) < 4:
            return _result(self.name, 0.0, "Insufficient price history", 1.0, 0.1)

        horizons = [3, 5, 10, 20]
        signals = []
        details = {}
        for h in horizons:
            if len(close) > h:
                ret = _safe_ratio(close[-1]-close[-1-h], abs(close[-1-h]))
                sig = _clamp(ret * 12.0)
                signals.append(sig)
                details[f"{h}bar_return"] = round(ret, 6)

        short = _slope(close, 5)
        long = _slope(close, min(20, len(close)))
        acceleration = short - long
        accel_signal = _clamp(acceleration * 10.0)

        score = 0.65*_mean(signals) + 0.35*accel_signal
        agreement = 1.0 - min(1.0, statistics.pstdev(signals) * 2) if len(signals)>1 else 0.3
        confidence = min(0.95, 0.35 + 0.5*agreement + 0.1*min(1, len(close)/100))

        return _result(
            self.name, score,
            f"multi-horizon momentum={score:.2f}, acceleration={accel_signal:.2f}",
            weight=1.0, confidence=confidence,
            horizons=details, acceleration=round(acceleration, 6)
        )
