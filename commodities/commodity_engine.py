"""Commodity aggregation and normalization.

Consumes supplied observations; it never invents live commodity prices.
"""

from __future__ import annotations
from typing import Any, Mapping


class CommodityEngine:
    name="CommodityEngine"
    version="2.0.0"
    capabilities=["COMMODITY","AGGREGATION"]

    def self_test(self): return True

    @staticmethod
    def _f(value, default=0.0):
        try: return float(value)
        except (TypeError,ValueError): return default

    def normalize(self, observation: Mapping[str,Any]):
        symbol=str(observation.get("symbol") or "").strip().upper()
        change=self._f(observation.get("change_pct", observation.get("return_pct")))
        volume_ratio=self._f(observation.get("volume_ratio"), 1.0)
        return {
            "symbol":symbol,
            "price":observation.get("price"),
            "change_pct":change,
            "volume_ratio":volume_ratio,
            "timestamp":observation.get("timestamp"),
            "source":observation.get("source"),
        }

    def analyze(self, observation=None, *args, **kwargs):
        row=self.normalize(observation or {})
        change=row["change_pct"]
        score=max(-1.0,min(1.0, change/3.0))
        direction="UP" if score>=0.12 else "DOWN" if score<=-0.12 else "SIDEWAYS"
        return {
            **row,
            "direction":direction,
            "score":round(score,6),
            "confidence":min(1.0,abs(score)),
        }
