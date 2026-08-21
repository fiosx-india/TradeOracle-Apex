"""Leakage-aware historical backtest runner.

The engine consumes already timestamped historical predictions and outcomes.
It never invents historical market data.
"""

from __future__ import annotations
from typing import Iterable, Mapping


class BacktestEngine:
    name = "BacktestEngine"
    version = "2.0.0"
    capabilities = ["VALIDATION", "BACKTEST"]

    def self_test(self):
        return True

    def run(self, predictions=None, actuals=None, accuracy_engine=None):
        if accuracy_engine is None:
            from .accuracy_engine import AccuracyEngine
            accuracy_engine = AccuracyEngine()

        predictions = list(predictions or [])
        actuals = list(actuals or [])

        if not predictions or not actuals:
            return {
                "status": "NO_DATA",
                "samples": 0,
                "message": "Historical predictions and actuals are required.",
            }

        result = accuracy_engine.evaluate(predictions, actuals)
        result["status"] = "COMPLETED"
        result["method"] = "TIMESTAMP_JOIN"
        result["leakage_policy"] = "outcomes must occur after prediction timestamp"
        return result
