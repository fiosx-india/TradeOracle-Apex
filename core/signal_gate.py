"""Final signal-quality gate for TradeOracle Apex."""
from __future__ import annotations

from typing import Any, Mapping


class SignalGate:
    """Withhold directional signals when data quality is insufficient."""

    def __init__(
        self,
        min_confidence: float = 0.60,
        min_history: int = 30,
        require_fresh: bool = True,
    ) -> None:
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.min_history = max(1, int(min_history))
        self.require_fresh = bool(require_fresh)

    def apply(
        self,
        decision: Mapping[str, Any],
        market_data_quality: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = dict(decision)
        quality = dict(market_data_quality or {})

        raw_direction = str(result.get("direction", "SIDEWAYS")).upper()
        result["raw_direction"] = raw_direction

        count = int(quality.get("count", 0) or 0)
        fresh = bool(quality.get("fresh", False))
        status = str(quality.get("status", "UNKNOWN")).upper()
        confidence = float(result.get("confidence", 0.0) or 0.0)

        reasons: list[str] = []
        if count < self.min_history:
            reasons.append(f"history_below_minimum:{count}<{self.min_history}")
        if self.require_fresh and not fresh:
            reasons.append(f"market_data_not_fresh:{status}")
        if confidence < self.min_confidence:
            reasons.append(
                f"confidence_below_minimum:{confidence:.4f}<{self.min_confidence:.4f}"
            )

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

        result.update(
            {
                "decision_status": "ACTIVE",
                "tradable_signal": raw_direction in {"UP", "DOWN"},
                "gate_reasons": [],
            }
        )
        return result
