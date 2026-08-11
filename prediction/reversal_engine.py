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
            "ReversalEngine requires "
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
# HORIZON WINDOWS
# ---------------------------------------------------------------------------

def _windows_for_horizon(
    horizon: int,
) -> tuple[int, int]:
    """
    Return:

        extension_window
        weakening_window

    for the selected horizon.

    The market data remains 1-minute candles.
    """

    return {
        5: (5, 2),
        15: (10, 3),
        30: (20, 5),
        60: (40, 8),
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

class ReversalEngine:
    """
    Detects potential directional reversal after an extended move.

    Supported horizons:

        5 minutes
        15 minutes
        30 minutes
        60 minutes

    Reversal evidence is based on:

        1. directional extension
        2. weakening of the most recent move
        3. short-term counter-movement
        4. optional volume confirmation

    The engine reports a model-derived reversal score.

    It does NOT:
        - claim a calibrated probability;
        - guarantee a reversal;
        - use future candles;
        - create a final BUY/SELL decision.
    """

    name = "ReversalEngine"
    version = "2.3.0"

    capabilities = [
        "PREDICTION",
        "REVERSAL",
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

        (
            extension_window,
            weakening_window,
        ) = _windows_for_horizon(
            horizon
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
            extension_window
            + weakening_window
            + 2
        )

        if len(close) < minimum_history:

            return _result(
                self.name,
                0.0,
                0.0,
                (
                    f"Insufficient history for "
                    f"{horizon}-minute reversal "
                    f"detection."
                ),
                0.0,

                horizon_minutes=horizon,

                extension_window=(
                    extension_window
                ),

                weakening_window=(
                    weakening_window
                ),

                reversal_detected=False,

                reversal_risk=0.0,

                direction="SIDEWAYS",

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INSUFFICIENT",

                extension=0.0,

                weakening=0.0,

                counter_move=0.0,

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
        # 3. CURRENT EXTENSION
        # --------------------------------------------------------------
        #
        # Measure the directional move over the selected horizon
        # window, excluding future information.
        # --------------------------------------------------------------

        extension_reference_index = (
            -(extension_window + 1)
        )

        extension_reference = close[
            extension_reference_index
        ]

        if extension_reference == 0:

            return _result(
                self.name,
                0.0,
                0.0,
                "Invalid extension reference price.",
                0.0,

                horizon_minutes=horizon,

                extension_window=(
                    extension_window
                ),

                weakening_window=(
                    weakening_window
                ),

                reversal_detected=False,

                reversal_risk=0.0,

                direction="SIDEWAYS",

                forecast_valid=False,

                calibration_status=(
                    "NOT_CALIBRATED"
                ),

                data_quality="INVALID_REFERENCE",

            )

        extension = _ratio(
            close[-1]
            - extension_reference,
            abs(extension_reference),
        )

        # --------------------------------------------------------------
        # 4. RECENT MOVE
        # --------------------------------------------------------------

        recent_reference_index = (
            -(weakening_window + 1)
        )

        recent_reference = close[
            recent_reference_index
        ]

        if recent_reference == 0:

            recent_move = 0.0

        else:

            recent_move = _ratio(
                close[-1]
                - recent_reference,
                abs(recent_reference),
            )

        # --------------------------------------------------------------
        # 5. PREVIOUS MOVE
        # --------------------------------------------------------------
        #
        # Compare the recent movement with the preceding segment.
        # This gives us a directional weakening signal rather than
        # simply checking whether the last candle changed sign.
        # --------------------------------------------------------------

        previous_end = (
            recent_reference_index
        )

        previous_start = (
            previous_end
            - weakening_window
        )

        previous_segment = close[
            previous_start:previous_end
        ]

        if len(previous_segment) >= 2:

            previous_reference = (
                previous_segment[0]
            )

            previous_last = (
                previous_segment[-1]
            )

            if previous_reference != 0:

                previous_move = _ratio(
                    previous_last
                    - previous_reference,
                    abs(previous_reference),
                )

            else:

                previous_move = 0.0

        else:

            previous_move = 0.0

        # --------------------------------------------------------------
        # 6. WEAKENING
        # --------------------------------------------------------------

        if extension > 0:

            # Bullish extension should weaken toward zero or turn
            # negative before an actual bearish reversal.
            weakening_amount = max(
                0.0,
                previous_move
                - recent_move,
            )

        elif extension < 0:

            # Bearish extension should weaken toward zero or turn
            # positive before an actual bullish reversal.
            weakening_amount = max(
                0.0,
                recent_move
                - previous_move,
            )

        else:

            weakening_amount = 0.0

        weakening_strength = min(
            1.0,
            abs(
                weakening_amount
            ) * 20.0,
        )

        # --------------------------------------------------------------
        # 7. COUNTER-MOVEMENT
        # --------------------------------------------------------------
        #
        # A reversal should have movement opposite to the original
        # extension direction.
        # --------------------------------------------------------------

        if extension > 0:

            counter_move = max(
                0.0,
                -recent_move,
            )

        elif extension < 0:

            counter_move = max(
                0.0,
                recent_move,
            )

        else:

            counter_move = 0.0

        counter_move_strength = min(
            1.0,
            abs(counter_move)
            * 20.0,
        )

        # --------------------------------------------------------------
        # 8. EXTENSION STRENGTH
        # --------------------------------------------------------------

        extension_strength = min(
            1.0,
            abs(extension)
            * 8.0,
        )

        # --------------------------------------------------------------
        # 9. DIRECTIONAL REVERSAL
        # --------------------------------------------------------------

        if extension > 0:

            reversal_direction = "DOWN"

        elif extension < 0:

            reversal_direction = "UP"

        else:

            reversal_direction = "SIDEWAYS"

        # --------------------------------------------------------------
        # 10. VOLUME
        # --------------------------------------------------------------

        relative_volume = 1.0

        volume_available = False

        volume_window = max(
            7,
            weakening_window + 1,
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
        # 11. VOLUME CONFIRMATION
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
        # 12. REVERSAL RISK
        # --------------------------------------------------------------
        #
        # Extension is necessary but not sufficient.
        #
        # We require weakening and/or counter-movement to build
        # meaningful reversal evidence.
        # --------------------------------------------------------------

        structural_risk = (
            0.45
            * extension_strength
            + 0.35
            * weakening_strength
            + 0.20
            * counter_move_strength
        )

        # No weakening/counter-movement means extension alone should
        # not create a strong reversal signal.
        confirmation_factor = (
            0.65
            + 0.35
            * max(
                weakening_strength,
                counter_move_strength,
            )
        )

        if volume_available:

            volume_factor = (
                0.85
                + 0.15
                * volume_confirmation
            )

        else:

            volume_factor = 0.85

        reversal_risk = _clamp(
            structural_risk
            * confirmation_factor
            * volume_factor,
            0.0,
            1.0,
        )

        # --------------------------------------------------------------
        # 13. REVERSAL GATE
        # --------------------------------------------------------------

        reversal_detected = (
            reversal_risk >= 0.25
            and extension_strength >= 0.20
            and (
                weakening_strength >= 0.15
                or counter_move_strength >= 0.15
            )
        )

        # --------------------------------------------------------------
        # 14. MODEL SCORE
        # --------------------------------------------------------------

        if reversal_detected:

            if reversal_direction == "DOWN":

                score = -reversal_risk

            elif reversal_direction == "UP":

                score = reversal_risk

            else:

                score = 0.0

        else:

            score = 0.0

        # --------------------------------------------------------------
        # 15. CONFIDENCE
        #
        # NOT probability.
        # --------------------------------------------------------------

        confidence = min(
            0.90,

            0.15
            + 0.35
            * extension_strength
            + 0.30
            * weakening_strength
            + 0.20
            * counter_move_strength
            + (
                0.05
                * volume_confirmation
                if volume_available
                else 0.0
            ),
        )

        if not reversal_detected:

            confidence *= 0.60

        # --------------------------------------------------------------
        # 16. VOLATILITY
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
        # 17. FORWARD SCENARIO
        # --------------------------------------------------------------

        if reversal_detected:

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
        # 18. SCENARIO RANGE
        # --------------------------------------------------------------

        if reversal_detected:

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

            if reversal_direction == "UP":

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

            elif reversal_direction == "DOWN":

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

        else:

            lower_move = 0.0
            upper_move = 0.0

        # --------------------------------------------------------------
        # 19. FORECAST VALIDITY
        # --------------------------------------------------------------

        forecast_valid = (
            reversal_detected
            and len(close)
            >= minimum_history
        )

        # --------------------------------------------------------------
        # 20. EXPLANATION
        # --------------------------------------------------------------

        reason = (
            f"{horizon}-minute reversal analysis: "
            f"extension={extension:.6f}, "
            f"recent_move={recent_move:.6f}, "
            f"previous_move={previous_move:.6f}, "
            f"weakening_strength="
            f"{weakening_strength:.3f}, "
            f"counter_move_strength="
            f"{counter_move_strength:.3f}, "
            f"reversal_risk="
            f"{reversal_risk:.3f}"
        )

        if volume_available:

            reason += (
                ", "
                f"relative_volume="
                f"{relative_volume:.2f}, "
                f"volume_confirmation="
                f"{volume_confirmation:.3f}"
            )

        else:

            reason += (
                ", volume_confirmation=UNAVAILABLE"
            )

        # --------------------------------------------------------------
        # 21. FINAL RESULT
        # --------------------------------------------------------------

        return _result(
            self.name,

            score,

            confidence,

            reason,

            0.80,

            horizon_minutes=horizon,

            extension_window=(
                extension_window
            ),

            weakening_window=(
                weakening_window
            ),

            reversal_detected=(
                reversal_detected
            ),

            reversal_risk=round(
                reversal_risk,
                6,
            ),

            direction=(
                reversal_direction
                if reversal_detected
                else "SIDEWAYS"
            ),

            extension=round(
                extension,
                8,
            ),

            recent_move=round(
                recent_move,
                8,
            ),

            previous_move=round(
                previous_move,
                8,
            ),

            weakening_strength=round(
                weakening_strength,
                6,
            ),

            counter_move_strength=round(
                counter_move_strength,
                6,
            ),

            extension_strength=round(
                extension_strength,
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

            forecast_valid=forecast_valid,

            calibration_status=(
                "NOT_CALIBRATED"
            ),

            data_quality="VALID",
        )

    analyze = predict
