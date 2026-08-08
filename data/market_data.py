"""Canonical market-data gateway for TradeOracle Apex."""
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional


class MarketData:
    name = "MarketData"
    version = "2.0.0"
    capabilities = ["MARKET_DATA"]

    def __init__(self, provider: Optional[Callable] = None, max_age_seconds: int = 120):
        self.provider = provider
        self.max_age_seconds = max_age_seconds

    @staticmethod
    def utc_now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _timestamp(value):
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _normalize(self, item, symbol=None):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        row.setdefault("symbol", symbol)
        ts = self._timestamp(row.get("timestamp") or row.get("time") or row.get("datetime"))
        if ts is None:
            return None
        row["timestamp"] = ts.isoformat()
        row["ingested_at"] = self.utc_now().isoformat()
        row["data_type"] = "market"
        return row

    def fetch(self, symbol=None, start=None, end=None, limit=None, **kwargs):
        if self.provider is None:
            return {"records": [], "quality": self.quality([]), "source": None}

        raw = self.provider(symbol=symbol, start=start, end=end, limit=limit, **kwargs)
        if isinstance(raw, dict) and "records" in raw:
            raw = raw["records"]
        if isinstance(raw, dict):
            raw = [raw]
        records = [x for x in (self._normalize(i, symbol) for i in (raw or [])) if x]
        if limit:
            records = records[-int(limit):]
        return {"records": records, "quality": self.quality(records), "source": getattr(self.provider, "__name__", str(self.provider))}

    def quality(self, records):
        if not records:
            return {"status": "EMPTY", "count": 0, "fresh": False, "missing": []}
        now = self.utc_now()
        ages = []
        for r in records:
            ts = self._timestamp(r.get("timestamp"))
            if ts:
                ages.append(max(0.0, (now - ts).total_seconds()))
        fresh = bool(ages) and min(ages) <= self.max_age_seconds
        return {"status": "OK", "count": len(records), "fresh": fresh, "missing": []}
