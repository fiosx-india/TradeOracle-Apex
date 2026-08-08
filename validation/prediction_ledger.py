"""Append-only prediction/outcome ledger abstraction."""

from __future__ import annotations
from datetime import datetime, timezone


class PredictionLedger:
    name = "PredictionLedger"
    version = "2.0.0"
    capabilities = ["VALIDATION", "LEDGER"]

    def __init__(self):
        self._rows = []

    def self_test(self):
        return True

    def record(self, prediction):
        if not isinstance(prediction, dict):
            raise TypeError("prediction must be a dict")

        row = dict(prediction)
        row.setdefault(
            "recorded_at",
            datetime.now(timezone.utc).isoformat(),
        )
        row.setdefault("status", "OPEN")
        self._rows.append(row)
        return dict(row)

    def close(self, symbol, outcome, timestamp=None):
        symbol = str(symbol).upper()
        changed = 0
        for row in self._rows:
            if str(row.get("symbol", "")).upper() == symbol and row.get("status") == "OPEN":
                row["outcome"] = outcome
                row["outcome_timestamp"] = timestamp or datetime.now(timezone.utc).isoformat()
                row["status"] = "CLOSED"
                changed += 1
        return changed

    def all(self):
        return [dict(row) for row in self._rows]

    def open_predictions(self):
        return [dict(row) for row in self._rows if row.get("status") == "OPEN"]
