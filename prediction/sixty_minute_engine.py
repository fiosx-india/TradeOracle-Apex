from __future__ import annotations

import statistics
from typing import Any


def _data(context) -> dict:
    data = getattr(context, "data", None)
    return data if isinstance(data, dict) else {}


def _series(context, *keys) -> list[float]:
    data = _data(context)

    for key in keys:
        value = data.get(key)

        if not isinstance(value, (list, tuple)):
            continue

        result = []

        for item in value:
            try:
                result.append(float(item))
            except (TypeError, ValueError):
                continue

        if result:
            return result

    return []


def _clamp(
    value: float,
    low: float = -1.0,
    high: float = 1.0,
) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0

    return max(low, min(high, value))


def _ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:
    if denominator == 0:
        return default

    return numerator / denominator


def _evidence(context) -> list[dict[str, Any]]:
    value = getattr(
        context,
        "research_evidence",
        None,
    )

    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    data = _data(context)

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
    **extra,
) -> dict[str, Any]:
    result = {
        "engine": engine,
        "score": round(
            _clamp(score),
            6,
        ),
        "confidence": round(
            max(
                0.0,
                min(
                    1.0,
                    float(confidence),
                ),
            ),
            6,
        ),
        "weight": max(
            0.0,
            float(weight),
        ),
        "reason": reason,
    }

    result.update(extra)

    return result


class SixtyMinuteEngine:
    """
    Forecast market direction over the next 60 minutes.

    This is a forward-looking scenario forecast based on
    currently available market evidence.

    It is NOT a statistically calibrated probability model
    until historical walk-forward calibration is performed.
    """

    name = "SixtyMinuteEngine"
    version = "2.1.0"

    capabilities = [
        "PREDICTION",
        "60_MINUTE",
    ]

    def self_test(self) -> bool:
        return True

    def predict(self, context) -> dict[str, Any]:
        evidence = _evidence(context)

        usable = []

        for item in evidence:
            try:
                score = _clamp(
                    float(
                        item.get(
                            "score",
                            0.0,
                        )
                    )
                )

                weight = max(
                    0.0,
                    float(
                        item.get(
                            "weight",
                            0.0,
                        )
                    ),
                )

                confidence = max(
                    0.0,
                    min(
                        1.0,
                        float(
                            item.get(
                                "confidence",
                                0.0,
                            )
                        ),
                    ),
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if weight <= 0 or confidence <= 0:
                continue

            usable.append(
                {
                    "score": score,
                    "weight": weight,
                    "confidence": confidence,
                    "engine": item.get(
                        "engine",
                        "unknown",
                    ),
                }
            )

        if not usable:
            return _result(
                self.name,
                0.0,
                0.0,
                "No usable evidence for 60-minute forward forecast.",
                1.25,
                direction="SIDEWAYS",
                horizon_minutes=60,
                forecast_available=False,
                calibrated=False,
                uncertainty=1.0,
            )

        weighted_scores = []

        total_weight = 0.0

        for item in usable:
            effective_weight = (
                item["weight"]
                * item["confidence"]
            )

            weighted_scores.append(
                item["score"]
                * effective_weight
            )

            total_weight += effective_weight

        if total_weight <= 0:
            return _result(
                self.name,
                0.0,
                0.0,
                "Evidence weights are unusable.",
                1.25,
                direction="SIDEWAYS",
                horizon_minutes=60,
                forecast_available=False,
                calibrated=False,
                uncertainty=1.0,
            )

        score = _ratio(
            sum(weighted_scores),
            total_weight,
        )

        positive_weight = sum(
            item["weight"] * item["confidence"]
            for item in usable
            if item["score"] > 0.05
        )

        negative_weight = sum(
            item["weight"] * item["confidence"]
            for item in usable
            if item["score"] < -0.05
        )

        directional_weight = (
            positive_weight
            + negative_weight
        )

        if directional_weight > 0:
            agreement = (
                max(
                    positive_weight,
                    negative_weight,
                )
                / directional_weight
            )
        else:
            agreement = 0.0

        if score >= 0.12:
            direction = "UP"

        elif score <= -0.12:
            direction = "DOWN"

        else:
            direction = "SIDEWAYS"

        # This is evidence strength, NOT calibrated probability.
        evidence_strength = min(
            1.0,
            abs(score) * 0.65
            + agreement * 0.35,
        )

        confidence = (
            0.10
            + evidence_strength * 0.70
        )

        confidence = min(
            0.85,
            confidence,
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

            if len(returns) > 1:
                volatility = statistics.pstdev(
                    returns
                )

        # Scenario movement estimate only.
        expected_return = (
            score
            * max(
                volatility,
                0.002,
            )
            * 2.0
        )

        expected_return = _clamp(
            expected_return,
            -0.10,
            0.10,
        )

        return _result(
            self.name,
            score,
            confidence,
            (
                "60-minute forward forecast: "
                f"score={score:.3f}, "
                f"agreement={agreement:.2f}, "
                f"evidence_count={len(usable)}"
            ),
            1.25,
            direction=direction,
            horizon_minutes=60,
            forecast_available=True,
            calibrated=False,
            evidence_count=len(usable),
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
                1.0 - confidence,
                6,
            ),
        )

    analyze = predict
