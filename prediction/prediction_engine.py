from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Any


SUPPORTED_HORIZONS = (5, 15, 30, 60)


# ---------------------------------------------------------------------------
# CONTEXT HELPERS
# ---------------------------------------------------------------------------

def _data(ctx) -> dict[str, Any]:
    data = getattr(ctx, "data", None)

    if isinstance(data, dict):
        return data

    if isinstance(ctx, dict):
        value = ctx.get("data")

        if isinstance(value, dict):
            return value

    return {}


def _get(ctx, key: str, default=None):
    if isinstance(ctx, dict):
        return ctx.get(key, default)

    return getattr(ctx, key, default)


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        number = float(value)

        if not math.isfinite(number):
            return default

        return number

    except (TypeError, ValueError):
        return default


def _clamp(
    value: float,
    low: float = -1.0,
    high: float = 1.0,
) -> float:
    return max(
        low,
        min(
            high,
            _safe_float(value),
        ),
    )


def _series(
    ctx,
    *keys,
) -> list[float]:

    data = _data(ctx)

    for key in keys:

        value = data.get(key)

        if not isinstance(
            value,
            (list, tuple),
        ):
            continue

        result: list[float] = []

        for item in value:

            try:
                number = float(item)

                if math.isfinite(number):
                    result.append(number)

            except (TypeError, ValueError):
                continue

        if result:
            return result

    return []


def _evidence(ctx) -> list[dict[str, Any]]:

    value = _get(
        ctx,
        "research_evidence",
        None,
    )

    if not isinstance(value, list):

        value = _data(ctx).get(
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


# ---------------------------------------------------------------------------
# HORIZON
# ---------------------------------------------------------------------------

def _get_horizon(ctx) -> int:
    """
    MarketContext is the authoritative source.

    Supported horizons:
        5
        15
        30
        60

    No silent fallback is allowed.
    """

    raw = _get(
        ctx,
        "horizon_minutes",
        None,
    )

    if raw is None:
        raise ValueError(
            "PredictionEngine requires "
            "context.horizon_minutes."
        )

    try:
        horizon = int(raw)

    except (TypeError, ValueError) as exc:
        raise ValueError(
            "context.horizon_minutes must be an integer."
        ) from exc

    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(
            "Unsupported prediction horizon: "
            f"{horizon}. Supported horizons: "
            f"{SUPPORTED_HORIZONS}."
        )

    return horizon


# ---------------------------------------------------------------------------
# RESULT
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ENGINE
# ---------------------------------------------------------------------------

class PredictionEngine:
    """
    Primary forward-looking prediction engine.

    Supported horizons:
        5 minutes
        15 minutes
        30 minutes
        60 minutes

    The horizon always comes from:

        context.horizon_minutes

    The engine:
        - consumes research evidence;
        - rejects invalid/stale evidence;
        - enforces horizon consistency;
        - performs weighted evidence fusion;
        - calculates directional agreement;
        - estimates historical volatility;
        - produces a forward movement scenario.

    It does NOT:
        - use future candles;
        - claim calibrated probability;
        - guarantee a future outcome;
        - make the final trading decision.
    """

    name = "PredictionEngine"
    version = "2.4.0"

    capabilities = [
        "PREDICTION",
        "FORWARD_FORECAST",
    ]

    SUPPORTED_HORIZONS = SUPPORTED_HORIZONS

    MIN_EVIDENCE_COUNT = 2

    def self_test(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # EVIDENCE PREPARATION
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_evidence(
        evidence: list[dict[str, Any]],
        horizon: int,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:

        usable: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        invalid_statuses = {
            "FAILED",
            "ERROR",
            "UNAVAILABLE",
            "INVALID",
            "STALE",
        }

        for item in evidence:

            engine_name = str(
                item.get(
                    "engine",
                    "UnknownEngine",
                )
            )

            # ----------------------------------------------------------
            # HORIZON CONSISTENCY
            # ----------------------------------------------------------

            item_horizon = item.get(
                "horizon_minutes",
                None,
            )

            if item_horizon is not None:

                try:
                    item_horizon = int(
                        item_horizon
                    )

                except (TypeError, ValueError):

                    rejected.append(
                        {
                            "engine": engine_name,
                            "reason": "invalid_horizon",
                        }
                    )

                    continue

                if item_horizon != horizon:

                    rejected.append(
                        {
                            "engine": engine_name,
                            "reason": "horizon_mismatch",
                            "evidence_horizon": item_horizon,
                            "context_horizon": horizon,
                        }
                    )

                    continue

            # ----------------------------------------------------------
            # NUMERIC VALUES
            # ----------------------------------------------------------

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

            # ----------------------------------------------------------
            # STATUS
            # ----------------------------------------------------------

            status = str(
                item.get(
                    "status",
                    "AVAILABLE",
                )
            ).upper()

            if status in invalid_statuses:

                rejected.append(
                    {
                        "engine": engine_name,
                        "reason": (
                            "engine_status_"
                            f"{status.lower()}"
                        ),
                    }
                )

                continue

            # ----------------------------------------------------------
            # WEIGHT
            # ----------------------------------------------------------

            if weight <= 0.0:

                rejected.append(
                    {
                        "engine": engine_name,
                        "reason": "non_positive_weight",
                    }
                )

                continue

            # ----------------------------------------------------------
            # CONFIDENCE
            # ----------------------------------------------------------

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

        return (
            usable,
            rejected,
        )

    # ------------------------------------------------------------------
    # HISTORICAL VOLATILITY
    # ------------------------------------------------------------------

    @staticmethod
    def _historical_volatility(
        context,
        horizon: int,
    ) -> float:

        close = _series(
            context,
            "close",
            "closes",
            "price",
            "prices",
        )

        if len(close) < 6:
            return 0.0

        window = min(
            len(close),
            max(
                6,
                horizon + 1,
            ),
        )

        recent = close[-window:]

        returns: list[float] = []

        for previous, current in zip(
            recent[:-1],
            recent[1:],
        ):

            if previous == 0:
                continue

            value = (
                current - previous
            ) / abs(previous)

            if math.isfinite(value):
                returns.append(value)

        if len(returns) < 2:
            return 0.0

        try:
            return max(
                0.0,
                statistics.pstdev(
                    returns
                ),
            )

        except statistics.StatisticsError:
            return 0.0

    # ------------------------------------------------------------------
    # HORIZON SCALING
    # ------------------------------------------------------------------

    @staticmethod
    def _horizon_scale(
        horizon: int,
    ) -> float:
        return math.sqrt(
            horizon / 5.0
        )

    # ------------------------------------------------------------------
    # DIRECTION
    # ------------------------------------------------------------------

    @staticmethod
    def _direction(
        score: float,
    ) -> str:

        if score >= 0.12:
            return "UP"

        if score <= -0.12:
            return "DOWN"

        return "SIDEWAYS"

    # ------------------------------------------------------------------
    # PREDICT
    # ------------------------------------------------------------------

    def predict(
        self,
        context,
    ) -> dict[str, Any]:

        horizon = _get_horizon(
            context
        )

        issued_at = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        evidence = _evidence(
            context
        )

        usable, rejected = (
            self._prepare_evidence(
                evidence,
                horizon,
            )
        )

        if len(usable) < self.MIN_EVIDENCE_COUNT:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    f"Insufficient usable research "
                    f"evidence for {horizon}-minute "
                    f"forecast."
                ),
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=horizon,
                forecast_type="FORWARD_DIRECTIONAL",
                forecast_valid=False,
                issued_at=issued_at,
                evidence_count=len(evidence),
                usable_evidence_count=len(usable),
                rejected_evidence_count=len(rejected),
                agreement=0.0,
                evidence_quality=0.0,
                average_evidence_confidence=0.0,
                volatility=0.0,
                horizon_scale=self._horizon_scale(horizon),
                expected_return=0.0,
                expected_move_range=[0.0, 0.0],
                calibration_status="NOT_CALIBRATED",
                contributing_engines=[],
                rejected_engines=rejected,
            )

        effective_weights = [
            item["weight"] * item["confidence"]
            for item in usable
        ]

        weighted_scores = [
            item["score"]
            * item["weight"]
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
                "Usable research evidence has no effective weight.",
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=horizon,
                forecast_type="FORWARD_DIRECTIONAL",
                forecast_valid=False,
                issued_at=issued_at,
                evidence_count=len(evidence),
                usable_evidence_count=len(usable),
                rejected_evidence_count=len(rejected),
                agreement=0.0,
                evidence_quality=0.0,
                average_evidence_confidence=0.0,
                volatility=0.0,
                horizon_scale=self._horizon_scale(horizon),
                expected_return=0.0,
                expected_move_range=[0.0, 0.0],
                calibration_status="NOT_CALIBRATED",
                contributing_engines=[],
                rejected_engines=rejected,
            )

        score = _clamp(
            sum(weighted_scores)
            / total_weight
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

        agreement = (
            max(
                positive_weight,
                negative_weight,
            )
            / directional_weight
            if directional_weight > 0.0
            else 0.0
        )

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

        direction = self._direction(
            score
        )

        volatility = (
            self._historical_volatility(
                context,
                horizon,
            )
        )

        base_volatility = max(
            volatility,
            0.0005,
        )

        horizon_scale = (
            self._horizon_scale(
                horizon
            )
        )

        expected_return = (
            score
            * base_volatility
            * horizon_scale
            * 1.5
        )

        expected_return = _clamp(
            expected_return,
            -0.10,
            0.10,
        )

        uncertainty_factor = max(
            0.25,
            1.0 - confidence,
        )

        movement_uncertainty = min(
            0.10,
            max(
                0.0005,
                base_volatility
                * horizon_scale
                * uncertainty_factor,
            ),
        )

        lower_move = _clamp(
            expected_return
            - movement_uncertainty,
            -0.10,
            0.10,
        )

        upper_move = _clamp(
            expected_return
            + movement_uncertainty,
            -0.10,
            0.10,
        )

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
                f"Forward {horizon}-minute "
                f"directional forecast generated "
                f"from {len(usable)} usable research "
                f"signals."
            ),
            1.10,
            direction=direction,
            horizon_minutes=horizon,
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
            volatility=round(
                volatility,
                8,
            ),
            horizon_scale=round(
                horizon_scale,
                6,
            ),
            expected_return=round(
                expected_return,
                6,
            ),
            expected_move_range=[
                round(lower_move, 6),
                round(upper_move, 6),
            ],
            calibration_status="NOT_CALIBRATED",
            contributing_engines=contributing_engines,
            rejected_engines=rejected,
            evidence_reasons=reasons,
        )

    analyze = predict
