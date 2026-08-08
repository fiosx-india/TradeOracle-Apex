"""Normalized volume data contract."""
class VolumeData:
    name = "VolumeData"
    capabilities = ["VOLUME_DATA"]
    def fetch(self, symbol, **kwargs):
        return []
