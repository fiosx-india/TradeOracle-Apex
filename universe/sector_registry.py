"""Sector registry and company-to-sector mapping."""

from __future__ import annotations
from collections import defaultdict


class SectorRegistry:
    name = "SectorRegistry"
    version = "2.0.0"
    capabilities = ["UNIVERSE", "SECTOR_REGISTRY"]

    def __init__(self, companies=None):
        self._sectors = defaultdict(set)
        if companies:
            self.load(companies)

    def self_test(self):
        return True

    def add(self, symbol, sector):
        symbol = str(symbol or "").strip().upper()
        sector = str(sector or "UNKNOWN").strip()
        if not symbol:
            raise ValueError("symbol is required")
        if not sector:
            sector = "UNKNOWN"
        self._sectors[sector].add(symbol)

    def load(self, companies):
        for company in companies or []:
            if isinstance(company, dict):
                self.add(company.get("symbol"), company.get("sector"))
        return self.report()

    def sectors(self):
        return sorted(self._sectors)

    def companies(self, sector):
        return sorted(self._sectors.get(str(sector), set()))

    def sector_for(self, symbol):
        symbol = str(symbol or "").strip().upper()
        for sector, symbols in self._sectors.items():
            if symbol in symbols:
                return sector
        return "UNKNOWN"

    def report(self):
        return {
            sector: sorted(symbols)
            for sector, symbols in sorted(self._sectors.items())
        }

    def validate(self):
        duplicate_symbols = []
        seen = {}
        for sector, symbols in self._sectors.items():
            for symbol in symbols:
                if symbol in seen and seen[symbol] != sector:
                    duplicate_symbols.append(symbol)
                seen[symbol] = sector
        return {
            "valid": not duplicate_symbols,
            "errors": [f"multi_sector:{x}" for x in duplicate_symbols],
            "sector_count": len(self._sectors),
        }
