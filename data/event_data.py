"""Structured event adapter."""
class EventData:
    name = "EventData"
    capabilities = ["EVENT_DATA"]
    def fetch(self, **kwargs):
        return []
