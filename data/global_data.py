"""Normalized global-market observation gateway."""
from datetime import datetime, timezone
from typing import Callable, Optional


class GlobalData:
    name = "GlobalData"
    version = "2.0.0"
    capabilities = ["GLOBAL_DATA"]

    def __init__(self, provider: Optional[Callable] = None):
        self.provider = provider

    def _normalize(self, item):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        symbol = str(row.get("symbol") or row.get("index") or "").strip()
        if not symbol:
            return None
        ts = row.get("timestamp") or row.get("time")
        if not isinstance(ts, str):
            return None
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            row["timestamp"] = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
        if row.get("close") is not None:
            try:
                row["close"] = float(row["close"])
            except (TypeError, ValueError):
                return None
        row["symbol"] = symbol
        row["region"] = row.get("region")
        row["data_type"] = "global"
        row["ingested_at"] = datetime.now(timezone.utc).isoformat()
        return row

    def fetch(self, symbol=None, region=None, start=None, end=None, limit=None, **kwargs):
        if self.provider is None:
            return {"records": [], "quality": self.quality([]), "source": None}
        raw = self.provider(symbol=symbol, region=region, start=start, end=end, limit=limit, **kwargs)
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
