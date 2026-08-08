"""Early movement alert layer for the dashboard.

Transforms prediction/market evidence into compact, de-duplicated alert
records. It does not decide trades; it surfaces unusually fast movement.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Mapping


class MovementAlert:
    name="MovementAlert"
    version="2.0.0"
    capabilities=["DASHBOARD","ALERT","EARLY_MOVEMENT"]

    def __init__(self, cooldown_seconds=120):
        self.cooldown_seconds=max(0,int(cooldown_seconds))
        self._last_seen={}

    def self_test(self):
        return True

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _float(value, default=0.0):
        try: return float(value)
        except (TypeError,ValueError): return default

    def build(self, item: Mapping[str,Any]):
        symbol=str(item.get("symbol") or "").strip().upper()
        if not symbol:
            return None

        score=self._float(item.get("score"))
        confidence=max(0.0,min(1.0,self._float(item.get("confidence"))))
        acceleration=self._float(item.get("acceleration"))
        relative_volume=self._float(
            item.get("relative_volume", item.get("volume_ratio", 1.0)), 1.0
        )
        early=bool(item.get("early_signal", abs(score)>=0.25))
        direction=str(item.get("direction") or (
            "UP" if score>=0.12 else "DOWN" if score<=-0.12 else "SIDEWAYS"
        )).upper()

        if not early or direction=="SIDEWAYS":
            return None

        severity="HIGH" if confidence>=0.75 and relative_volume>=1.5 else (
            "MEDIUM" if confidence>=0.50 else "LOW"
        )
        now=self._now()
        key=f"{symbol}:{direction}"
        previous=self._last_seen.get(key)
        if previous is not None:
            age=(now-previous).total_seconds()
            if age < self.cooldown_seconds:
                return None
        self._last_seen[key]=now

        return {
            "type":"EARLY_MOVEMENT",
            "symbol":symbol,
            "direction":direction,
            "severity":severity,
            "score":round(score,6),
            "confidence":round(confidence,6),
            "acceleration":round(acceleration,6),
            "relative_volume":round(relative_volume,4),
            "price":item.get("price", item.get("current_price")),
            "message":(
                f"{symbol} is showing an early {direction} movement "
                f"with relative volume {relative_volume:.2f}x."
            ),
            "timestamp":now.isoformat(),
        }

    def build_many(self, items):
        alerts=[]
        for item in items or []:
            if isinstance(item,Mapping):
                alert=self.build(item)
                if alert:
                    alerts.append(alert)
        return sorted(
            alerts,
            key=lambda x:(x["severity"],abs(x["score"])),
            reverse=True
        )

    def clear(self):
        self._last_seen.clear()
