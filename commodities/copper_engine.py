"""Copper analysis adapter."""
class CopperEngine:
    name = "CopperEngine"
    capabilities = ["COMMODITY"]
    def analyze(self, *args, **kwargs):
        return {"direction": "SIDEWAYS", "score": 0.0}
