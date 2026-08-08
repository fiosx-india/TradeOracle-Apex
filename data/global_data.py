"""Global market context adapter."""
class GlobalData:
    name = "GlobalData"
    capabilities = ["GLOBAL_DATA"]
    def fetch(self, **kwargs):
        return []
