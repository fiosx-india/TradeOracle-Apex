"""Base prediction interface."""
class PredictionEngine:
    name = "PredictionEngine"
    capabilities = ["PREDICTION"]
    def predict(self, context):
        return {
            "direction": "SIDEWAYS",
            "probability": 0.50,
            "horizon_minutes": getattr(context, "horizon_minutes", 60),
            "expected_move": [0.0, 0.0],
            "reason": "Model/data adapter not connected yet."
        }
