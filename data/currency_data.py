"""Normalized FX/currency observation gateway."""
from datetime import datetime, timezone
from typing import Callable, Optional


class CurrencyData:
    name = "CurrencyData"
    version = "2.0.0"
    capabilities = ["CURRENCY_DATA"]

    def __init__(self, provider: Optional[Callable] = None):
        self.provider = provider

    def _normalize(self, item):
        if not isinstance(item, dict):
            return None
        row = dict(item)
        base = str(row.get("base") or row.get("base_currency") or "").upper()
        quote = str(row.get("quote") or row.get("quote_currency") or "").upper()
        if len(base) != 3 or len(quote) != 3:
            return None
        rate = row.get("rate", row.get("close"))
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            return None
        if rate <= 0:
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
        row.update({"base": base, "quote": quote, "rate": rate, "data_type": "currency", "ingested_at": datetime.now(timezone.utc).isoformat()})
        return row

    def fetch(self, base="USD", quote="INR", start=None, end=None, limit=None, **kwargs):
        if self.provider is None:
            return {"records": [], "quality": self.quality([]), "source": None}
        raw = self.provider(base=base, quote=quote, start=start, end=end, limit=limit, **kwargs)
        if isinstance(raw, dict) and "records" in raw:
            raw = raw["records"]
        if isinstance(raw, dict):
            raw = [raw]
        records = [x for x in (self._normalize(i) for i in (raw or [])) if x]
        if limit:
            records = records[-int(limit):]
        return {"records": records, "quality": self.quality(records), "source": getattr(self.provider, "__name__", str(self.provider))}

    def quality(self, records):
        return {"status": "OK" if records else "EMPTY", "count": len(records), "positive_rates": all(x["rate"] > 0 for x in records)}
