"""Immutable prediction snapshots."""
class PredictionLedger:
    def run(self, *args, **kwargs):
        return {"status": "NOT_CONFIGURED", "purpose": self.__class__.__doc__}
