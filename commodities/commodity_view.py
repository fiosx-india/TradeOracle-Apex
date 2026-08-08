"""Commodity dashboard view builder."""

from __future__ import annotations
from typing import Any, Mapping


class CommodityView:
    name="CommodityView"
    version="2.0.0"
    capabilities=["DASHBOARD","COMMODITY_VIEW"]

    def self_test(self):
        return True

    def render(self, data: Mapping[str, Any] | None = None):
        data=data if isinstance(data,Mapping) else {}
        raw=data.get("commodities",data.get("items",[]))

        if isinstance(raw,Mapping):
            rows=[
                {"symbol":symbol,**dict(item)}
                for symbol,item in raw.items()
                if isinstance(item,Mapping)
            ]
        elif isinstance(raw,(list,tuple)):
            rows=[dict(x) for x in raw if isinstance(x,Mapping)]
        else:
            rows=[]

        normalized=[]
        for row in rows:
            normalized.append({
                "symbol":str(row.get("symbol",row.get("commodity",""))).upper(),
                "price":row.get("price"),
                "change_pct":row.get("change_pct"),
                "direction":row.get("direction"),
                "score":row.get("score"),
                "confidence":row.get("confidence"),
                "sector_impact":row.get("sector_impact"),
                "company_impact":row.get("company_impact"),
                "timestamp":row.get("timestamp"),
            })

        return {
            "commodities":normalized,
            "count":len(normalized),
            "timestamp":data.get("timestamp"),
        }
