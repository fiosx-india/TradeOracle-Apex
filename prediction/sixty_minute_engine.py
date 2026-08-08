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

class SixtyMinuteEngine:
    """Forecast direction over the next 60 minutes from current evidence.

    This produces a calibrated model output, not a guarantee of market outcome.
    """
    name="SixtyMinuteEngine"; version="2.0.0"
    capabilities=["PREDICTION","60_MINUTE"]

    def self_test(self): return True

    def predict(self, context):
        ev=_evidence(context)
        scores=[]; weights=[]
        for e in ev:
            s=_clamp(e.get("score",0)); w=max(0,float(e.get("weight",1)))
            c=max(0,min(1,float(e.get("confidence",0))))
            scores.append(s*w*c); weights.append(w*c)
        if not weights or sum(weights)<=0:
            return _result(self.name,0,0.05,"Insufficient evidence for 60-minute forecast",
                           1.2,direction="SIDEWAYS",horizon_minutes=60)
        score=_ratio(sum(scores),sum(weights))
        agreement=_ratio(max(
            sum(w for e,w in zip(ev,weights) if float(e.get("score",0))>0.05),
            sum(w for e,w in zip(ev,weights) if float(e.get("score",0))<-0.05)
        ),sum(weights))
        direction="UP" if score>=0.12 else "DOWN" if score<=-0.12 else "SIDEWAYS"
        confidence=min(0.97,0.20+0.55*abs(score)+0.35*agreement)
        # Movement estimate is a scenario range, not a price promise.
        close=_series(context,"close","closes","price","prices")
        volatility=0.0
        if len(close)>=6:
            rets=[_ratio(b-a,abs(a)) for a,b in zip(close[-6:-1],close[-5:]) if a]
            volatility=statistics.pstdev(rets) if len(rets)>1 else 0
        expected=_clamp(score)*max(volatility,0.002)*2.0
        return _result(self.name,score,confidence,
                       f"60-minute ensemble score={score:.3f}, agreement={agreement:.2f}",
                       1.25,direction=direction,horizon_minutes=60,
                       expected_return=round(expected,6),
                       agreement=round(agreement,6),
                       uncertainty=round(max(0.0,1-confidence),6))
    analyze=predict
