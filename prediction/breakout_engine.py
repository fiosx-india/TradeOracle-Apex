from __future__ import annotations

from typing import Any
import statistics


def _data(ctx) -> dict[str, Any]:
    data = getattr(ctx, "data", None)
    return data if isinstance(data, dict) else {}


def _series(ctx, *keys: str) -> list[float]:
    data = _data(ctx)

    for key in keys:
        values = data.get(key)

        if not isinstance(values, (list, tuple)):
            continue

        output: list[float] = []

        for value in values:
            try:
                number = float(value)

                if number == number:
                    output.append(number)

            except (TypeError, ValueError):
                continue

        if output:
            return output

    return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)

        if number != number:
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
        min(high, _safe_float(value)),
    )


def _mean(
    values: list[float],
    default: float = 0.0,
) -> float:
    if not values:
        return default

    return statistics.fmean(values)


def _ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:
    if denominator == 0:
        return default

    return numerator / denominator


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


class BreakoutEngine:
    """
    Detects a confirmed short-term price breakout.

    This engine is intentionally conservative.

    It:
    - uses only completed historical observations supplied
      by the current MarketContext;
    - compares the latest price with the prior range;
    - optionally uses relative volume as confirmation;
    - does not manufacture probability;
    - does not claim historical calibration;
    - reports model-derived confidence only.

    Historical calibration belongs to the validation layer.
    """

    name = "BreakoutEngine"
    version = "2.1.0"

    capabilities = [
        "PREDICTION",
        "BREAKOUT",
    ]

    def self_test(self) -> bool:
        return True

    def predict(self, context) -> dict[str, Any]:
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

        # ---------------------------------------------------------
        # Minimum data requirement
        # ---------------------------------------------------------
        if len(close) < 12:
            return _result(
                self.name,
                0.0,
                0.05,
                "Insufficient history for breakout detection.",
                0.0,
                breakout=False,
                direction="SIDEWAYS",
                calibration_status="NOT_CALIBRATED",
                data_quality="INSUFFICIENT",
            )

        # ---------------------------------------------------------
        # Previous completed range
        #
        # IMPORTANT:
        # The current candle is NOT included in the range.
        # This prevents the breakout threshold from using the
        # observation that is itself being tested.
        # ---------------------------------------------------------
        previous = close[-11:-1]

        if len(previous) < 10:
            return _result(
                self.name,
                0.0,
                0.05,
                "Insufficient prior range for breakout detection.",
                0.0,
                breakout=False,
                direction="SIDEWAYS",
                calibration_status="NOT_CALIBRATED",
                data_quality="INSUFFICIENT",
            )

        range_high = max(previous)
        range_low = min(previous)

        last_price = close[-1]

        # ---------------------------------------------------------
        # Range width
        # ---------------------------------------------------------
        range_width = range_high - range_low

        if range_width <= 0:
            return _result(
                self.name,
                0.0,
                0.05,
                "Previous price range is not usable.",
                0.0,
                breakout=False,
                direction="SIDEWAYS",
                calibration_status="NOT_CALIBRATED",
                data_quality="INVALID_RANGE",
            )

        # ---------------------------------------------------------
        # Breakout distance
        #
        # Normalize the distance by the previous range width.
        # This prevents the raw price scale from dominating.
        # ---------------------------------------------------------
        upside_distance = _ratio(
            last_price - range_high,
            range_width,
        )

        downside_distance = _ratio(
            range_low - last_price,
            range_width,
        )

        # ---------------------------------------------------------
        # Relative volume
        # ---------------------------------------------------------
        relative_volume = 1.0
        volume_available = False

        if len(volume) >= 11:
            previous_volume = volume[-11:-1]

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

        # ---------------------------------------------------------
        # Volume confirmation
        #
        # We do NOT treat missing/zero index volume as confirmation.
        # ---------------------------------------------------------
        if volume_available:
            volume_confirmation = _clamp(
                (relative_volume - 1.0) / 1.5,
                0.0,
                1.0,
            )
        else:
            volume_confirmation = 0.0

        # ---------------------------------------------------------
        # Breakout detection
        # ---------------------------------------------------------
        upward_breakout = last_price > range_high
        downward_breakout = last_price < range_low

        if not upward_breakout and not downward_breakout:
            return _result(
                self.name,
                0.0,
                0.15,
                (
                    "No confirmed breakout. "
                    f"price={last_price:.4f}, "
                    f"range_high={range_high:.4f}, "
                    f"range_low={range_low:.4f}"
                ),
                0.8,
                breakout=False,
                direction="SIDEWAYS",
                range_high=round(range_high, 6),
                range_low=round(range_low, 6),
                relative_volume=round(
                    relative_volume,
                    6,
                ),
                volume_confirmation=round(
                    volume_confirmation,
                    6,
                ),
                calibration_status="NOT_CALIBRATED",
            )

        # ---------------------------------------------------------
        # Breakout strength
        #
        # Distance contributes more than volume because price
        # structure is available even when index volume is absent.
        # ---------------------------------------------------------
        if upward_breakout:
            distance = max(
                0.0,
                upside_distance,
            )

            direction = "UP"

        else:
            distance = max(
                0.0,
                downside_distance,
            )

            direction = "DOWN"

        distance_strength = min(
            1.0,
            distance * 3.0,
        )

        # Base structural strength.
        structural_strength = min(
            1.0,
            0.55 + 0.35 * distance_strength,
        )

        # Volume is confirmation, not the primary trigger.
        confirmation_strength = (
            0.75
            + 0.25 * volume_confirmation
            if volume_available
            else 0.75
        )

        strength = _clamp(
            structural_strength
            * confirmation_strength,
            0.0,
            1.0,
        )

        # ---------------------------------------------------------
        # Model-derived score
        # ---------------------------------------------------------
        score = strength if direction == "UP" else -strength

        # ---------------------------------------------------------
        # Model-derived confidence
        #
        # This is intentionally conservative and NOT a calibrated
        # probability.
        # ---------------------------------------------------------
        confidence = min(
            0.90,
            0.25
            + 0.45 * strength
            + 0.15 * distance_strength
            + (
                0.10 * volume_confirmation
                if volume_available
                else 0.0
            ),
        )

        reason_parts = [
            f"breakout={True}",
            f"direction={direction}",
            f"distance_strength={distance_strength:.3f}",
            f"relative_volume={relative_volume:.2f}",
        ]

        if volume_available:
            reason_parts.append(
                f"volume_confirmation={volume_confirmation:.3f}"
            )
        else:
            reason_parts.append(
                "volume_confirmation=UNAVAILABLE"
            )

        return _result(
            self.name,
            score,
            confidence,
            ", ".join(reason_parts),
            0.9,
            breakout=True,
            direction=direction,
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
            volume_available=volume_available,
            calibration_status="NOT_CALIBRATED",
            forecast_valid=True,
        )

    analyze = predict
