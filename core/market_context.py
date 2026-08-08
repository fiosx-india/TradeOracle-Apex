"""Shared market context passed between Apex engines."""
from dataclasses import dataclass, field
from typing import Any

@dataclass
class MarketContext:
    timestamp: str
    symbol: str = ""
    sector: str = ""
    horizon_minutes: int = 60
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
