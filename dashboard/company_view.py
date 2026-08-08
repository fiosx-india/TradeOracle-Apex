"""Company detail view builder for the TradeOracle dashboard."""

from __future__ import annotations
from typing import Any, Mapping


class CompanyView:
    name="CompanyView"
    version="2.0.0"
    capabilities=["DASHBOARD","COMPANY_VIEW"]

    def self_test(self):
        return True

    @staticmethod
    def _f(value, default=0.0):
        try: return float(value)
        except (TypeError,ValueError): return default

    def render(self, data: Mapping[str, Any] | None = None):
        data=data if isinstance(data,Mapping) else {}
        score=self._f(data.get("score", data.get("prediction_score")))
        confidence=max(0.0,min(1.0,self._f(data.get("confidence"))))
        direction=str(data.get("direction") or (
            "UP" if score>=0.12 else "DOWN" if score<=-0.12 else "SIDEWAYS"
        )).upper()

        return {
            "symbol":str(data.get("symbol") or "").upper(),
            "name":data.get("name"),
            "sector":data.get("sector"),
            "price":data.get("price",data.get("current_price")),
            "change_pct":data.get("change_pct"),
            "volume":data.get("volume"),
            "relative_volume":data.get("relative_volume",data.get("volume_ratio")),
            "direction":direction,
            "prediction_score":round(score,6),
            "confidence":round(confidence,6),
            "sixty_minute":data.get("sixty_minute",data.get("prediction")),
            "early_movement":data.get("early_signal",False),
            "breakout":data.get("breakout"),
            "reversal_risk":data.get("reversal_risk"),
            "commodity_impact":data.get("commodity_impact"),
            "timestamp":data.get("timestamp"),
        }
