"""Structured company/market event gateway."""
from datetime import datetime, timezone
from typing import Callable, Optional


class EventData:
    name = "EventData"
    version = "2.0.0"
    capabilities = ["EVENT_DATA"]

    EVENT_TYPES = {"EARNINGS", "RESULT", "ORDER", "MERGER", "ACQUISITION", "DIVIDEND", "BUYBACK", "GUIDANCE", "OTHER"}

    def __init__(self, provider: Optional[Callable] = None):
        self.provider = provider

    def _normalize(self, item):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        ts = row.get("timestamp") or row.get("event_time") or row.get("date")
        if not isinstance(ts, str):
            return None
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            row["timestamp"] = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
        event_type = str(row.get("event_type") or row.get("type") or "OTHER").upper()
        row["event_type"] = event_type if event_type in self.EVENT_TYPES else "OTHER"
        row["symbol"] = row.get("symbol")
        row["sector"] = row.get("sector")
        row["description"] = str(row.get("description") or "").strip()
        row["data_type"] = "event"
        row["ingested_at"] = datetime.now(timezone.utc).isoformat()
        return row

    def fetch(self, symbol=None, event_type=None, start=None, end=None, limit=None, **kwargs):
        if self.provider is None:
            return {"records": [], "quality": self.quality([]), "source": None}
        raw = self.provider(symbol=symbol, event_type=event_type, start=start, end=end, limit=limit, **kwargs)
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
