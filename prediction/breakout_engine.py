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

def _data(ctx) -> dict[str, Any]:
    data = getattr(
        ctx,
        "data",
        None,
    )

    if isinstance(data, dict):
        return data

    if isinstance(ctx, dict):
        value = ctx.get("data")

        if isinstance(value, dict):
            return value

    return {}


def _get(
    ctx,
    key: str,
    default=None,
):
    if isinstance(ctx, dict):
        return ctx.get(
            key,
            default,
        )

    return getattr(
        ctx,
        key,
        default,
    )


def _series(
    ctx,
    *keys: str,
) -> list[float]:

    data = _data(ctx)

    for key in keys:

        values = data.get(key)

        if not isinstance(
            values,
            (list, tuple),
        ):
            continue

        output: list[float] = []

        for value in values:

            try:
                number = float(value)

                if math.isfinite(number):
                    output.append(
                        number
                    )

            except (
                TypeError,
                ValueError,
            ):
                continue

        if output:
            return output

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


def _mean(
    values: list[float],
    default: float = 0.0,
) -> float:

    if not values:
        return default

    try:
        return statistics.fmean(
            values
        )

    except (
        TypeError,
        ValueError,
        statistics.StatisticsError,
    ):
        return default


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

def _get_horizon(ctx) -> int:
    """
    Resolve the authoritative prediction horizon.

    No silent fallback to 60 minutes.
    """

    raw = _get(
        ctx,
        "horizon_minutes",
        None,
    )

    if raw is None:
        raise ValueError(
            "BreakoutEngine requires "
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
            f"{SUPPORTED_HORIZONS}."
        )

    return horizon


# ---------------------------------------------------------------------------
# HORIZON-SPECIFIC LOOKBACK
# ---------------------------------------------------------------------------

def _lookback_for_horizon(
    horizon: int,
) -> int:
    """
    Select a structural breakout lookback based on the prediction horizon.

    The market data remains 1-minute data.

    The horizon controls how much completed price structure is examined.
    """

    return {
        5: 10,
        15: 15,
        30: 30,
        60: 60,
    }[horizon]


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
            _safe_float(
                weight
            ),
        ),

        "reason": reason,
    }

    result.update(extra)

    return result


# ---------------------------------------------------------------------------
# ENGINE
# ---------------------------------------------------------------------------

class BreakoutEngine:
    """
    Horizon-aware breakout / breakdown prediction engine.

    Supported horizons:

        5 minutes
        15 minutes
        30 minutes
        60 minutes

    The engine:

    - uses only current/completed observations;
    - excludes the latest observation from the historical range;
    - adapts structural lookback to the requested horizon;
    - optionally uses relative volume as confirmation;
    - produces model-derived score and confidence;
    - does NOT produce calibrated probability;
    - does NOT use future candles;
    - does NOT guarantee a future breakout.

    MasterBrain executes this engine independently for each
    MarketContext/horizon.
    """

    name = "BreakoutEngine"
    version = "2.3.0"

    capabilities = [
        "PREDICTION",
        "BREAKOUT",
    ]

    SUPPORTED_HORIZONS = SUPPORTED_HORIZONS

    def self_test(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # VOLATILITY
    # ------------------------------------------------------------------

    @staticmethod
    def _volatility(
        close: list[float],
        horizon: int,
    ) -> float:
        """
        Estimate recent 1-minute return volatility.

        This is historical/current volatility only.
        """

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

        lookback = (
            _lookback_for_horizon(
                horizon
            )
        )

        # --------------------------------------------------------------
        # 2. MARKET SERIES
        # --------------------------------------------------------------

        close = _series(
            context,
            "close",
            "closes",
            "price",
            "prices",
        )

        volume = _series(
            context,
            "volume",
            "volumes",
            "trade_volume",
        )

        # --------------------------------------------------------------
        # 3. DATA REQUIREMENT
        # --------------------------------------------------------------

        minimum_history = (
            lookback + 2
        )

        if len(close) < minimum_history:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    f"Insufficient history for "
                    f"{horizon}-minute breakout "
                    f"detection."
                ),
                0.0,

                breakout=False,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                lookback_bars=lookback,

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INSUFFICIENT",

                range_high=None,

                range_low=None,

                breakout_distance=0.0,

                distance_strength=0.0,

                relative_volume=1.0,

                volume_confirmation=0.0,

                volume_available=False,

                volatility=0.0,

                expected_return=0.0,

                expected_move_range=[
                    0.0,
                    0.0,
                ],
            )

        # --------------------------------------------------------------
        # 4. COMPLETED HISTORICAL RANGE
        #
        # IMPORTANT:
        #
        # The latest observation is excluded from the range.
        #
        # This prevents the observation being tested from defining
        # its own breakout threshold.
        # --------------------------------------------------------------

        previous = close[
            -(lookback + 1):-1
        ]

        if len(previous) < lookback:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    "Insufficient completed "
                    "historical range."
                ),
                0.0,

                breakout=False,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                lookback_bars=lookback,

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INSUFFICIENT",

            )

        range_high = max(
            previous
        )

        range_low = min(
            previous
        )

        last_price = close[-1]

        # --------------------------------------------------------------
        # 5. RANGE VALIDITY
        # --------------------------------------------------------------

        range_width = (
            range_high
            - range_low
        )

        if range_width <= 0:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    "Previous price range "
                    "is not usable."
                ),
                0.0,

                breakout=False,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                lookback_bars=lookback,

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INVALID_RANGE",

                range_high=round(
                    range_high,
                    6,
                ),

                range_low=round(
                    range_low,
                    6,
                ),

            )

        # --------------------------------------------------------------
        # 6. BREAKOUT DISTANCE
        # --------------------------------------------------------------

        upside_distance = _ratio(
            last_price - range_high,
            range_width,
        )

        downside_distance = _ratio(
            range_low - last_price,
            range_width,
        )

        # --------------------------------------------------------------
        # 7. RELATIVE VOLUME
        # --------------------------------------------------------------

        relative_volume = 1.0

        volume_available = False

        if len(volume) >= (
            lookback + 1
        ):

            previous_volume = volume[
                -(lookback + 1):-1
            ]

            average_volume = _mean(
                previous_volume,
                0.0,
            )

            current_volume = (
                volume[-1]
            )

            if average_volume > 0:

                relative_volume = _ratio(
                    current_volume,
                    average_volume,
                    1.0,
                )

                volume_available = True

        # --------------------------------------------------------------
        # 8. VOLUME CONFIRMATION
        # --------------------------------------------------------------

        if volume_available:

            volume_confirmation = _clamp(
                (
                    relative_volume
                    - 1.0
                ) / 1.5,
                0.0,
                1.0,
            )

        else:

            volume_confirmation = 0.0

        # --------------------------------------------------------------
        # 9. BREAKOUT STATE
        # --------------------------------------------------------------

        upward_breakout = (
            last_price > range_high
        )

        downward_breakout = (
            last_price < range_low
        )

        breakout = (
            upward_breakout
            or downward_breakout
        )

        # --------------------------------------------------------------
        # 10. NO BREAKOUT
        # --------------------------------------------------------------

        if not breakout:

            volatility = (
                self._volatility(
                    close,
                    horizon,
                )
            )

            return _result(
                self.name,

                0.0,

                0.15,

                (
                    f"No confirmed breakout for "
                    f"{horizon}-minute horizon. "
                    f"price={last_price:.4f}, "
                    f"range_high={range_high:.4f}, "
                    f"range_low={range_low:.4f}"
                ),

                0.80,

                breakout=False,

                direction="SIDEWAYS",

                horizon_minutes=horizon,

                lookback_bars=lookback,

                range_high=round(
                    range_high,
                    6,
                ),

                range_low=round(
                    range_low,
                    6,
                ),

                breakout_distance=0.0,

                distance_strength=0.0,

                relative_volume=round(
                    relative_volume,
                    6,
                ),

                volume_confirmation=round(
                    volume_confirmation,
                    6,
                ),

                volume_available=(
                    volume_available
                ),

                volatility=round(
                    volatility,
                    8,
                ),

                expected_return=0.0,

                expected_move_range=[
                    0.0,
                    0.0,
                ],

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="VALID",

            )

        # --------------------------------------------------------------
        # 11. DIRECTION + DISTANCE
        # --------------------------------------------------------------

        if upward_breakout:

            direction = "UP"

            distance = max(
                0.0,
                upside_distance,
            )

        else:

            direction = "DOWN"

            distance = max(
                0.0,
                downside_distance,
            )

        # --------------------------------------------------------------
        # 12. BREAKOUT STRENGTH
        # --------------------------------------------------------------

        distance_strength = min(
            1.0,
            distance * 3.0,
        )

        structural_strength = min(
            1.0,
            0.55
            + 0.35
            * distance_strength,
        )

        # Volume is confirmation only.
        if volume_available:

            confirmation_strength = (
                0.75
                + 0.25
                * volume_confirmation
            )

        else:

            confirmation_strength = 0.75

        strength = _clamp(
            structural_strength
            * confirmation_strength,
            0.0,
            1.0,
        )

        # --------------------------------------------------------------
        # 13. MODEL-DERIVED SCORE
        # --------------------------------------------------------------

        if direction == "UP":

            score = strength

        else:

            score = -strength

        # --------------------------------------------------------------
        # 14. CONFIDENCE
        #
        # NOT probability.
        # --------------------------------------------------------------

        confidence = min(
            0.90,

            0.25
            + 0.45 * strength
            + 0.15 * distance_strength
            + (
                0.10
                * volume_confirmation
                if volume_available
                else 0.0
            ),
        )

        # --------------------------------------------------------------
        # 15. HISTORICAL VOLATILITY
        # --------------------------------------------------------------

        volatility = (
            self._volatility(
                close,
                horizon,
            )
        )

        base_volatility = max(
            volatility,
            0.0005,
        )

        horizon_scale = math.sqrt(
            horizon / 5.0
        )

        # --------------------------------------------------------------
        # 16. FORWARD MOVEMENT SCENARIO
        #
        # This does NOT mean the breakout is guaranteed.
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
        # 17. SCENARIO RANGE
        # --------------------------------------------------------------

        uncertainty_factor = max(
            0.25,
            1.0 - confidence,
        )

        movement_uncertainty = (
            base_volatility
            * horizon_scale
            * uncertainty_factor
        )

        movement_uncertainty = min(
            0.10,
            max(
                0.0005,
                movement_uncertainty,
            ),
        )

        if direction == "UP":

            lower_move = max(
                0.0,
                expected_return
                - movement_uncertainty,
            )

            upper_move = min(
                0.10,
                expected_return
                + movement_uncertainty,
            )

        else:

            lower_move = max(
                -0.10,
                expected_return
                - movement_uncertainty,
            )

            upper_move = min(
                0.0,
                expected_return
                + movement_uncertainty,
            )

        # --------------------------------------------------------------
        # 18. EXPLANATION
        # --------------------------------------------------------------

        reason_parts = [
            "breakout=True",
            f"direction={direction}",
            f"horizon={horizon}m",
            f"lookback={lookback}",
            (
                "distance_strength="
                f"{distance_strength:.3f}"
            ),
            (
                "relative_volume="
                f"{relative_volume:.2f}"
            ),
        ]

        if volume_available:

            reason_parts.append(
                (
                    "volume_confirmation="
                    f"{volume_confirmation:.3f}"
                )
            )

        else:

            reason_parts.append(
                "volume_confirmation=UNAVAILABLE"
            )

        # --------------------------------------------------------------
        # 19. FINAL RESULT
        # --------------------------------------------------------------

        return _result(
            self.name,

            score,

            confidence,

            ", ".join(
                reason_parts
            ),

            0.90,

            breakout=True,

            direction=direction,

            horizon_minutes=horizon,

            lookback_bars=lookback,

            range_high=round(
                range_high,
                6,
            ),

            range_low=round(
                range_low,
                6,
            ),

            breakout_distance=round(
                distance,
                6,
            ),

            distance_strength=round(
                distance_strength,
                6,
            ),

            relative_volume=round(
                relative_volume,
                6,
            ),

            volume_confirmation=round(
                volume_confirmation,
                6,
            ),

            volume_available=(
                volume_available
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
                round(
                    lower_move,
                    6,
                ),
                round(
                    upper_move,
                    6,
                ),
            ],

            forecast_valid=True,

            calibration_status=(
                "NOT_CALIBRATED"
            ),

            data_quality="VALID",
        )

    analyze = predict
