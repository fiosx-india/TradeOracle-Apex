from __future__ import annotations

import statistics
from typing import Any


def _data(ctx: Any) -> dict:
    data = getattr(ctx, "data", None)
    return data if isinstance(data, dict) else {}


def _series(ctx: Any, *keys: str) -> list[float]:
    data = _data(ctx)

    for key in keys:
        values = data.get(key)

        if not isinstance(values, (list, tuple)):
            continue

        result = []

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
    low: float = -1.0,
    high: float = 1.0,
) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0

    return max(low, min(high, value))


def _safe_ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:
    if not denominator:
        return default

    return numerator / denominator


def _evidence(ctx: Any) -> list[dict]:
    evidence = getattr(ctx, "research_evidence", None)

    if isinstance(evidence, list):
        return [
            item
            for item in evidence
            if isinstance(item, dict)
        ]

    data = _data(ctx)

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
    Forecast the directional bias for the next 60 minutes.

    This engine produces a model-derived forecast from the evidence
    available at the current market timestamp.

    It does not claim historical probability calibration and it does
    not guarantee the future market outcome.
    """

    name = "SixtyMinuteEngine"
    version = "2.1.0"

    capabilities = [
        "PREDICTION",
        "60_MINUTE",
        "FORWARD_FORECAST",
    ]

    def self_test(self) -> bool:
        return True

    def predict(self, context: Any) -> dict:
        evidence = _evidence(context)

        if not evidence:
            return _result(
                self.name,
                0.0,
                0.05,
                "Insufficient evidence for 60-minute forecast",
                1.2,
                direction="SIDEWAYS",
                horizon_minutes=60,
                forecast_type="MODEL_DERIVED",
            )

        weighted_scores = []
        weighted_confidences = []

        for item in evidence:
            try:
                score = _clamp(
                    float(item.get("score", 0.0))
                )
            except (TypeError, ValueError):
                score = 0.0

            try:
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
            except (TypeError, ValueError):
                confidence = 0.0

            try:
                weight = max(
                    0.0,
                    float(
                        item.get(
                            "weight",
                            1.0,
                        )
                    ),
                )
            except (TypeError, ValueError):
                weight = 1.0

            effective_weight = (
                weight * confidence
            )

            if effective_weight <= 0:
                continue

            weighted_scores.append(
                score * effective_weight
            )

            weighted_confidences.append(
                effective_weight
            )

        total_weight = sum(
            weighted_confidences
        )

        if total_weight <= 0:
            return _result(
                self.name,
                0.0,
                0.05,
                "Available evidence has no usable confidence",
                1.2,
                direction="SIDEWAYS",
                horizon_minutes=60,
                forecast_type="MODEL_DERIVED",
            )

        score = _safe_ratio(
            sum(weighted_scores),
            total_weight,
        )

        positive_weight = 0.0
        negative_weight = 0.0

        for item in evidence:
            try:
                item_score = float(
                    item.get("score", 0.0)
                )
            except (TypeError, ValueError):
                item_score = 0.0

            try:
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
            except (TypeError, ValueError):
                confidence = 0.0

            try:
                weight = max(
                    0.0,
                    float(
                        item.get(
                            "weight",
                            1.0,
                        )
                    ),
                )
            except (TypeError, ValueError):
                weight = 1.0

            effective_weight = (
                weight * confidence
            )

            if item_score > 0.05:
                positive_weight += effective_weight

            elif item_score < -0.05:
                negative_weight += effective_weight

        agreement = _safe_ratio(
            max(
                positive_weight,
                negative_weight,
            ),
            total_weight,
        )

        if score >= 0.12:
            direction = "UP"

        elif score <= -0.12:
            direction = "DOWN"

        else:
            direction = "SIDEWAYS"

        # This is intentionally a model-confidence estimate.
        # It is NOT presented as statistically calibrated probability.
        confidence = min(
            0.95,
            0.20
            + 0.55 * abs(score)
            + 0.30 * agreement,
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
                    _safe_ratio(
                        current - previous,
                        abs(previous),
                    )
                )

            if len(returns) > 1:
                volatility = statistics.pstdev(
                    returns
                )

        expected_return = (
            _clamp(score)
            * max(
                volatility,
                0.002,
            )
            * 2.0
        )

        return _result(
            self.name,
            score,
            confidence,
            (
                "60-minute forward forecast "
                f"score={score:.3f}, "
                f"agreement={agreement:.2f}"
            ),
            1.25,
            direction=direction,
            horizon_minutes=60,
            forecast_type="MODEL_DERIVED",
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
                    1.0 - confidence,
                ),
                6,
            ),
        )

    analyze = predict
