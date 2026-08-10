from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _data(ctx) -> dict[str, Any]:
    data = getattr(ctx, "data", None)
    return data if isinstance(data, dict) else {}


def _get(ctx, key: str, default=None):
    if isinstance(ctx, dict):
        return ctx.get(key, default)

    return getattr(ctx, key, default)


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


def _evidence(ctx) -> list[dict[str, Any]]:
    value = _get(ctx, "research_evidence", None)

    if not isinstance(value, list):
        value = _data(ctx).get("research_evidence", [])

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


class PredictionEngine:
    """
    Primary forward-looking prediction fusion engine.

    Converts usable research evidence into a directional
    forecast for the configured future horizon.

    Important:
    - This is a model-derived forecast.
    - It is NOT a calibrated probability.
    - It does NOT guarantee a future market outcome.
    - Failed/unavailable evidence is excluded.
    - Historical calibration belongs to the validation layer.
    """

    name = "PredictionEngine"
    version = "2.2.0"

    capabilities = [
        "PREDICTION",
        "FORWARD_FORECAST",
    ]

    def self_test(self) -> bool:
        return True

    def predict(self, context) -> dict[str, Any]:
        evidence = _evidence(context)

        horizon_minutes = _safe_float(
            _get(context, "horizon_minutes", 60),
            60.0,
        )

        if horizon_minutes <= 0:
            horizon_minutes = 60.0

        horizon_minutes = int(horizon_minutes)

        issued_at = datetime.now(timezone.utc).isoformat()

        usable: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for item in evidence:
            engine_name = str(
                item.get(
                    "engine",
                    "UnknownEngine",
                )
            )

            score = _clamp(
                _safe_float(
                    item.get("score", 0.0),
                )
            )

            weight = max(
                0.0,
                _safe_float(
                    item.get("weight", 0.0),
                ),
            )

            confidence = max(
                0.0,
                min(
                    1.0,
                    _safe_float(
                        item.get("confidence", 0.0),
                    ),
                ),
            )

            reason = str(
                item.get(
                    "reason",
                    "No reason supplied",
                )
            )

            # ------------------------------------------------------
            # HARD REJECTION RULES
            # ------------------------------------------------------

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

            # Explicit unavailable/failed status must never
            # silently become prediction evidence.
            status = str(
                item.get(
                    "status",
                    "AVAILABLE",
                )
            ).upper()

            if status in {
                "FAILED",
                "ERROR",
                "UNAVAILABLE",
                "INVALID",
                "STALE",
            }:
                rejected.append(
                    {
                        "engine": engine_name,
                        "reason": f"engine_status_{status.lower()}",
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

        # ----------------------------------------------------------
        # NO USABLE EVIDENCE
        # ----------------------------------------------------------

        if not usable:
            return _result(
                self.name,
                0.0,
                0.0,
                "No usable research evidence is available.",
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=horizon_minutes,
                forecast_valid=False,
                forecast_type="FORWARD_DIRECTIONAL",
                issued_at=issued_at,
                evidence_count=len(evidence),
                usable_evidence_count=0,
                rejected_evidence_count=len(rejected),
                agreement=0.0,
                evidence_quality=0.0,
                calibration_status="NOT_CALIBRATED",
                contributing_engines=[],
                rejected_engines=rejected,
            )

        # ----------------------------------------------------------
        # WEIGHTED FORWARD SCORE
        # ----------------------------------------------------------

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

        total_weight = sum(effective_weights)

        if total_weight <= 0.0:
            return _result(
                self.name,
                0.0,
                0.0,
                "Usable evidence has no effective weight.",
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=horizon_minutes,
                forecast_valid=False,
                forecast_type="FORWARD_DIRECTIONAL",
                issued_at=issued_at,
                evidence_count=len(evidence),
                usable_evidence_count=len(usable),
                rejected_evidence_count=len(rejected),
                agreement=0.0,
                evidence_quality=0.0,
                calibration_status="NOT_CALIBRATED",
                contributing_engines=[],
                rejected_engines=rejected,
            )

        score = sum(weighted_scores) / total_weight
        score = _clamp(score)

        # ----------------------------------------------------------
        # DIRECTIONAL AGREEMENT
        # ----------------------------------------------------------

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

        agreement = max(
            0.0,
            min(1.0, agreement),
        )

        # ----------------------------------------------------------
        # EVIDENCE QUALITY
        # ----------------------------------------------------------

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
            / max(1.0, len(evidence)),
        )

        evidence_quality = (
            average_confidence
            * agreement
            * coverage
        )

        # ----------------------------------------------------------
        # MODEL-DERIVED CONFIDENCE
        #
        # This is deliberately NOT probability.
        # ----------------------------------------------------------

        confidence = (
            0.10
            + 0.35 * abs(score)
            + 0.35 * agreement
            + 0.20 * average_confidence
        )

        confidence *= coverage

        confidence = max(
            0.0,
            min(0.95, confidence),
        )

        # ----------------------------------------------------------
        # FORWARD DIRECTION
        # ----------------------------------------------------------

        if score >= 0.12:
            direction = "UP"
        elif score <= -0.12:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        # ----------------------------------------------------------
        # FORECAST VALIDITY
        # ----------------------------------------------------------

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

        # ----------------------------------------------------------
        # EXPLAINABILITY
        # ----------------------------------------------------------

        reasons = [
            item["reason"]
            for item in usable
            if item.get("reason")
        ]

        contributing_engines = [
            item["engine"]
            for item in usable
        ]

        return _result(
            self.name,
            score,
            confidence,
            (
                f"Forward {horizon_minutes}-minute "
                f"directional forecast generated from "
                f"{len(usable)} usable research signals."
            ),
            1.1,
            direction=direction,
            horizon_minutes=horizon_minutes,
            forecast_type="FORWARD_DIRECTIONAL",
            issued_at=issued_at,
            forecast_valid=forecast_valid,
            evidence_count=len(evidence),
            usable_evidence_count=len(usable),
            rejected_evidence_count=len(rejected),
            agreement=round(agreement, 6),
            evidence_quality=round(
                evidence_quality,
                6,
            ),
            average_evidence_confidence=round(
                average_confidence,
                6,
            ),
            calibration_status="NOT_CALIBRATED",
            contributing_engines=contributing_engines,
            rejected_engines=rejected,
            evidence_reasons=reasons,
        )

    analyze = predict
