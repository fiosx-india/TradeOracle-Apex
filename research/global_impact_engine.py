"""Global-to-local market impact mapping."""
class GlobalImpactEngine:
    name = "GlobalImpactEngine"
    capabilities = ["RESEARCH"]
    def analyze(self, context):
        return {"score": 0.0, "weight": 1.0, "reason": self.name}
