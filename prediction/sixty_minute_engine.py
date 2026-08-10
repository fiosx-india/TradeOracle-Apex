from __future__ import annotations

import statistics
from typing import Any


def _data(context: Any) -> dict:
    data = getattr(context, "data", None)
    return data if isinstance(data, dict) else {}


def _series(context: Any, *keys: str) -> list[float]:
    data = _data(context)

    for key in keys:
        values = data.get(key)

        if not isinstance(values, (list, tuple)):
            continue

        result: list[float] = []

        for value in values:
            try:
                result.append(float(value))
            except (TypeError, ValueError):
                continue

        if result:
            return result

    return []


def _clamp(
    value: float,
    minimum: float = -1.0,
    maximum: float = 1.0,
) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0

    return max(minimum, min(maximum, value))


def _safe_ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:
    if denominator == 0:
        return default

    return numerator / denominator


def _evidence(context: Any) -> list[dict]:
    evidence = getattr(context, "research_evidence", None)

    if isinstance(evidence, list):
        return [
            item
            for item in evidence
            if isinstance(item, dict)
        ]

    data = _data(context)
    evidence = data.get("research_evidence")

    if isinstance(evidence, list):
        return [
            item
            for item in evidence
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


class SixtyMinuteEngine:
    """
    Forward-looking 60-minute directional forecast.

    The engine uses only evidence available at the current evaluation time.
    It does not use future candles or future outcomes.

    Confidence is an evidence-strength estimate.
    It is NOT presented as historically calibrated probability until
    validation/calibration data has been established.
    """

    name = "SixtyMinuteEngine"
    version = "2.1.0"

    capabilities = [
        "PREDICTION",
        "60_MINUTE",
    ]

    HORIZON_MINUTES = 60

    def self_test(self) -> bool:
        return True

    def predict(self, context: Any) -> dict:
        evidence = _evidence(context)

        if not evidence:
            return _result(
                self.name,
                0.0,
                0.0,
                "No current research evidence available",
                1.25,
                direction="SIDEWAYS",
                horizon_minutes=self.HORIZON_MINUTES,
                forecast_type="FORWARD",
                calibration_status="NOT_CALIBRATED",
                prediction_available=False,
            )

        weighted_scores: list[float] = []
        effective_weights: list[float] = []

        for item in evidence:
            try:
                score = _clamp(
                    float(item.get("score", 0.0))
                )
            except (TypeError, ValueError):
                continue

            try:
                weight = max(
                    0.0,
                    float(item.get("weight", 1.0)),
                )
            except (TypeError, ValueError):
                weight = 0.0

            try:
                confidence = max(
                    0.0,
                    min(
                        1.0,
                        float(item.get("confidence", 0.0)),
                    ),
                )
            except (TypeError, ValueError):
                confidence = 0.0

            effective_weight = weight * confidence

            if effective_weight <= 0:
                continue

            weighted_scores.append(
                score * effective_weight
            )
            effective_weights.append(
                effective_weight
            )

        if not effective_weights:
            return _result(
                self.name,
                0.0,
                0.0,
                "Current evidence has no usable confidence-weighted support",
                1.25,
                direction="SIDEWAYS",
                horizon_minutes=self.HORIZON_MINUTES,
                forecast_type="FORWARD",
                calibration_status="NOT_CALIBRATED",
                prediction_available=False,
            )

        total_weight = sum(effective_weights)

        score = _safe_ratio(
            sum(weighted_scores),
            total_weight,
        )

        positive_weight = 0.0
        negative_weight = 0.0
        neutral_weight = 0.0

        for item, effective_weight in zip(
            evidence,
            effective_weights,
        ):
            try:
                item_score = float(
                    item.get("score", 0.0)
                )
            except (TypeError, ValueError):
                item_score = 0.0

            if item_score > 0.05:
                positive_weight += effective_weight
            elif item_score < -0.05:
                negative_weight += effective_weight
            else:
                neutral_weight += effective_weight

        directional_weight = (
            positive_weight + negative_weight
        )

        if directional_weight > 0:
            agreement = max(
                positive_weight,
                negative_weight,
            ) / directional_weight
        else:
            agreement = 0.0

        if score >= 0.12:
            direction = "UP"
        elif score <= -0.12:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        evidence_strength = min(
            1.0,
            total_weight / 3.0,
        )

        directional_strength = min(
            1.0,
            abs(score),
        )

        confidence = (
            0.10
            + 0.35 * evidence_strength
            + 0.35 * directional_strength
            + 0.20 * agreement
        )

        confidence = max(
            0.0,
            min(0.95, confidence),
        )

        close = _series(
            context,
            "close",
            "closes",
            "price",
            "prices",
        )

        volatility = 0.0

        if len(close) >= 6:
            returns = []

            for previous, current in zip(
                close[-6:-1],
                close[-5:],
            ):
                if previous == 0:
                    continue

                returns.append(
                    (current - previous)
                    / abs(previous)
                )

            if len(returns) >= 2:
                volatility = statistics.pstdev(
                    returns
                )

        expected_return = (
            score
            * max(volatility, 0.002)
            * 2.0
        )

        expected_return = _clamp(
            expected_return,
            -0.25,
            0.25,
        )

        uncertainty = max(
            0.0,
            1.0 - confidence,
        )

        reason = (
            f"60-minute forward forecast: "
            f"score={score:.3f}, "
            f"agreement={agreement:.2f}, "
            f"evidence_strength={evidence_strength:.2f}"
        )

        return _result(
            self.name,
            score,
            confidence,
            reason,
            1.25,
            direction=direction,
            horizon_minutes=self.HORIZON_MINUTES,
            forecast_type="FORWARD",
            prediction_available=True,
            calibration_status="NOT_CALIBRATED",
            evidence_count=len(effective_weights),
            positive_weight=round(
                positive_weight,
                6,
            ),
            negative_weight=round(
                negative_weight,
                6,
            ),
            neutral_weight=round(
                neutral_weight,
                6,
            ),
            agreement=round(
                agreement,
                6,
            ),
            evidence_strength=round(
                evidence_strength,
                6,
            ),
            expected_return=round(
                expected_return,
                6,
            ),
            uncertainty=round(
                uncertainty,
                6,
            ),
        )

    analyze = predict
