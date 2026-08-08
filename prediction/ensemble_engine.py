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

class EnsembleEngine:
    """Combines prediction-stage outputs with confidence-aware weighting."""

    name="EnsembleEngine"; version="2.0.0"
    capabilities=["PREDICTION","ENSEMBLE"]

    def self_test(self): return True

    def predict(self, context):
        ev=_evidence(context)
        if not ev:
            return _result(self.name,0,.05,"No prediction evidence supplied",1.0,
                           direction="SIDEWAYS")
        selected=[e for e in ev if str(e.get("engine",""))!="EnsembleEngine"]
        weights=[]; scores=[]
        for e in selected:
            s=_clamp(e.get("score",0)); w=max(0,float(e.get("weight",1)))
            c=max(0,min(1,float(e.get("confidence",0))))
            weights.append(w*c); scores.append(s*w*c)
        score=_ratio(sum(scores),sum(weights))
        direction="UP" if score>.12 else "DOWN" if score<-.12 else "SIDEWAYS"
        agreement=_ratio(max(
            sum(w for e,w in zip(selected,weights) if float(e.get("score",0))>.05),
            sum(w for e,w in zip(selected,weights) if float(e.get("score",0))<-.05)
        ),sum(weights))
        conf=min(.97,.20+.55*agreement+.25*abs(score))
        return _result(self.name,score,conf,
                       f"prediction ensemble from {len(selected)} components",1.2,
                       direction=direction,agreement=round(agreement,6))
    analyze=predict
