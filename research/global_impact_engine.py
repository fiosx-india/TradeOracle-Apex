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

class GlobalImpactEngine:
    """Maps normalized global-market factors to directional local evidence."""

    name = "GlobalImpactEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "GLOBAL_IMPACT"]

    FACTOR_WEIGHTS = {
        "us_market": 0.20,
        "europe_market": 0.10,
        "asia_market": 0.15,
        "vix": -0.15,
        "dxy": -0.10,
        "us10y": -0.10,
        "oil": 0.10,
        "gold": -0.05,
        "global_risk": -0.15,
    }

    def self_test(self):
        return True

    def analyze(self, context):
        data = _data(context)
        contributions = []
        details = {}

        for key, weight in self.FACTOR_WEIGHTS.items():
            if key not in data:
                continue
            try:
                value = float(data[key])
                if abs(value) > 1:
                    value /= 100.0
                value = _clamp(value)
                contribution = value * weight
                contributions.append(contribution)
                details[key] = round(contribution, 6)
            except (TypeError, ValueError):
                continue

        if not contributions:
            return _result(self.name, 0.0, "No normalized global factors supplied", 0.8, 0.05)

        score = _clamp(sum(contributions))
        confidence = min(0.9, 0.20 + 0.07*len(contributions))

        return _result(
            self.name, score,
            f"global_factors_used={len(contributions)}",
            weight=0.85, confidence=confidence,
            contributions=details
        )
