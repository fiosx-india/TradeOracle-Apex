from __future__ import annotations

from typing import Any
import statistics


def _data(context) -> dict[str, Any]:
    data = getattr(context, "data", None)
    return data if isinstance(data, dict) else {}


def _get(context, key: str, default=None):
    if isinstance(context, dict):
        return context.get(key, default)

    return getattr(context, key, default)


def _series(context, *keys: str) -> list[float]:
    data = _data(context)

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


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _evidence(context) -> list[dict[str, Any]]:
    value = _get(
        context,
        "research_evidence",
        None,
    )

    if not isinstance(value, list):
        value = _data(context).get(
            "research_evidence",
            [],
        )

    if not isinstance(value, list):
        return []

    return [
        item
        for item in value
        if isinstance(item, dict)
    ]


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
                    _safe_float(
                        confidence
                    ),
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
    Forward-looking 60-minute directional forecast.

    This engine continuously estimates the direction of the
    next 60 minutes from the currently available research evidence.

    It is NOT a historically calibrated probability model.
    It does NOT guarantee the future market outcome.

    Historical calibration must be performed separately by
    the validation/calibration layer.
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

        horizon_minutes = _safe_float(
            _get(
                context,
                "horizon_minutes",
                60,
            ),
            60.0,
        )

        if horizon_minutes <= 0:
            horizon_minutes = 60.0

        usable = []
        rejected = []

        for item in evidence:

            engine_name = str(
                item.get(
                    "engine",
                    "UnknownEngine",
                )
            )

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

            reason = str(
                item.get(
                    "reason",
                    "No reason supplied",
                )
            )

            # Never allow failed or unavailable engines
            # to influence the forecast.
            if weight <= 0.0:
                rejected.append(
                    {
                        "engine": engine_name,
                        "reason": "non_positive_weight",
                    }
                )
                continue

            if confidence <= 0.0:
                rejected.append(
                    {
                        "engine": engine_name,
                        "reason": "zero_confidence",
                    }
                )
                continue

            usable.append(
                {
                    "engine": engine_name,
                    "score": score,
                    "weight": weight,
                    "confidence": confidence,
                    "reason": reason,
                }
            )

        # ---------------------------------------------------------
        # No usable evidence
        # ---------------------------------------------------------

        if not usable:

            return _result(
                self.name,
                0.0,
                0.0,
                "No usable research evidence is available.",
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=int(
                    horizon_minutes
                ),
                forecast_valid=False,
                evidence_count=len(evidence),
                usable_evidence_count=0,
                rejected_evidence_count=len(rejected),
                agreement=0.0,
                evidence_quality=0.0,
                calibration_status="NOT_CALIBRATED",
            )

        # ---------------------------------------------------------
        # Weighted directional score
        # ---------------------------------------------------------

        weighted_scores = [
            item["score"]
            * item["weight"]
            * item["confidence"]
            for item in usable
        ]

        effective_weights = [
            item["weight"]
            * item["confidence"]
            for item in usable
        ]

        total_weight = sum(
            effective_weights
        )

        if total_weight <= 0.0:

            return _result(
                self.name,
                0.0,
                0.0,
                "Usable evidence has no effective weight.",
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=int(
                    horizon_minutes
                ),
                forecast_valid=False,
                evidence_count=len(evidence),
                usable_evidence_count=len(usable),
                rejected_evidence_count=len(rejected),
                agreement=0.0,
                evidence_quality=0.0,
                calibration_status="NOT_CALIBRATED",
            )

        score = (
            sum(weighted_scores)
            / total_weight
        )

        score = _clamp(score)

        # ---------------------------------------------------------
        # Directional agreement
        # ---------------------------------------------------------

        positive_weight = sum(
            item["weight"]
            * item["confidence"]
            for item in usable
            if item["score"] > 0.05
        )

        negative_weight = sum(
            item["weight"]
            * item["confidence"]
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

        agreement = max(
            0.0,
            min(
                1.0,
                agreement,
            ),
        )

        # ---------------------------------------------------------
        # Evidence confidence
        # ---------------------------------------------------------

        average_confidence = (
            sum(
                item["confidence"]
                for item in usable
            )
            / len(usable)
        )

        coverage = min(
            1.0,
            len(usable)
            / max(
                1.0,
                len(evidence),
            ),
        )

        evidence_quality = (
            average_confidence
            * agreement
            * coverage
        )

        # ---------------------------------------------------------
        # Model-derived confidence
        #
        # IMPORTANT:
        # This is NOT statistical probability.
        # It is only confidence in the current evidence.
        # ---------------------------------------------------------

        confidence = (
            0.10
            + 0.35 * abs(score)
            + 0.35 * agreement
            + 0.20 * average_confidence
        )

        confidence *= coverage

        confidence = max(
            0.0,
            min(
                0.95,
                confidence,
            ),
        )

        # ---------------------------------------------------------
        # Direction
        # ---------------------------------------------------------

        if score >= 0.12:
            direction = "UP"

        elif score <= -0.12:
            direction = "DOWN"

        else:
            direction = "SIDEWAYS"

        # ---------------------------------------------------------
        # Forecast validity
        #
        # A directional forecast requires at least two
        # independent usable evidence sources.
        # ---------------------------------------------------------

        if direction == "SIDEWAYS":

            forecast_valid = (
                abs(score) >= 0.05
                and len(usable) >= 2
            )

        else:

            forecast_valid = (
                len(usable) >= 2
                and agreement >= 0.55
            )

        # ---------------------------------------------------------
        # Current forward-looking movement context
        # ---------------------------------------------------------

        close = _series(
            context,
            "close",
            "closes",
            "price",
            "prices",
        )

        volatility = 0.0

        if len(close) >= 6:

            returns = [
                (b - a) / abs(a)
                for a, b in zip(
                    close[-6:-1],
                    close[-5:],
                )
                if a
            ]

            if len(returns) > 1:
                volatility = (
                    statistics.pstdev(
                        returns
                    )
                )

        # Scenario estimate only.
        # Never present this as a guaranteed price move.
        expected_return = (
            score
            * max(
                volatility,
                0.002,
            )
            * 2.0
        )

        expected_return = _clamp(
            expected_return
        )

        reasons = [
            item["reason"]
            for item in usable
            if item.get("reason")
        ]

        return _result(
            self.name,
            score,
            confidence,
            (
                f"Forward {int(horizon_minutes)}-minute "
                f"directional forecast from "
                f"{len(usable)} usable research signals."
            ),
            1.25,
            direction=direction,
            horizon_minutes=int(
                horizon_minutes
            ),
            forecast_valid=forecast_valid,
            evidence_count=len(evidence),
            usable_evidence_count=len(usable),
            rejected_evidence_count=len(rejected),
            agreement=round(
                agreement,
                6,
            ),
            evidence_quality=round(
                evidence_quality,
                6,
            ),
            average_evidence_confidence=round(
                average_confidence,
                6,
            ),
            expected_return=round(
                expected_return,
                6,
            ),
            uncertainty=round(
                max(
                    0.0,
                    1.0 - confidence,
                ),
                6,
            ),
            calibration_status="NOT_CALIBRATED",
            contributing_engines=[
                item["engine"]
                for item in usable
            ],
            rejected_engines=rejected,
            evidence_reasons=reasons,
        )

    analyze = predict
