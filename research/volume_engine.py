"""Relative-volume and participation research."""
class VolumeEngine:
    name = "VolumeEngine"
    capabilities = ["RESEARCH"]
    def analyze(self, context):
        return {"score": 0.0, "weight": 1.0, "reason": self.name}
