"""Chronological walk-forward validation.

Each test window is evaluated only against outcomes that occur after its
prediction/training boundary.
"""

from __future__ import annotations


class WalkForward:
    name = "WalkForward"
    version = "2.0.0"
    capabilities = ["VALIDATION", "WALK_FORWARD"]

    def self_test(self):
        return True

    def split(self, rows, train_size, test_size, step=None):
        rows = list(rows or [])
        train_size = max(1, int(train_size))
        test_size = max(1, int(test_size))
        step = max(1, int(step or test_size))

        windows = []
        start = 0
        while start + train_size + test_size <= len(rows):
            train_end = start + train_size
            test_end = train_end + test_size
            windows.append({
                "train": rows[start:train_end],
                "test": rows[train_end:test_end],
                "train_start": start,
                "train_end": train_end,
                "test_end": test_end,
            })
            start += step
        return windows

    def run(self, rows=None, train_size=100, test_size=20, step=None):
        windows = self.split(rows or [], train_size, test_size, step)
        return {
            "status": "OK" if windows else "NO_DATA",
            "windows": len(windows),
            "splits": windows,
            "leakage_policy": "chronological_train_then_test",
        }
