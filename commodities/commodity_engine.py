"""Commodity aggregation and normalization."""
class CommodityEngine:
    name = "CommodityEngine"
    capabilities = ["COMMODITY"]
    def analyze(self, *args, **kwargs):
        return {"direction": "SIDEWAYS", "score": 0.0}
