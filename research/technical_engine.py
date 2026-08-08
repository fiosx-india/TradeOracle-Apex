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

class TechnicalEngine:
    """Multi-indicator technical structure engine."""

    name = "TechnicalEngine"
    version = "2.0.0"
    capabilities = ["RESEARCH", "TECHNICAL"]

    def self_test(self):
        return True

    def analyze(self, context):
        _, high, low, close = _ohlc(context)
        if len(close) < 5:
            return _result(self.name, 0.0, "Insufficient OHLC history", 0.8, 0.1)

        last = close[-1]
        fast = _mean(close[-10:])
        slow = _mean(close[-30:]) if len(close) >= 30 else _mean(close)
        trend = _safe_ratio(last - slow, abs(slow))
        ma_signal = _clamp(trend * 8.0)

        returns = []
        for a, b in zip(close[-21:-1], close[-20:]):
            if a:
                returns.append((b-a)/abs(a))
        vol = statistics.pstdev(returns) if len(returns) > 1 else 0.0

        ranges = []
        for h, l, c in zip(high[-20:], low[-20:], close[-20:]):
            ranges.append(_safe_ratio(h-l, abs(c)))
        atr_proxy = _mean(ranges)

        # A compact RSI-like oscillator.
        gains, losses = [], []
        for a, b in zip(close[-15:-1], close[-14:]):
            delta = b-a
            (gains if delta > 0 else losses).append(abs(delta))
        avg_gain = _mean(gains)
        avg_loss = _mean(losses)
        rsi = 100.0 if avg_loss == 0 and avg_gain else (
            100.0 - 100.0 / (1.0 + avg_gain / avg_loss) if avg_loss else 50.0
        )
        rsi_signal = _clamp((rsi - 50.0) / 35.0)

        breakout = 0.0
        if len(close) >= 21:
            prior_high = max(close[-21:-1])
            prior_low = min(close[-21:-1])
            if last > prior_high:
                breakout = 0.7
            elif last < prior_low:
                breakout = -0.7

        score = 0.45*ma_signal + 0.30*rsi_signal + 0.25*breakout
        confidence = min(0.95, 0.35 + min(0.4, len(close)/100) + 0.2*min(1, abs(score)))

        return _result(
            self.name, score,
            f"MA trend={ma_signal:.2f}, RSI={rsi:.1f}, breakout={breakout:.2f}",
            weight=1.1, confidence=confidence,
            indicators={"rsi": round(rsi, 2), "trend": round(trend, 6),
                        "volatility_proxy": round(vol, 6), "atr_proxy": round(atr_proxy, 6)}
        )
