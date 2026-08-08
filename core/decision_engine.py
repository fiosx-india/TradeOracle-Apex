"""Converts fused evidence into a transparent directional state."""
class DecisionEngine:
    def decide(self, fused):
        score = fused.get("score", 0.0)
        direction = "UP" if score > 0.15 else "DOWN" if score < -0.15 else "SIDEWAYS"
        return {
            "direction": direction,
            "confidence": fused.get("confidence", 0.0),
            "reasons": fused.get("reasons", []),
        }
