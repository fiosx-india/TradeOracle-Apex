"""NIFTY, SENSEX and BANKNIFTY market overview builder."""

from __future__ import annotations
from typing import Any, Mapping


class MarketView:
    name="MarketView"
    version="2.0.0"
    capabilities=["DASHBOARD","MARKET_VIEW"]

    def self_test(self):
        return True

    @staticmethod
    def _f(value, default=0.0):
        try: return float(value)
        except (TypeError,ValueError): return default

    def render(self, data: Mapping[str, Any] | None = None):
        data=data if isinstance(data,Mapping) else {}
        indices=data.get("indices",data.get("market_indices",{}))
        if not isinstance(indices,Mapping):
            indices={}

        result={}
        for name in ("NIFTY","SENSEX","BANKNIFTY"):
            raw=indices.get(name,indices.get(name.lower(),{}))
            raw=raw if isinstance(raw,Mapping) else {}
            score=self._f(raw.get("score",raw.get("prediction_score")))
            direction=str(raw.get("direction") or (
                "UP" if score>=0.12 else "DOWN" if score<=-0.12 else "SIDEWAYS"
            )).upper()
            result[name]={
                "price":raw.get("price",raw.get("current_price")),
                "change_pct":raw.get("change_pct"),
                "direction":direction,
                "score":round(score,6),
                "confidence":max(0.0,min(1.0,self._f(raw.get("confidence")))),
                "breadth":raw.get("breadth"),
                "timestamp":raw.get("timestamp"),
            }

        return {
            "indices":result,
            "market_direction":data.get("market_direction"),
            "advance_ratio":data.get("advance_ratio"),
            "decline_ratio":data.get("decline_ratio"),
            "timestamp":data.get("timestamp"),
        }
