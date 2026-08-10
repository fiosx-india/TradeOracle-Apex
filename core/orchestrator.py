"""Apex orchestration: discover -> validate -> benchmark -> register -> evaluate.

The orchestrator owns the shared MarketContext and is the only layer that
coordinates research/prediction engines. Market data is never fabricated.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .master_brain import ApexMasterBrain
from .system_registry import SystemRegistry
from .capability_router import CapabilityRouter
from .market_context import MarketContext
from .builtin_engines import BUILTIN_ENGINE_CLASSES
from plugins.plugin_loader import PluginLoader
from plugins.plugin_validator import PluginValidator
from plugins.plugin_benchmark import PluginBenchmark
from data.market_data import MarketData

try:
    from config import INCOMING_DIR, LIVE_DATA_MAX_AGE_SECONDS
except ImportError:
    INCOMING_DIR = "incoming"
    LIVE_DATA_MAX_AGE_SECONDS = 120


class ApexOrchestrator:
    """Coordinate the complete Apex runtime."""

    def __init__(
        self,
        incoming: str = INCOMING_DIR,
        market_data: Optional[MarketData] = None,
        market_provider: Optional[Callable[..., Any]] = None,
        max_age_seconds: int = LIVE_DATA_MAX_AGE_SECONDS,
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
    # BUILT-IN + INCOMING ENGINE REGISTRATION
    # ------------------------------------------------------------------

    def _register_engine(self, engine, source_file: str):
        validation = self.validator.validate(engine)
        if not validation["valid"]:
            return {
                "stage": "VALIDATION",
                "status": "REJECTED",
                "name": getattr(engine, "name", source_file),
                "file": source_file,
                "errors": validation["errors"],
            }

        benchmark = self.benchmark.benchmark(engine)
        if not benchmark["passed"]:
            return {
                "stage": "BENCHMARK",
                "status": "REJECTED",
                "name": getattr(engine, "name", source_file),
                "file": source_file,
                "errors": benchmark["errors"],
                "benchmark": benchmark,
            }

        self.registry.register(
            engine,
            benchmark=benchmark,
            source_file=source_file,
        )
        return {
            "stage": "REGISTRATION",
            "status": "ACTIVE",
            "name": engine.name,
            "file": source_file,
            "benchmark": benchmark,
        }

    def discover_validate_benchmark_register(self):
        report = []

        # Core engines are part of the application and must be available even
        # when incoming/ is empty. They are still contract-tested before use.
        for engine_cls in BUILTIN_ENGINE_CLASSES:
            try:
                report.append(
                    self._register_engine(
                        engine_cls(),
                        f"builtin:{engine_cls.__module__}.{engine_cls.__name__}",
                    )
                )
            except Exception as exc:
                report.append({
                    "stage": "REGISTRATION",
                    "status": "ERROR",
                    "name": getattr(engine_cls, "name", engine_cls.__name__),
                    "file": f"builtin:{engine_cls.__module__}.{engine_cls.__name__}",
                    "errors": [f"{type(exc).__name__}: {exc}"],
                })

        # User-supplied compatible engines remain supported.
        loader = PluginLoader(self.incoming)
        for item in loader.discover():
            if not item["loaded"]:
                report.append(item)
                continue

            report.append(
                self._register_engine(
                    item["engine"],
                    item["file"],
                )
            )

        self.brain.attach_registry(self.registry, self.router)
        return report

    # ------------------------------------------------------------------
    # LIVE DATA -> SHARED MARKET CONTEXT
    # ------------------------------------------------------------------

    @staticmethod
    def _records_to_data(records):
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
            "volume": ("volume", "Volume", "trade_volume"),
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

        # Keep useful scalar gateway metadata available to engines/UI.
        if ordered:
            latest = ordered[-1]
            for key in (
                "price",
                "change",
                "change_pct",
                "exchange",
                "symbol_token",
                "source",
                "live",
                "data_type",
            ):
                if key in latest:
                    data[key] = latest[key]

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

        context = MarketContext(
            timestamp=latest_timestamp,
            symbol=symbol or "",
            sector=sector or "",
            horizon_minutes=int(horizon_minutes),
            data=data,
            evidence=[],
        )

        # Shared runtime contract: keep quality in data for compatibility
        # and expose it at context level for MasterBrain/SignalGate.
        context.market_data_quality = quality
        context.market_data_source = fetched.get("source")

        return context

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
                "MARKET_DATA",
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
                "source": getattr(context, "data", {}).get("market_data_source"),
            })

        return result
