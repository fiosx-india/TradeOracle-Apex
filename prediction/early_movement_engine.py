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


def _ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:

    if denominator == 0:
        return default

    return numerator / denominator


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


# ---------------------------------------------------------------------------
# HORIZON
# ---------------------------------------------------------------------------

def _get_horizon(ctx) -> int:
    """
    MarketContext is the authoritative source of the horizon.

    Do not silently fall back to 60 minutes.
    """

    raw = _get(
        ctx,
        "horizon_minutes",
        None,
    )

    if raw is None:
        raise ValueError(
            "EarlyMovementEngine requires "
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
# HORIZON PARAMETERS
# ---------------------------------------------------------------------------

def _windows_for_horizon(
    horizon: int,
) -> tuple[int, int]:
    """
    Return:

        short_window
        prior_window

    for the selected prediction horizon.

    The source data remains 1-minute candles.
    """

    return {
        5: (3, 7),
        15: (5, 15),
        30: (10, 30),
        60: (15, 60),
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

class EarlyMovementEngine:
    """
    Detect early acceleration before a full breakout.

    Supported prediction horizons:

        5 minutes
        15 minutes
        30 minutes
        60 minutes

    The engine looks for:

        short-term movement
                versus
        prior movement

    and measures whether the current movement is accelerating.

    Volume is used only as confirmation.

    This is a model-derived early-movement signal.
    It is NOT a calibrated probability.
    It does NOT guarantee a future breakout or price movement.
    """

    name = "EarlyMovementEngine"
    version = "2.3.0"

    capabilities = [
        "PREDICTION",
        "EARLY_MOVEMENT",
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

        short_window, prior_window = (
            _windows_for_horizon(
                horizon
            )
        )

        # --------------------------------------------------------------
        # 2. MARKET DATA
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

        minimum_history = (
            prior_window + 1
        )

        if len(close) < minimum_history:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    f"Insufficient history for "
                    f"{horizon}-minute early "
                    f"movement detection."
                ),
                0.0,

                horizon_minutes=horizon,

                short_window=short_window,

                prior_window=prior_window,

                early_signal=False,

                direction="SIDEWAYS",

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INSUFFICIENT",

                acceleration=0.0,

                short_return=0.0,

                prior_return=0.0,

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
        # 3. SHORT-TERM MOVEMENT
        # --------------------------------------------------------------

        short_reference_index = (
            -(short_window + 1)
        )

        short_reference = close[
            short_reference_index
        ]

        if short_reference == 0:

            return _result(
                self.name,
                0.0,
                0.0,
                "Invalid short-term reference price.",
                0.0,

                horizon_minutes=horizon,

                short_window=short_window,

                prior_window=prior_window,

                early_signal=False,

                direction="SIDEWAYS",

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INVALID_REFERENCE",

            )

        short_return = _ratio(
            close[-1]
            - short_reference,
            abs(short_reference),
        )

        # --------------------------------------------------------------
        # 4. PRIOR MOVEMENT
        # --------------------------------------------------------------
        #
        # Compare the previous movement segment with the current
        # short-term segment.
        #
        # Example for 15m:
        #
        # current  = latest 5 bars
        # prior    = preceding 15 bars
        # --------------------------------------------------------------

        prior_end = (
            -(short_window + 1)
        )

        prior_start = (
            -(short_window + prior_window + 1)
        )

        prior_segment = close[
            prior_start:prior_end
        ]

        if len(prior_segment) < 2:

            return _result(
                self.name,
                0.0,
                0.0,
                "Insufficient prior movement segment.",
                0.0,

                horizon_minutes=horizon,

                short_window=short_window,

                prior_window=prior_window,

                early_signal=False,

                direction="SIDEWAYS",

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INSUFFICIENT",

            )

        prior_reference = (
            prior_segment[0]
        )

        prior_last = (
            prior_segment[-1]
        )

        if prior_reference == 0:

            prior_return = 0.0

        else:

            prior_return = _ratio(
                prior_last
                - prior_reference,
                abs(prior_reference),
            )

        # --------------------------------------------------------------
        # 5. ACCELERATION
        # --------------------------------------------------------------

        acceleration = (
            short_return
            - prior_return
        )

        # --------------------------------------------------------------
        # 6. DIRECTION
        # --------------------------------------------------------------

        if acceleration >= 0.0005:

            direction = "UP"

        elif acceleration <= -0.0005:

            direction = "DOWN"

        else:

            direction = "SIDEWAYS"

        # --------------------------------------------------------------
        # 7. RELATIVE VOLUME
        # --------------------------------------------------------------

        relative_volume = 1.0

        volume_available = False

        volume_window = max(
            7,
            short_window + 1,
        )

        if len(volume) >= volume_window:

            previous_volume = volume[
                -volume_window:-1
            ]

            average_volume = _mean(
                previous_volume,
                0.0,
            )

            if average_volume > 0:

                relative_volume = _ratio(
                    volume[-1],
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
        # 9. ACCELERATION STRENGTH
        # --------------------------------------------------------------

        # Scale the raw return difference into a bounded score.
        #
        # This remains a model score, not probability.
        acceleration_strength = min(
            1.0,
            abs(acceleration)
            * 15.0,
        )

        # Current movement itself must also have meaningful
        # directional magnitude. Acceleration alone is not enough.
        movement_strength = min(
            1.0,
            abs(short_return)
            * 20.0,
        )

        structural_strength = (
            0.65
            * acceleration_strength
            + 0.35
            * movement_strength
        )

        # --------------------------------------------------------------
        # 10. VOLUME CONFIRMATION
        # --------------------------------------------------------------

        if volume_available:

            confirmation_multiplier = (
                0.80
                + 0.20
                * volume_confirmation
            )

        else:

            # Missing volume must not destroy the signal,
            # but also must not strengthen it.
            confirmation_multiplier = 0.80

        strength = _clamp(
            structural_strength
            * confirmation_multiplier,
            0.0,
            1.0,
        )

        # --------------------------------------------------------------
        # 11. MODEL SCORE
        # --------------------------------------------------------------

        if direction == "UP":

            score = strength

        elif direction == "DOWN":

            score = -strength

        else:

            score = 0.0

        # --------------------------------------------------------------
        # 12. CONFIDENCE
        #
        # NOT probability.
        # --------------------------------------------------------------

        confidence = min(
            0.90,
            0.20
            + 0.45
            * acceleration_strength
            + 0.20
            * movement_strength
            + (
                0.10
                * volume_confirmation
                if volume_available
                else 0.0
            ),
        )

        # Very small acceleration should not receive high confidence.
        if acceleration_strength < 0.15:

            confidence *= 0.65

        # --------------------------------------------------------------
        # 13. EARLY SIGNAL GATE
        # --------------------------------------------------------------

        early_signal = (
            abs(score) >= 0.25
            and acceleration_strength >= 0.20
            and movement_strength >= 0.10
        )

        # --------------------------------------------------------------
        # 14. VOLATILITY
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
        # 15. FORWARD MOVEMENT SCENARIO
        # --------------------------------------------------------------

        if early_signal:

            expected_return = (
                score
                * base_volatility
                * horizon_scale
                * 1.25
            )

        else:

            expected_return = 0.0

        expected_return = _clamp(
            expected_return,
            -0.10,
            0.10,
        )

        # --------------------------------------------------------------
        # 16. SCENARIO RANGE
        # --------------------------------------------------------------

        if early_signal:

            uncertainty_factor = max(
                0.30,
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

        else:

            lower_move = 0.0
            upper_move = 0.0

        # --------------------------------------------------------------
        # 17. FORECAST VALIDITY
        # --------------------------------------------------------------

        forecast_valid = (
            early_signal
            and len(close)
            >= minimum_history
        )

        # --------------------------------------------------------------
        # 18. EXPLANATION
        # --------------------------------------------------------------

        reason = (
            f"{horizon}-minute early movement: "
            f"acceleration={acceleration:.6f}, "
            f"short_return={short_return:.6f}, "
            f"prior_return={prior_return:.6f}, "
            f"relative_volume={relative_volume:.2f}, "
            f"early_signal={early_signal}"
        )

        if volume_available:

            reason += (
                ", "
                f"volume_confirmation="
                f"{volume_confirmation:.3f}"
            )

        else:

            reason += (
                ", volume_confirmation=UNAVAILABLE"
            )

        # --------------------------------------------------------------
        # 19. FINAL RESULT
        # --------------------------------------------------------------

        return _result(
            self.name,

            score,

            confidence,

            reason,

            0.90,

            horizon_minutes=horizon,

            short_window=short_window,

            prior_window=prior_window,

            early_signal=early_signal,

            direction=direction,

            forecast_valid=forecast_valid,

            acceleration=round(
                acceleration,
                8,
            ),

            short_return=round(
                short_return,
                8,
            ),

            prior_return=round(
                prior_return,
                8,
            ),

            acceleration_strength=round(
                acceleration_strength,
                6,
            ),

            movement_strength=round(
                movement_strength,
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

            calibration_status=(
                "NOT_CALIBRATED"
            ),

            data_quality="VALID",
        )

    analyze = predict
