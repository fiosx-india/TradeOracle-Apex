from __future__ import annotations

import math
import statistics
from typing import Any


# ---------------------------------------------------------------------------
# SUPPORTED HORIZONS
# ---------------------------------------------------------------------------

SUPPORTED_HORIZONS = (5, 15, 30, 60)


# ---------------------------------------------------------------------------
# CONTEXT HELPERS
# ---------------------------------------------------------------------------

def _data(context) -> dict[str, Any]:
    data = getattr(
        context,
        "data",
        None,
    )

    if isinstance(data, dict):
        return data

    if isinstance(context, dict):
        value = context.get("data")

        if isinstance(value, dict):
            return value

    return {}


def _get(
    context,
    key: str,
    default=None,
):
    if isinstance(context, dict):
        return context.get(
            key,
            default,
        )

    return getattr(
        context,
        key,
        default,
    )


def _series(
    context,
    *keys: str,
) -> list[float]:

    data = _data(context)

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

            except (
                TypeError,
                ValueError,
            ):
                continue

        if result:
            return result

    return []


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        number = float(value)

        if not math.isfinite(number):
            return default

        return number

    except (
        TypeError,
        ValueError,
    ):
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


def _ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:

    if denominator == 0:
        return default

    return numerator / denominator


# ---------------------------------------------------------------------------
# HORIZON
# ---------------------------------------------------------------------------

def _get_horizon(context) -> int:
    """
    The shared MarketContext is the authoritative source
    of the prediction horizon.

    Supported:
        5
        15
        30
        60

    No silent fallback is allowed.
    """

    raw = _get(
        context,
        "horizon_minutes",
        None,
    )

    if raw is None:
        raise ValueError(
            "SixtyMinuteEngine requires "
            "context.horizon_minutes."
        )

    try:
        horizon = int(raw)

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise ValueError(
            "context.horizon_minutes must be "
            "an integer."
        ) from exc

    if horizon not in SUPPORTED_HORIZONS:

        raise ValueError(
            "Unsupported prediction horizon: "
            f"{horizon}. Supported horizons: "
            f"{SUPPORTED_HORIZONS}"
        )

    return horizon


# ---------------------------------------------------------------------------
# EVIDENCE
# ---------------------------------------------------------------------------

def _evidence(
    context,
) -> list[dict[str, Any]]:

    value = _get(
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
        "research_evidence",
        [],
    )

    if isinstance(value, list):

        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    return []


def _prepare_evidence(
    evidence: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Separate usable and rejected evidence.

    Failed/stale/invalid evidence must never silently
    become a prediction vote.
    """

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
            }
        )

    return usable, rejected


# ---------------------------------------------------------------------------
# RESULT
# ---------------------------------------------------------------------------

def _result(
    engine: str,
    score: float,
    confidence: float,
    reason: str,
    weight: float = 1.0,
    **extra: Any,
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


# ---------------------------------------------------------------------------
# ENGINE
# ---------------------------------------------------------------------------

class SixtyMinuteEngine:
    """
    Backward-compatible horizon-aware forward forecast engine.

    Runtime horizons:

        5 minutes
        15 minutes
        30 minutes
        60 minutes

    The class name remains SixtyMinuteEngine for compatibility
    with the existing Apex registry and imports.

    The actual horizon is always obtained from:

        context.horizon_minutes

    This engine:
        - consumes research evidence;
        - performs confidence-weighted aggregation;
        - calculates directional agreement;
        - estimates historical/current volatility;
        - produces a forward movement scenario.

    It does NOT:
        - use future candles;
        - claim calibrated probability;
        - guarantee future price movement;
        - make the final BUY/SELL decision.
    """

    name = "SixtyMinuteEngine"
    version = "2.4.0"

    capabilities = [
        "PREDICTION",
        "FORWARD_FORECAST",
    ]

    SUPPORTED_HORIZONS = SUPPORTED_HORIZONS

    MIN_EVIDENCE_COUNT = 2
    MIN_DIRECTIONAL_EVIDENCE = 1

    def self_test(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # AGGREGATION
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate(
        evidence: list[dict[str, Any]],
    ) -> tuple[
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
                0,
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
            _clamp(
                agreement,
                0.0,
                1.0,
            ),
            total_weight,
            directional_count,
        )

    # ------------------------------------------------------------------
    # VOLATILITY
    # ------------------------------------------------------------------

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

        window = min(
            len(close),
            max(
                6,
                horizon_minutes + 1,
            ),
        )

        recent_close = close[
            -window:
        ]

        returns: list[float] = []

        for previous, current in zip(
            recent_close[:-1],
            recent_close[1:],
        ):

            if previous == 0:
                continue

            value = (
                current - previous
            ) / abs(previous)

            if math.isfinite(value):
                returns.append(
                    value
                )

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

        # --------------------------------------------------------------
        # 1. HORIZON
        # --------------------------------------------------------------

        horizon = _get_horizon(
            context
        )

        # --------------------------------------------------------------
        # 2. RESEARCH EVIDENCE
        # --------------------------------------------------------------

        raw_evidence = _evidence(
            context
        )

        usable, rejected = (
            _prepare_evidence(
                raw_evidence
            )
        )

        # --------------------------------------------------------------
        # 3. MINIMUM EVIDENCE
        # --------------------------------------------------------------

        if len(usable) < (
            self.MIN_EVIDENCE_COUNT
        ):

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    f"Insufficient independent "
                    f"evidence for a "
                    f"{horizon}-minute forecast."
                ),
                0.0,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                forecast_available=False,

                calibrated=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                evidence_count=len(
                    raw_evidence
                ),

                usable_evidence_count=len(
                    usable
                ),

                rejected_evidence_count=len(
                    rejected
                ),

                directional_evidence_count=0,

                evidence_strength=0.0,

                agreement=0.0,

                expected_return=0.0,

                uncertainty=1.0,

                volatility=0.0,

                contributing_engines=[],

                rejected_engines=rejected,
            )

        # --------------------------------------------------------------
        # 4. AGGREGATE
        # --------------------------------------------------------------

        (
            score,
            agreement,
            total_weight,
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
                    f"No usable weighted "
                    f"evidence for "
                    f"{horizon}-minute forecast."
                ),
                0.0,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                forecast_available=False,

                calibrated=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                evidence_count=len(
                    raw_evidence
                ),

                usable_evidence_count=len(
                    usable
                ),

                rejected_evidence_count=len(
                    rejected
                ),

                directional_evidence_count=0,

                evidence_strength=0.0,

                agreement=0.0,

                expected_return=0.0,

                uncertainty=1.0,

                volatility=0.0,

                contributing_engines=[],

                rejected_engines=rejected,
            )

        # --------------------------------------------------------------
        # 5. DIRECTION
        # --------------------------------------------------------------

        direction = self._direction(
            score
        )

        # --------------------------------------------------------------
        # 6. EVIDENCE STRENGTH
        # --------------------------------------------------------------

        score_strength = min(
            1.0,
            abs(score),
        )

        evidence_strength = _clamp(
            (
                score_strength
                * 0.65
                + agreement
                * 0.35
            ),
            0.0,
            1.0,
        )

        # --------------------------------------------------------------
        # 7. CONFIDENCE
        #
        # This is NOT probability.
        # --------------------------------------------------------------

        confidence = (
            0.10
            + evidence_strength
            * 0.70
        )

        confidence = min(
            0.85,
            confidence,
        )

        if agreement < 0.55:

            confidence *= 0.75

        # --------------------------------------------------------------
        # 8. DATA VOLATILITY
        # --------------------------------------------------------------

        volatility = (
            self._volatility(
                context,
                horizon,
            )
        )

        base_volatility = max(
            volatility,
            0.0005,
        )

        # --------------------------------------------------------------
        # 9. HORIZON SCALING
        # --------------------------------------------------------------

        horizon_scale = math.sqrt(
            horizon / 5.0
        )

        # --------------------------------------------------------------
        # 10. FORWARD MOVEMENT SCENARIO
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # 11. FORECAST VALIDITY
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # 12. CONTRIBUTING ENGINES
        # --------------------------------------------------------------

        contributing_engines = [
            item["engine"]
            for item in usable
        ]

        # --------------------------------------------------------------
        # 13. REASON
        # --------------------------------------------------------------

        reason = (
            f"{horizon}-minute forward forecast: "
            f"score={score:.3f}, "
            f"agreement={agreement:.2f}, "
            f"usable_evidence="
            f"{len(usable)}, "
            f"directional_evidence="
            f"{directional_evidence_count}"
        )

        # --------------------------------------------------------------
        # 14. FINAL RESULT
        # --------------------------------------------------------------

        return _result(
            self.name,

            score,

            confidence,

            reason,

            1.25,

            direction=direction,

            horizon_minutes=horizon,

            forecast_available=(
                forecast_available
            ),

            calibrated=False,

            calibration_status=(
                "NOT_CALIBRATED"
            ),

            evidence_count=len(
                raw_evidence
            ),

            usable_evidence_count=len(
                usable
            ),

            rejected_evidence_count=len(
                rejected
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

            horizon_scale=round(
                horizon_scale,
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

            contributing_engines=(
                contributing_engines
            ),

            rejected_engines=rejected,
        )

    analyze = predict
