"""Shared market-context enrichment for optional secondary data sources."""
from __future__ import annotations

from typing import Any, Optional

from .event_data import EventData
from .global_data import GlobalData
from .macro_data import MacroData
from .currency_data import CurrencyData
from .news_data import NewsData


class MarketContextEnricher:
    """Attach normalized secondary evidence without replacing price data."""

    def __init__(
        self,
        news_data: Optional[NewsData] = None,
        event_data: Optional[EventData] = None,
        macro_data: Optional[MacroData] = None,
        global_data: Optional[GlobalData] = None,
        currency_data: Optional[CurrencyData] = None,
    ) -> None:
        self.news_data = news_data or NewsData()
        self.event_data = event_data or EventData()
        self.macro_data = macro_data or MacroData()
        self.global_data = global_data or GlobalData()
        self.currency_data = currency_data or CurrencyData()

    def enrich(self, context: Any) -> dict[str, Any]:
        data = getattr(context, "data", None)
        if not isinstance(data, dict):
            return {"status": "INVALID_CONTEXT"}

        symbol = str(getattr(context, "symbol", "") or "")
        report: dict[str, Any] = {}

        news = self.news_data.fetch(symbol=symbol, limit=50)
        if news.get("records"):
            data["news"] = news["records"]
            data["sentiment_scores"] = news.get("sentiment_scores", [])
        if news.get("events"):
            data["events"] = news["events"]
        data["news_data_quality"] = news.get("quality", {})
        report["news"] = {
            "source": news.get("source"),
            "count": len(news.get("records", [])),
            "status": news.get("quality", {}).get("status", "UNKNOWN"),
        }

        for name, gateway, kwargs in (
            ("events", self.event_data, {"symbol": symbol}),
            ("macro", self.macro_data, {}),
            ("global", self.global_data, {}),
            ("currency", self.currency_data, {}),
        ):
            try:
                result = gateway.fetch(**kwargs)
            except Exception as exc:
                report[name] = {
                    "status": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                continue

            records = result.get("records", []) if isinstance(result, dict) else []
            if records:
                data[name] = records

            data[f"{name}_data_quality"] = (
                result.get("quality", {}) if isinstance(result, dict) else {}
            )
            report[name] = {
                "source": result.get("source") if isinstance(result, dict) else None,
                "count": len(records),
                "status": (
                    result.get("quality", {}).get("status", "UNKNOWN")
                    if isinstance(result, dict)
                    else "UNKNOWN"
                ),
            }

        data["context_enrichment"] = report
        return report
