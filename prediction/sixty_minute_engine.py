from __future__ import annotations

from typing import Any, Mapping
import math
import statistics


def _data(ctx: Any) -> dict:
    data = getattr(ctx, "data", None)
    return data if isinstance(data, dict) else {}


def _series(ctx: Any, *keys: str) -> list[float]:
    data = _data(ctx)

    for key in keys:
        value = data.get(key)

        if isinstance(value, (list, tuple)):
            output: list[float] = []

            for item in value:
                try:
                    number = float(item)
                except (TypeError, ValueError):
                    continue

                if math.isfinite(number):
                    output.append(number)

            if output:
                return output

    return []


def _clamp(
    value: float,
    low: float = -1.0,
    high: float = 1.0,
) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0

    if not math.isfinite(value):
        return 0.0

    return max(low, min(high, value))


def _ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:
    if denominator == 0:
        return default

    value = numerator / denominator

    if not math.isfinite(value):
        return default

    return value


def _evidence(ctx: Any) -> list[dict]:
    value = getattr(ctx, "research_evidence", None)

    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    data = _data(ctx)
    value = data.get("research_evidence")

    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    return []


def _result(
    engine: str,
    score: float,
    confidence: float,
    reason: str,
    weight: float = 1.0,
    **extra: Any,
) -> dict:
    result = {
        "engine": engine,
        "score": round(_clamp(score), 6),
        "confidence": round(
            max(0.0, min(1.0, float(confidence))),
            6,
        ),
        "weight": max(0.0, float(weight)),
        "reason": reason,
    }

    result.update(extra)
    return result


def _direction(score: float) -> str:
    if score >= 0.12:
        return "UP"

    if score <= -0.12:
        return "DOWN"

    return "SIDEWAYS"


def _calculate_recent_volatility(
    closes: list[float],
) -> float:
    if len(closes) < 6:
        return 0.0

    returns: list[float] = []

    for previous, current in zip(
        closes[-6:-1],
        closes[-5:],
    ):
        if previous == 0:
            continue

        value = (current - previous) / abs(previous)

        if math.isfinite(value):
            returns.append(value)

    if len(returns) < 2:
        return 0.0

    return statistics.pstdev(returns)


def _calculate_momentum(
    closes: list[float],
) -> float:
    if len(closes) < 8:
        return 0.0

    short_move = _ratio(
        closes[-1] - closes[-3],
        abs(closes[-3]),
    )

    medium_move = _ratio(
        closes[-1] - closes[-6],
        abs(closes[-6]),
    )

    return _clamp(
        (short_move * 0.55)
        + (medium_move * 0.45)
    )


def _calculate_acceleration(
    closes: list[float],
) -> float:
    if len(closes) < 8:
        return 0.0

    recent = _ratio(
        closes[-1] - closes[-3],
        abs(closes[-3]),
    )

    previous = _ratio(
        closes[-3] - closes[-7],
        abs(closes[-7]),
    )

    return _clamp(
        (recent - previous) * 12.0
    )


def _calculate_evidence_score(
    evidence: list[dict],
) -> tuple[float, float, int]:
    weighted_scores: list[float] = []
    effective_weights: list[float] = []

    for item in evidence:
        try:
            score = _clamp(item.get("score", 0.0))
            confidence = max(
                0.0,
                min(1.0, float(item.get("confidence", 0.0))),
            )
            weight = max(
                0.0,
                float(item.get("weight", 1.0)),
            )
        except (TypeError, ValueError):
            continue

        if weight <= 0 or confidence <= 0:
            continue

        effective_weight = weight * confidence

        weighted_scores.append(
            score * effective_weight
        )
        effective_weights.append(
            effective_weight
        )

    if not effective_weights:
        return 0.0, 0.0, 0

    total_weight = sum(effective_weights)

    score = _ratio(
        sum(weighted_scores),
        total_weight,
    )

    positive_weight = sum(
        weight
        for item, weight in zip(
            evidence,
            effective_weights,
        )
        if float(item.get("score", 0.0)) > 0.05
    )

    negative_weight = sum(
        weight
        for item, weight in zip(
            evidence,
            effective_weights,
        )
        if float(item.get("score", 0.0)) < -0.05
    )

    agreement = _ratio(
        max(
            positive_weight,
            negative_weight,
        ),
        total_weight,
    )

    return (
        _clamp(score),
        max(0.0, min(1.0, agreement)),
        len(effective_weights),
    )


def _forecast_for_horizon(
    base_score: float,
    momentum: float,
    acceleration: float,
    agreement: float,
    horizon_minutes: int,
) -> tuple[float, float, str]:
    """
    Produce a directional scenario for the requested future horizon.

    This is a forecast score, not a guaranteed future price prediction.
    It must be validated later with walk-forward historical data.
    """

    if horizon_minutes <= 15:
        momentum_weight = 0.45
        acceleration_weight = 0.35
        evidence_weight = 0.20

    elif horizon_minutes <= 30:
        momentum_weight = 0.35
        acceleration_weight = 0.25
        evidence_weight = 0.40

    else:
        momentum_weight = 0.20
        acceleration_weight = 0.10
        evidence_weight = 0.70

    score = _clamp(
        (base_score * evidence_weight)
        + (momentum * momentum_weight)
        + (acceleration * acceleration_weight)
    )

    directional_strength = abs(score)

    confidence = (
        0.20
        + (directional_strength * 0.50)
        + (agreement * 0.25)
    )

    confidence = max(
        0.05,
        min(0.95, confidence),
    )

    return (
        score,
        confidence,
        _direction(score),
    )


class SixtyMinuteEngine:
    """
    Evidence-based forward forecast engine.

    The engine estimates directional scenarios for the next
    15, 30 and 60 minutes from the current market context.

    It does NOT claim that a movement can be detected exactly
    15/30/60 minutes before it occurs.

    Historical walk-forward validation is required before
    interpreting confidence as empirical probability.
    """

    name = "SixtyMinuteEngine"
    version = "3.0.0"

    capabilities = [
        "PREDICTION",
        "FORWARD_FORECAST",
        "15_MINUTE",
        "30_MINUTE",
        "60_MINUTE",
    ]

    def self_test(self) -> bool:
        return True

    def predict(
        self,
        context: Any,
    ) -> dict:
        evidence = _evidence(context)

        closes = _series(
            context,
            "close",
            "closes",
            "price",
            "prices",
        )

        if len(closes) < 8:
            return _result(
                self.name,
                0.0,
                0.05,
                "Insufficient price history for forward forecasting",
                1.25,
                direction="SIDEWAYS",
                horizon_minutes=60,
                forecasts={},
                forecast_status="INSUFFICIENT_DATA",
                calibrated=False,
            )

        base_score, agreement, evidence_count = (
            _calculate_evidence_score(evidence)
        )

        momentum = _calculate_momentum(closes)
        acceleration = _calculate_acceleration(closes)

        volatility = _calculate_recent_volatility(
            closes
        )

        forecasts: dict[str, dict] = {}

        for horizon in (15, 30, 60):
            score, confidence, direction = (
                _forecast_for_horizon(
                    base_score=base_score,
                    momentum=momentum,
                    acceleration=acceleration,
                    agreement=agreement,
                    horizon_minutes=horizon,
                )
            )

            forecasts[str(horizon)] = {
                "horizon_minutes": horizon,
                "direction": direction,
                "score": round(score, 6),
                "confidence": round(confidence, 6),
            }

        sixty = forecasts["60"]

        expected_return = (
            float(sixty["score"])
            * max(volatility, 0.002)
            * 2.0
        )

        expected_return = _clamp(
            expected_return,
            -0.20,
            0.20,
        )

        return _result(
            self.name,
            float(sixty["score"]),
            float(sixty["confidence"]),
            (
                "Forward forecast built from current evidence, "
                f"momentum={momentum:.3f}, "
                f"acceleration={acceleration:.3f}, "
                f"agreement={agreement:.2f}"
            ),
            1.25,
            direction=sixty["direction"],
            horizon_minutes=60,
            forecasts=forecasts,
            evidence_count=evidence_count,
            momentum=round(momentum, 6),
            acceleration=round(acceleration, 6),
            volatility=round(volatility, 8),
            expected_return=round(
                expected_return,
                6,
            ),
            agreement=round(
                agreement,
                6,
            ),
            uncertainty=round(
                max(
                    0.0,
                    1.0 - float(sixty["confidence"]),
                ),
                6,
            ),
            calibrated=False,
            forecast_status="SCENARIO_FORECAST",
        )

    analyze = predict
