"""Crude analysis adapter."""
class CrudeEngine:
    name = "CrudeEngine"
    capabilities = ["COMMODITY"]
    def analyze(self, *args, **kwargs):
        return {"direction": "SIDEWAYS", "score": 0.0}
