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

class CorrelationEngine:
    """Cross-asset and peer correlation context engine."""

    name = "CorrelationEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "CORRELATION"]

    def self_test(self):
        return True

    def analyze(self, context):
        data = _data(context)
        peer = data.get("peer_returns")
        benchmark = data.get("benchmark_returns")

        if not isinstance(peer, (list, tuple)) or not isinstance(benchmark, (list, tuple)):
            return _result(self.name, 0.0, "Peer and benchmark return series not supplied", 0.7, 0.05)

        n = min(len(peer), len(benchmark))
        if n < 5:
            return _result(self.name, 0.0, "Insufficient paired return history", 0.7, 0.05)

        x, y = [], []
        for a, b in zip(peer[-n:], benchmark[-n:]):
            try:
                x.append(float(a))
                y.append(float(b))
            except (TypeError, ValueError):
                pass

        if len(x) < 5:
            return _result(self.name, 0.0, "Invalid paired return history", 0.7, 0.05)

        mx, my = _mean(x), _mean(y)
        cov = sum((a-mx)*(b-my) for a,b in zip(x,y)) / len(x)
        sx = statistics.pstdev(x)
        sy = statistics.pstdev(y)

        corr = _safe_ratio(cov, sx*sy)
        corr = _clamp(corr)

        # Correlation alone has no direction. Use the benchmark's latest
        # standardized movement as the directional context.
        benchmark_mean = _mean(y)
        directional = _clamp(corr * _clamp(benchmark_mean * 12.0))

        confidence = min(0.9, 0.25 + 0.60*abs(corr))

        return _result(
            self.name, directional,
            f"correlation={corr:.3f}, benchmark_mean_return={benchmark_mean:.5f}",
            weight=0.65, confidence=confidence,
            correlation=round(corr, 6),
            sample_count=len(x)
        )
