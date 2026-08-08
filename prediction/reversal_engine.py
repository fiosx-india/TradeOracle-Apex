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

class ReversalEngine:
    name="ReversalEngine"; version="2.0.0"
    capabilities=["PREDICTION","REVERSAL"]

    def self_test(self): return True

    def predict(self, context):
        close=_series(context,"close","closes","price","prices")
        if len(close)<6:
            return _result(self.name,0,0.05,"Insufficient history",0.8,reversal_risk=0)
        recent=_ratio(close[-1]-close[-5],abs(close[-5]))
        # Large directional extension + weakening last move raises risk.
        last_move=_ratio(close[-1]-close[-2],abs(close[-2]))
        extension=min(1,abs(recent)*8)
        weakening=1 if recent*last_move<0 else 0
        risk=_clamp(0.65*extension+0.35*weakening,0,1)
        score=-risk if recent>0 else risk
        return _result(self.name,score,0.55,
                       f"extension={extension:.2f}, weakening={weakening}",0.8,
                       reversal_risk=round(risk,6))
    analyze=predict
