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

class EarlyMovementEngine:
    """Detects early acceleration before requiring a full breakout."""

    name="EarlyMovementEngine"; version="2.0.0"
    capabilities=["PREDICTION","EARLY_MOVEMENT"]

    def self_test(self): return True

    def predict(self, context):
        close=_series(context,"close","closes","price","prices")
        volume=_series(context,"volume","volumes","trade_volume")
        if len(close)<8:
            return _result(self.name,0,0.05,"Insufficient history",0.8,early_signal=False)
        short=_ratio(close[-1]-close[-3],abs(close[-3]))
        prior=_ratio(close[-3]-close[-7],abs(close[-7]))
        acceleration=short-prior
        vr=1
        if len(volume)>=8:
            vr=_ratio(volume[-1],_mean(volume[-8:-1]),1)
        score=_clamp(acceleration*15)
        if vr>1.3: score=_clamp(score*1.15)
        return _result(self.name,score,min(.9,.25+abs(score)*.5),
                       f"acceleration={acceleration:.5f}, relative_volume={vr:.2f}",0.9,
                       early_signal=abs(score)>=.25)
    analyze=predict
