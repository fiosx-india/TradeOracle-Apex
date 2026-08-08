"""Fundamental context interface."""
class FundamentalEngine:
    name = "FundamentalEngine"
    capabilities = ["RESEARCH"]
    def analyze(self, context):
        return {"score": 0.0, "weight": 1.0, "reason": self.name}
