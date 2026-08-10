from __future__ import annotations

from typing import Any


def _get(context, key: str, default=None):
    if isinstance(context, dict):
        return context.get(key, default)

    return getattr(context, key, default)


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
    value = _get(context, "prediction_evidence", None)

    if not isinstance(value, list):
        value = _get(context, "research_evidence", None)

    if not isinstance(value, list):
        data = _get(context, "data", {})
        if isinstance(data, dict):
            value = data.get("prediction_evidence", [])
            if not isinstance(value, list):
                value = data.get("research_evidence", [])

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


class ProbabilityEngine:
    """
    Converts directional model evidence into scenario scores.

    IMPORTANT:
    This engine does NOT claim historically calibrated probability.

    The returned values are model-derived scenario weights only.
    Historical probability calibration must be performed by the
    validation/calibration layer using realized future outcomes.
    """

    name = "ProbabilityEngine"
    version = "2.1.0"

    capabilities = [
        "PREDICTION",
        "PROBABILITY",
    ]

    def self_test(self) -> bool:
        return True

    def predict(self, context) -> dict[str, Any]:
        evidence = _evidence(context)

        usable: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for item in evidence:
            engine = str(
                item.get(
                    "engine",
                    "UnknownEngine",
                )
            )

            score = _clamp(
                _safe_float(
                    item.get("score", 0.0)
                )
            )

            confidence = max(
                0.0,
                min(
                    1.0,
                    _safe_float(
                        item.get("confidence", 0.0)
                    ),
                ),
            )

            weight = max(
                0.0,
                _safe_float(
                    item.get("weight", 0.0)
                ),
            )

            if weight <= 0.0:
                rejected.append(
                    {
                        "engine": engine,
                        "reason": "non_positive_weight",
                    }
                )
                continue

            if confidence <= 0.0:
                rejected.append(
                    {
                        "engine": engine,
                        "reason": "zero_confidence",
                    }
                )
                continue

            usable.append(
                {
                    "engine": engine,
                    "score": score,
                    "confidence": confidence,
                    "weight": weight,
                }
            )

        if not usable:
            return _result(
                self.name,
                0.0,
                0.0,
                "No usable evidence for scenario estimation.",
                0.0,
                probabilities={
                    "UP": 0.0,
                    "DOWN": 0.0,
                    "SIDEWAYS": 0.0,
                },
                probability_status="UNAVAILABLE",
                calibrated=False,
                calibration_status="NOT_CALIBRATED",
                forecast_valid=False,
                evidence_count=len(evidence),
                usable_evidence_count=0,
                rejected_evidence_count=len(rejected),
            )

        effective_weights = [
            item["weight"] * item["confidence"]
            for item in usable
        ]

        total_weight = sum(effective_weights)

        if total_weight <= 0.0:
            return _result(
                self.name,
                0.0,
                0.0,
                "Evidence has no effective predictive weight.",
                0.0,
                probabilities={
                    "UP": 0.0,
                    "DOWN": 0.0,
                    "SIDEWAYS": 0.0,
                },
                probability_status="UNAVAILABLE",
                calibrated=False,
                calibration_status="NOT_CALIBRATED",
                forecast_valid=False,
                evidence_count=len(evidence),
                usable_evidence_count=len(usable),
                rejected_evidence_count=len(rejected),
            )

        weighted_score = sum(
            item["score"] * item["weight"] * item["confidence"]
            for item in usable
        ) / total_weight

        score = _clamp(weighted_score)

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

        neutral_weight = max(
            0.0,
            total_weight
            - positive_weight
            - negative_weight,
        )

        directional_weight = (
            positive_weight
            + negative_weight
        )

        if directional_weight > 0.0:
            directional_bias = (
                positive_weight
                - negative_weight
            ) / directional_weight

            directional_strength = (
                directional_weight
                / total_weight
            )
        else:
            directional_bias = 0.0
            directional_strength = 0.0

        # ------------------------------------------------------------------
        # These are SCENARIO WEIGHTS, NOT CALIBRATED PROBABILITIES.
        #
        # Do not present these as "historical probability" until the
        # calibration engine has fitted them against realized outcomes.
        # ------------------------------------------------------------------

        raw_up = max(
            0.0,
            directional_bias,
        ) * directional_strength

        raw_down = max(
            0.0,
            -directional_bias,
        ) * directional_strength

        raw_sideways = max(
            0.0,
            1.0 - directional_strength,
        )

        total = (
            raw_up
            + raw_down
            + raw_sideways
        )

        if total <= 0.0:
            up = 0.0
            down = 0.0
            sideways = 1.0
        else:
            up = raw_up / total
            down = raw_down / total
            sideways = raw_sideways / total

        if score >= 0.12:
            direction = "UP"
        elif score <= -0.12:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        average_confidence = sum(
            item["confidence"]
            for item in usable
        ) / len(usable)

        evidence_quality = (
            average_confidence
            * directional_strength
        )

        forecast_valid = (
            len(usable) >= 2
            and average_confidence >= 0.40
            and (
                direction == "SIDEWAYS"
                or directional_strength >= 0.50
            )
        )

        return _result(
            self.name,
            score,
            average_confidence,
            (
                "Model-derived scenario weights generated from "
                f"{len(usable)} usable prediction signals."
            ),
            0.9,
            direction=direction,
            probabilities={
                "UP": round(up, 6),
                "DOWN": round(down, 6),
                "SIDEWAYS": round(sideways, 6),
            },
            probability_status="MODEL_DERIVED",
            calibrated=False,
            calibration_status="NOT_CALIBRATED",
            forecast_valid=forecast_valid,
            evidence_count=len(evidence),
            usable_evidence_count=len(usable),
            rejected_evidence_count=len(rejected),
            directional_strength=round(
                directional_strength,
                6,
            ),
            directional_bias=round(
                directional_bias,
                6,
            ),
            neutral_weight=round(
                neutral_weight,
                6,
            ),
            evidence_quality=round(
                evidence_quality,
                6,
            ),
            contributing_engines=[
                item["engine"]
                for item in usable
            ],
            rejected_engines=rejected,
        )

    analyze = predict
