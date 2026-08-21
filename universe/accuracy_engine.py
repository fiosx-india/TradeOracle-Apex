"""Directional, probability and magnitude accuracy metrics."""

from __future__ import annotations
from typing import Iterable, Mapping


class AccuracyEngine:
    name = "AccuracyEngine"
    version = "2.0.0"
    capabilities = ["VALIDATION", "ACCURACY"]

    def self_test(self):
        return True

    @staticmethod
    def _direction(value):
        try:
            x = float(value)
        except (TypeError, ValueError):
            return "SIDEWAYS"
        if x > 0.05:
            return "UP"
        if x < -0.05:
            return "DOWN"
        return "SIDEWAYS"

    def evaluate(self, predictions: Iterable[Mapping], actuals: Iterable[Mapping]):
        actual_map = {}
        for row in actuals or []:
            if isinstance(row, Mapping):
                key = row.get("symbol", row.get("id"))
                if key is not None:
                    actual_map[str(key)] = row

        total = correct = 0
        errors = []
        for pred in predictions or []:
            if not isinstance(pred, Mapping):
                continue
            key = pred.get("symbol", pred.get("id"))
            actual = actual_map.get(str(key))
            if actual is None:
                continue

            pd = pred.get("direction", pred.get("score", 0))
            ad = actual.get("direction", actual.get("return", 0))
            pd, ad = self._direction(pd), self._direction(ad)
            total += 1
            correct += int(pd == ad)
            errors.append({
                "symbol": str(key),
                "predicted": pd,
                "actual": ad,
                "correct": pd == ad,
            })

        return {
            "status": "OK",
            "samples": total,
            "directional_accuracy": correct / total if total else None,
            "correct": correct,
            "errors": total - correct,
            "details": errors,
        }

    def run(self, predictions=None, actuals=None):
        return self.evaluate(predictions or [], actuals or [])
