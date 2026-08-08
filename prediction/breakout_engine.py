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

class BreakoutEngine:
    name="BreakoutEngine"; version="2.0.0"
    capabilities=["PREDICTION","BREAKOUT"]

    def self_test(self): return True

    def predict(self, context):
        close=_series(context,"close","closes","price","prices")
        volume=_series(context,"volume","volumes","trade_volume")
        if len(close)<12:
            return _result(self.name,0,0.05,"Insufficient history",0.8,breakout=False)
        hi=max(close[-11:-1]); lo=min(close[-11:-1]); last=close[-1]
        vol_ratio=1
        if len(volume)>=11:
            vol_ratio=_ratio(volume[-1],_mean(volume[-11:-1]),1)
        if last>hi:
            score=_clamp(.55+.25*min(1,vol_ratio/2-0.5))
            direction="UP"; br=True
        elif last<lo:
            score=-_clamp(.55+.25*min(1,vol_ratio/2-0.5))
            direction="DOWN"; br=True
        else:
            score=0; direction="SIDEWAYS"; br=False
        return _result(self.name,score,0.70 if br else 0.25,
                       f"breakout={br}, relative_volume={vol_ratio:.2f}",0.9,
                       breakout=br,direction=direction)
    analyze=predict
