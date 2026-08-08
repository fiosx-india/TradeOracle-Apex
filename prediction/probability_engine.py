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

class ProbabilityEngine:
    """Maps a bounded ensemble score/confidence into scenario probabilities."""

    name="ProbabilityEngine"; version="2.0.0"
    capabilities=["PREDICTION","PROBABILITY"]

    def self_test(self): return True

    def predict(self, context):
        ev=_evidence(context)
        if not ev:
            return _result(self.name,0,.05,"No evidence for probability estimate",0.8,
                           probabilities={"UP":.5,"DOWN":.5,"SIDEWAYS":0})
        score=_mean([_clamp(e.get("score",0)) for e in ev])
        conf=_mean([max(0,min(1,float(e.get("confidence",0)))) for e in ev])
        strength=min(1,abs(score)*1.5)*(.5+.5*conf)
        up=.333; down=.333; side=.334
        if score>0:
            up=.333+.667*strength; down=.333*(1-strength); side=1-up-down
        elif score<0:
            down=.333+.667*strength; up=.333*(1-strength); side=1-up-down
        return _result(self.name,score,conf,
                       f"scenario probabilities from score={score:.3f}",.9,
                       probabilities={"UP":round(up,6),"DOWN":round(down,6),
                                      "SIDEWAYS":round(side,6)})
    analyze=predict
