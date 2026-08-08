"""Commodity-to-sector/company impact."""
class CommodityImpact:
    name = "CommodityImpact"
    capabilities = ["COMMODITY"]
    def analyze(self, *args, **kwargs):
        return {"direction": "SIDEWAYS", "score": 0.0}
