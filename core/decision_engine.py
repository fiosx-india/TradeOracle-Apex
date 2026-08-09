"""Transparent directional decision layer with data-quality gating.

This module converts already-fused primary evidence into a directional
assessment. It does not fetch market data and it never places orders.

Contract:
    EvidenceFusion -> DecisionEngine -> SignalGate -> MasterBrain
"""

from __future__ import annotations

from typing import Any, Mapping

from config import (
    DOWN_THRESHOLD,
    MIN_CONFIDENCE_FOR_SIGNAL,
    MIN_HISTORY_BARS,
    REQUIRE_FRESH_DATA_FOR_SIGNAL,
    UP_THRESHOLD,
)

from .signal_gate import SignalGate


class DecisionEngine:
    """Turn fused evidence into a gated, explainable decision."""

    def __init__(self) -> None:
        self.gate = SignalGate(
            min_confidence=MIN_CONFIDENCE_FOR_SIGNAL,
            min_history=MIN_HISTORY_BARS,
            require_fresh=REQUIRE_FRESH_DATA_FOR_SIGNAL,
        )

    def decide(
        self,
        fused: Mapping[str, Any],
        market_data_quality: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create the final directional assessment before presentation.

        Parameters
        ----------
        fused:
            Already-fused evidence produced by EvidenceFusion.

        market_data_quality:
            Quality information produced by MarketData. This is passed to
            SignalGate so stale or insufficient market data cannot produce
            an active directional signal.

        Returns
        -------
        dict[str, Any]
            Explainable decision containing direction, score, confidence,
            signal strength, evidence, and final gate status.
        """

        score = float(
            fused.get("score", 0.0) or 0.0
        )

        confidence = float(
            fused.get("confidence", 0.0) or 0.0
        )

        # Keep externally supplied values inside the expected ranges.
        score = max(-1.0, min(1.0, score))
        confidence = max(0.0, min(1.0, confidence))

        # ---------------------------------------------------------
        # Direction classification
        # ---------------------------------------------------------
        if score >= UP_THRESHOLD:
            direction = "UP"

        elif score <= DOWN_THRESHOLD:
            direction = "DOWN"

        else:
            direction = "SIDEWAYS"

        # ---------------------------------------------------------
        # Signal strength
        # ---------------------------------------------------------
        if confidence >= 0.80:
            signal_strength = "STRONG"

        elif confidence >= MIN_CONFIDENCE_FOR_SIGNAL:
            signal_strength = "MODERATE"

        else:
            signal_strength = "WEAK"

        # ---------------------------------------------------------
        # Build explainable decision
        # ---------------------------------------------------------
        decision = {
            "direction": direction,
            "score": round(score, 6),
            "confidence": round(confidence, 6),
            "signal_strength": signal_strength,

            "agreement": fused.get(
                "agreement",
                0.0,
            ),

            "reasons": list(
                fused.get(
                    "reasons",
                    [],
                )
                or []
            ),

            "evidence": list(
                fused.get(
                    "evidence",
                    [],
                )
                or []
            ),

            "explainable": True,
        }

        # ---------------------------------------------------------
        # Final data-quality safety boundary
        #
        # DecisionEngine does not decide whether market data is
        # trustworthy. SignalGate owns that responsibility.
        #
        # Therefore:
        #
        #   fresh + sufficient + confidence OK
        #       -> active decision
        #
        #   stale / insufficient / low confidence
        #       -> WITHHELD
        # ---------------------------------------------------------
        return self.gate.apply(
            decision,
            market_data_quality=market_data_quality,
        )
