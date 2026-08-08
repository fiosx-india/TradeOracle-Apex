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

class MovementPathEngine:
    """Creates a coarse path: start, continuation and target scenario."""

    name="MovementPathEngine"; version="2.0.0"
    capabilities=["PREDICTION","MOVEMENT_PATH"]

    def self_test(self): return True

    def predict(self, context):
        base=_series(context,"close","closes","price","prices")
        ev=_evidence(context)
        score=_mean([_clamp(e.get("score",0)) for e in ev]) if ev else 0
        direction="UP" if score>.12 else "DOWN" if score<-.12 else "SIDEWAYS"
        last=base[-1] if base else None
        path=["START","CONTINUE","TARGET"] if direction!="SIDEWAYS" else ["START","RANGE"]
        return _result(self.name,score,0.45 if ev else 0.05,
                       f"path scenario={direction}",0.9,
                       direction=direction,path=path,current_price=last)
    analyze=predict
