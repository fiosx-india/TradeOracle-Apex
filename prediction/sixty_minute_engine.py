from __future__ import annotations

import math
import statistics
from typing import Any


SUPPORTED_HORIZONS = (5, 15, 30, 60)


def _data(context) -> dict[str, Any]:
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


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_horizon(context) -> int:
    """
    Read the prediction horizon from MarketContext.

    The orchestrator is responsible for creating separate contexts
    for 5, 15, 30 and 60 minutes.
    """

    raw = getattr(
        context,
        "horizon_minutes",
        5,
    )

    try:
        horizon = int(raw)
    except (TypeError, ValueError):
        horizon = 5

    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(
            "Unsupported prediction horizon: "
            f"{horizon}. Supported horizons: "
            f"{SUPPORTED_HORIZONS}"
        )

    return horizon


def _evidence(context) -> list[dict[str, Any]]:
    """
    Read research evidence from the shared MarketContext.
    """

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

    value = data.get(
        "research_evidence"
    )

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
    Horizon-aware forward prediction engine.

    Backward-compatible class name:
        SixtyMinuteEngine

    Runtime behavior:
        5  -> 5-minute forecast
        15 -> 15-minute forecast
        30 -> 30-minute forecast
        60 -> 60-minute forecast

    The actual horizon is ALWAYS taken from:

        context.horizon_minutes

    This engine does not claim calibrated probability.
    Confidence represents current evidence strength only.

    No future candles are used.
    """

    name = "SixtyMinuteEngine"
    version = "2.3.0"

    # IMPORTANT:
    #
    # Do NOT declare "60_MINUTE" here.
    #
    # This engine is now horizon-aware and must participate
    # in all supported prediction contexts.
    capabilities = [
        "PREDICTION",
        "FORWARD_FORECAST",
    ]

    SUPPORTED_HORIZONS = SUPPORTED_HORIZONS

    MIN_EVIDENCE_COUNT = 2
    MIN_DIRECTIONAL_EVIDENCE = 1

    def self_test(self) -> bool:
        return True

    # ================================================================
    # EVIDENCE PREPARATION
    # ================================================================

    @staticmethod
    def _prepare_evidence(
        evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        usable: list[dict[str, Any]] = []

        for item in evidence:

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

        return usable

    # ================================================================
    # WEIGHTED EVIDENCE
    # ================================================================

    @staticmethod
    def _aggregate(
        evidence: list[dict[str, Any]],
    ) -> tuple[
        float,
        float,
        float,
        float,
        int,
    ]:

        weighted_scores: list[float] = []
        effective_weights: list[float] = []

        positive_weight = 0.0
        negative_weight = 0.0

        directional_count = 0

        for item in evidence:

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

            if item["score"] > 0.05:
                positive_weight += (
                    effective_weight
                )
                directional_count += 1

            elif item["score"] < -0.05:
                negative_weight += (
                    effective_weight
                )
                directional_count += 1

        total_weight = sum(
            effective_weights
        )

        if total_weight <= 0.0:
            return (
                0.0,
                0.0,
                0.0,
                0.0,
                directional_count,
            )

        score = _ratio(
            sum(weighted_scores),
            total_weight,
        )

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

        return (
            _clamp(score),
            _clamp(agreement, 0.0, 1.0),
            total_weight,
            positive_weight,
            directional_count,
        )

    # ================================================================
    # HISTORICAL VOLATILITY
    # ================================================================

    @staticmethod
    def _volatility(
        context,
        horizon_minutes: int,
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

        # Use a horizon-dependent historical window.
        #
        # 5m  -> recent 5-minute behavior
        # 15m -> recent 15-minute behavior
        # 30m -> recent 30-minute behavior
        # 60m -> recent 60-minute behavior
        #
        # The available dataset is still the canonical 1-minute
        # candle series.

        window = min(
            len(close),
            max(
                6,
                horizon_minutes + 1,
            ),
        )

        recent_close = close[-window:]

        returns: list[float] = []

        for previous, current in zip(
            recent_close[:-1],
            recent_close[1:],
        ):

            if previous == 0:
                continue

            returns.append(
                (
                    current - previous
                )
                / abs(previous)
            )

        if len(returns) < 2:
            return 0.0

        return max(
            0.0,
            statistics.pstdev(
                returns
            ),
        )

    # ================================================================
    # DIRECTION
    # ================================================================

    @staticmethod
    def _direction(
        score: float,
    ) -> str:

        if score >= 0.12:
            return "UP"

        if score <= -0.12:
            return "DOWN"

        return "SIDEWAYS"

    # ================================================================
    # PREDICTION
    # ================================================================

    def predict(
        self,
        context,
    ) -> dict[str, Any]:

        # ------------------------------------------------------------
        # 0. Read horizon from context
        # ------------------------------------------------------------

        horizon = _get_horizon(
            context
        )

        # ------------------------------------------------------------
        # 1. Read evidence
        # ------------------------------------------------------------

        evidence = _evidence(
            context
        )

        usable = self._prepare_evidence(
            evidence
        )

        # ------------------------------------------------------------
        # 2. Evidence availability gate
        # ------------------------------------------------------------

        if len(usable) < self.MIN_EVIDENCE_COUNT:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    f"Insufficient independent evidence "
                    f"for a {horizon}-minute forecast."
                ),
                1.25,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                forecast_available=False,

                calibrated=False,

                evidence_count=len(
                    usable
                ),

                directional_evidence_count=0,

                evidence_strength=0.0,

                expected_return=0.0,

                uncertainty=1.0,

                volatility=0.0,

            )

        # ------------------------------------------------------------
        # 3. Aggregate evidence
        # ------------------------------------------------------------

        (
            score,
            agreement,
            total_weight,
            _positive_weight,
            directional_evidence_count,
        ) = self._aggregate(
            usable
        )

        if total_weight <= 0.0:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    f"No usable weighted evidence "
                    f"for {horizon}-minute forecast."
                ),
                1.25,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                forecast_available=False,

                calibrated=False,

                evidence_count=len(
                    usable
                ),

                directional_evidence_count=0,

                evidence_strength=0.0,

                expected_return=0.0,

                uncertainty=1.0,

                volatility=0.0,

            )

        # ------------------------------------------------------------
        # 4. Direction
        # ------------------------------------------------------------

        direction = self._direction(
            score
        )

        # ------------------------------------------------------------
        # 5. Evidence strength
        # ------------------------------------------------------------

        score_strength = min(
            1.0,
            abs(score),
        )

        evidence_strength = _clamp(
            (
                score_strength * 0.65
                + agreement * 0.35
            ),
            0.0,
            1.0,
        )

        # ------------------------------------------------------------
        # 6. Conservative confidence
        #
        # IMPORTANT:
        # This is evidence confidence, NOT probability.
        # ------------------------------------------------------------

        confidence = (
            0.10
            + evidence_strength * 0.70
        )

        confidence = min(
            0.85,
            confidence,
        )

        if agreement < 0.55:
            confidence *= 0.75

        # ------------------------------------------------------------
        # 7. Historical/current volatility
        # ------------------------------------------------------------

        volatility = self._volatility(
            context,
            horizon,
        )

        # ------------------------------------------------------------
        # 8. Horizon-aware movement scenario
        #
        # This is a scenario estimate, not a guaranteed target.
        #
        # The sqrt(horizon) scaling reflects the use of a 1-minute
        # return series as the underlying market-data basis.
        # ------------------------------------------------------------

        base_volatility = max(
            volatility,
            0.0005,
        )

        horizon_scale = math.sqrt(
            horizon / 5.0
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

        # ------------------------------------------------------------
        # 9. Forecast availability
        # ------------------------------------------------------------

        forecast_available = (
            len(usable)
            >= self.MIN_EVIDENCE_COUNT
            and directional_evidence_count
            >= self.MIN_DIRECTIONAL_EVIDENCE
        )

        if not forecast_available:

            direction = "SIDEWAYS"
            confidence = 0.0
            expected_return = 0.0

        # ------------------------------------------------------------
        # 10. Explanation
        # ------------------------------------------------------------

        reason = (
            f"{horizon}-minute forward forecast: "
            f"score={score:.3f}, "
            f"agreement={agreement:.2f}, "
            f"evidence_count={len(usable)}, "
            f"directional_evidence="
            f"{directional_evidence_count}"
        )

        # ------------------------------------------------------------
        # 11. Final result
        # ------------------------------------------------------------

        return _result(
            self.name,

            score,

            confidence,

            reason,

            1.25,

            direction=direction,

            horizon_minutes=horizon,

            forecast_available=forecast_available,

            calibrated=False,

            evidence_count=len(
                usable
            ),

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
