"""Input-data quality checks for trading validation."""

from __future__ import annotations
from datetime import datetime


class DataQuality:
    name = "DataQuality"
    version = "2.0.0"
    capabilities = ["VALIDATION", "DATA_QUALITY"]

    def self_test(self):
        return True

    def validate(self, rows, required=("timestamp", "symbol")):
        rows = list(rows or [])
        errors = []
        warnings = []
        seen = set()

        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"row_{i}:not_mapping")
                continue

            for key in required:
                if row.get(key) in (None, ""):
                    errors.append(f"row_{i}:missing_{key}")

            timestamp = row.get("timestamp")
            if timestamp:
                try:
                    datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                except ValueError:
                    warnings.append(f"row_{i}:invalid_timestamp")

            key = (row.get("symbol"), row.get("timestamp"))
            if key in seen:
                warnings.append(f"row_{i}:duplicate_timestamp_symbol")
            seen.add(key)

        return {
            "status": "PASS" if not errors else "FAIL",
            "rows": len(rows),
            "errors": errors,
            "warnings": warnings,
            "quality_score": (
                max(0.0, 1.0 - min(1.0, len(errors) / max(1, len(rows))))
                if rows else 0.0
            ),
        }

    def run(self, rows=None):
        return self.validate(rows or [])
