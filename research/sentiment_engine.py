"""Sentiment aggregation interface."""
class SentimentEngine:
    name = "SentimentEngine"
    capabilities = ["RESEARCH"]
    def analyze(self, context):
        return {"score": 0.0, "weight": 1.0, "reason": self.name}
