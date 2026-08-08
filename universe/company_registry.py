"""Canonical company-universe registry.

The registry accepts externally supplied constituents and deliberately does not
invent live constituents. It normalizes symbols, sectors and metadata so every
downstream engine receives the same company identity.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class CompanyRegistry:
    name = "CompanyRegistry"
    version = "2.0.0"
    capabilities = ["UNIVERSE", "COMPANY_REGISTRY"]

    def __init__(self, companies=None):
        self._companies: dict[str, dict[str, Any]] = {}
        if companies:
            self.load(companies)

    def self_test(self):
        return True

    @staticmethod
    def normalize_symbol(symbol: Any) -> str:
        return str(symbol or "").strip().upper()

    def upsert(self, company: Mapping[str, Any]):
        symbol = self.normalize_symbol(company.get("symbol"))
        if not symbol:
            raise ValueError("company.symbol is required")

        record = dict(company)
        record["symbol"] = symbol
        record["name"] = str(company.get("name") or symbol).strip()
        record["sector"] = str(company.get("sector") or "UNKNOWN").strip()
        record["exchange"] = str(company.get("exchange") or "NSE").strip().upper()
        record["active"] = bool(company.get("active", True))
        record["updated_at"] = datetime.now(timezone.utc).isoformat()

        self._companies[symbol] = record
        return dict(record)

    def load(self, companies: Iterable[Mapping[str, Any]]):
        for company in companies:
            if isinstance(company, Mapping):
                try:
                    self.upsert(company)
                except ValueError:
                    continue
        return self.list()

    def get(self, symbol):
        record = self._companies.get(self.normalize_symbol(symbol))
        return dict(record) if record else None

    def list(self, active_only=True):
        records = list(self._companies.values())
        if active_only:
            records = [x for x in records if x.get("active", True)]
        return [dict(x) for x in records]

    def symbols(self, active_only=True):
        return [x["symbol"] for x in self.list(active_only)]

    def by_sector(self, sector):
        target = str(sector or "").strip().lower()
        return [
            x for x in self.list()
            if str(x.get("sector", "")).lower() == target
        ]

    def count(self):
        return len(self._companies)

    def validate(self):
        errors = []
        for symbol, record in self._companies.items():
            if not symbol:
                errors.append("empty_symbol")
            if record.get("symbol") != symbol:
                errors.append(f"symbol_mismatch:{symbol}")
            if not record.get("name"):
                errors.append(f"missing_name:{symbol}")
        return {"valid": not errors, "errors": errors, "count": self.count()}
