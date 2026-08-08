"""Generic index constituent and breadth engine."""

from __future__ import annotations
from typing import Any, Mapping


class IndexEngine:
    name = "IndexEngine"
    version = "2.0.0"
    capabilities = ["UNIVERSE", "INDEX"]

    def self_test(self):
        return True

    def __init__(self, name="INDEX", constituents=None):
        self.index_name = str(name).upper()
        self.constituents = []
        self.set_constituents(constituents or [])

    def set_constituents(self, constituents):
        normalized = []
        for item in constituents:
            if isinstance(item, str):
                symbol = item.strip().upper()
                if symbol:
                    normalized.append({"symbol": symbol, "weight": None})
            elif isinstance(item, Mapping):
                symbol = str(item.get("symbol") or "").strip().upper()
                if symbol:
                    weight = item.get("weight")
                    try:
                        weight = float(weight) if weight is not None else None
                    except (TypeError, ValueError):
                        weight = None
                    normalized.append({
                        **dict(item),
                        "symbol": symbol,
                        "weight": weight,
                    })
        self.constituents = normalized
        return self.constituents

    def symbols(self):
        return [x["symbol"] for x in self.constituents]

    def breadth(self, predictions=None):
        predictions = predictions or {}
        up = down = flat = 0
        rows = []

        for constituent in self.constituents:
            symbol = constituent["symbol"]
            item = predictions.get(symbol, {})
            try:
                score = float(item.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0

            if score > 0.05:
                direction = "UP"
                up += 1
            elif score < -0.05:
                direction = "DOWN"
                down += 1
            else:
                direction = "SIDEWAYS"
                flat += 1

            rows.append({
                "symbol": symbol,
                "score": score,
                "direction": direction,
                "weight": constituent.get("weight"),
            })

        total = len(rows)
        return {
            "index": self.index_name,
            "constituents": total,
            "up": up,
            "down": down,
            "sideways": flat,
            "advance_ratio": up / total if total else 0.0,
            "decline_ratio": down / total if total else 0.0,
            "rows": rows,
        }

    def analyze(self, context):
        data = getattr(context, "data", {})
        predictions = data.get("predictions", {}) if isinstance(data, dict) else {}
        breadth = self.breadth(predictions)
        score = breadth["advance_ratio"] - breadth["decline_ratio"]
        return {
            "engine": self.name,
            "score": round(max(-1.0, min(1.0, score)), 6),
            "weight": 0.8,
            "confidence": 0.7 if breadth["constituents"] else 0.05,
            "reason": (
                f"{self.index_name} breadth: "
                f"{breadth['up']} up / {breadth['down']} down / "
                f"{breadth['sideways']} sideways"
            ),
            "breadth": breadth,
        }
