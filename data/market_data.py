"""Market data adapter contract."""
class MarketData:
    name = "MarketData"
    capabilities = ["MARKET_DATA"]
    def fetch(self, symbol=None, start=None, end=None):
        return []
