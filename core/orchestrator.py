"""Apex orchestration: Discover -> Validate -> Benchmark -> Register -> Master Brain.

Live-data integration remains provider-driven: the orchestrator never invents
market data. When a MarketData provider is supplied, the orchestrator can
normalize the latest records into a shared MarketContext before evaluation.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .master_brain import ApexMasterBrain
from .system_registry import SystemRegistry
from .capability_router import CapabilityRouter
from .market_context import MarketContext
from plugins.plugin_loader import PluginLoader
from plugins.plugin_validator import PluginValidator
from plugins.plugin_benchmark import PluginBenchmark
from data.market_data import MarketData

try:
    from config import INCOMING_DIR
except ImportError:
    INCOMING_DIR = "incoming"


class ApexOrchestrator:
    """Coordinate Apex discovery, validation, registration and evaluation."""

    def __init__(
        self,
        incoming: str = INCOMING_DIR,
        market_data: Optional[MarketData] = None,
        market_provider: Optional[Callable[..., Any]] = None,
        max_age_seconds: int = 120,
    ):
        self.incoming = incoming

        self.registry = SystemRegistry()
        self.router = CapabilityRouter(self.registry)
        self.validator = PluginValidator()
        self.benchmark = PluginBenchmark()

        self.market_data = market_data or MarketData(
            provider=market_provider,
            max_age_seconds=max_age_seconds,
        )

        self.brain = ApexMasterBrain(
            registry=self.registry,
            router=self.router,
        )

    # ------------------------------------------------------------------
    # DISCOVER -> VALIDATE -> BENCHMARK -> REGISTER
    # ------------------------------------------------------------------

    def discover_validate_benchmark_register(self):
        report = []
        loader = PluginLoader(self.incoming)

        for item in loader.discover():
            if not item["loaded"]:
                report.append(item)
                continue

            engine = item["engine"]

            validation = self.validator.validate(engine)
            if not validation["valid"]:
                report.append({
                    "stage": "VALIDATION",
                    "status": "REJECTED",
                    "name": getattr(engine, "name", item["file"]),
                    "file": item["file"],
                    "errors": validation["errors"],
                })
                continue

            benchmark = self.benchmark.benchmark(engine)
            if not benchmark["passed"]:
                report.append({
                    "stage": "BENCHMARK",
                    "status": "REJECTED",
                    "name": engine.name,
                    "file": item["file"],
                    "errors": benchmark["errors"],
                    "benchmark": benchmark,
                })
                continue

            self.registry.register(
                engine,
                benchmark=benchmark,
                source_file=item["file"],
            )

            report.append({
                "stage": "REGISTRATION",
                "status": "ACTIVE",
                "name": engine.name,
                "file": item["file"],
                "benchmark": benchmark,
            })

        self.brain.attach_registry(self.registry, self.router)
        return report

    # ------------------------------------------------------------------
    # LIVE DATA -> SHARED MARKET CONTEXT
    # ------------------------------------------------------------------

    @staticmethod
    def _records_to_data(records):
        """Convert normalized gateway records into engine-friendly series.

        Records are expected to contain OHLCV-style fields. Unknown fields
        are preserved as additional scalar/list data where possible.
        """
        if not records:
            return {}

        ordered = sorted(
            [dict(row) for row in records if isinstance(row, dict)],
            key=lambda row: str(row.get("timestamp", "")),
        )

        data = {}
        field_aliases = {
            "open": ("open", "Open"),
            "high": ("high", "High"),
            "low": ("low", "Low"),
            "close": ("close", "Close", "price", "last_price"),
            "volume": ("volume", "Volume"),
        }

        for target, aliases in field_aliases.items():
            values = []
            for row in ordered:
                value = next(
                    (row.get(key) for key in aliases if row.get(key) is not None),
                    None,
                )
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    continue
            if values:
                data[target] = values

        timestamps = [
            row.get("timestamp")
            for row in ordered
            if row.get("timestamp")
        ]
        if timestamps:
            data["timestamps"] = timestamps

        return data

    def build_market_context(
        self,
        symbol: str,
        *,
        sector: str = "",
        start=None,
        end=None,
        limit: int = 120,
        horizon_minutes: int = 60,
        **kwargs,
    ):
        """Fetch gateway data and build the single shared MarketContext.

        No provider means an empty context with explicit gateway diagnostics.
        No synthetic prices are generated.
        """
        fetched = self.market_data.fetch(
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
            **kwargs,
        )

        records = fetched.get("records", [])
        quality = fetched.get("quality", {})

        data = self._records_to_data(records)
        data["market_data_quality"] = quality
        data["market_data_source"] = fetched.get("source")

        latest_timestamp = (
            records[-1].get("timestamp")
            if records
            else datetime.now(timezone.utc).isoformat()
        )

        return MarketContext(
            timestamp=latest_timestamp,
            symbol=symbol or "",
            sector=sector or "",
            horizon_minutes=int(horizon_minutes),
            data=data,
            evidence=[],
        )

    # ------------------------------------------------------------------
    # PUBLIC RUNTIME
    # ------------------------------------------------------------------

    def run(
        self,
        context=None,
        *,
        symbol: Optional[str] = None,
        sector: str = "",
        start=None,
        end=None,
        limit: int = 120,
        horizon_minutes: int = 60,
        **market_kwargs,
    ):
        report = self.discover_validate_benchmark_register()

        result = {
            "status": "READY",
            "pipeline": [
                "DISCOVER",
                "VALIDATE",
                "BENCHMARK",
                "REGISTER",
                "MASTER_BRAIN",
            ],
            "registered_engines": list(self.registry.all()),
            "registry_report": self.registry.report(),
            "report": report,
            "market_data": {
                "provider_connected": self.market_data.provider is not None,
                "max_age_seconds": self.market_data.max_age_seconds,
            },
        }

        # Explicit context always wins.
        if context is None and symbol:
            context = self.build_market_context(
                symbol,
                sector=sector,
                start=start,
                end=end,
                limit=limit,
                horizon_minutes=horizon_minutes,
                **market_kwargs,
            )

        if context is not None:
            result["master_brain"] = self.brain.evaluate(context)

            quality = getattr(context, "data", {}).get(
                "market_data_quality",
                {},
            )
            result["market_data"].update({
                "quality": quality,
                "symbol": getattr(context, "symbol", ""),
                "timestamp": getattr(context, "timestamp", None),
                "records": quality.get("count", 0),
                "fresh": quality.get("fresh", False),
            })

        return result
