"""Normalized price data contract."""
class PriceData:
    name = "PriceData"
    capabilities = ["PRICE_DATA"]
    def fetch(self, symbol, **kwargs):
        return []
