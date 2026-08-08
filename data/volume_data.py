"""Normalized volume gateway."""
from datetime import datetime, timezone
from typing import Callable, Optional


class VolumeData:
    name = "VolumeData"
    version = "2.0.0"
    capabilities = ["VOLUME_DATA"]

    def __init__(self, provider: Optional[Callable] = None):
        self.provider = provider

    def _normalize(self, item, symbol):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        row["symbol"] = row.get("symbol") or symbol
        value = row.get("volume", row.get("value"))
        if value is None:
            return None
        try:
            row["volume"] = float(value)
        except (TypeError, ValueError):
            return None
        if row["volume"] < 0:
            return None
        ts = row.get("timestamp") or row.get("time") or row.get("datetime")
        if not isinstance(ts, str):
            return None
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            row["timestamp"] = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
        row["data_type"] = "volume"
        row["ingested_at"] = datetime.now(timezone.utc).isoformat()
        return row

    def fetch(self, symbol, start=None, end=None, interval=None, limit=None, **kwargs):
        if self.provider is None:
            return {"records": [], "quality": self.quality([]), "source": None}
        raw = self.provider(symbol=symbol, start=start, end=end, interval=interval, limit=limit, **kwargs)
        if isinstance(raw, dict) and "records" in raw:
            raw = raw["records"]
        if isinstance(raw, dict):
            raw = [raw]
        records = [x for x in (self._normalize(i, symbol) for i in (raw or [])) if x]
        if limit:
            records = records[-int(limit):]
        return {"records": records, "quality": self.quality(records), "source": getattr(self.provider, "__name__", str(self.provider))}

    def quality(self, records):
        return {"status": "OK" if records else "EMPTY", "count": len(records), "non_negative": True}
