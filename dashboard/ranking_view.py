"""Top UP/DOWN and early-movement ranking builder."""

from __future__ import annotations
from typing import Any, Mapping


class RankingView:
    name="RankingView"
    version="2.0.0"
    capabilities=["DASHBOARD","RANKING_VIEW"]

    def self_test(self):
        return True

    @staticmethod
    def _f(value, default=0.0):
        try: return float(value)
        except (TypeError,ValueError): return default

    def render(self, data: Mapping[str, Any] | None = None, limit: int = 10):
        data=data if isinstance(data,Mapping) else {}
        raw=data.get("predictions",data.get("companies",[]))

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

        prepared=[]
        for row in rows:
            score=self._f(row.get("score",row.get("prediction_score")))
            confidence=max(0.0,min(1.0,self._f(row.get("confidence"))))
            direction=str(row.get("direction") or (
                "UP" if score>=0.12 else "DOWN" if score<=-0.12 else "SIDEWAYS"
            )).upper()
            prepared.append({
                "symbol":str(row.get("symbol") or "").upper(),
                "name":row.get("name"),
                "sector":row.get("sector"),
                "score":round(score,6),
                "confidence":round(confidence,6),
                "rank_score":round(score*confidence,6),
                "direction":direction,
                "early_movement":bool(row.get("early_signal",False)),
                "relative_volume":row.get("relative_volume",row.get("volume_ratio")),
            })

        n=max(1,int(limit))
        top_up=sorted(
            [x for x in prepared if x["direction"]=="UP"],
            key=lambda x:x["rank_score"],reverse=True
        )[:n]
        top_down=sorted(
            [x for x in prepared if x["direction"]=="DOWN"],
            key=lambda x:x["rank_score"]
        )[:n]
        early_up=sorted(
            [x for x in prepared if x["early_movement"] and x["direction"]=="UP"],
            key=lambda x:abs(x["rank_score"]),reverse=True
        )[:n]
        early_down=sorted(
            [x for x in prepared if x["early_movement"] and x["direction"]=="DOWN"],
            key=lambda x:abs(x["rank_score"]),reverse=True
        )[:n]

        return {
            "top_up":top_up,
            "top_down":top_down,
            "early_movers":early_up,
            "early_fallers":early_down,
            "total":len(prepared),
        }
