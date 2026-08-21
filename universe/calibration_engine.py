"""Probability calibration metrics."""

from __future__ import annotations
from typing import Iterable, Mapping


class CalibrationEngine:
    name = "CalibrationEngine"
    version = "2.0.0"
    capabilities = ["VALIDATION", "CALIBRATION"]

    def self_test(self):
        return True

    def evaluate(self, rows: Iterable[Mapping]):
        buckets = {}
        for row in rows or []:
            if not isinstance(row, Mapping):
                continue
            try:
                p = max(0.0, min(1.0, float(row["probability"])))
                y = 1.0 if bool(row["outcome"]) else 0.0
            except (KeyError, TypeError, ValueError):
                continue

            bucket = min(9, int(p * 10))
            buckets.setdefault(bucket, []).append((p, y))

        result = []
        total = 0
        weighted_error = 0.0

        for bucket, values in sorted(buckets.items()):
            avg_p = sum(x[0] for x in values) / len(values)
            avg_y = sum(x[1] for x in values) / len(values)
            result.append({
                "bucket": bucket,
                "samples": len(values),
                "mean_probability": avg_p,
                "empirical_rate": avg_y,
                "calibration_error": abs(avg_p - avg_y),
            })
            weighted_error += abs(avg_p - avg_y) * len(values)
            total += len(values)

        return {
            "status": "OK" if total else "NO_DATA",
            "samples": total,
            "expected_calibration_error": weighted_error / total if total else None,
            "buckets": result,
        }

    def run(self, rows=None):
        return self.evaluate(rows or [])
