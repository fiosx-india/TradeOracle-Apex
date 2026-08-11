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

        result: list[float] = []

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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
                    _safe_float(confidence),
                ),
            ),
            6,
        ),
        "weight": max(
            0.0,
            _safe_float(weight),
        ),
        "reason": reason,
    }

    result.update(extra)

    return result


class SixtyMinuteEngine:
    """
    Forecast market direction for the next 60 minutes.

    The engine produces a forward-looking scenario forecast
    from currently available evidence.

    Important:
    - This is NOT a calibrated probability.
    - Confidence represents evidence strength only.
    - Historical walk-forward validation is required before
      treating the confidence value as statistically reliable.
    - No future candles are used to generate the current forecast.
    """

    name = "SixtyMinuteEngine"
    version = "2.2.0"

    capabilities = [
        "PREDICTION",
        "60_MINUTE",
        "FORWARD_FORECAST",
    ]

    HORIZON_MINUTES = 60

    MIN_EVIDENCE_COUNT = 2
    MIN_DIRECTIONAL_EVIDENCE = 1

    def self_test(self) -> bool:
        return True

    def predict(self, context) -> dict[str, Any]:
        evidence = _evidence(context)

        usable: list[dict[str, Any]] = []

        for item in evidence:
            try:
                score = _clamp(
                    _safe_float(
                        item.get(
                            "score",
                            0.0,
                        )
                    )
                )

                weight = max(
                    0.0,
                    _safe_float(
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
                        _safe_float(
                            item.get(
                                "confidence",
                                0.0,
                            )
                        ),
                    ),
                )

            except (TypeError, ValueError):
                continue

            if weight <= 0.0:
                continue

            if confidence <= 0.0:
                continue

            usable.append(
                {
                    "engine": item.get(
                        "engine",
                        "unknown",
                    ),
                    "score": score,
                    "weight": weight,
                    "confidence": confidence,
                }
            )

        # ---------------------------------------------------------
        # 1. Evidence availability gate
        # ---------------------------------------------------------

        if len(usable) < self.MIN_EVIDENCE_COUNT:
            return _result(
                self.name,
                0.0,
                0.0,
                (
                    "Insufficient independent evidence for "
                    "a 60-minute forward forecast."
                ),
                1.25,
                direction="SIDEWAYS",
                horizon_minutes=self.HORIZON_MINUTES,
                forecast_available=False,
                calibrated=False,
                evidence_count=len(usable),
                directional_evidence_count=0,
                evidence_strength=0.0,
                expected_return=0.0,
                uncertainty=1.0,
            )

        # ---------------------------------------------------------
        # 2. Weighted evidence aggregation
        # ---------------------------------------------------------

        weighted_scores: list[float] = []
        effective_weights: list[float] = []

        for item in usable:
            effective_weight = (
                item["weight"]
                * item["confidence"]
            )

            if effective_weight <= 0.0:
                continue

            weighted_scores.append(
                item["score"]
                * effective_weight
            )

            effective_weights.append(
                effective_weight
            )

        total_weight = sum(effective_weights)

        if total_weight <= 0.0:
            return _result(
                self.name,
                0.0,
                0.0,
                "No usable weighted evidence for forecast.",
                1.25,
                direction="SIDEWAYS",
                horizon_minutes=self.HORIZON_MINUTES,
                forecast_available=False,
                calibrated=False,
                evidence_count=len(usable),
                directional_evidence_count=0,
                evidence_strength=0.0,
                expected_return=0.0,
                uncertainty=1.0,
            )

        score = _ratio(
            sum(weighted_scores),
            total_weight,
        )

        score = _clamp(score)

        # ---------------------------------------------------------
        # 3. Directional agreement
        # ---------------------------------------------------------

        positive_weight = 0.0
        negative_weight = 0.0

        for item in usable:
            effective_weight = (
                item["weight"]
                * item["confidence"]
            )

            if item["score"] > 0.05:
                positive_weight += effective_weight

            elif item["score"] < -0.05:
                negative_weight += effective_weight

        directional_weight = (
            positive_weight
            + negative_weight
        )

        if directional_weight > 0.0:
            agreement = (
                max(
                    positive_weight,
                    negative_weight,
                )
                / directional_weight
            )
        else:
            agreement = 0.0

        directional_evidence_count = sum(
            1
            for item in usable
            if abs(item["score"]) > 0.05
        )

        # ---------------------------------------------------------
        # 4. Direction decision
        # ---------------------------------------------------------

        if score >= 0.12:
            direction = "UP"

        elif score <= -0.12:
            direction = "DOWN"

        else:
            direction = "SIDEWAYS"

        # ---------------------------------------------------------
        # 5. Evidence strength
        #
        # This is NOT probability.
        # ---------------------------------------------------------

        score_strength = min(
            1.0,
            abs(score),
        )

        evidence_strength = _clamp(
            score_strength * 0.65
            + agreement * 0.35,
            0.0,
            1.0,
        )

        # ---------------------------------------------------------
        # 6. Confidence
        #
        # Confidence is deliberately conservative.
        # It must NOT be interpreted as calibrated probability.
        # ---------------------------------------------------------

        confidence = (
            0.10
            + evidence_strength * 0.70
        )

        confidence = min(
            0.85,
            confidence,
        )

        # If there is almost no directional agreement,
        # reduce confidence even when the aggregate score
        # is slightly directional.
        if agreement < 0.55:
            confidence *= 0.75

        # ---------------------------------------------------------
        # 7. Market volatility context
        #
        # Use only historical/current candles already available
        # in the context. No future information is used.
        # ---------------------------------------------------------

        close = _series(
            context,
            "close",
            "closes",
            "price",
            "prices",
        )

        volatility = 0.0

        if len(close) >= 10:
            returns: list[float] = []

            # Use recent completed observations only.
            recent_close = close[-30:]

            for previous, current in zip(
                recent_close[:-1],
                recent_close[1:],
            ):
                if previous == 0:
                    continue

                returns.append(
                    (current - previous)
                    / abs(previous)
                )

            if len(returns) >= 5:
                volatility = statistics.pstdev(
                    returns
                )

        # ---------------------------------------------------------
        # 8. Forward movement scenario
        #
        # This is an estimate, NOT a guaranteed target price.
        # ---------------------------------------------------------

        base_volatility = max(
            volatility,
            0.0005,
        )

        expected_return = (
            score
            * base_volatility
            * 2.0
        )

        expected_return = _clamp(
            expected_return,
            -0.10,
            0.10,
        )

        # ---------------------------------------------------------
        # 9. Forecast availability
        # ---------------------------------------------------------

        forecast_available = (
            len(usable) >= self.MIN_EVIDENCE_COUNT
            and directional_evidence_count
            >= self.MIN_DIRECTIONAL_EVIDENCE
        )

        if not forecast_available:
            direction = "SIDEWAYS"
            confidence = 0.0
            expected_return = 0.0

        # ---------------------------------------------------------
        # 10. Final explanation
        # ---------------------------------------------------------

        reason = (
            "60-minute forward forecast: "
            f"score={score:.3f}, "
            f"agreement={agreement:.2f}, "
            f"evidence_count={len(usable)}, "
            f"directional_evidence={directional_evidence_count}"
        )

        return _result(
            self.name,
            score,
            confidence,
            reason,
            1.25,
            direction=direction,
            horizon_minutes=self.HORIZON_MINUTES,
            forecast_available=forecast_available,
            calibrated=False,
            evidence_count=len(usable),
            directional_evidence_count=(
                directional_evidence_count
            ),
            agreement=round(
                agreement,
                6,
            ),
            evidence_strength=round(
                evidence_strength,
                6,
            ),
            volatility=round(
                volatility,
                8,
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
