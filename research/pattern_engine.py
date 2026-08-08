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

class PatternEngine:
    """Lightweight, leakage-safe pattern similarity engine using prior returns."""

    name = "PatternEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "PATTERN"]

    def self_test(self):
        return True

    def _returns(self, close):
        return [
            _safe_ratio(b-a, abs(a))
            for a,b in zip(close[:-1], close[1:]) if a
        ]

    def analyze(self, context):
        close = _series(context, "close", "closes", "price", "prices")
        if len(close) < 25:
            return _result(self.name, 0.0, "Insufficient history for pattern similarity", 0.8, 0.1)

        returns = self._returns(close)
        window = 4
        if len(returns) < window*3:
            return _result(self.name, 0.0, "Insufficient return windows", 0.8, 0.1)

        current = returns[-window:]
        candidates = []
        # Only compare with windows ending before the current pattern.
        for end in range(window, len(returns)-window, 1):
            prior = returns[end-window:end]
            distance = math.sqrt(sum((a-b)**2 for a,b in zip(current, prior)))
            future = returns[end:end+window]
            if len(future) == window:
                candidates.append((distance, _mean(future)))

        if not candidates:
            return _result(self.name, 0.0, "No comparable historical patterns", 0.8, 0.1)

        candidates.sort(key=lambda x: x[0])
        nearest = candidates[:min(10, len(candidates))]
        weighted = []
        weights = []
        for distance, future in nearest:
            w = 1.0/(1.0 + distance*50.0)
            weighted.append(future*w)
            weights.append(w)

        expected = _safe_ratio(sum(weighted), sum(weights))
        score = _clamp(expected*15.0)
        confidence = min(0.90, 0.25 + 0.55*_safe_ratio(weights[0], sum(weights), 0.0))

        return _result(
            self.name, score,
            f"nearest_patterns={len(nearest)}, expected_forward_return={expected:.5f}",
            weight=0.8, confidence=confidence,
            sample_count=len(candidates)
        )
