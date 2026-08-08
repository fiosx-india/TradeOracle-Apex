"""Normalized news gateway. Raw article text is not invented or persisted here."""
from datetime import datetime, timezone
from typing import Callable, Optional


class NewsData:
    name = "NewsData"
    version = "2.0.0"
    capabilities = ["NEWS_DATA"]

    def __init__(self, provider: Optional[Callable] = None):
        self.provider = provider

    def _normalize(self, item):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        ts = row.get("timestamp") or row.get("published_at") or row.get("published")
        if not isinstance(ts, str):
            return None
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            row["timestamp"] = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
        row["headline"] = str(row.get("headline") or row.get("title") or "").strip()
        if not row["headline"]:
            return None
        row["source"] = str(row.get("source") or "").strip() or None
        row["symbols"] = list(row.get("symbols") or row.get("tickers") or [])
        row["sectors"] = list(row.get("sectors") or [])
        row["data_type"] = "news"
        row["ingested_at"] = datetime.now(timezone.utc).isoformat()
        return row

    def fetch(self, symbol=None, sector=None, start=None, end=None, limit=None, **kwargs):
        if self.provider is None:
            return {"records": [], "quality": self.quality([]), "source": None}
        raw = self.provider(symbol=symbol, sector=sector, start=start, end=end, limit=limit, **kwargs)
        if isinstance(raw, dict) and "records" in raw:
            raw = raw["records"]
        if isinstance(raw, dict):
            raw = [raw]
        records = [x for x in (self._normalize(i) for i in (raw or [])) if x]
        if limit:
            records = records[-int(limit):]
        return {"records": records, "quality": self.quality(records), "source": getattr(self.provider, "__name__", str(self.provider))}

    def quality(self, records):
        return {"status": "OK" if records else "EMPTY", "count": len(records), "timestamped": all("timestamp" in x for x in records)}
