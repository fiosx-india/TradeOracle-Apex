"""Maps commodity moves to supplied sector/company exposure."""

from __future__ import annotations
from typing import Mapping


class CommodityImpact:
    name="CommodityImpact"
    version="2.0.0"
    capabilities=["COMMODITY","SECTOR_IMPACT"]

    def self_test(self): return True

    def analyze(self, commodity=None, exposures=None, *args, **kwargs):
        commodity=commodity if isinstance(commodity,Mapping) else {}
        exposures=exposures if isinstance(exposures,Mapping) else {}
        score=float(commodity.get("score",0.0) or 0.0)
        symbol=str(commodity.get("symbol") or "").upper()

        rows=[]
        for target, exposure in exposures.items():
            try: beta=float(exposure)
            except (TypeError,ValueError): continue
            impact=max(-1.0,min(1.0,score*beta))
            rows.append({
                "target":str(target),
                "commodity":symbol,
                "exposure":beta,
                "impact_score":round(impact,6),
                "direction":"UP" if impact>0.12 else "DOWN" if impact<-0.12 else "SIDEWAYS",
            })
        rows.sort(key=lambda x:abs(x["impact_score"]),reverse=True)
        return {"commodity":symbol,"score":score,"impacts":rows}
