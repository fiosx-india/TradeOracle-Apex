"""Currency/FX data adapter."""
class CurrencyData:
    name = "CurrencyData"
    capabilities = ["CURRENCY_DATA"]
    def fetch(self, **kwargs):
        return []
