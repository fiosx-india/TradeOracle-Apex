"""Normalized OHLC price gateway."""
from datetime import datetime, timezone
from typing import Callable, Optional


class PriceData:
    name = "PriceData"
    version = "2.0.0"
    capabilities = ["PRICE_DATA"]

    FIELDS = ("open", "high", "low", "close")

    def __init__(self, provider: Optional[Callable] = None):
        self.provider = provider

    @staticmethod
    def _ts(value):
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            return None
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

    def _normalize(self, item, symbol):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        row["symbol"] = row.get("symbol") or symbol
        ts = self._ts(row.get("timestamp") or row.get("time") or row.get("datetime"))
        if ts is None:
            return None
        row["timestamp"] = ts.isoformat()
        missing = [f for f in self.FIELDS if row.get(f) is None]
        if missing:
            return None
        try:
            for f in self.FIELDS:
                row[f] = float(row[f])
            if row.get("volume") is not None:
                row["volume"] = float(row["volume"])
        except (TypeError, ValueError):
            return None
        if row["high"] < max(row["open"], row["close"]) or row["low"] > min(row["open"], row["close"]):
            return None
        row["data_type"] = "price"
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
        return {
            "status": "OK" if records else "EMPTY",
            "count": len(records),
            "required_fields": list(self.FIELDS),
        }
