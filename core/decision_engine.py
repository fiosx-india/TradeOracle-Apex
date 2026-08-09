"""Transparent directional decision layer with data-quality gating."""

from config import (
    DOWN_THRESHOLD,
    MIN_CONFIDENCE_FOR_SIGNAL,
    MIN_HISTORY_BARS,
    REQUIRE_FRESH_DATA_FOR_SIGNAL,
    UP_THRESHOLD,
)
from .signal_gate import SignalGate


class DecisionEngine:
    def __init__(self):
        self.gate = SignalGate(
            min_confidence=MIN_CONFIDENCE_FOR_SIGNAL,
            min_history=MIN_HISTORY_BARS,
            require_fresh=REQUIRE_FRESH_DATA_FOR_SIGNAL,
        )

    def decide(self, fused, market_data_quality=None):
        score = float(fused.get("score", 0.0))
        confidence = float(fused.get("confidence", 0.0))

        if score >= UP_THRESHOLD:
            direction = "UP"
        elif score <= DOWN_THRESHOLD:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        signal_strength = (
            "STRONG" if confidence >= 0.80
            else "MODERATE" if confidence >= MIN_CONFIDENCE_FOR_SIGNAL
            else "WEAK"
        )

        decision = {
            "direction": direction,
            "score": round(score, 6),
            "confidence": round(confidence, 6),
            "signal_strength": signal_strength,
            "agreement": fused.get("agreement", 0.0),
            "reasons": fused.get("reasons", []),
            "evidence": fused.get("evidence", []),
            "explainable": True,
        }
        return self.gate.apply(decision, market_data_quality)
