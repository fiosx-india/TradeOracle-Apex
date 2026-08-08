"""Silver analysis adapter."""
class SilverEngine:
    name = "SilverEngine"
    capabilities = ["COMMODITY"]
    def analyze(self, *args, **kwargs):
        return {"direction": "SIDEWAYS", "score": 0.0}
