"""Final signal-quality gate for TradeOracle Apex.

Responsibilities:
- withhold directional signals when market-data quality is insufficient
- enforce minimum usable history
- enforce market-data freshness when configured
- reject INVALID / ERROR market-data states explicitly
- enforce a bounded confidence threshold
- preserve the original model direction as ``raw_direction``
- never manufacture, repair, or upgrade a trading signal

This module contains NO order-placement or GTT operations.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


class SignalGate:
    """Withhold directional signals when data quality is insufficient."""

    name = "SignalGate"
    version = "2.2.0"

    ALLOWED_DIRECTIONS = {
        "UP",
        "DOWN",
        "SIDEWAYS",
    }

    def __init__(
        self,
        min_confidence: float = 0.60,
        min_history: int = 30,
        require_fresh: bool = True,
    ) -> None:
        self.min_confidence = max(
            0.0,
            min(
                1.0,
                float(min_confidence),
            ),
        )

        self.min_history = max(
            1,
            int(min_history),
        )

        self.require_fresh = bool(
            require_fresh
        )

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

        if not math.isfinite(number):
            return default

        return number

    @staticmethod
    def _safe_int(
        value: Any,
        default: int = 0,
    ) -> int:
        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

    # ==================================================================
    # APPLY GATE
    # ==================================================================

    def apply(
        self,
        decision: Mapping[str, Any],
        market_data_quality: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Apply the final data-quality gate to a model decision.

        A directional decision is ACTIVE only when:
        1. market-data status is not INVALID/ERROR,
        2. usable history meets min_history,
        3. data is fresh when require_fresh=True,
        4. confidence is finite and >= min_confidence,
        5. the model direction is UP or DOWN.

        The gate never changes a valid model direction into another
        direction. When blocked, direction is explicitly SIDEWAYS.
        """

        result = dict(decision)
        quality = dict(
            market_data_quality or {}
        )

        # --------------------------------------------------------------
        # RAW DIRECTION
        # --------------------------------------------------------------

        raw_direction = str(
            result.get(
                "direction",
                "SIDEWAYS",
            )
        ).upper().strip()

        result["raw_direction"] = raw_direction

        # Unknown directions are not tradable. Preserve them in
        # raw_direction for diagnostics rather than inventing a mapping.
        if raw_direction not in self.ALLOWED_DIRECTIONS:
            direction_is_valid = False
        else:
            direction_is_valid = True

        # --------------------------------------------------------------
        # QUALITY FIELDS
        # --------------------------------------------------------------

        total_count = self._safe_int(
            quality.get("count", 0),
            0,
        )

        valid_count_value = quality.get(
            "valid_count"
        )

        if valid_count_value is None:
            usable_history = total_count
        else:
            usable_history = self._safe_int(
                valid_count_value,
                0,
            )

        invalid_count = self._safe_int(
            quality.get("invalid_count", 0),
            0,
        )

        fresh = bool(
            quality.get(
                "fresh",
                False,
            )
        )

        status = str(
            quality.get(
                "status",
                "UNKNOWN",
            )
        ).upper().strip()

        # Explicit provider/gateway failures must never be treated as
        # merely "not fresh". They are distinct diagnostic conditions.
        market_data_blocked = status in {
            "INVALID",
            "ERROR",
        }

        # If the quality payload reports invalid records but does not
        # provide invalid_count, fall back to the presence of "invalid".
        invalid_items = quality.get(
            "invalid"
        )

        if invalid_count <= 0 and isinstance(
            invalid_items,
            (list, tuple),
        ):
            invalid_count = len(
                invalid_items
            )

        # --------------------------------------------------------------
        # CONFIDENCE
        # --------------------------------------------------------------

        raw_confidence = result.get(
            "confidence",
            0.0,
        )

        confidence = self._safe_float(
            raw_confidence,
            0.0,
        )

        result["confidence"] = confidence

        # --------------------------------------------------------------
        # REASONS
        # --------------------------------------------------------------

        reasons: list[str] = []

        if not direction_is_valid:
            reasons.append(
                f"invalid_direction:{raw_direction}"
            )

        if market_data_blocked:
            reasons.append(
                f"market_data_status:{status}"
            )

        if invalid_count > 0:
            reasons.append(
                f"invalid_market_data_records:{invalid_count}"
            )

        if usable_history < self.min_history:
            reasons.append(
                "history_below_minimum:"
                f"{usable_history}<{self.min_history}"
            )

        if self.require_fresh and not fresh:
            reasons.append(
                f"market_data_not_fresh:{status}"
            )

        if confidence < self.min_confidence:
            reasons.append(
                "confidence_below_minimum:"
                f"{confidence:.4f}<{self.min_confidence:.4f}"
            )

        # --------------------------------------------------------------
        # WITHHELD
        # --------------------------------------------------------------

        if reasons:
            result.update(
                {
                    "direction": "SIDEWAYS",
                    "signal_strength": "WITHHELD",
                    "decision_status": "WITHHELD",
                    "tradable_signal": False,
                    "gate_reasons": reasons,
                }
            )

            return result

        # --------------------------------------------------------------
        # ACTIVE
        # --------------------------------------------------------------

        result.update(
            {
                "decision_status": "ACTIVE",
                "tradable_signal": (
                    raw_direction
                    in {
                        "UP",
                        "DOWN",
                    }
                ),
                "gate_reasons": [],
            }
        )

        return result

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health(self) -> dict[str, Any]:
        """Return gate configuration for diagnostics."""

        return {
            "engine": self.name,
            "version": self.version,
            "min_confidence": self.min_confidence,
            "min_history": self.min_history,
            "require_fresh": self.require_fresh,
            "allowed_directions": sorted(
                self.ALLOWED_DIRECTIONS
            ),
        }
