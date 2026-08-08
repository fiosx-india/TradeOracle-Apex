"""Normalized macro-economic observation gateway."""
from datetime import datetime, timezone
from typing import Callable, Optional


class MacroData:
    name = "MacroData"
    version = "2.0.0"
    capabilities = ["MACRO_DATA"]

    def __init__(self, provider: Optional[Callable] = None):
        self.provider = provider

    def _normalize(self, item):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        indicator = str(row.get("indicator") or row.get("series") or "").strip()
        if not indicator:
            return None
        value = row.get("value")
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        ts = row.get("timestamp") or row.get("date")
        if not isinstance(ts, str):
            return None
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            row["timestamp"] = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
        row.update({"indicator": indicator, "value": value, "data_type": "macro", "ingested_at": datetime.now(timezone.utc).isoformat()})
        return row

    def fetch(self, indicator=None, country=None, start=None, end=None, limit=None, **kwargs):
        if self.provider is None:
            return {"records": [], "quality": self.quality([]), "source": None}
        raw = self.provider(indicator=indicator, country=country, start=start, end=end, limit=limit, **kwargs)
        if isinstance(raw, dict) and "records" in raw:
            raw = raw["records"]
        if isinstance(raw, dict):
            raw = [raw]
        records = [x for x in (self._normalize(i) for i in (raw or [])) if x]
        if limit:
            records = records[-int(limit):]
        return {"records": records, "quality": self.quality(records), "source": getattr(self.provider, "__name__", str(self.provider))}

    def quality(self, records):
        return {"status": "OK" if records else "EMPTY", "count": len(records)}
