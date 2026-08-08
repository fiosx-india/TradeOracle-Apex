from __future__ import annotations
from typing import Any, Mapping
import math
import statistics

def _data(ctx):
    d=getattr(ctx,"data",None)
    return d if isinstance(d,dict) else {}

def _series(ctx,*keys):
    d=_data(ctx)
    for k in keys:
        v=d.get(k)
        if isinstance(v,(list,tuple)):
            out=[]
            for x in v:
                try: out.append(float(x))
                except (TypeError,ValueError): pass
            if out: return out
    return []

def _clamp(x,lo=-1.0,hi=1.0):
    try: x=float(x)
    except (TypeError,ValueError): x=0.0
    return max(lo,min(hi,x))

def _mean(v,default=0.0):
    return statistics.fmean(v) if v else default

def _ratio(a,b,default=0.0):
    return a/b if b else default

def _evidence(ctx):
    v=getattr(ctx,"research_evidence",None)
    if isinstance(v,list): return [x for x in v if isinstance(x,dict)]
    d=_data(ctx)
    v=d.get("research_evidence")
    return v if isinstance(v,list) else []

def _result(engine,score,confidence,reason,weight=1.0,**extra):
    r={"engine":engine,"score":round(_clamp(score),6),
       "confidence":round(max(0,min(1,float(confidence))),6),
       "weight":max(0,float(weight)),"reason":reason}
    r.update(extra)
    return r

class RankingEngine:
    """Ranks a batch of symbols by a supplied prediction score."""

    name="RankingEngine"; version="2.0.0"
    capabilities=["PREDICTION","RANKING"]

    def self_test(self): return True

    def predict(self, context):
        candidates=_data(context).get("candidates",[])
        if not isinstance(candidates,list):
            return _result(self.name,0,.05,"No candidate list supplied",.7,ranks=[])
        rows=[]
        for item in candidates:
            if not isinstance(item,Mapping): continue
            try:
                score=_clamp(item.get("score",0))
                conf=max(0,min(1,float(item.get("confidence",0))))
            except (TypeError,ValueError):
                continue
            rows.append({
                "symbol":str(item.get("symbol","")),
                "score":round(score,6),
                "confidence":round(conf,6),
                "rank_score":round(score*conf,6)
            })
        rows.sort(key=lambda x:x["rank_score"],reverse=True)
        for i,row in enumerate(rows,1): row["rank"]=i
        return _result(self.name,0.0,0.8 if rows else .05,
                       f"ranked {len(rows)} candidates",.7,ranks=rows)
    analyze=predict
