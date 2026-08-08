"""Price-action structure research."""
class PriceActionEngine:
    name = "PriceActionEngine"
    capabilities = ["RESEARCH"]
    def analyze(self, context):
        return {"score": 0.0, "weight": 1.0, "reason": self.name}
