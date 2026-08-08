"""Gold analysis adapter."""
class GoldEngine:
    name = "GoldEngine"
    capabilities = ["COMMODITY"]
    def analyze(self, *args, **kwargs):
        return {"direction": "SIDEWAYS", "score": 0.0}
